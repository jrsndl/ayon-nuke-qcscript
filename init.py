"""Nuke startup hook.

Runs in both GUI and terminal sessions, before menu.py. The panel itself is
installed from menu.py; here we only make sure the package is importable when
Nuke was told about this directory in some other way than pluginAddPath.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.append(_ROOT)
