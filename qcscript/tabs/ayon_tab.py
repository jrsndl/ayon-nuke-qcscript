"""AYON tab - browse folders and tasks, add containers, load single items."""

import logging

from ..compat import QtCore, QtWidgets
from .. import ayonio, containers, templates
from .base import (
    TabController,
    busy,
    fill_table,
    get_entity,
    selected_table_rows,
    set_entity,
    split_words,
    table_entity,
)

log = logging.getLogger(__name__)

# widgets that make up the two optional panels
PRODUCT_PANEL = ("label_2", "ayon_products_spreadsheet")
REPRESENTATION_PANEL = (
    "line_2", "label_3", "ayon_repres_latest", "ayon_repres_spreadsheet",
    "ayon_load",
)

SEARCH_SOURCES = {
    "Folder Name": ("folder", "name"),
    "Folder Status": ("folder", "status"),
    "Task Asignee": ("task", "assignees"),
    "Task Name": ("task", "name"),
    "Task Status": ("task", "status"),
    "Task Type": ("task", "taskType"),
}


class AyonTab(TabController):

    def setup(self):
        self.tree = self.widget("ayon_tree")
        self.products_table = self.widget("ayon_products_spreadsheet")
        self.repres_table = self.widget("ayon_repres_spreadsheet")
        self.project_field = self.widget("ayon_project")

        self._folders = []
        self._tasks = []
        self._products = []
        self._versions_by_product = {}

        project = ayonio.current_project_name()
        if self.project_field is not None:
            self.project_field.setText(project)

        self.widget("ayon_reload").clicked.connect(self.reload)
        self.widget("ayon_search").clicked.connect(self.populate_tree)
        self.widget("ayon_search_text").returnPressed.connect(
            self.populate_tree
        )
        self.widget("ayon_add_container").clicked.connect(self.add_containers)
        self.widget("ayon_load").clicked.connect(self.load_representation)

        for name in ("ayon_task", "ayon_product"):
            self.widget(name).toggled.connect(self.populate_tree)

        self.widget("ayon_show_products").toggled.connect(
            lambda state: self._set_panel_visible(PRODUCT_PANEL, state)
        )
        self.widget("ayon_show_representations").toggled.connect(
            lambda state: self._set_panel_visible(REPRESENTATION_PANEL, state)
        )
        self.widget("ayon_repres_latest").toggled.connect(
            self.populate_representations
        )

        if self.tree is not None:
            self.tree.setSelectionMode(
                QtWidgets.QAbstractItemView.ExtendedSelection
            )
            self.tree.itemSelectionChanged.connect(self.populate_products)
        if self.products_table is not None:
            self.products_table.itemSelectionChanged.connect(
                self.populate_representations
            )

        # the .ui ships with example rows so the layout is readable in Designer
        fill_table(self.products_table, [])
        fill_table(self.repres_table, [])
        if self.tree is not None:
            self.tree.clear()

        if project and ayonio.is_available():
            self.reload()

    # -- helpers -----------------------------------------------------------

    def project_name(self):
        if self.project_field is None:
            return ""
        return self.project_field.text().strip()

    def _set_panel_visible(self, widget_names, visible):
        for name in widget_names:
            widget = self.ui.findChild(QtCore.QObject, name)
            if widget is not None:
                widget.setVisible(bool(visible))

    # -- data --------------------------------------------------------------

    def reload(self):
        """Re-query the whole folder/task tree from AYON."""
        project = self.project_name()
        if not project:
            self.report(["No AYON project - is Nuke running inside AYON?"])
            return
        error = ayonio.availability_error()
        if error:
            self.report([error])
            return

        with busy():
            self._folders = ayonio.get_folders(project)
            self._tasks = ayonio.get_tasks(project)
        self.populate_tree()

    def task_names_by_id(self):
        return {task["id"]: task.get("name", "") for task in self._tasks}

    # -- tree --------------------------------------------------------------

    def populate_tree(self):
        if self.tree is None:
            return
        self.tree.clear()

        search_text = self.widget("ayon_search_text").text().strip().lower()
        source = self.widget("ayon_search_source").currentText()
        task_filter_on = self.widget("ayon_task").isChecked()
        task_words = [
            word.lower()
            for word in split_words(self.widget("ayon_task_text").text())
        ]

        tasks_by_folder = {}
        for task in self._tasks:
            if task_filter_on and task_words:
                name = (task.get("name") or "").lower()
                if not any(word in name for word in task_words):
                    continue
            if not self._matches_search(search_text, source, task=task):
                continue
            tasks_by_folder.setdefault(task["folderId"], []).append(task)

        items_by_id = {}
        folders_by_id = {f["id"]: f for f in self._folders}

        def visible(folder):
            if tasks_by_folder.get(folder["id"]):
                return True
            return self._matches_search(search_text, source, folder=folder)

        # Sort by path so parents are always created before their children.
        for folder in sorted(
            self._folders, key=lambda f: f.get("path") or f.get("name") or ""
        ):
            if not self._folder_in_scope(folder, folders_by_id, visible):
                continue
            parent_item = items_by_id.get(folder.get("parentId"))
            item = QtWidgets.QTreeWidgetItem(
                parent_item if parent_item is not None else self.tree
            )
            item.setText(0, folder.get("name") or "")
            item.setText(1, folder.get("folderType") or "")
            item.setText(2, folder.get("status") or "")
            item.setText(4, folder.get("path") or "")
            set_entity(item, {"type": "folder", "folder": folder})
            items_by_id[folder["id"]] = item

        for folder_id, tasks in tasks_by_folder.items():
            parent_item = items_by_id.get(folder_id)
            if parent_item is None:
                continue
            folder = folders_by_id.get(folder_id, {})
            for task in sorted(tasks, key=lambda t: t.get("name") or ""):
                item = QtWidgets.QTreeWidgetItem(parent_item)
                item.setText(0, task.get("name") or "")
                item.setText(1, task.get("taskType") or "")
                item.setText(2, task.get("status") or "")
                item.setText(3, ", ".join(task.get("assignees") or []))
                item.setText(4, "task")
                set_entity(
                    item, {"type": "task", "task": task, "folder": folder}
                )

        self.tree.expandAll()

    def _folder_in_scope(self, folder, folders_by_id, visible):
        """Keep a folder when it or any of its descendants is visible."""
        if visible(folder):
            return True
        folder_path = folder.get("path") or ""
        if not folder_path:
            return False
        prefix = folder_path.rstrip("/") + "/"
        for other in self._folders:
            other_path = other.get("path") or ""
            if other_path.startswith(prefix) and visible(other):
                return True
        return False

    def _matches_search(self, text, source, folder=None, task=None):
        if not text:
            return True
        kind, field = SEARCH_SOURCES.get(source, ("folder", "name"))
        entity = folder if kind == "folder" else task
        if entity is None:
            # A folder is never excluded by a task-based search on its own;
            # the tree keeps it when one of its tasks matched.
            return False
        value = entity.get(field)
        if isinstance(value, (list, tuple)):
            value = ", ".join(value)
        return text in str(value or "").lower()

    def selected_tasks(self):
        """The folder+task pairs Add Container should build.

        A selected task is taken as it is. A selected folder stands for
        everything below it, so picking a sequence adds every shot and task
        under it - but only the ones the template has something to say about,
        which is decided later, once AYON has been asked.

        Returns a list of (folder_entity, task_entity, expanded) triples, where
        ``expanded`` marks the pairs that came from a folder rather than from a
        deliberate task selection.
        """
        direct = []
        expanded = []
        if self.tree is None:
            return []

        for item in self.tree.selectedItems():
            entity = get_entity(item)
            if not entity:
                continue
            if entity.get("type") == "task":
                direct.append((entity["folder"], entity["task"]))
            else:
                expanded.extend(self._tasks_below(item))

        # Only the tasks the tree is actually showing are collected, so the
        # Task Filter and the search box narrow the expansion as well.
        seen = set()
        result = []
        for pairs, is_expanded in ((direct, False), (expanded, True)):
            for folder, task in pairs:
                key = (folder.get("id"), task.get("name"))
                if key in seen:
                    continue
                seen.add(key)
                result.append((folder, task, is_expanded))
        return result

    def _tasks_below(self, item):
        """Every task item underneath a folder item, at any depth."""
        found = []
        for index in range(item.childCount()):
            child = item.child(index)
            entity = get_entity(child)
            if entity and entity.get("type") == "task":
                found.append((entity["folder"], entity["task"]))
            else:
                found.extend(self._tasks_below(child))
        return found

    # -- products ----------------------------------------------------------

    def populate_products(self):
        if self.products_table is None:
            return
        project = self.project_name()
        folder = None
        if self.tree is not None:
            for item in reversed(self.tree.selectedItems()):
                entity = get_entity(item)
                if entity:
                    folder = entity.get("folder")
                    break
        if not folder:
            fill_table(self.products_table, [])
            fill_table(self.repres_table, [])
            return

        with busy():
            self._products = ayonio.get_products(project, [folder["id"]])
            self._versions_by_product = {}
            versions = ayonio.get_versions(
                project, [p["id"] for p in self._products]
            )
            for version in versions:
                self._versions_by_product.setdefault(
                    version["productId"], []
                ).append(version)

        product_filter_on = self.widget("ayon_product").isChecked()
        base_types = [
            word.lower()
            for word in split_words(self.widget("ayon_product_text").text())
        ]

        rows = []
        entities = []
        for product in sorted(self._products, key=lambda p: p.get("name") or ""):
            base_type = ayonio.product_base_type(product)
            if product_filter_on and base_types:
                if base_type.lower() not in base_types:
                    continue
            versions = self._versions_by_product.get(product["id"], [])
            last = max(
                (v.get("version") or 0 for v in versions), default=0
            )
            rows.append([
                product.get("name") or "",
                base_type,
                ayonio.product_variant(product),
                str(last) if last else "",
                product.get("status") or "",
            ])
            entities.append(product)

        fill_table(self.products_table, rows, entities)
        self.populate_representations()

    # -- representations ---------------------------------------------------

    def populate_representations(self):
        if self.repres_table is None:
            return
        project = self.project_name()
        selected = selected_table_rows(self.products_table)
        if selected:
            products = [
                table_entity(self.products_table, row) for row in selected
            ]
        else:
            products = list(self._products)
        products = [p for p in products if p]
        if not products:
            fill_table(self.repres_table, [])
            return

        latest_only = self.widget("ayon_repres_latest").isChecked()
        products_by_id = {p["id"]: p for p in products}

        version_entities = []
        for product_id in products_by_id:
            versions = self._versions_by_product.get(product_id, [])
            published = [v for v in versions if (v.get("version") or 0) >= 0]
            if latest_only and published:
                published = [max(published, key=lambda v: v["version"])]
            version_entities.extend(published)

        if not version_entities:
            fill_table(self.repres_table, [])
            return

        with busy():
            repres = ayonio.get_representations(
                project, [v["id"] for v in version_entities]
            )
        versions_by_id = {v["id"]: v for v in version_entities}

        rows = []
        entities = []
        for repre in repres:
            version = versions_by_id.get(repre.get("versionId"))
            if version is None:
                continue
            product = products_by_id.get(version["productId"], {})
            rows.append([
                repre.get("name") or "",
                product.get("name") or "",
                str(version.get("version") or ""),
                repre.get("status") or "",
            ])
            entities.append({
                "representation": repre,
                "version": version,
                "product": product,
            })

        fill_table(self.repres_table, rows, entities)

    # -- actions -----------------------------------------------------------

    def add_containers(self):
        """Add one container per selected folder + task."""
        pairs = self.selected_tasks()
        if not pairs:
            self.report([
                "Select one or more tasks in the AYON tree, or a folder to "
                "add everything below it."
            ])
            return

        template = self.panel.template()
        if not template.loaders and not template.node_text.strip():
            self.report([
                "The Template tab is empty - there is no recipe to build a "
                "container from."
            ])
            return

        project = self.project_name()
        task_names = self.task_names_by_id()
        cache = {}  # shared across every folder of this one press
        messages = []
        created = 0
        no_match = 0

        with busy():
            for folder, task, expanded in pairs:
                # A folder was a broad gesture, so shots the template says
                # nothing about are quietly passed over; a task the supervisor
                # picked by hand is always attempted, and reports why if it
                # comes back empty.
                if expanded and template.loaders and not templates.any_row_resolves(
                    project, folder["id"], template, task_names, cache
                ):
                    no_match += 1
                    continue

                # One bad shot must not abandon the rest of the batch.
                try:
                    result = containers.create_container(
                        project, folder, task, template, task_names, cache
                    )
                except Exception as exc:
                    log.exception("Could not build a container")
                    messages.append("{}: {}".format(
                        containers.container_label(
                            folder.get("path") or "", task.get("name") or ""
                        ),
                        exc,
                    ))
                    continue
                messages.extend(result.messages)
                if result.created:
                    created += 1

        # Refresh before reporting: the report is modal, and the Inventory
        # should already show the new containers once it is dismissed.
        if created:
            self.panel.refresh_inventory()

        summary = "Created {} of {} container(s).".format(created, len(pairs))
        if no_match:
            summary += " {} skipped, no template row matched.".format(no_match)
        messages.insert(0, summary)
        self.report(messages)

    def load_representation(self):
        """Load the hand picked representation with the default loader."""
        rows = selected_table_rows(self.repres_table)
        if not rows:
            self.report(["Select a representation to load."])
            return

        messages = []
        with busy():
            for row in rows:
                entity = table_entity(self.repres_table, row)
                if not entity:
                    continue
                repre = entity["representation"]
                product = entity["product"]
                base_type = ayonio.product_base_type(product)
                loader = self.settings.default_loader_for(base_type)
                if not loader:
                    messages.append(
                        "No default loader for base type '{}' - set one in "
                        "Preferences.".format(base_type or "?")
                    )
                    continue
                try:
                    ayonio.load_representation(repre, loader)
                except Exception as exc:
                    messages.append(
                        "{} / {}: {}".format(
                            product.get("name"), repre.get("name"), exc
                        )
                    )
        if not messages:
            messages = ["Loaded {} representation(s).".format(len(rows))]
        self.report(messages)
