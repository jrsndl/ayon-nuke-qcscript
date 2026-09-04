# QC Script Helper

A dockable Nuke panel that builds and maintains "QC scripts" - one Nuke script
holding many shots, each shot as a container of AYON loaded reads, so a
compositing supervisor can check shot to shot continuity and technical problems
in one place.

Built for Foundry Nuke 15.2+ (PySide6, falling back to PySide2) and the AYON
pipeline from Ynput.

## Install

Put the repository on Nuke's plugin path, from the user `init.py`:

```python
nuke.pluginAddPath("D:/_code/ayon-nuke-qcscript")
```

`menu.py` then installs the panel in GUI sessions and adds
*QC Script Helper > Open QC Script Helper* to the Nuke menu bar.

Launch Nuke through AYON (the launcher or an Ftrack action), otherwise the AYON
tab has no project to read and only the Nuke side of the tool works.

## Concepts

**Container** - one shot's worth of nodes wrapped in a Nuke `BackdropNode`. Its
unique key is `{folder path}:{task name}`, the label shown to the user is
`{leaf folder name}:{task name}`. The backdrop carries a hidden `qcs_data` JSON
knob with project, folder, task and assignees; every node the template produced
is stamped with `qcs_key` so the container survives saving and reopening.

**Template** - the recipe every container is built from. It is a block of pasted
Nuke nodes plus a spreadsheet of *templated loaders*. Each templated loader row
resolves to a product, then a version, then a representation, and its loaded
nodes replace the placeholder that carries the row's id.

**Placeholder** - a `Dot` (or `NoOp`) node in the template nodes that marks where
a templated loader's result belongs. Nuke refuses node names that start with a
digit, so put the loader id in the node's **label** (`001`); a name such as
`L001` or `qcs001` is matched as well.

## Tabs

| Tab | What it does |
| --- | --- |
| AYON | Browse folders and tasks, filter them, add one container per selected folder+task, or load a hand picked representation. |
| Inventory | Read the containers out of the open script, fetch their versions from AYON, filter, and mass change versions. Changed containers are tinted with the colour chosen next to *Change Color*. |
| Container | Properties of the single container selected in the node graph: frame range, format, version history, links to AYON and Ftrack. |
| Template | Edit the container recipe. Autosaves. |
| Preferences | Default loader per product base type, used by *Load* and by templated loaders that name no loader. |

### Version hints

A templated loader picks its version with a *Version Hint*:

| Hint | Meaning |
| --- | --- |
| `max`, `latest`, `last`, empty | newest published version |
| `min`, `first` | oldest published version |
| `hero` | the hero version |
| `7` | exactly version 7 |
| `-2` | two steps back from the newest |

*Version Lock* keeps an item out of every mass version change.

### Loader args

`Loader Args` is a comma separated list of `key=value` pairs handed to the
loader as its options, for example `start_at_workfile=true, offset=10`.
Anything that is not a pair is passed through under the `args` key.

## Layout

```
menu.py              Nuke GUI entry point, installs the panel
init.py              makes the package importable in any Nuke session
gui_layout/          Qt Designer .ui (the design source of truth) + screenshots
qcscript/
  compat.py          PySide6 / PySide2 shim
  uiloader.py        runtime loading of gui_layout.ui
  panel.py           the dockable panel, owns the tab controllers
  ayonio.py          defensive wrapper around ayon_api / ayon_core
  nukeio.py          node graph helpers - paste, backdrops, placeholders
  containers.py      QC containers: create, find, read back
  templates.py       templated loaders and their resolution against AYON
  settings.py        autosaved preferences and template
  tabs/              one controller per tab
```

Preferences and the template live in `~/.ayon-nuke-qcscript/settings.json`
(override the directory with `QCSCRIPT_CONFIG_DIR`).

## Development

The `.ui` is loaded at runtime, so editing it in Qt Designer is enough - there
is no generated Python to regenerate. Keep widget `objectName`s stable, they are
the contract between the design and the controllers.

Byte-compile and run the logic checks (no Nuke needed):

```
python -m compileall -q qcscript menu.py init.py
```

Nuke side checks run in terminal mode:

```
"C:/_GFX_library/dcc/nuke/Nuke17.0v1/Nuke17.0.exe" -t tests/test_nuke.py
```
