"""Locations of the files that ship with the tool."""

import os

PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(PACKAGE_DIR)

GUI_LAYOUT_DIR = os.path.join(ROOT_DIR, "gui_layout")
UI_FILE = os.path.join(GUI_LAYOUT_DIR, "gui_layout.ui")


def user_config_dir():
    """Directory holding preferences and templates for this user."""
    base = os.environ.get("QCSCRIPT_CONFIG_DIR")
    if not base:
        base = os.path.join(os.path.expanduser("~"), ".ayon-nuke-qcscript")
    if not os.path.isdir(base):
        os.makedirs(base)
    return base
