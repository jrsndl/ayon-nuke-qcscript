"""Shared plumbing for the tab controllers."""

import contextlib
import logging

from ..compat import QtCore, QtWidgets

log = logging.getLogger(__name__)

# Role used to hang AYON entities off tree/table items.
ENTITY_ROLE = QtCore.Qt.UserRole + 1


class TabController(object):
    """Wires one tab of the loaded .ui to the tool's logic."""

    def __init__(self, panel):
        self.panel = panel
        self.ui = panel.ui
        self.settings = panel.settings
        self.setup()

    def setup(self):
        """Connect signals and fill initial state."""

    def refresh(self):
        """Called when the panel wants the tab to re-read the scene."""

    def widget(self, name):
        found = self.ui.findChild(QtCore.QObject, name)
        if found is None:
            log.warning("Widget '%s' is missing from gui_layout.ui", name)
        return found

    # -- feedback ----------------------------------------------------------

    def report(self, messages, title="QC Script Helper"):
        self.panel.report(messages, title=title)


# ---------------------------------------------------------------------------
# widget helpers
# ---------------------------------------------------------------------------

@contextlib.contextmanager
def busy():
    """Override cursor for the duration of a blocking AYON query."""
    app = QtWidgets.QApplication.instance()
    if app is not None:
        app.setOverrideCursor(QtCore.Qt.WaitCursor)
    try:
        yield
    finally:
        if app is not None:
            app.restoreOverrideCursor()


def set_entity(item, entity, column=0):
    item.setData(column, ENTITY_ROLE, entity)


def get_entity(item, column=0):
    if item is None:
        return None
    return item.data(column, ENTITY_ROLE)


def clear_tree(tree):
    if tree is not None:
        tree.clear()


def fill_table(table, rows, entities=None):
    """Replace the contents of a QTableWidget.

    ``rows`` is a list of lists of strings; ``entities`` an optional parallel
    list stored on the first column of each row.
    """
    if table is None:
        return
    table.setRowCount(0)
    table.setRowCount(len(rows))
    for row_index, values in enumerate(rows):
        for column, value in enumerate(values):
            if column >= table.columnCount():
                break
            item = QtWidgets.QTableWidgetItem(str(value))
            if column == 0 and entities:
                item.setData(ENTITY_ROLE, entities[row_index])
            table.setItem(row_index, column, item)


def table_entity(table, row):
    if table is None:
        return None
    item = table.item(row, 0)
    if item is None:
        return None
    return item.data(ENTITY_ROLE)


def selected_table_rows(table):
    if table is None:
        return []
    rows = {index.row() for index in table.selectedIndexes()}
    return sorted(rows)


def table_row_values(table, row):
    values = []
    for column in range(table.columnCount()):
        item = table.item(row, column)
        values.append(item.text() if item is not None else "")
    return values


def set_combo_items(combo, items, keep_current=True):
    """Replace combo box contents, keeping the current text when possible."""
    if combo is None:
        return
    current = combo.currentText() if keep_current else ""
    combo.blockSignals(True)
    combo.clear()
    combo.addItems(items)
    if current:
        index = combo.findText(current)
        if index >= 0:
            combo.setCurrentIndex(index)
    combo.blockSignals(False)


def split_words(text):
    """Split a space separated filter field into a list of words."""
    return [word for word in (text or "").replace(",", " ").split() if word]
