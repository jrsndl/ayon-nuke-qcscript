"""Template tab - the container recipe."""

import logging

from ..compat import QtWidgets
from .. import ayonio, templates
from .base import (
    TabController,
    fill_table,
    selected_table_rows,
    set_combo_items,
    table_row_values,
)

log = logging.getLogger(__name__)


class TemplateTab(TabController):

    def setup(self):
        self.table = self.widget("template_loader_spreadsheet")
        self.node_text = self.widget("template_template_nodes")

        self.widget("template_add_row").clicked.connect(self.add_row)
        self.widget("template_delete_row").clicked.connect(self.delete_rows)

        if self.table is not None:
            self.table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            self.table.itemChanged.connect(self._on_table_changed)
        if self.node_text is not None:
            self.node_text.textChanged.connect(self._on_nodes_changed)
            self.node_text.setPlaceholderText(
                "Paste Nuke nodes here (Ctrl+C in Nuke, Ctrl+V here).\n"
                "Add a Dot node labelled with a loader id, for example 001, "
                "where the loaded nodes should end up."
            )

        self._loading = False
        self._refresh_loader_combos()
        self.load_from_settings()

    # -- combos -------------------------------------------------------------

    def _refresh_loader_combos(self):
        """Replace the placeholder loader list with what AYON really offers."""
        labels = sorted(ayonio.get_loaders_by_label())
        if labels:
            set_combo_items(self.widget("template_loader"), labels)

    # -- persistence --------------------------------------------------------

    def template(self):
        """Current template, read straight from the widgets."""
        rows = []
        if self.table is not None:
            for row in range(self.table.rowCount()):
                values = table_row_values(self.table, row)
                if not any(value.strip() for value in values):
                    continue
                rows.append(templates.TemplatedLoader.from_row(values))
        node_text = self.node_text.toPlainText() if self.node_text else ""
        return templates.Template(node_text=node_text, loaders=rows)

    def load_from_settings(self):
        template = templates.Template.from_data(self.settings.get("template"))
        self._loading = True
        try:
            fill_table(
                self.table, [loader.to_row() for loader in template.loaders]
            )
            if self.node_text is not None:
                self.node_text.setPlainText(template.node_text)
        finally:
            self._loading = False

    def save_to_settings(self):
        if self._loading:
            return
        self.settings.set("template", self.template().to_data())

    def _on_table_changed(self, *args):
        self.save_to_settings()

    def _on_nodes_changed(self):
        self.save_to_settings()

    # -- rows ---------------------------------------------------------------

    def add_row(self):
        """Add a templated loader from the fields above the spreadsheet."""
        if self.table is None:
            return
        template = self.template()
        loader = templates.TemplatedLoader(
            loader_id=template.next_loader_id(),
            product_base_type=self.widget(
                "template_product_base_type"
            ).currentText(),
            representation=self.widget("template_representation").text(),
            loader=self.widget("template_loader").currentText(),
            version_hint=self.widget("template_version_hint_text").text(),
            version_lock=self.widget("template_version_lock").isChecked(),
            loader_args=self.widget("template_loader_args").text(),
            task_regex=self.widget("template_task_regex").text(),
            variant_regex=self.widget("template_variant_regex").text(),
            product_regex=self.widget("template_product_regex").text(),
        )

        rows = [
            table_row_values(self.table, row)
            for row in range(self.table.rowCount())
        ]
        rows = [row for row in rows if any(value.strip() for value in row)]
        rows.append(loader.to_row())

        self._loading = True
        try:
            fill_table(self.table, rows)
        finally:
            self._loading = False
        self.save_to_settings()

    def delete_rows(self):
        if self.table is None:
            return
        selected = set(selected_table_rows(self.table))
        if not selected:
            self.report(["Select the rows to delete."])
            return
        rows = [
            table_row_values(self.table, row)
            for row in range(self.table.rowCount())
            if row not in selected
        ]
        self._loading = True
        try:
            fill_table(self.table, rows)
        finally:
            self._loading = False
        self.save_to_settings()

    # -- helpers for the rest of the tool -----------------------------------

    def placeholder_report(self):
        """Which loader ids have no placeholder Dot in the template nodes."""
        template = self.template()
        if not template.node_text.strip():
            return []
        missing = []
        for loader in template.loaders:
            token = loader.loader_id
            if token and token not in template.node_text:
                missing.append(token)
        return missing
