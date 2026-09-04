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
