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
    check("backdrop is drawn as a border, not filled",
          container.backdrop["appearance"].value() == "Border",
          container.backdrop["appearance"].value())

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

# --- a container built through a templated loader ---------------------------
# The loader path deletes the placeholder, so the node list the backdrop is
# sized from must not keep a reference to it. AYON is stubbed out here; only
# the node bookkeeping is under test.
clear_script()

row = templates.TemplatedLoader(
    loader_id="001", product_base_type="render", representation="exr",
    loader="Stub Loader",
)
loader_template = templates.Template(node_text=node_text, loaders=[row])

real_resolve = containers.templates.resolve
real_load = containers.ayonio.load_representation


def fake_resolve(project_name, folder_id, loader_row, task_names_by_id=None,
                 cache=None):
    return templates.Resolved(
        loader_row,
        product={"id": "p1", "name": "renderMain"},
        version={"id": "v1", "version": 3},
        representation={"id": "r1", "name": "exr"},
    )


def fake_load(representation, loader_label, options=None, name=None):
    read = nuke.nodes.Read()
    read.setXYpos(4000, 4000)
    return read


containers.templates.resolve = fake_resolve
containers.ayonio.load_representation = fake_load
try:
    result = containers.create_container("PRJ", folder, task, loader_template)
finally:
    containers.templates.resolve = real_resolve
    containers.ayonio.load_representation = real_load

check("container with a templated loader created",
      result.created and result.ok, result.messages)
check("no messages from a clean templated build", not result.messages,
      result.messages)

backdrops = [n for n in nuke.allNodes() if n.Class() == "BackdropNode"]
check("the backdrop exists", len(backdrops) == 1, len(backdrops))

if backdrops and result.container is not None:
    backdrop = backdrops[0]
    inside = nukeio.nodes_in_backdrop(backdrop)
    reads = [n for n in nuke.allNodes() if n.Class() == "Read"]
    check("the loaded node is inside the backdrop",
          bool(reads) and reads[0] in inside,
          [n.name() for n in inside])
    check("the backdrop covers the merge as well",
          any(n.Class() == "Merge2" for n in inside),
          [n.Class() for n in inside])
    check("the loaded node is stamped with the container key",
          nukeio.get_string_knob(reads[0], "qcs_key") == result.container.key)
    check("the loaded node knows its loader id",
          nukeio.get_string_knob(reads[0], "qcs_loader_id") == "001")
    check("the placeholder is gone",
          all(n.Class() != "Dot" for n in nuke.allNodes()))

# --- script root range and format ------------------------------------------
nukeio.set_root_range(1001, 1096)
check("root frame range set",
      (nuke.root()["first_frame"].value(), nuke.root()["last_frame"].value())
      == (1001, 1096),
      (nuke.root()["first_frame"].value(), nuke.root()["last_frame"].value()))

used = nukeio.set_root_format(1920, 1080, 1.0, "QCS_1920x1080")
root_format = nuke.root()["format"].value()
check("root format set to a matching format",
      root_format.width() == 1920 and root_format.height() == 1080,
      "{} ({}x{})".format(used, root_format.width(), root_format.height()))
check("an existing Nuke format is reused rather than duplicated",
      used == root_format.name() and used != "QCS_1920x1080", used)

before = len(nuke.formats())
odd = nukeio.set_root_format(1234, 567, 2.0, "QCS_odd")
check("an unknown format is added once", odd == "QCS_odd", odd)
nukeio.set_root_format(1234, 567, 2.0, "QCS_odd")
check("setting the same odd format twice does not add it again",
      len(nuke.formats()) == before + 1,
      (before, len(nuke.formats())))

# a stale reference to a deleted node must not break sizing
ghost = nuke.nodes.Dot()
survivor = nuke.nodes.Dot()
nuke.delete(ghost)
check("node_bbox ignores deleted nodes",
      nukeio.node_bbox([ghost, survivor]) is not None)
check("alive() drops deleted nodes",
      nukeio.alive([ghost, survivor]) == [survivor])

print("")
if failures:
    print("FAILURES: {}".format(failures))
    sys.exit(1)
print("ALL NUKE CHECKS PASSED")
