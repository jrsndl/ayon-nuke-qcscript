"""QC Script Helper - AYON driven QC scripts for Foundry Nuke.

Imports of Qt and Nuke are deferred so this package can be imported in a
terminal session without pulling a GUI in.
"""

__version__ = "0.1.0"

__all__ = ["install", "show_panel", "__version__"]


def install():
    """Register the dockable panel and add the Nuke menu entry."""
    from .panel import install as _install

    return _install()


def show_panel():
    """Open the QC Script Helper panel."""
    from .panel import show_panel as _show_panel

    return _show_panel()
