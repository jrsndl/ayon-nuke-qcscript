"""The container recipe: template nodes plus a list of templated loaders.

A templated loader is one row of the Template tab spreadsheet. For every
container the tool resolves each row against AYON - product, then version,
then representation - and runs the loader on the result. The loaded nodes then
replace the placeholder Dot node carrying that row's id.
"""

import logging

from . import ayonio

log = logging.getLogger(__name__)

# Column order of ``template_loader_spreadsheet`` in gui_layout.ui.
COLUMNS = [
    "ID",
    "Base Type",
    "Repre",
    "Loader",
    "Version Hint",
    "Version Lock",
    "Loader Args",
    "Task Regex",
    "Variant Regex",
    "Product Regex",
]

VERSION_HINT_HELP = (
    "max / latest, min / first, hero, an absolute version number (7), "
    "or a relative step back from the latest (-2)"
)


class TemplatedLoader(object):
    """One row of the templated loader spreadsheet."""

    def __init__(
        self,
        loader_id="",
        product_base_type="",
        representation="",
        loader="",
        version_hint="max",
        version_lock=False,
        loader_args="",
        task_regex="",
        variant_regex="",
        product_regex="",
    ):
        self.loader_id = str(loader_id)
        self.product_base_type = product_base_type
        self.representation = representation
        self.loader = loader
        self.version_hint = version_hint or "max"
        self.version_lock = bool(version_lock)
        self.loader_args = loader_args
        self.task_regex = task_regex
        self.variant_regex = variant_regex
        self.product_regex = product_regex

    # -- serialisation -----------------------------------------------------

    def to_data(self):
        return {
            "loader_id": self.loader_id,
            "product_base_type": self.product_base_type,
            "representation": self.representation,
            "loader": self.loader,
            "version_hint": self.version_hint,
            "version_lock": self.version_lock,
            "loader_args": self.loader_args,
            "task_regex": self.task_regex,
            "variant_regex": self.variant_regex,
            "product_regex": self.product_regex,
        }

    @classmethod
    def from_data(cls, data):
        defaults = cls().to_data()
        return cls(**{
            key: (data or {}).get(key, default)
            for key, default in defaults.items()
        })

    def to_row(self):
        """Values in spreadsheet column order."""
        return [
            self.loader_id,
            self.product_base_type,
            self.representation,
            self.loader,
            self.version_hint,
            "yes" if self.version_lock else "",
            self.loader_args,
            self.task_regex,
            self.variant_regex,
            self.product_regex,
        ]

    @classmethod
    def from_row(cls, values):
        values = list(values) + [""] * (len(COLUMNS) - len(values))
        return cls(
            loader_id=values[0],
            product_base_type=values[1],
            representation=values[2],
            loader=values[3],
            version_hint=values[4],
            version_lock=str(values[5]).strip().lower() in ("yes", "true", "1"),
            loader_args=values[6],
            task_regex=values[7],
            variant_regex=values[8],
            product_regex=values[9],
        )

    # -- loader options ----------------------------------------------------

    def options(self):
        """Parse ``Loader Args`` into a dict of loader options.

        Accepts ``key=value`` pairs separated by commas; anything that does not
        parse is passed through untouched under the ``args`` key so a loader
        can still make use of it.
        """
        text = (self.loader_args or "").strip()
        if not text:
            return {}
        options = {}
        leftovers = []
        for chunk in text.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "=" in chunk:
                key, value = chunk.split("=", 1)
                options[key.strip()] = _coerce(value.strip())
            else:
                leftovers.append(chunk)
        if leftovers:
            options["args"] = " ".join(leftovers)
        return options


def move_selected(rows, selected, step):
    """Move the selected indices one place up (step -1) or down (step 1).

    A block of selected rows slides as one and stops together at the end of
    the list. Returns (reordered rows, new selection).
    """
    rows = list(rows)
    selected = sorted({index for index in selected if 0 <= index < len(rows)})
    if not selected or step not in (-1, 1):
        return rows, selected

    moved = set(selected)
    # Start from the edge the rows are moving towards, so each row finds its
    # target free.
    order = selected if step < 0 else list(reversed(selected))
    for index in order:
        target = index + step
        if target < 0 or target >= len(rows) or target in moved:
            continue
        rows[index], rows[target] = rows[target], rows[index]
        moved.discard(index)
        moved.add(target)
    return rows, sorted(moved)


def _coerce(value):
    lowered = value.lower()
    if lowered in ("true", "yes"):
        return True
    if lowered in ("false", "no"):
        return False
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


class Template(object):
    """Template nodes plus the templated loaders that fill their placeholders."""

    def __init__(self, node_text="", loaders=None):
        self.node_text = node_text
        self.loaders = list(loaders or [])

    def to_data(self):
        return {
            "node_text": self.node_text,
            "loaders": [loader.to_data() for loader in self.loaders],
        }

    @classmethod
    def from_data(cls, data):
        data = data or {}
        return cls(
            node_text=data.get("node_text", ""),
            loaders=[
                TemplatedLoader.from_data(row)
                for row in data.get("loaders") or []
            ],
        )

    def renumber(self):
        """Ids follow position: row 1 is 001, row 2 is 002, and so on.

        The id is a slot, not an identity - a placeholder Dot labelled 001
        always means "whatever the first row loads", which is what makes
        reordering rows meaningful.
        """
        for index, loader in enumerate(self.loaders):
            loader.loader_id = "{:03d}".format(index + 1)
        return self

    def next_loader_id(self):
        """Smallest unused zero filled id, counting from 1."""
        used = set()
        for loader in self.loaders:
            try:
                used.add(int(loader.loader_id))
            except (TypeError, ValueError):
                continue
        number = 1
        while number in used:
            number += 1
        return "{:03d}".format(number)


