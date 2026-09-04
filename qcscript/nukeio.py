"""Nuke node graph helpers.

Nothing in here knows about AYON; it only manipulates nodes, knobs and
backdrops so the rest of the tool can stay readable.
"""

import logging
import os
import tempfile

log = logging.getLogger(__name__)

try:
    import nuke
except ImportError:  # pragma: no cover - only importable inside Nuke
    nuke = None


# tile_color values, 0xRRGGBBAA
COLORS = {
    "Red": 0xFF0000FF,
    "Green": 0x00FF00FF,
    "Blue": 0x0000FFFF,
    "Bl,ue": 0x0000FFFF,  # the .ui has this typo in the combo box
    "Cyan": 0x00FFFFFF,
    "Magenta": 0xFF00FFFF,
    "Yellow": 0xFFFF00FF,
}


def is_available():
    return nuke is not None


def all_nodes():
    if nuke is None:
        return []
    return nuke.allNodes(recurseGroups=False)


def node_by_name(name):
    if nuke is None:
        return None
    return nuke.toNode(name)


def selected_nodes():
    if nuke is None:
        return []
    return nuke.selectedNodes()


def clear_selection():
    for node in selected_nodes():
        node.setSelected(False)


def select_nodes(nodes, clear=True):
    if clear:
        clear_selection()
    for node in nodes:
        try:
            node.setSelected(True)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# knobs
# ---------------------------------------------------------------------------

def ensure_string_knob(node, name, label=None, hidden=True):
    knob = node.knob(name)
    if knob is None:
        knob = nuke.String_Knob(name, label or name)
        node.addKnob(knob)
        if hidden:
            knob.setVisible(False)
    return knob


def set_string_knob(node, name, value, label=None, hidden=True):
    knob = ensure_string_knob(node, name, label=label, hidden=hidden)
    knob.setValue(value if value is not None else "")
    return knob


def get_string_knob(node, name, default=""):
    knob = node.knob(name)
    if knob is None:
        return default
    try:
        return knob.value()
    except Exception:
        return default


def has_knob(node, name):
    return node.knob(name) is not None


# ---------------------------------------------------------------------------
# copy / paste
# ---------------------------------------------------------------------------

def paste_node_text(node_text):
    """Paste a block of .nk node text and return the nodes it created."""
    if nuke is None or not node_text.strip():
        return []

    before = set(all_nodes())
    handle, path = tempfile.mkstemp(suffix=".nk", prefix="qcscript_")
    try:
        with os.fdopen(handle, "w") as stream:
            stream.write(node_text)
        clear_selection()
        nuke.nodePaste(path)
    finally:
        try:
            os.remove(path)
        except OSError:
            pass

    return [node for node in all_nodes() if node not in before]


class CapturedNodes(object):
    """Context manager recording which nodes appeared inside the block.

    Loaders create an unpredictable number of nodes, so the only reliable way
    to know what a loader produced is to diff the graph around the call.
    """

    def __init__(self):
        self.before = set()
        self.created = []

    def __enter__(self):
        self.before = set(all_nodes())
        return self

    def __exit__(self, *exc_info):
        self.created = [n for n in all_nodes() if n not in self.before]
        return False


# ---------------------------------------------------------------------------
# geometry
# ---------------------------------------------------------------------------

def node_bbox(nodes):
    """(x, y, width, height) covering the given nodes, or None."""
    nodes = [n for n in nodes if n is not None]
    if not nodes:
        return None
    xs, ys, x2s, y2s = [], [], [], []
    for node in nodes:
        x, y = node.xpos(), node.ypos()
        xs.append(x)
        ys.append(y)
        x2s.append(x + node.screenWidth())
        y2s.append(y + node.screenHeight())
    x, y = min(xs), min(ys)
    return x, y, max(x2s) - x, max(y2s) - y


def move_nodes(nodes, dx, dy):
    for node in nodes:
        node.setXYpos(int(node.xpos() + dx), int(node.ypos() + dy))


def move_nodes_to(nodes, x, y):
    bbox = node_bbox(nodes)
    if bbox is None:
        return
    move_nodes(nodes, x - bbox[0], y - bbox[1])


# ---------------------------------------------------------------------------
# backdrops
# ---------------------------------------------------------------------------

BACKDROP_PADDING = 60
BACKDROP_HEADER = 90


