"""Inventory tab - what is in the script, and mass version changes."""

import datetime
import logging

from ..compat import QtWidgets
from .. import ayonio, containers, nukeio
from .base import TabController, busy, get_entity, set_entity

log = logging.getLogger(__name__)

# inventory_tree column order
COL_CONTAINER = 0
COL_PRODUCT = 1
COL_REPRE = 2
COL_VERSION = 3
COL_VERSIONS = 4
COL_LOCK = 5
COL_AUTHOR = 6
COL_STATUS = 7
COL_AGE = 8
COL_TAGS = 9

FILTER_ROWS = (1, 2, 3)


class InventoryTab(TabController):

    def setup(self):
        self.tree = self.widget("inventory_tree")
        self._containers = []
        self._folders_by_id = {}
        self._folded = False

        self.widget("inventory_fetch_nuke").clicked.connect(self.fetch_nuke)
        self.widget("inventory_fetch_ayon").clicked.connect(self.fetch_ayon)
        self.widget("inventory_fold").clicked.connect(self.toggle_fold)
        self.widget("inventory_select_nodes").clicked.connect(
            self.select_container_nodes
        )
        self.widget("inventory_change_color").clicked.connect(self.change_color)
        self.widget("inventory_version_min").clicked.connect(
            lambda: self.change_version("min")
        )
        self.widget("inventory_version_max").clicked.connect(
            lambda: self.change_version("max")
        )
        self.widget("inventory_version_up").clicked.connect(
            lambda: self.change_version("up")
        )
        self.widget("inventory_version_down").clicked.connect(
            lambda: self.change_version("down")
        )

        for index in FILTER_ROWS:
            self.widget("inventory_filter{}".format(index)).toggled.connect(
                self.apply_filters
            )
            self.widget(
                "inventory_filter{}_text".format(index)
            ).editingFinished.connect(self.apply_filters)
            self.widget(
                "inventory_filter{}_drop".format(index)
            ).currentIndexChanged.connect(self.apply_filters)
            self.widget(
                "inventory_filter{}_invert".format(index)
            ).toggled.connect(self.apply_filters)

        if self.tree is not None:
            self.tree.clear()
            self.tree.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection
            )

    def refresh(self):
        self.fetch_nuke()

    # -- reading the script -------------------------------------------------

    def fetch_nuke(self):
        """Read QC containers, and their AYON containers, out of the script."""
        if not nukeio.is_available():
            self.report(["Nuke is not available."])
            return

        self._containers = []
        for container in containers.find_containers():
            try:
                items = container.ayon_containers()
            except Exception:
                log.warning(
                    "Could not read AYON containers of %s",
                    container.key, exc_info=True
                )
                items = []
            self._containers.append({
                "container": container,
                "items": [
                    {"ayon": item, "repre": None, "version": None,
                     "product": None, "versions": []}
                    for item in items
                ],
            })
        self.populate()

    def fetch_ayon(self):
        """Fill in product, version and status information from AYON."""
        if not self._containers:
            self.fetch_nuke()
        error = ayonio.availability_error()
        if error:
            self.report([error])
            return

        project = ayonio.current_project_name()
        rows = [
            row for entry in self._containers for row in entry["items"]
        ]
        repre_ids = [row["ayon"].get("representation") for row in rows]

        with busy():
            repres = ayonio.get_representations_by_ids(project, repre_ids)
            repres_by_id = {r["id"]: r for r in repres}

            versions = ayonio.get_versions_by_ids(
                project, {r["versionId"] for r in repres}
            )
            versions_by_id = {v["id"]: v for v in versions}

            product_ids = {v["productId"] for v in versions}
            products = ayonio.get_products_by_ids(project, product_ids)
            products_by_id = {p["id"]: p for p in products}

            all_versions = ayonio.get_versions(project, product_ids)
            versions_by_product = {}
            for version in all_versions:
                versions_by_product.setdefault(
                    version["productId"], []
                ).append(version)

        for row in rows:
            repre = repres_by_id.get(row["ayon"].get("representation"))
            row["repre"] = repre
            if repre is None:
                continue
            version = versions_by_id.get(repre["versionId"])
            row["version"] = version
            if version is None:
                continue
            row["product"] = products_by_id.get(version["productId"])
            row["versions"] = sorted(
                (
                    v.get("version") or 0
                    for v in versions_by_product.get(version["productId"], [])
                    if (v.get("version") or 0) >= 0
                )
            )

        self.populate()

    # -- tree ---------------------------------------------------------------

    def populate(self):
        if self.tree is None:
            return
        self.tree.clear()
        for entry in self._containers:
            container = entry["container"]
            parent = QtWidgets.QTreeWidgetItem(self.tree)
            parent.setText(COL_CONTAINER, container.label or container.key)
            parent.setText(COL_AUTHOR, ", ".join(container.assignees))
            set_entity(parent, {"type": "container", "entry": entry})

            for row in entry["items"]:
                item = QtWidgets.QTreeWidgetItem(parent)
                self._fill_item(item, row)
                set_entity(
                    item, {"type": "item", "row": row, "entry": entry}
                )
        self.tree.expandAll()
        self.apply_filters()

    def _fill_item(self, item, row):
        ayon_container = row["ayon"]
        product = row.get("product") or {}
        version = row.get("version") or {}
        repre = row.get("repre") or {}

        item.setText(COL_CONTAINER, ayon_container.get("name", ""))
        item.setText(COL_PRODUCT, product.get("name", ""))
        item.setText(COL_REPRE, repre.get("name", ""))
        item.setText(
            COL_VERSION,
            str(version.get("version", "")) if version else ""
        )
        item.setText(
            COL_VERSIONS,
            ", ".join(str(v) for v in row.get("versions") or [])
        )
        item.setText(
            COL_LOCK, "locked" if ayon_container.get("qcs_version_lock") else ""
        )
        item.setText(COL_AUTHOR, version.get("author", "") if version else "")
        item.setText(COL_STATUS, version.get("status", "") if version else "")
        age = age_hours(version.get("createdAt")) if version else None
        item.setText(COL_AGE, "" if age is None else "{:.1f}".format(age))
        item.setText(COL_TAGS, ", ".join(version.get("tags") or []))

    # -- filters ------------------------------------------------------------

    def apply_filters(self):
        if self.tree is None:
            return
        filters = []
        for index in FILTER_ROWS:
            if not self.widget("inventory_filter{}".format(index)).isChecked():
                continue
            filters.append({
                "text": self.widget(
                    "inventory_filter{}_text".format(index)
                ).text().strip(),
                "source": self.widget(
                    "inventory_filter{}_drop".format(index)
                ).currentText(),
                "invert": self.widget(
                    "inventory_filter{}_invert".format(index)
                ).isChecked(),
            })

        for index in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(index)
            entity = get_entity(item)
            entry = entity["entry"] if entity else None
            item.setHidden(
                entry is not None and not self._entry_matches(entry, filters)
            )

    def _entry_matches(self, entry, filters):
        for spec in filters:
            matched = self._matches_one(entry, spec)
            if spec["invert"]:
                matched = not matched
            if not matched:
                return False
        return True

    def _matches_one(self, entry, spec):
        container = entry["container"]
        source = spec["source"]
        text = spec["text"]

        if source == "Age Younger":
            try:
                limit = float(text)
            except ValueError:
                return True
            for row in entry["items"]:
                version = row.get("version") or {}
                age = age_hours(version.get("createdAt"))
                if age is not None and age < limit:
                    return True
            return False

        if source == "Version Not Latest":
            for row in entry["items"]:
                version = row.get("version") or {}
                current = version.get("version")
                available = row.get("versions") or []
                if current is not None and available and current != available[-1]:
                    return True
            return False

        values = {
            "Folder Name": container.folder_path.rstrip("/").rsplit("/", 1)[-1],
            "Folder Path": container.folder_path,
            "Folder Status": self._folder_status(container),
            "Task Asignee": ", ".join(container.assignees),
            "Task Name": container.task_name,
            "Task Status": container.data.get("task_status", ""),
            "Task Type": container.data.get("task_type", ""),
        }
        value = values.get(source, "")
        if not text:
            return True
        return text.lower() in str(value).lower()

    def _folder_status(self, container):
        folder = self._folders_by_id.get(container.folder_id)
        if folder is None:
            folder = ayonio.get_folder_by_id(
                container.project_name, container.folder_id
            ) or {}
            self._folders_by_id[container.folder_id] = folder
        return folder.get("status", "")

    # -- selection ----------------------------------------------------------

    def selected_entries(self):
        """QC container entries touched by the current tree selection."""
        entries = []
        if self.tree is None:
            return entries
        for item in self.tree.selectedItems():
            entity = get_entity(item)
            if not entity:
                continue
            entry = entity["entry"]
            if entry not in entries:
                entries.append(entry)
        return entries

    def selected_rows(self):
        """Loaded items touched by the selection, honouring version locks."""
        rows = []
        if self.tree is None:
            return rows
        for item in self.tree.selectedItems():
            entity = get_entity(item)
            if not entity:
                continue
            if entity["type"] == "item":
                candidates = [entity["row"]]
            else:
                candidates = entity["entry"]["items"]
            for row in candidates:
                if row not in rows:
                    rows.append(row)
        return rows

    # -- actions ------------------------------------------------------------

    def toggle_fold(self):
        if self.tree is None:
            return
        self._folded = not self._folded
        if self._folded:
            self.tree.collapseAll()
        else:
            self.tree.expandAll()

    def select_container_nodes(self):
        entries = self.selected_entries()
        if not entries:
            self.report(["Select one or more containers in the tree."])
            return
        nukeio.clear_selection()
        for entry in entries:
            entry["container"].select()

    def change_color(self):
        entries = self.selected_entries()
        if not entries:
            self.report(["Select one or more containers in the tree."])
            return
        color = self.widget("inventory_color").currentText()
        for entry in entries:
            entry["container"].set_color(color)

    def change_version(self, mode):
        """Mass version change. ``mode`` is min, max, up or down."""
        rows = self.selected_rows()
        if not rows:
            self.report(["Select containers or items in the tree first."])
            return
        error = ayonio.availability_error()
        if error:
            self.report([error])
            return

        color = self.widget("inventory_color").currentText()
        messages = []
        changed_containers = []
        changed = 0

        with busy():
            for row in rows:
                ayon_container = row["ayon"]
                if ayon_container.get("qcs_version_lock"):
                    continue
                target = self._target_version(row, mode)
                if target is None:
                    continue
                try:
                    ayonio.set_container_version(ayon_container, target)
                except Exception as exc:
                    messages.append(
                        "{}: {}".format(ayon_container.get("name", "?"), exc)
                    )
                    continue
                changed += 1
                key = ayon_container.get("qcs_key")
                if key and key not in changed_containers:
                    changed_containers.append(key)

        # Flow B: mark what moved so the supervisor can find it in the graph.
        for entry in self._containers:
            if entry["container"].key in changed_containers:
                entry["container"].set_color(color)

        messages.insert(
            0,
            "Version {}: changed {} of {} item(s).".format(
                mode, changed, len(rows)
            ),
        )
        locked = sum(
            1 for row in rows if row["ayon"].get("qcs_version_lock")
        )
        if locked:
            messages.append("{} item(s) skipped, version locked.".format(locked))
        self.report(messages)
        self.fetch_nuke()
        self.fetch_ayon()

    def _target_version(self, row, mode):
        available = row.get("versions") or []
        version = row.get("version") or {}
        current = version.get("version")

        if mode == "max":
            if not available:
                return -1  # ayon_core resolves -1 to the latest version
            return None if current == available[-1] else available[-1]
        if mode == "min":
            if not available:
                return None
            return None if current == available[0] else available[0]
        if current is None or not available:
            return None
        try:
            index = available.index(current)
        except ValueError:
            return None
        if mode == "up":
            index = min(index + 1, len(available) - 1)
        elif mode == "down":
            index = max(index - 1, 0)
        target = available[index]
        return None if target == current else target


# ---------------------------------------------------------------------------

def age_hours(created_at):
    """Hours since an AYON ``createdAt`` value, or None."""
    if not created_at:
        return None
    if isinstance(created_at, (int, float)):
        created = datetime.datetime.fromtimestamp(
            created_at, datetime.timezone.utc
        )
    else:
        text = str(created_at).replace("Z", "+00:00")
        try:
            created = datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    if created.tzinfo is None:
        created = created.replace(tzinfo=datetime.timezone.utc)
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - created).total_seconds() / 3600.0
