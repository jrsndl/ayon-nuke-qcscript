"""The QC Script Helper dockable Nuke panel."""

import logging

from .compat import QtWidgets, exec_dialog
from .resources import UI_FILE
from .settings import Settings
from .uiloader import load_ui
from .tabs import AyonTab, ContainerTab, InventoryTab, PrefsTab, TemplateTab

log = logging.getLogger(__name__)

PANEL_NAME = "QC Script Helper"
PANEL_ID = "com.blindcatvfx.QCScriptHelper"
PANEL_CLASS = "qcscript.panel.QCScriptPanel"


class QCScriptPanel(QtWidgets.QWidget):
    """Loads gui_layout.ui and hands each tab to its controller."""

    def __init__(self, parent=None):
        super(QCScriptPanel, self).__init__(parent)
        self.setObjectName("QCScriptHelperPanel")
        self.setWindowTitle(PANEL_NAME)

        self.settings = Settings()
        self.ui = load_ui(UI_FILE)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.ui)

        # Template and preferences first - the AYON tab reads from both.
        self.template_tab = TemplateTab(self)
        self.prefs_tab = PrefsTab(self)
        self.ayon_tab = AyonTab(self)
        self.inventory_tab = InventoryTab(self)
        self.container_tab = ContainerTab(self)

        # QUiLoader does not honour the designed current index reliably
        tabs = self.ui.findChild(QtWidgets.QTabWidget, "tabWidget")
        if tabs is not None:
            tabs.setCurrentIndex(0)

    # -- services for the tabs ---------------------------------------------

    def template(self):
        return self.template_tab.template()

    def refresh_inventory(self):
        try:
            self.inventory_tab.fetch_nuke()
        except Exception:
            log.warning("Could not refresh the inventory", exc_info=True)

    def report(self, messages, title=PANEL_NAME):
        """Show a short summary, with the details behind a button."""
        if isinstance(messages, str):
            messages = [messages]
        messages = [str(message) for message in messages if message]
        if not messages:
            return
        for message in messages:
            log.info("%s", message)

        box = QtWidgets.QMessageBox(self)
        box.setWindowTitle(title)
        box.setIcon(QtWidgets.QMessageBox.Information)
        box.setText(messages[0])
        if len(messages) > 1:
            box.setDetailedText("\n".join(messages[1:]))
        exec_dialog(box)


# ---------------------------------------------------------------------------
# Nuke integration
# ---------------------------------------------------------------------------

def _register_panel(create=False):
    """Register the widget with Nuke.

    ``registerWidgetAsPanel`` only returns a panel object when ``create`` is
    True; with create=False it registers the Pane menu entry and returns None.
    """
    from nukescripts import panels

    return panels.registerWidgetAsPanel(
        PANEL_CLASS, PANEL_NAME, PANEL_ID, create=create
    )


def show_panel():
    """Open the panel, docked next to the properties pane when possible."""
    import nuke
    from nukescripts import panels

    panel = _register_panel(create=True)
    if panel is None:  # should not happen, but never crash the menu command
        return panels.restorePanel(PANEL_ID)

    # addToPane falls back to the current pane, then to a floating window,
    # so a missing Properties pane is not a problem.
    return panel.addToPane(nuke.getPaneFor("Properties.1"))


def install():
    """Register the panel and add the Nuke menu entry."""
    import nuke

    _register_panel()

    menu = nuke.menu("Nuke")
    entry = menu.findItem(PANEL_NAME) or menu.addMenu(PANEL_NAME)
    entry.addCommand(
        "Open {}".format(PANEL_NAME),
        "import qcscript; qcscript.show_panel()",
    )
    log.info("QC Script Helper installed")