# ---------------------------------------------------------------------------
# resolution against AYON
# ---------------------------------------------------------------------------

class Resolved(object):
    """What a templated loader resolved to for one folder."""

    def __init__(self, loader_row, product=None, version=None,
                 representation=None, error=""):
        self.loader_row = loader_row
        self.product = product
        self.version = version
        self.representation = representation
        self.error = error

    @property
    def ok(self):
        return self.representation is not None and not self.error


def _cached(cache, key, factory):
    """Memoise an AYON query for the duration of one Add Container press."""
    if cache is None:
        return factory()
    if key not in cache:
        cache[key] = factory()
    return cache[key]


def resolve(project_name, folder_id, loader_row, task_names_by_id=None,
            cache=None):
    """Resolve one templated loader row for one folder.

    ``task_names_by_id`` maps task id -> task name, which is what ``Task
    Regex`` is matched against; it is looked up per folder when not supplied.
    ``cache`` is a plain dict shared across rows and folders so adding a whole
    sequence queries each folder once instead of once per row.
    """
    if not ayonio.is_available():
        return Resolved(loader_row, error="AYON is not available")

    products = _cached(
        cache, ("products", folder_id),
        lambda: ayonio.get_products(project_name, [folder_id]),
    )
    candidates = []
    for product in products:
        if loader_row.product_base_type and (
            ayonio.product_base_type(product) != loader_row.product_base_type
        ):
            continue
        if not ayonio.regex_matches(
            loader_row.product_regex, product.get("name") or ""
        ):
            continue
        if not ayonio.regex_matches(
            loader_row.variant_regex, ayonio.product_variant(product)
        ):
            continue
        candidates.append(product)

    if not candidates:
        return Resolved(
            loader_row,
            error="no product matches base type '{}'".format(
                loader_row.product_base_type or "*"
            ),
        )

    products_by_id = {product["id"]: product for product in candidates}

    # One query per folder, then filtered down to the matching products.
    folder_versions = _cached(
        cache, ("versions", folder_id),
        lambda: ayonio.get_versions(
            project_name, [product["id"] for product in products]
        ),
    )
    versions = [
        version for version in folder_versions
        if version.get("productId") in products_by_id
    ]

    if loader_row.task_regex:
        # Task Regex is matched against the task name the version was
        # published from.
        names_by_id = task_names_by_id
        if names_by_id is None:
            names_by_id = _cached(
                cache, ("tasks", folder_id),
                lambda: {
                    task["id"]: task.get("name") or ""
                    for task in ayonio.get_tasks(project_name, [folder_id])
                },
            )
        versions = [
            version for version in versions
            if ayonio.regex_matches(
                loader_row.task_regex,
                names_by_id.get(version.get("taskId"), ""),
            )
        ]
    if not versions:
        return Resolved(loader_row, error="no version matches the row filters")

    versions_by_product = {}
    for version in versions:
        versions_by_product.setdefault(version["productId"], []).append(version)

    # When several products match, prefer the one that was published last -
    # that is almost always the output the supervisor means.
    def _freshness(product_id):
        return max(
            (v.get("createdAt") or "") for v in versions_by_product[product_id]
        )

    product_id = sorted(versions_by_product, key=_freshness, reverse=True)[0]
    product = products_by_id[product_id]
    version = pick_version(
        versions_by_product[product_id], loader_row.version_hint
    )
    if version is None:
        return Resolved(
            loader_row,
            product=product,
            error="version hint '{}' matched nothing".format(
                loader_row.version_hint
            ),
        )

    representations = _cached(
        cache, ("repres", version["id"]),
        lambda: ayonio.get_representations(project_name, [version["id"]]),
    )
    representation = None
    for repre in representations:
        if repre.get("name") == loader_row.representation:
            representation = repre
            break
    if representation is None and not loader_row.representation:
        representation = representations[0] if representations else None
    if representation is None:
        return Resolved(
            loader_row,
            product=product,
            version=version,
            error="representation '{}' not in version {}".format(
                loader_row.representation, version.get("version")
            ),
        )

    return Resolved(loader_row, product, version, representation)


def any_row_resolves(project_name, folder_id, template, task_names_by_id=None,
                     cache=None):
    """Whether at least one templated loader finds something for this folder.

    Used when Add Container expands a folder into everything below it - a shot
    the template has nothing to say about should not get an empty container.
    """
    for row in template.loaders:
        if resolve(
            project_name, folder_id, row, task_names_by_id, cache
        ).ok:
            return True
    return False


def pick_version(versions, hint):
    """Choose one version entity out of many, following the version hint.

    See ``VERSION_HINT_HELP`` for the accepted spellings.
    """
    if not versions:
        return None

    hint = (hint or "max").strip().lower()
    published = [v for v in versions if (v.get("version") or 0) >= 0]
    heroes = [v for v in versions if (v.get("version") or 0) < 0]
    ordered = sorted(published, key=lambda v: v.get("version") or 0)

    if hint == "hero":
        return heroes[0] if heroes else None
    if hint in ("", "max", "latest", "last"):
        return ordered[-1] if ordered else None
    if hint in ("min", "first"):
        return ordered[0] if ordered else None

    try:
        number = int(hint)
    except ValueError:
        log.warning("Unknown version hint %r, using latest", hint)
        return ordered[-1] if ordered else None

    if number < 0:
        # relative step back from the latest
        index = len(ordered) - 1 + number
        if index < 0:
            index = 0
        return ordered[index] if ordered else None

    for version in ordered:
        if version.get("version") == number:
            return version
    return None
