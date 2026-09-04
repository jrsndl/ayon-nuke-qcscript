"""Qt binding shim.

Nuke 16+ ships PySide6, Nuke 15.x ships PySide2. Everything in this package
imports Qt through this module so the rest of the code never has to care.
"""

QT_BINDING = None

try:  # Nuke 16 / 17
    from PySide6 import QtCore, QtGui, QtWidgets  # noqa: F401
    from PySide6.QtUiTools import QUiLoader  # noqa: F401

    QT_BINDING = "PySide6"
except ImportError:  # Nuke 15.2
    from PySide2 import QtCore, QtGui, QtWidgets  # noqa: F401
    from PySide2.QtUiTools import QUiLoader  # noqa: F401

    QT_BINDING = "PySide2"


# QAction moved from QtWidgets to QtGui in Qt6.
QAction = getattr(QtGui, "QAction", None) or QtWidgets.QAction

# Enums are scoped in Qt6 but the unscoped aliases still resolve in PySide6,
# so `QtCore.Qt.UserRole` and friends are used directly elsewhere.


def exec_dialog(dialog):
    """Modal exec that works on both bindings."""
    runner = getattr(dialog, "exec", None) or dialog.exec_
    return runner()
