"""Nuke side checks. Run with Nuke in terminal mode:

    Nuke17.0.exe -t tests/test_nuke.py

They need no AYON connection - everything AYON dependent is skipped by using a
template with no templated loaders.
"""

import os
import sys
import tempfile

import nuke

sys.path.insert(
    0, os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from qcscript import containers, nukeio, templates  # noqa: E402

failures = []


def check(label, condition, extra=""):
    print("[{}] {} {}".format("PASS" if condition else "FAIL", label, extra))
    if not condition:
        failures.append(label)


def clear_script():
    for node in nuke.allNodes():
        nuke.delete(node)


# --- Nuke will not accept a zero filled id as a node name -------------------
dot = nuke.nodes.Dot()
try:
    dot.setName("001")
except Exception:
    pass
check(
    "a node cannot be named '001', so placeholders are matched by label",
    dot.name() != "001", dot.name()
)
clear_script()

# --- template text round trip ----------------------------------------------
dot = nuke.nodes.Dot()
dot["label"].setValue("001")
dot.setXYpos(0, 0)
merge = nuke.nodes.Merge2()
merge.setXYpos(0, 200)
merge.setInput(0, dot)

nuke.selectAll()
template_file = os.path.join(tempfile.gettempdir(), "qcscript_test_template.nk")
nuke.nodeCopy(template_file)
with open(template_file) as stream:
    node_text = stream.read()
os.remove(template_file)
check("template text captured", "Dot" in node_text and "Merge2" in node_text)

clear_script()
pasted = nukeio.paste_node_text(node_text)
check("paste_node_text returns only the new nodes", len(pasted) == 2,
      [n.name() for n in pasted])

placeholder = nukeio.find_placeholder(pasted, "001")
check("placeholder found by label", placeholder is not None,
      placeholder.name() if placeholder else "")

# --- placeholder replacement ------------------------------------------------
nukeio.move_nodes_to(pasted, 500, 500)
loaded = nuke.nodes.Read()
nukeio.replace_placeholder(placeholder, loaded)
downstream = [n for n in nuke.allNodes() if n.Class() == "Merge2"][0]
check("downstream input rewired to the loaded node",
      downstream.input(0) is loaded)
check("placeholder deleted", all(n.Class() != "Dot" for n in nuke.allNodes()))
check("loaded node landed on the placeholder position",
      (loaded.xpos(), loaded.ypos()) == (500, 500),
      (loaded.xpos(), loaded.ypos()))

nukeio.set_string_knob(loaded, "qcs_key", "/shots/sh010:comp")
check("string knob written and read back",
      nukeio.get_string_knob(loaded, "qcs_key") == "/shots/sh010:comp")

# --- containers -------------------------------------------------------------
clear_script()

template = templates.Template(node_text=node_text)
folder = {"id": "folder-id", "path": "/shots/seq101/sh010", "name": "sh010"}
task = {"id": "task-id", "name": "comp", "taskType": "Compositing",
        "assignees": ["Jane Doe"]}

result = containers.create_container("PRJ", folder, task, template)
check("container created", result.created and result.ok, result.messages)

found = containers.find_containers()
check("container found again", len(found) == 1, [c.key for c in found])

container = found[0] if found else None
if container is not None:
    check("container key", container.key == "/shots/seq101/sh010:comp",
          container.key)
    check("container label", container.label == "sh010:comp", container.label)
    check("assignees survived the round trip",
          container.assignees == ["Jane Doe"], container.assignees)
    check("member nodes stamped with the key",
          len(container.member_nodes()) >= 2, len(container.member_nodes()))
    check("lookup by key works",
          containers.find_container_by_key(container.key) is not None)

    container.set_color("Yellow")
    check("backdrop colour set",
          container.backdrop["tile_color"].value() == 0xFFFF00FF)

again = containers.create_container("PRJ", folder, task, template)
check("adding the same folder+task twice is a no-op",
      not again.created and len(containers.find_containers()) == 1,
      again.messages)

task2 = dict(task, name="lighting", id="task-id-2")
check("second container created",
      containers.create_container("PRJ", folder, task2, template).created)
positions = sorted(c.backdrop.xpos() for c in containers.find_containers())
check("containers are placed side by side", len(set(positions)) == 2, positions)

# --- selection --------------------------------------------------------------
nukeio.clear_selection()
target = containers.find_container_by_key("/shots/seq101/sh010:comp")
target.select()
selected, error = containers.container_from_selection()
check("container found from the node selection",
      selected is not None and selected.key == target.key, error)

nukeio.clear_selection()
none_selected, error = containers.container_from_selection()
check("empty selection reports an error", none_selected is None and bool(error))

print("")
if failures:
    print("FAILURES: {}".format(failures))
    sys.exit(1)
print("ALL NUKE CHECKS PASSED")
