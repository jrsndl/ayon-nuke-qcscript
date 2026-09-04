# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Nuke QC Script Helper

This tool is for Compositing supervisors using Foundry Nuke 15.2 and up, together with AYON pipeline from Ynput.
Use Pyside6 with fallback to Pyside2 for gui - make it a Nuke dockable panel.
Nuke 17 executable can be found at "C:\_GFX_library\dcc\nuke\Nuke17.0v1\Nuke17.0.exe"
for testing AYON, use [http://192.168.100.21:5000/projects/BCV_000_Playground](http://192.168.100.21:5000/projects/BCV_000_Playground/overview?project=BCV_000_Playground&type=task&id=965f33f2a88911f1a152bc24117f40ea)
User init.py for Nuke contains line: nuke.pluginAddPath("D:/_code/ayon-nuke-qcscript")
AYON install can be found at "C:/_GFX_library/ayon/app/AYON 1.6.3/ayon_console.exe"

## Architecture

Nuke, PySide and `ayon_core` / `ayon_nuke` all come from the host DCC environment, never
from pip — `pyproject.toml` declares no dependencies on purpose. Nuke 17 is Python 3.11 +
PySide6 6.5.3; Nuke 15.2 is PySide2, which is why all Qt goes through `qcscript/compat.py`.

```
menu.py              Nuke GUI entry point, calls qcscript.install()
init.py              puts the repo root on sys.path for non-plugin-path launches
qcscript/
  compat.py          PySide6 -> PySide2 shim (QAction moved to QtGui in Qt6)
  uiloader.py        QUiLoader wrapper - gui_layout.ui is loaded at RUNTIME
  panel.py           QCScriptPanel + Nuke panel/menu registration
  ayonio.py          every ayon_api / ayon_core call, each one degrading to empty
  nukeio.py          node graph only: paste, backdrops, knobs, placeholders
  containers.py      QC containers - create, find, read back, folder attributes
  templates.py       templated loader rows + resolution to a representation
  settings.py        autosaved JSON preferences and template
  tabs/              one controller per tab, all subclassing tabs.base.TabController
tests/               see Commands below
```

Two rules that shape everything: **the panel must open with no AYON at all** (plain Nuke
launches have no `ayon_api`), so `ayonio` never raises on a missing import and every getter
returns an empty result; and **the `.ui` is loaded at runtime**, so there is no generated
Python to regenerate and widget `objectName`s are the contract between Designer and the
controllers.

Loaders create an unpredictable number of nodes, so `nukeio.CapturedNodes` diffs
`nuke.allNodes()` around a loader call rather than trusting its return value.

## Commands

```
python tests/test_logic.py                       # no Nuke, no AYON needed
python -m compileall -q qcscript menu.py init.py
"C:/_GFX_library/dcc/nuke/Nuke17.0v1/Nuke17.0.exe" -t tests/test_nuke.py
```

`tests/test_nuke.py` covers the node graph side (paste, placeholder replacement, container
create/find/colour/selection) without touching AYON. There is no test runner and no lint
config; the test files are plain scripts that exit non-zero on failure.

To smoke test the GUI without a human, point `NUKE_PATH` at a scratch directory holding a
`menu.py` that builds `QCScriptPanel()`, calls `widget.grab().save(path)` from a
`QtCore.QTimer.singleShot`, and then `os._exit(0)`. Nuke's terminal mode (`-t`) cannot
create a `QApplication`, so Qt work has to happen in a real GUI launch.

## Running it

The repo root is on Nuke's plugin path via the user `init.py`
(`nuke.pluginAddPath("D:/_code/ayon-nuke-qcscript")`), so Nuke auto-sources `menu.py` and
`init.py` from the repo root. Launch Nuke through AYON
(`C:/_GFX_library/ayon/app/AYON 1.6.3/ayon_console.exe`) rather than the bare executable
whenever the code touches AYON — the AYON context (project, folder, task) comes from the
launcher environment, and the `ayon_project` field is autofilled from it.

Preferences and the template autosave to `~/.ayon-nuke-qcscript/settings.json`; the .ui has
no save button, so every edit writes through. `QCSCRIPT_CONFIG_DIR` overrides the location.

Editing the GUI: open `gui_layout/gui_layout.ui` in Qt Designer. The `.ui` is the design
source of truth; do not hand-edit Python generated from it. Widget `objectName`s in that
file are the contract described below — keep them stable when wiring signals.

## Use Case
Comp supervisor needs to check many versions of many different shots, comparing the current output with previous versions, while checking shot to shot continuity.
For this task, comp supervisor creates so called "qc script", where for each shot there is the current version of the output loaded, together with first version and possibly main plate.
Comp supervisor uses "qc script" for checking shot to shot continuity, and for checking technical problems.
Creating and updating the qc script is tedious work, this needs to be automated.
Every supervisor wants the qc script to look bit different, so there needs to be template based flexibility.

## Core domain concepts

* **Container** — one shot's worth of nodes in the QC script, wrapped in a Nuke BackDrop that
  carries metadata knobs. Its unique key is `{folder path}:{task name}`; the user-facing name
  is `{leaf folder name}:{task name}`. A container normally holds several AYON-loaded reads
  (current version, first version, plate) produced from one template.
* **Template** — the recipe used to build every container: a block of Nuke nodes pasted as a
  starting point, plus a spreadsheet of "templated loaders". Dot nodes named after a templated
  loader's ID act as **placeholders**; once the AYON loader runs, the loaded nodes replace
  (connect into) those dots. Loader IDs are autogenerated, unique, zero-filled numbers from 1 up.
  Nuke rejects a node name starting with a digit (`setName("001")` raises "illegal name"), so
  `nukeio.find_placeholder` matches the id against the node's **label** first, and accepts the
  spellings `001`, `L001`, `qcs001`, `placeholder001` as names.
* **Inventory** — the containers that already exist in the open Nuke script, read back from
  those BackDrop metadata knobs and reconciled against AYON versions.

## "QC Script Helper" GUI
1. "AYON" - offers selecting one or more "folder + task", can add containers to the Nuke script, can also load hand licked representations.
2. "Inventory" - shows containers existing in the Nuke Script, allows filtering and (mass) updating versions
4. "Container" - properties of the container currently selected in Nuke node view. Only one container can be edited like that
5. "Template" - how to make a container recipe. Combines pasting nuke nodes together with loading representations via AYON loaders  
6. "Preferences" - the "QC Script Helper" settings

See XML file for QT Designer gui_layout/gui_layout.ui and gui screenshots in gui_layout folder for gui layout.
The XML contains "tooltips" that describe some of the functionality.

### Widget naming and per-tab data shape

Every widget is prefixed by its tab (`ayon_*`, `inventory_*`, `container_*`, `template_*`,
`prefs_*`), so the prefix says which controller owns it. The tree/table columns below are
effectively the data model each tab has to produce:

* **AYON tab** — `ayon_tree` (folders + tasks: Name, Type, Status, Asignee, Category) drives
  `ayon_products_spreadsheet` (Name, Type, Variant, Last Version, Status) for the last selected
  task, which drives `ayon_repres_spreadsheet` (Name, Product, Version, Status).
  `ayon_add_container` builds containers from the tree selection; `ayon_load` loads a
  hand-picked representation using the default loader for its product base type. Filtering is
  `ayon_search_text` + `ayon_search_source` (which field to match), plus independent
  `ayon_task` / `ayon_product` filters whose text fields accept several space-separated names.
* **Inventory tab** — `inventory_tree` columns: Container, Product, Repre, Version, Versions,
  Version Lock, Author, Status, Age Hours, Tags. Three identical, invertible filter rows
  (`inventory_filterN` + `_text` / `_drop` / `_invert`). Fetching is split in two:
  `inventory_fetch_nuke` (read containers out of the script) and `inventory_fetch_ayon` (query
  available versions). Mass actions operate on the tree selection:
  `inventory_version_min/max/up/down`, `inventory_change_color`, `inventory_select_nodes`.
* **Container tab** — `container_get_selected` pulls the container selected in the Nuke node
  graph. *Set Range* and *Set Format* apply that container's numbers to the **Nuke script
  root**, so the supervisor can play the shot. With *Auto* ticked the numbers come from
  `containers.container_attributes()`, which reads the container's **task** attributes and
  falls back to its **folder** for anything the task does not define (and entirely, when the
  container has no task); *Add Slate* extends the start by one frame. With *Auto* off the
  spin boxes are applied as typed. `set_root_format` reuses an existing Nuke format when the
  numbers match (so a 1920x1080 shot shows as `HD_1080`) instead of adding a `QCS_` format on
  every press. `container_tree` lists that
  container's versions (Name, Repre, Version, Status, Author, Age, Tags) for
  `container_setversion`. Deep links out: `container_ayon_activity`, `container_ftrack_notes`.
* **Template tab** — `template_loader_spreadsheet` columns: ID, Base Type, Repre, Loader,
  Version Hint, Version Lock, Loader Args, Variant Regex, Product Regex. The regex fields
  (`template_task_regex`, `template_variant_regex`, `template_product_regex`) are how a
  templated loader picks which product/representation it resolves to per shot.
  `template_template_nodes` holds the pasted Nuke node text containing the placeholder dots.
* **Preferences tab** — `prefs_default_loaders` maps Product Base Type -> Loader; this is the
  default consulted by `ayon_load` and by templated loaders that name no explicit loader.

## Example Flow A
* Supe launches Nuke via AYON (using Ftrack action or AYON launcher)
* the task type is compositing, the task name starts with "QC", for example "QC_seq012"
* The resolution and frame range of the folder and task is not relevant, AYON will set it, but it can be ignored
* Supe launches the "QC Script Helper"
* Supe selects one or more folder + task in AYON tab, presses button "Add Container"
  * "QC Script Helper" checks if "container" with the "folder + task + product" exists
  * If container doesn't exist, "QC Script Helper" will create the container. 

### "Add Container" sequence (from the `ayon_add_container` tooltip)
1. make sure the container is not present already
2. derive the names: user name `{leaf folder name}:{task name}`, unique key `{folder path}:{task name}`
3. find the container's placement in the Nuke Node Graph
4. paste the template Nuke nodes
5. run the AYON loaders defined by the template
6. replace (connect) the placeholder dot nodes with the nodes loaded from AYON
7. create a Nuke BackDrop encapsulating the nodes into a "container"
8. add metadata knobs to the container BackDrop for later Inventory use

## Example Flow B
* Supe launches Nuke via AYON (using Ftrack action or AYON launcher), opening existing qc script
* Supe launches the "QC Script Helper"
* Supe uses "Inventory" to mass update to latest versions, coloring the updated containers to yellow
* Supe selects one yellow container in Nuke node view, uses "Container" to set proper frame range, and checks the shot

## Using AYON in Nuke
See AYON repos for guidance, AYON "workfile template builder" uses similar logic, just for one "shot & task", not many.
https://github.com/ynput/ayon-core/blob/develop/client/ayon_core/pipeline/workfile/workfile_template_builder.py
https://github.com/ynput/ayon-nuke/blob/develop/client/ayon_nuke/api/workfile_template_builder.py

The key difference from that reference: the workfile template builder resolves placeholders for
a single shot+task context, whereas this tool resolves the same kind of placeholders repeatedly,
once per selected folder+task, into separate BackDrop containers inside one script.
