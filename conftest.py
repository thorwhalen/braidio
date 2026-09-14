"""Make the suite test *this* checkout, not whatever `braidio` is installed.

braidio is normally installed editable, and an editable install's path hook points
at the checkout it was installed from. Work on the package in a second location --
a git worktree, a CI job that checked the repo out somewhere else, a release
verification against an unpacked sdist -- and `from braidio import ...` silently
resolves to the *other* tree. The suite then passes or fails against code that is
not the code under review, which is the worst kind of green.

Putting the repo root first on `sys.path` makes the checkout that contains this
file win. No effect at all in the common case, where the two are the same tree.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).parent.resolve())

if sys.path and sys.path[0] != _REPO_ROOT:
    while _REPO_ROOT in sys.path:
        sys.path.remove(_REPO_ROOT)
    sys.path.insert(0, _REPO_ROOT)
