"""braidio as an nw app: a :class:`nw.Project` for commentary-weave productions.

Subclassing ``nw.Project`` inherits the whole folder facade + lacing graph +
freshness (``stale_after``) machinery; braidio adds its production kind and its
domain/render body-schema vocabulary (registered on import of
:mod:`braidio.bodies`). This module requires ``nw``; it is imported lazily by
``braidio/__init__`` only when ``nw`` is available.

The costed ``plan``/``execute`` Transform pipeline (each transform delegating to
braidio's functional core for the actual audio, and recording provenance via
:mod:`braidio.provenance`) is the next increment — see the design doc and
nw#9 (generalizing nw's shot/mp4 render seam).
"""

from __future__ import annotations

import nw

from braidio import bodies as _bodies  # noqa: F401  (import registers schemas)
from braidio.kinds import WeaveKind


class Project(nw.Project):
    """An nw project for a braidio commentary-weave production."""

    KIND: WeaveKind = WeaveKind.COMMENTARY_WEAVE
