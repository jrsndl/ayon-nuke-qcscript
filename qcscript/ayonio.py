"""Thin, defensive wrapper around ayon_api / ayon_core.

Nuke can be launched without AYON (plain executable), and the panel must still
open in that case - every accessor here degrades to an empty result and
``availability_error()`` explains why.
"""

import logging
import re

log = logging.getLogger(__name__)

try:
    import ayon_api

    _AYON_API_ERROR = None
except Exception as exc:  # pragma: no cover - depends on host environment
    ayon_api = None
    _AYON_API_ERROR = "ayon_api is not importable: {}".format(exc)

try:
    from ayon_core.pipeline import (
        discover_loader_plugins,
        get_current_project_name,
        get_current_folder_path,
        get_current_task_name,
        load_container,
        loaders_from_representation,
        update_container,
    )

    _AYON_CORE_ERROR = None
except Exception as exc:  # pragma: no cover - depends on host environment
    discover_loader_plugins = None
    get_current_project_name = None
    get_current_folder_path = None
    get_current_task_name = None
    load_container = None
    loaders_from_representation = None
    update_container = None
    _AYON_CORE_ERROR = "ayon_core is not importable: {}".format(exc)


def is_available():
    return ayon_api is not None and discover_loader_plugins is not None


def availability_error():
    """Human readable reason why AYON cannot be used, or None."""
    problems = [p for p in (_AYON_API_ERROR, _AYON_CORE_ERROR) if p]
    if not problems:
        return None
    return " / ".join(problems)


# ---------------------------------------------------------------------------
# context
# ---------------------------------------------------------------------------

def current_project_name():
    if get_current_project_name is None:
        return ""
    try:
        return get_current_project_name() or ""
    except Exception:
        log.warning("Could not read current AYON project", exc_info=True)
        return ""


def current_folder_path():
    if get_current_folder_path is None:
        return ""
    try:
        return get_current_folder_path() or ""
    except Exception:
        return ""


def current_task_name():
    if get_current_task_name is None:
        return ""
    try:
        return get_current_task_name() or ""
    except Exception:
        return ""


def server_url():
    if ayon_api is None:
        return ""
    try:
        return ayon_api.get_base_url() or ""
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# entities
# ---------------------------------------------------------------------------

def _query(func_name, *args, **kwargs):
    """Call an ayon_api getter and always return a list."""
    if ayon_api is None:
        return []
    func = getattr(ayon_api, func_name, None)
    if func is None:
        log.warning("ayon_api has no '%s'", func_name)
        return []
    try:
        return list(func(*args, **kwargs))
    except Exception:
        log.warning("AYON query %s failed", func_name, exc_info=True)
        return []


def get_folders(project_name):
    return _query("get_folders", project_name)


def get_tasks(project_name, folder_ids=None):
    if folder_ids is None:
        return _query("get_tasks", project_name)
    folder_ids = list(folder_ids)
    if not folder_ids:
        return []
    return _query("get_tasks", project_name, folder_ids=folder_ids)


def get_products(project_name, folder_ids=None):
    if folder_ids is None:
        return _query("get_products", project_name)
    folder_ids = list(folder_ids)
    if not folder_ids:
        return []
    return _query("get_products", project_name, folder_ids=folder_ids)


def get_versions(project_name, product_ids):
    product_ids = list(product_ids)
    if not product_ids:
        return []
    return _query("get_versions", project_name, product_ids=product_ids)


def get_representations(project_name, version_ids):
    version_ids = list(version_ids)
    if not version_ids:
        return []
    return _query(
        "get_representations", project_name, version_ids=version_ids
    )


def get_representations_by_ids(project_name, repre_ids):
    repre_ids = [rid for rid in repre_ids if rid]
    if not repre_ids:
        return []
    return _query(
        "get_representations", project_name, representation_ids=repre_ids
    )


def get_versions_by_ids(project_name, version_ids):
    version_ids = [vid for vid in version_ids if vid]
    if not version_ids:
        return []
    return _query("get_versions", project_name, version_ids=version_ids)


def get_products_by_ids(project_name, product_ids):
    product_ids = [pid for pid in product_ids if pid]
    if not product_ids:
        return []
    return _query("get_products", project_name, product_ids=product_ids)


