"""braidio — weave narration with extracted media segments into productions.

Braid two kinds of strand into one production: authored **narration** (TTS —
single voice or a cycled pool) and extracted **segments** of source media (song
clips, audiobook passages, news, SFX). The result renders to an audiovisual
object.

This is the **functional core** (pure Python over files + numbers; deps:
``mixing``, ``elevenlabs``, and ``ffmpeg`` on PATH). An optional nw-app layer
(graph bodies, transforms, provenance / partial re-render) will be added on top
and imported only when ``nw`` is available — ``import braidio`` never requires
it.

Extracted from the Hamilton lyrics-podcast; see that project + issues #18/#28.
"""

from __future__ import annotations

# --- narration synthesis ---
from braidio.tts import (  # noqa: F401
    narrate,
    resolve_voice_id,
    DEFAULT_VOICE_ID,
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE_SETTINGS,
    VOICE_ENV_VAR,
)
from braidio.delivery import (  # noqa: F401
    Delivery,
    DELIVERIES,
    BASELINE,
    V2_TUNED,
    V2_AGGRESSIVE,
    V3_NATURAL,
    V3_CREATIVE,
)

# --- multi-voice casting ---
from braidio.multivoice import (  # noqa: F401
    Voice,
    POOL_4,
    POOL_MANY,
    POOLS,
    strip_markup,
    split_segments,
    assign_voices,
    group_turns,
    render_multivoice,
)

# --- configuration ---
from braidio.weave_config import WeaveConfig, PRESETS  # noqa: F401

# --- composition + weaving (audio) ---
from braidio.compose import compose_narration  # noqa: F401
from braidio.weave import (  # noqa: F401
    TimelineItem,
    extract_padded,
    weave_timeline,
    layout_starts,
    duration_s,
)

__all__ = [
    # tts
    "narrate", "resolve_voice_id", "DEFAULT_VOICE_ID", "DEFAULT_MODEL_ID",
    "DEFAULT_VOICE_SETTINGS", "VOICE_ENV_VAR",
    # delivery
    "Delivery", "DELIVERIES", "BASELINE", "V2_TUNED", "V2_AGGRESSIVE",
    "V3_NATURAL", "V3_CREATIVE",
    # multivoice
    "Voice", "POOL_4", "POOL_MANY", "POOLS", "strip_markup", "split_segments",
    "assign_voices", "group_turns", "render_multivoice",
    # config
    "WeaveConfig", "PRESETS",
    # compose + weave
    "compose_narration", "TimelineItem", "extract_padded", "weave_timeline",
    "layout_starts", "duration_s",
]
