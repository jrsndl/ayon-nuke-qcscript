"""Container tab - properties of the one container selected in the node graph."""

import logging
import os
import webbrowser

from ..compat import QtWidgets
from .. import ayonio, containers, nukeio
from .base import TabController, busy, get_entity, set_entity
from .inventory_tab import age_hours

log = logging.getLogger(__name__)

# container_tree column order
COL_NAME = 0
COL_REPRE = 1
COL_VERSION = 2
COL_STATUS = 3
COL_AUTHOR = 4
COL_AGE = 5
COL_TAGS = 6


class ContainerTab(TabController):

    def setup(self):
        self.tree = self.widget("container_tree")
        self.container = None
        self._rows = []

        self.widget("container_get_selected").clicked.connect(
            self.get_selected
        )
        self.widget("container_set_range").clicked.connect(self.set_range)
        self.widget("container_set_format").clicked.connect(self.set_format)
        self.widget("container_setversion").clicked.connect(self.set_version)
        self.widget("container_ayon_activity").clicked.connect(
            self.open_ayon_activity
        )
        self.widget("container_ftrack_notes").clicked.connect(
            self.open_ftrack_notes
        )
        self.widget("container_set_range_auto").toggled.connect(
            self._auto_fill_range
        )
        self.widget("container_set_format_auto").toggled.connect(
            self._auto_fill_format
        )
        self.widget("container_hide_locked").toggled.connect(self.populate)
        self.widget("container_show_last").valueChanged.connect(self.populate)

        if self.tree is not None:
            self.tree.clear()
            self.tree.setSelectionMode(
                QtWidgets.QAbstractItemView.SingleSelection
            )
        self._clear_labels()

    def _clear_labels(self):
        for name in (
            "container_folder_path", "container_name", "container_assignee"
        ):
            widget = self.widget(name)
            if widget is not None:
                widget.setText("")

    # -- reading the selection ---------------------------------------------

    def get_selected(self):
        container, error = containers.container_from_selection()
        if error:
            self.container = None
            self._rows = []
            self._clear_labels()
            if self.tree is not None:
                self.tree.clear()
            self.report([error])
            return

        self.container = container
        self.widget("container_folder_path").setText(container.folder_path)
        self.widget("container_name").setText(container.label)
        self.widget("container_assignee").setText(
            ", ".join(container.assignees)
        )

        self._fetch_rows()
        self.populate()
        self._auto_fill_range()
        self._auto_fill_format()

    def _fetch_rows(self):
        """Version history of every AYON container inside this QC container."""
        self._rows = []
        if self.container is None:
            return
        project = self.container.project_name or ayonio.current_project_name()

        try:
            items = self.container.ayon_containers()
        except Exception:
            log.warning("Could not read AYON containers", exc_info=True)
            items = []

        if not items or not ayonio.is_available():
            self._rows = [
                {"ayon": item, "product": None, "current": None, "versions": []}
                for item in items
            ]
            return

        with busy():
            repres = ayonio.get_representations_by_ids(
                project, [item.get("representation") for item in items]
            )
            repres_by_id = {r["id"]: r for r in repres}
            versions = ayonio.get_versions_by_ids(
                project, {r["versionId"] for r in repres}
            )
            versions_by_id = {v["id"]: v for v in versions}
            product_ids = {v["productId"] for v in versions}
            products_by_id = {
                p["id"]: p
                for p in ayonio.get_products_by_ids(project, product_ids)
            }
            all_versions = {}
            for version in ayonio.get_versions(project, product_ids):
                all_versions.setdefault(
                    version["productId"], []
                ).append(version)

        for item in items:
            repre = repres_by_id.get(item.get("representation"))
            version = versions_by_id.get(repre["versionId"]) if repre else None
            product = (
                products_by_id.get(version["productId"]) if version else None
            )
            history = sorted(
                all_versions.get(version["productId"], []) if version else [],
                key=lambda v: v.get("version") or 0,
                reverse=True,
            )
            self._rows.append({
                "ayon": item,
                "repre": repre,
                "product": product,
                "current": version,
                "versions": [v for v in history if (v.get("version") or 0) >= 0],
            })

    # -- tree ---------------------------------------------------------------

    def populate(self):
        if self.tree is None:
            return
        self.tree.clear()
        hide_locked = self.widget("container_hide_locked").isChecked()
        show_last = self.widget("container_show_last").value() or 10

        for row in self._rows:
            locked = row["ayon"].get("qcs_version_lock")
            if hide_locked and locked:
                continue
            product = row.get("product") or {}
            repre = row.get("repre") or {}
            current = row.get("current") or {}

            parent = QtWidgets.QTreeWidgetItem(self.tree)
            parent.setText(
                COL_NAME, product.get("name") or row["ayon"].get("name", "")
            )
            parent.setText(COL_REPRE, repre.get("name", ""))
            parent.setText(
                COL_VERSION, str(current.get("version", "")) if current else ""
            )
            if locked:
                parent.setText(COL_TAGS, "version locked")
            set_entity(parent, {"type": "product", "row": row})

            for version in row.get("versions", [])[:show_last]:
                item = QtWidgets.QTreeWidgetItem(parent)
                item.setText(COL_VERSION, str(version.get("version", "")))
                item.setText(COL_STATUS, version.get("status", ""))
                item.setText(COL_AUTHOR, version.get("author", ""))
                age = age_hours(version.get("createdAt"))
                item.setText(COL_AGE, "" if age is None else "{:.1f}".format(age))
                item.setText(COL_TAGS, ", ".join(version.get("tags") or []))
                set_entity(
                    item, {"type": "version", "row": row, "version": version}
                )
        self.tree.expandAll()

    def set_version(self):
        if self.tree is None or self.container is None:
            self.report(["Fetch a container first."])
            return
        items = self.tree.selectedItems()
        entity = get_entity(items[0]) if items else None
        if not entity or entity["type"] != "version":
            self.report(["Select a version row in the list."])
            return

        row = entity["row"]
        if row["ayon"].get("qcs_version_lock"):
            self.report(["This item is version locked."])
            return

        number = entity["version"].get("version")
        try:
            with busy():
                ayonio.set_container_version(row["ayon"], number)
        except Exception as exc:
            self.report(["Could not set version {}: {}".format(number, exc)])
            return

        self._fetch_rows()
        self.populate()
        self.panel.refresh_inventory()

    # -- range and format ---------------------------------------------------

    def _folder_attributes(self):
        if self.container is None:
            return {}
        return containers.folder_attributes(
            self.container.project_name or ayonio.current_project_name(),
            self.container.folder_id,
        )

    def _auto_fill_range(self):
        if not self.widget("container_set_range_auto").isChecked():
            return
        attrib = self._folder_attributes()
        if not attrib:
            return
        start = attrib.get("frameStart")
        end = attrib.get("frameEnd")
        if start is None or end is None:
            return
        start = int(start) - int(attrib.get("handleStart") or 0)
        end = int(end) + int(attrib.get("handleEnd") or 0)
        if self.widget("checkBox").isChecked():  # Add Slate
            start -= 1
        self.widget("container_start").setValue(start)
        self.widget("container_end").setValue(end)

    def _auto_fill_format(self):
        if not self.widget("container_set_format_auto").isChecked():
            return
        attrib = self._folder_attributes()
        if not attrib:
            return
        width = attrib.get("resolutionWidth")
        height = attrib.get("resolutionHeight")
        if not width or not height:
            return
        self.widget("container_width").setValue(int(width))
        self.widget("container_height").setValue(int(height))
        self.widget("container_pixel_aspect").setValue(
            float(attrib.get("pixelAspect") or 1.0)
        )

    def set_range(self):
        self._auto_fill_range()
        start = self.widget("container_start").value()
        end = self.widget("container_end").value()
        if end < start:
            self.report(["End frame is before start frame."])
            return
        nukeio.set_root_range(start, end)
        self.report(["Frame range set to {} - {}.".format(start, end)])

    def set_format(self):
        self._auto_fill_format()
        width = self.widget("container_width").value()
        height = self.widget("container_height").value()
        pixel_aspect = self.widget("container_pixel_aspect").value()
        if not width or not height:
            self.report(["Width and height must be set."])
            return
        name = "QCS_{}x{}".format(width, height)
        nukeio.set_root_format(width, height, pixel_aspect, name)
        self.report([
            "Format set to {} x {} @ {}.".format(width, height, pixel_aspect)
        ])

    # -- links --------------------------------------------------------------

    def open_ayon_activity(self):
        if self.container is None:
            self.report(["Fetch a container first."])
            return
        url = ayonio.folder_url(
            self.container.project_name,
            self.container.folder_id,
            self.container.task_id,
        )
        if not url:
            self.report(["No AYON server url available."])
            return
        webbrowser.open(url)

    def open_ftrack_notes(self):
        if self.container is None:
            self.report(["Fetch a container first."])
            return
        server = os.environ.get("FTRACK_SERVER", "").rstrip("/")
        if not server:
            self.report([
                "FTRACK_SERVER is not set - launch Nuke through AYON with the "
                "ftrack addon enabled."
            ])
            return

        project = self.container.project_name
        folder = ayonio.get_folder_by_id(project, self.container.folder_id) or {}
        ftrack_id = (folder.get("data") or {}).get("ftrackId") or ""
        if not ftrack_id:
            self.report(["This folder has no ftrack id in AYON."])
            return
        webbrowser.open("{}/#slideEntityId={}&view=tasks".format(
            server, ftrack_id
        ))
