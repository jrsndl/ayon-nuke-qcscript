"""QC containers: one shot's worth of nodes wrapped in a Nuke BackdropNode.

The backdrop carries the identity of the container (project, folder, task) in a
hidden JSON knob, and every node the template loaded is stamped with the
container key so the Inventory can group them again after the script is
reopened.
"""

import json
import logging

from . import ayonio, nukeio, templates

log = logging.getLogger(__name__)

# knobs on the backdrop
KNOB_MARKER = "qcs_container"
KNOB_DATA = "qcs_data"

# knobs stamped on every node a templated loader produced
KNOB_CONTAINER_KEY = "qcs_key"
KNOB_LOADER_ID = "qcs_loader_id"
KNOB_VERSION_HINT = "qcs_version_hint"
KNOB_VERSION_LOCK = "qcs_version_lock"

# node graph grid used when placing a new container
GRID_COLUMNS = 6
GRID_SPACING_X = 900
GRID_SPACING_Y = 700


def container_key(folder_path, task_name):
    """Unique key of a container."""
    return "{}:{}".format(folder_path, task_name)


def container_label(folder_path, task_name):
    """Name shown to the user."""
    leaf = (folder_path or "").rstrip("/").rsplit("/", 1)[-1]
    return "{}:{}".format(leaf, task_name)


class QCContainer(object):
    """A backdrop that groups the nodes belonging to one folder + task."""

    def __init__(self, backdrop, data):
        self.backdrop = backdrop
        self.data = data or {}

    # -- identity ----------------------------------------------------------

    @property
    def key(self):
        return self.data.get("key", "")

    @property
    def label(self):
        return self.data.get("label", "")

    @property
    def project_name(self):
        return self.data.get("project_name", "")

    @property
    def folder_path(self):
        return self.data.get("folder_path", "")

    @property
    def folder_id(self):
        return self.data.get("folder_id", "")

    @property
    def task_name(self):
        return self.data.get("task_name", "")

    @property
    def task_id(self):
        return self.data.get("task_id", "")

    @property
    def assignees(self):
        return self.data.get("assignees") or []

    # -- contents ----------------------------------------------------------

    def nodes(self):
        return nukeio.nodes_in_backdrop(self.backdrop)

    def member_nodes(self):
        """Nodes stamped with this container's key, plus anything inside."""
        key = self.key
        stamped = [
            node for node in nukeio.all_nodes()
            if nukeio.get_string_knob(node, KNOB_CONTAINER_KEY) == key
        ]
        inside = self.nodes()
        seen = set()
        result = []
        for node in stamped + inside:
            name = node.fullName()
            if name in seen:
                continue
            seen.add(name)
            result.append(node)
        return result

    def ayon_containers(self):
        """AYON containers (loaded nodes) that belong to this QC container."""
        from ayon_nuke.api.pipeline import parse_container

        result = []
        for node in self.member_nodes():
            try:
                container = parse_container(node)
            except Exception:
                container = None
            if container:
                container["qcs_key"] = self.key
                container["qcs_loader_id"] = nukeio.get_string_knob(
                    node, KNOB_LOADER_ID
                )
                container["qcs_version_lock"] = (
                    nukeio.get_string_knob(node, KNOB_VERSION_LOCK) == "yes"
                )
                result.append(container)
        return result

    # -- persistence -------------------------------------------------------

    def save(self):
        nukeio.set_string_knob(
            self.backdrop, KNOB_DATA, json.dumps(self.data, sort_keys=True)
        )

    def select(self):
        nodes = self.member_nodes()
        nukeio.select_nodes(nodes + [self.backdrop])

    def set_color(self, color_name):
        nukeio.set_tile_color([self.backdrop], color_name)


# ---------------------------------------------------------------------------
# lookup
# ---------------------------------------------------------------------------

def _read_container(backdrop):
    if not nukeio.has_knob(backdrop, KNOB_MARKER):
        return None
    raw = nukeio.get_string_knob(backdrop, KNOB_DATA, "")
    try:
        data = json.loads(raw) if raw else {}
    except ValueError:
        log.warning("Container %s has unreadable data", backdrop.name())
        data = {}
    return QCContainer(backdrop, data)


def find_containers():
    """Every QC container in the current script."""
    result = []
    for backdrop in nukeio.all_backdrops():
        container = _read_container(backdrop)
        if container is not None:
            result.append(container)
    return result


def find_container_by_key(key):
    for container in find_containers():
        if container.key == key:
            return container
    return None


def container_from_selection():
    """The QC container the user has selected in the node graph.

    Accepts either the backdrop itself or any node inside it. Returns
    (container, error_message).
    """
    selected = nukeio.selected_nodes()
    if not selected:
        return None, "Nothing is selected in the Nuke node graph."

    containers = find_containers()
    by_backdrop = {c.backdrop.fullName(): c for c in containers}

    found = []
    for node in selected:
        name = node.fullName()
        if name in by_backdrop:
            found.append(by_backdrop[name])
            continue
        key = nukeio.get_string_knob(node, KNOB_CONTAINER_KEY)
        if key:
            match = next((c for c in containers if c.key == key), None)
            if match is not None:
                found.append(match)
                continue
        for container in containers:
            if any(n.fullName() == name for n in container.nodes()):
                found.append(container)
                break

    unique = []
    for container in found:
        if container not in unique:
            unique.append(container)

    if not unique:
        return None, "The selection is not part of a QC container."
    if len(unique) > 1:
        return None, (
            "More than one container is selected - only one can be edited "
            "at a time."
        )
    return unique[0], ""


