"""Checks that need neither Nuke nor AYON:

    python tests/test_logic.py
"""

import os
import sys

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from qcscript import containers, templates  # noqa: E402

failures = []


def check(label, condition, extra=""):
    print("[{}] {} {}".format("PASS" if condition else "FAIL", label, extra))
    if not condition:
        failures.append(label)


# --- version hints ----------------------------------------------------------
versions = [
    {"version": number, "createdAt": "2026-01-0{}".format(number)}
    for number in (1, 2, 3, 5)
]
versions.append({"version": -1, "createdAt": "2026-01-09"})

expectations = [
    ("max", 5), ("latest", 5), ("last", 5), ("", 5),
    ("min", 1), ("first", 1),
    ("3", 3), ("-1", 3), ("-2", 2), ("-99", 1),
    ("hero", -1), ("42", None), ("nonsense", 5),
]
for hint, expected in expectations:
    picked = templates.pick_version(versions, hint)
    got = picked.get("version") if picked else None
    check("version hint {!r} -> {}".format(hint, expected), got == expected, got)

check("no versions resolves to nothing",
      templates.pick_version([], "max") is None)

# --- templated loader rows --------------------------------------------------
row = templates.TemplatedLoader(
    "001", "render", "exr", "Load Clip", "max", True,
    "start_at_workfile=true, offset=10", "comp", ".*[mM]ain.*", ""
)
check("row survives the spreadsheet round trip",
      templates.TemplatedLoader.from_row(row.to_row()).to_data()
      == row.to_data())
check("loader args parsed into options",
      row.options() == {"start_at_workfile": True, "offset": 10},
      row.options())
check("free form loader args are kept",
      templates.TemplatedLoader(loader_args="whatever").options()
      == {"args": "whatever"})

template = templates.Template(loaders=[row])
check("next loader id skips used ones",
      template.next_loader_id() == "002", template.next_loader_id())
check("template survives the settings round trip",
      templates.Template.from_data(template.to_data()).loaders[0].to_data()
      == row.to_data())

# --- reordering rows --------------------------------------------------------
rows = ["a", "b", "c", "d"]
check("a single row moves up",
      templates.move_selected(rows, [2], -1) == (["a", "c", "b", "d"], [1]),
      templates.move_selected(rows, [2], -1))
check("a single row moves down",
      templates.move_selected(rows, [1], 1) == (["a", "c", "b", "d"], [2]),
      templates.move_selected(rows, [1], 1))
check("a block of rows slides as one",
      templates.move_selected(rows, [1, 2], -1)
      == (["b", "c", "a", "d"], [0, 1]),
      templates.move_selected(rows, [1, 2], -1))
check("a block moving down slides as one",
      templates.move_selected(rows, [1, 2], 1)
      == (["a", "d", "b", "c"], [2, 3]),
      templates.move_selected(rows, [1, 2], 1))
check("rows at the top do not move up",
      templates.move_selected(rows, [0, 1], -1) == (rows, [0, 1]),
      templates.move_selected(rows, [0, 1], -1))
check("rows at the bottom do not move down",
      templates.move_selected(rows, [2, 3], 1) == (rows, [2, 3]),
      templates.move_selected(rows, [2, 3], 1))
check("moving nothing changes nothing",
      templates.move_selected(rows, [], -1) == (rows, []))

reordered = templates.Template(loaders=[
    templates.TemplatedLoader(loader_id="007"),
    templates.TemplatedLoader(loader_id="003"),
]).renumber()
check("ids are renumbered by position",
      [loader.loader_id for loader in reordered.loaders] == ["001", "002"],
      [loader.loader_id for loader in reordered.loaders])

# --- resolution: task regex, and the query cache ----------------------------
PRODUCTS = [
    {"id": "p_comp", "name": "renderCompMain", "productType": "render",
     "folderId": "f1"},
    {"id": "p_plate", "name": "plateMain", "productType": "plate",
     "folderId": "f1"},
]
VERSIONS = [
    {"id": "v_comp", "productId": "p_comp", "version": 4,
     "taskId": "t_comp", "createdAt": "2026-02-01"},
    {"id": "v_lgt", "productId": "p_comp", "version": 5,
     "taskId": "t_lgt", "createdAt": "2026-02-02"},
    {"id": "v_plate", "productId": "p_plate", "version": 1,
     "taskId": None, "createdAt": "2026-01-01"},
]
REPRES = {
    "v_comp": [{"id": "r1", "name": "exr", "versionId": "v_comp"}],
    "v_lgt": [{"id": "r2", "name": "exr", "versionId": "v_lgt"}],
    "v_plate": [{"id": "r3", "name": "exr", "versionId": "v_plate"}],
}
TASKS = [
    {"id": "t_comp", "name": "comp"},
    {"id": "t_lgt", "name": "lighting"},
]
calls = []

ayonio = templates.ayonio
ayonio.is_available = lambda: True
ayonio.get_products = lambda p, ids: (calls.append("products"), PRODUCTS)[1]
ayonio.get_versions = lambda p, ids: (calls.append("versions"), VERSIONS)[1]
ayonio.get_tasks = lambda p, ids=None: (calls.append("tasks"), TASKS)[1]
ayonio.get_representations = lambda p, ids: (
    calls.append("repres"), REPRES.get(ids[0], [])
)[1]

comp_row = templates.TemplatedLoader(
    product_base_type="render", representation="exr", task_regex="comp"
)
resolved = templates.resolve("PRJ", "f1", comp_row)
check("task regex picks the version published from that task",
      resolved.ok and resolved.version["id"] == "v_comp",
      resolved.error or resolved.version)

lgt_row = templates.TemplatedLoader(
    product_base_type="render", representation="exr", task_regex="light"
)
resolved = templates.resolve("PRJ", "f1", lgt_row)
check("a different task regex picks a different version",
      resolved.ok and resolved.version["id"] == "v_lgt",
      resolved.error or resolved.version)

any_row = templates.TemplatedLoader(
    product_base_type="render", representation="exr"
)
resolved = templates.resolve("PRJ", "f1", any_row)
check("an empty task regex matches any task",
      resolved.ok and resolved.version["version"] == 5,
      resolved.error or resolved.version)

resolved = templates.resolve("PRJ", "f1", templates.TemplatedLoader(
    product_base_type="render", representation="exr", task_regex="nothing"
))
check("a task regex matching no task resolves to nothing",
      not resolved.ok, resolved.error)

calls[:] = []
cache = {}
template = templates.Template(loaders=[comp_row, lgt_row, any_row])
for row in template.loaders:
    templates.resolve("PRJ", "f1", row, None, cache)
check("the cache queries each folder once, whatever the row count",
      calls.count("products") == 1 and calls.count("versions") == 1,
      calls)

check("any_row_resolves is true when one row matches",
      templates.any_row_resolves("PRJ", "f1", template, None, {}))
check("any_row_resolves is false when no row matches",
      not templates.any_row_resolves("PRJ", "f1", templates.Template(
          loaders=[templates.TemplatedLoader(product_base_type="nonesuch")]
      ), None, {}))

# --- container naming -------------------------------------------------------
check("container key is folder path plus task",
      containers.container_key("/shots/seq101/sh010", "comp")
      == "/shots/seq101/sh010:comp")
check("container label uses the leaf folder name",
      containers.container_label("/shots/seq101/sh010", "comp")
      == "sh010:comp")

print("")
if failures:
    print("FAILURES: {}".format(failures))
    sys.exit(1)
print("ALL LOGIC CHECKS PASSED")
