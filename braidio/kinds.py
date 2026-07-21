"""Production kinds braidio defines. Pure (no optional deps)."""

from __future__ import annotations

from enum import Enum


class WeaveKind(str, Enum):
    """A braidio production kind. ``COMMENTARY_WEAVE`` = narration woven with
    extracted media segments (audio now, video later)."""

    COMMENTARY_WEAVE = "commentary_weave"
