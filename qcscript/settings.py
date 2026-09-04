"""Persistent preferences and template storage.

Everything the supervisor configures in the Template and Preferences tabs is
autosaved to a single JSON file, because the .ui has no explicit save button.
"""

import json
import logging
import os

from .resources import user_config_dir

log = logging.getLogger(__name__)

SETTINGS_FILE_NAME = "settings.json"

DEFAULTS = {
    # [{"product_base_type": "render", "loader": "Load Clip"}, ...]
    "default_loaders": [],
    # see templates.Template.to_data()
    "template": {},
    # remembered widget state of the AYON and Inventory tabs
    "ui_state": {},
}


def settings_path():
    return os.path.join(user_config_dir(), SETTINGS_FILE_NAME)


def load():
    path = settings_path()
    data = dict(DEFAULTS)
    if not os.path.isfile(path):
        return data
    try:
        with open(path, "r") as stream:
            stored = json.load(stream)
        if isinstance(stored, dict):
            data.update(stored)
    except Exception:
        log.warning("Could not read settings from %s", path, exc_info=True)
    return data


def save(data):
    path = settings_path()
    try:
        with open(path, "w") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
    except Exception:
        log.warning("Could not write settings to %s", path, exc_info=True)


class Settings(object):
    """In-memory settings that write through on every change."""

    def __init__(self):
        self._data = load()

    def get(self, key, default=None):
        if default is None:
            default = DEFAULTS.get(key)
        return self._data.get(key, default)

    def set(self, key, value):
        self._data[key] = value
        save(self._data)

    # -- default loaders ---------------------------------------------------

    def default_loaders(self):
        """Mapping product base type -> loader label."""
        result = {}
        for row in self.get("default_loaders") or []:
            base_type = row.get("product_base_type")
            loader = row.get("loader")
            if base_type and loader:
                result[base_type] = loader
        return result

    def set_default_loaders(self, mapping):
        rows = [
            {"product_base_type": base_type, "loader": loader}
            for base_type, loader in sorted(mapping.items())
        ]
        self.set("default_loaders", rows)

    def default_loader_for(self, product_base_type):
        return self.default_loaders().get(product_base_type, "")
