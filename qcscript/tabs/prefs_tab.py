"""Preferences tab - default loader per product base type."""

import logging

from ..compat import QtWidgets
from .. import ayonio
from .base import (
    TabController,
    fill_table,
    selected_table_rows,
    set_combo_items,
    table_row_values,
)

log = logging.getLogger(__name__)


class PrefsTab(TabController):

    def setup(self):
        self.table = self.widget("prefs_default_loaders")

        self.widget("prefs_default_loaders_add").clicked.connect(self.add_row)
        self.widget("prefs_default_loaders_delete").clicked.connect(
            self.delete_rows
        )
        if self.table is not None:
            self.table.setSelectionBehavior(
                QtWidgets.QAbstractItemView.SelectRows
            )
            self.table.itemChanged.connect(self._on_changed)

        self._loading = False
        labels = sorted(ayonio.get_loaders_by_label())
        if labels:
            set_combo_items(self.widget("prefs_loader"), labels)
        self.load_from_settings()

    # -- persistence --------------------------------------------------------

    def load_from_settings(self):
        mapping = self.settings.default_loaders()
        rows = [[base_type, loader] for base_type, loader in sorted(
            mapping.items()
        )]
        self._loading = True
        try:
            fill_table(self.table, rows)
        finally:
            self._loading = False

    def save_to_settings(self):
        if self._loading or self.table is None:
            return
        mapping = {}
        for row in range(self.table.rowCount()):
            base_type, loader = (table_row_values(self.table, row) + ["", ""])[:2]
            if base_type.strip() and loader.strip():
                mapping[base_type.strip()] = loader.strip()
        self.settings.set_default_loaders(mapping)

    def _on_changed(self, *args):
        self.save_to_settings()

    # -- rows ---------------------------------------------------------------

    def add_row(self):
        base_type = self.widget("prefs_product_base_type").currentText()
        loader = self.widget("prefs_loader").currentText()
        if not base_type or not loader:
            self.report(["Pick a product base type and a loader."])
            return

        mapping = self.settings.default_loaders()
        mapping[base_type] = loader
        self.settings.set_default_loaders(mapping)
        self.load_from_settings()

    def delete_rows(self):
        if self.table is None:
            return
        selected = set(selected_table_rows(self.table))
        if not selected:
            self.report(["Select the rows to delete."])
            return
        mapping = {}
        for row in range(self.table.rowCount()):
            if row in selected:
                continue
            base_type, loader = (table_row_values(self.table, row) + ["", ""])[:2]
            if base_type.strip() and loader.strip():
                mapping[base_type.strip()] = loader.strip()
        self.settings.set_default_loaders(mapping)
        self.load_from_settings()