def create_backdrop(nodes, label, tile_color=None, font_size=42):
    """Wrap nodes in a BackdropNode sized to fit them."""
    if nuke is None:
        return None
    bbox = node_bbox(nodes)
    if bbox is None:
        bbox = (0, 0, 400, 200)
    x, y, width, height = bbox

    kwargs = {
        "xpos": int(x - BACKDROP_PADDING),
        "ypos": int(y - BACKDROP_HEADER),
        "bdwidth": int(width + BACKDROP_PADDING * 2),
        "bdheight": int(height + BACKDROP_HEADER + BACKDROP_PADDING),
        "label": label,
        "note_font_size": font_size,
    }
    if tile_color is not None:
        kwargs["tile_color"] = tile_color

    backdrop = nuke.nodes.BackdropNode(**kwargs)
    backdrop.setSelected(False)
    return backdrop


def resize_backdrop(backdrop, nodes):
    bbox = node_bbox(nodes)
    if bbox is None:
        return
    x, y, width, height = bbox
    backdrop.setXYpos(int(x - BACKDROP_PADDING), int(y - BACKDROP_HEADER))
    backdrop["bdwidth"].setValue(int(width + BACKDROP_PADDING * 2))
    backdrop["bdheight"].setValue(
        int(height + BACKDROP_HEADER + BACKDROP_PADDING)
    )


def nodes_in_backdrop(backdrop):
    """Nodes covered by a backdrop, excluding the backdrop itself."""
    getter = getattr(backdrop, "getNodes", None)
    if getter is not None:
        try:
            return [n for n in getter() if n is not backdrop]
        except Exception:
            pass

    # Geometric fallback for older Nuke versions.
    bx, by = backdrop.xpos(), backdrop.ypos()
    bw = backdrop["bdwidth"].value()
    bh = backdrop["bdheight"].value()
    result = []
    for node in all_nodes():
        if node is backdrop or node.Class() == "BackdropNode":
            continue
        nx, ny = node.xpos(), node.ypos()
        if bx <= nx <= bx + bw and by <= ny <= by + bh:
            result.append(node)
    return result


def all_backdrops():
    return [n for n in all_nodes() if n.Class() == "BackdropNode"]


# ---------------------------------------------------------------------------
# placeholders
# ---------------------------------------------------------------------------

def find_placeholder(nodes, loader_id):
    """Find the Dot node standing in for a templated loader.

    Nuke node names cannot start with a digit, so a plain ``001`` id is
    matched against the node label and against common name spellings.
    """
    loader_id = str(loader_id)
    candidates = {loader_id, "L" + loader_id, "qcs" + loader_id,
                  "placeholder" + loader_id}
    labelled = None
    for node in nodes:
        if node.Class() not in ("Dot", "NoOp"):
            continue
        name = node.name()
        if name in candidates:
            return node
        label_knob = node.knob("label")
        label = label_knob.value().strip() if label_knob else ""
        if label == loader_id and labelled is None:
            labelled = node
        elif name.endswith(loader_id) and labelled is None:
            labelled = node
    return labelled


def replace_placeholder(placeholder, new_node):
    """Put ``new_node`` where the placeholder was and rewire its outputs."""
    if placeholder is None or new_node is None:
        return

    x, y = placeholder.xpos(), placeholder.ypos()
    for dependent in placeholder.dependent(nuke.INPUTS, forceEvaluate=False):
        for index in range(dependent.inputs()):
            if dependent.input(index) is placeholder:
                dependent.setInput(index, new_node)

    nuke.delete(placeholder)
    new_node.setXYpos(int(x), int(y))


# ---------------------------------------------------------------------------
# colours
# ---------------------------------------------------------------------------

def set_tile_color(nodes, color_name):
    value = COLORS.get(color_name)
    if value is None:
        return
    for node in nodes:
        knob = node.knob("tile_color")
        if knob is not None:
            knob.setValue(value)


# ---------------------------------------------------------------------------
# script level
# ---------------------------------------------------------------------------

def set_root_range(first, last):
    if nuke is None:
        return
    root = nuke.root()
    root["first_frame"].setValue(int(first))
    root["last_frame"].setValue(int(last))


def set_root_format(width, height, pixel_aspect, name="QC Script Helper"):
    if nuke is None:
        return
    format_string = "{} {} {} {}".format(
        int(width), int(height), float(pixel_aspect), name
    )
    try:
        nuke.addFormat(format_string)
        nuke.root()["format"].setValue(name)
    except Exception:
        log.warning("Could not set format %s", format_string, exc_info=True)


def message(text):
    if nuke is None:
        print(text)
        return
    nuke.message(text)