def get_representation_by_id(project_name, repre_id):
    if ayon_api is None or not repre_id:
        return None
    try:
        return ayon_api.get_representation_by_id(project_name, repre_id)
    except Exception:
        log.warning("Could not fetch representation %s", repre_id,
                    exc_info=True)
        return None


def get_version_by_id(project_name, version_id):
    if ayon_api is None or not version_id:
        return None
    try:
        return ayon_api.get_version_by_id(project_name, version_id)
    except Exception:
        return None


def get_product_by_id(project_name, product_id):
    if ayon_api is None or not product_id:
        return None
    try:
        return ayon_api.get_product_by_id(project_name, product_id)
    except Exception:
        return None


def get_folder_by_id(project_name, folder_id):
    if ayon_api is None or not folder_id:
        return None
    try:
        return ayon_api.get_folder_by_id(project_name, folder_id)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# entity helpers
# ---------------------------------------------------------------------------

def product_base_type(product_entity):
    """Base type of a product.

    ``productBaseType`` is the newer AYON field; older servers only have
    ``productType``.
    """
    if not product_entity:
        return ""
    return (
        product_entity.get("productBaseType")
        or product_entity.get("productType")
        or ""
    )


def product_variant(product_entity):
    """Best effort variant, i.e. the product name without its type prefix."""
    if not product_entity:
        return ""
    name = product_entity.get("name") or ""
    for key in ("productType", "productBaseType"):
        prefix = product_entity.get(key) or ""
        if prefix and name.lower().startswith(prefix.lower()):
            return name[len(prefix):]
    return name


def entity_status(entity):
    if not entity:
        return ""
    return entity.get("status") or ""


def entity_tags(entity):
    if not entity:
        return []
    return list(entity.get("tags") or [])


def folder_url(project_name, folder_id, task_id=None):
    """Web link to an entity in the AYON server UI."""
    base = server_url()
    if not base or not project_name or not folder_id:
        return ""
    url = (
        "{}/projects/{}/overview?project={}&type=task&id={}"
    ).format(
        base.rstrip("/"), project_name, project_name, task_id or folder_id
    )
    return url


# ---------------------------------------------------------------------------
# loaders
# ---------------------------------------------------------------------------

def get_loaders_by_label():
    """Mapping of loader label -> loader plugin class."""
    if discover_loader_plugins is None:
        return {}
    try:
        plugins = discover_loader_plugins()
    except Exception:
        log.warning("Could not discover loader plugins", exc_info=True)
        return {}

    result = {}
    for plugin in plugins:
        label = getattr(plugin, "label", None) or plugin.__name__
        result[label] = plugin
    return result


def compatible_loader_labels(repre_entity):
    """Loader labels that accept the given representation."""
    labels = []
    if loaders_from_representation is None or not repre_entity:
        return labels
    try:
        plugins = discover_loader_plugins()
        for plugin in loaders_from_representation(plugins, repre_entity):
            labels.append(getattr(plugin, "label", None) or plugin.__name__)
    except Exception:
        log.warning("Could not resolve compatible loaders", exc_info=True)
    return labels


def load_representation(repre_entity, loader_label, options=None, name=None):
    """Run an AYON loader on a representation.

    Returns whatever the loader returns; raises on failure so the caller can
    report which templated loader row went wrong.
    """
    if load_container is None:
        raise RuntimeError("ayon_core is not available, cannot load")

    loaders = get_loaders_by_label()
    plugin = loaders.get(loader_label)
    if plugin is None:
        raise RuntimeError(
            "Loader '{}' not found. Available: {}".format(
                loader_label, ", ".join(sorted(loaders)) or "none"
            )
        )
    return load_container(
        plugin, repre_entity, name=name, options=options or {}
    )


def set_container_version(container, version):
    """Switch an AYON container to a version number (-1 means latest)."""
    if update_container is None:
        raise RuntimeError("ayon_core is not available, cannot update")
    return update_container(container, version=version)


# ---------------------------------------------------------------------------
# small utilities
# ---------------------------------------------------------------------------

def regex_matches(pattern, value):
    """Empty pattern matches everything; invalid pattern matches nothing."""
    if not pattern:
        return True
    try:
        return re.search(pattern, value or "") is not None
    except re.error:
        log.warning("Invalid regex %r", pattern)
        return False
