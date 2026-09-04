"""Runtime loading of gui_layout.ui.

The .ui file is the design source of truth, so it is loaded at runtime rather
than compiled to Python - the panel can never drift from what Qt Designer shows.
"""

from .compat import QtCore, QUiLoader


def load_ui(path, parent=None):
    """Load a Qt Designer file and return its root widget."""
    loader = QUiLoader()
    ui_file = QtCore.QFile(path)
    if not ui_file.open(QtCore.QFile.ReadOnly):
        raise IOError("Could not open UI file: {}".format(path))
    try:
        widget = loader.load(ui_file, parent)
    finally:
        ui_file.close()

    if widget is None:
        raise RuntimeError(
            "Could not build UI from {}: {}".format(path, loader.errorString())
        )
    return widget