# ---------------------------------------------------------------------------
# creation
# ---------------------------------------------------------------------------

def next_position():
    """Where the next container should go in the node graph."""
    index = len(find_containers())
    column = index % GRID_COLUMNS
    row = index // GRID_COLUMNS
    return column * GRID_SPACING_X, row * GRID_SPACING_Y


class CreateResult(object):
    def __init__(self, container=None, created=False, messages=None):
        self.container = container
        self.created = created
        self.messages = messages or []

    @property
    def ok(self):
        return self.container is not None


def create_container(
    project_name,
    folder_entity,
    task_entity,
    template,
    task_names_by_id=None,
):
    """Build one container from the template - the Add Container sequence."""
    folder_path = folder_entity.get("path") or folder_entity.get("name") or ""
    task_name = task_entity.get("name") or ""
    key = container_key(folder_path, task_name)
    messages = []

    existing = find_container_by_key(key)
    if existing is not None:
        return CreateResult(
            existing, False, ["'{}' already exists, skipped.".format(key)]
        )

    label = container_label(folder_path, task_name)

    # 1. template nodes
    template_nodes = nukeio.paste_node_text(template.node_text)
    if not template_nodes and template.node_text.strip():
        messages.append("Template nodes could not be pasted.")

    x, y = next_position()
    if template_nodes:
        nukeio.move_nodes_to(template_nodes, x, y)

    all_container_nodes = list(template_nodes)

    # 2. templated loaders
    for row in template.loaders:
        resolved = templates.resolve(
            project_name, folder_entity["id"], row, task_names_by_id
        )
        if not resolved.ok:
            messages.append(
                "{} / loader {}: {}".format(label, row.loader_id, resolved.error)
            )
            continue

        loader_label = row.loader
        if not loader_label:
            messages.append(
                "{} / loader {}: no loader set".format(label, row.loader_id)
            )
            continue

        with nukeio.CapturedNodes() as capture:
            try:
                ayonio.load_representation(
                    resolved.representation,
                    loader_label,
                    options=row.options(),
                )
            except Exception as exc:
                messages.append(
                    "{} / loader {}: {}".format(label, row.loader_id, exc)
                )
                continue

        loaded = capture.created
        if not loaded:
            messages.append(
                "{} / loader {}: loader created no nodes".format(
                    label, row.loader_id
                )
            )
            continue

        for node in loaded:
            nukeio.set_string_knob(node, KNOB_CONTAINER_KEY, key)
            nukeio.set_string_knob(node, KNOB_LOADER_ID, row.loader_id)
            nukeio.set_string_knob(node, KNOB_VERSION_HINT, row.version_hint)
            nukeio.set_string_knob(
                node, KNOB_VERSION_LOCK, "yes" if row.version_lock else ""
            )

        placeholder = nukeio.find_placeholder(template_nodes, row.loader_id)
        primary = _primary_node(loaded)
        if placeholder is not None:
            # translate the whole loaded block so the primary node lands
            # exactly where the placeholder was
            nukeio.move_nodes(
                loaded,
                placeholder.xpos() - primary.xpos(),
                placeholder.ypos() - primary.ypos(),
            )
            nukeio.replace_placeholder(placeholder, primary)
            if placeholder in template_nodes:
                template_nodes.remove(placeholder)
        else:
            nukeio.move_nodes_to(loaded, x, y + 300)
            messages.append(
                "{} / loader {}: no placeholder Dot named '{}', nodes were "
                "left next to the container".format(
                    label, row.loader_id, row.loader_id
                )
            )

        all_container_nodes.extend(loaded)

    if not all_container_nodes:
        return CreateResult(
            None, False,
            messages + ["Nothing was created for '{}'.".format(key)]
        )

    # 3. backdrop
    backdrop = nukeio.create_backdrop(all_container_nodes, label)
    nukeio.set_string_knob(backdrop, KNOB_MARKER, "yes", label="qc container")

    data = {
        "key": key,
        "label": label,
        "project_name": project_name,
        "folder_path": folder_path,
        "folder_id": folder_entity.get("id", ""),
        "task_name": task_name,
        "task_id": task_entity.get("id", ""),
        "assignees": list(task_entity.get("assignees") or []),
        "task_type": task_entity.get("taskType", ""),
    }
    container = QCContainer(backdrop, data)
    container.save()

    for node in all_container_nodes:
        nukeio.set_string_knob(node, KNOB_CONTAINER_KEY, key)

    return CreateResult(container, True, messages)


def _primary_node(nodes):
    """The node a placeholder should be replaced with.

    Prefer the AYON container node, then a Read, then the first node created.
    """
    for node in nodes:
        if nukeio.has_knob(node, "AvalonTab") or nukeio.has_knob(node, "avalon"):
            return node
    for node in nodes:
        if node.Class() in ("Read", "Group", "Precomp"):
            return node
    return nodes[0]


# ---------------------------------------------------------------------------
# folder attributes, used by the Container tab
# ---------------------------------------------------------------------------

def folder_attributes(project_name, folder_id):
    """Frame range and format attributes of a folder, or an empty dict."""
    folder = ayonio.get_folder_by_id(project_name, folder_id)
    if not folder:
        return {}
    return dict(folder.get("attrib") or {})
