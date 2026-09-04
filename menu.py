"""Nuke GUI entry point.

Sourced automatically because the repository root is on Nuke's plugin path
(``nuke.pluginAddPath("D:/_code/ayon-nuke-qcscript")`` in the user init.py).
"""

import traceback

import nuke

if nuke.GUI:
    try:
        import qcscript

        qcscript.install()
    except Exception:
        nuke.tprint("QC Script Helper failed to install:")
        traceback.print_exc()
