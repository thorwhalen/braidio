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

# --- composition model ---
from braidio.script import (  # noqa: F401
    Script,
    Narration,
    SegmentBeat,
    Dialogue,
    Beat,
    narration_segments,
)

# --- rights profiles ---
from braidio.rights import (  # noqa: F401
    Profile,
    RightsPolicy,
    RenderPlan,
    PlannedBeat,
    plan_production,
    find_verbatim_text,
    content_violations,
    segment_is_publishable,
    PUBLISHABLE_CLIP_RIGHTS,
)

# --- segment sources (reference -> cuttable window) ---
from braidio.sources import (  # noqa: F401
    SegmentSource,
    ResolvedSegment,
    Segment,
    TimedLine,
    TimedLineSegmentSource,
    find_segment,
    load_timing,
    cut_quote,
)

# --- narration synthesis ---
from braidio.tts import (  # noqa: F401
    narrate,
    text_to_dialogue,
    resolve_voice_id,
    DEFAULT_VOICE_ID,
    DEFAULT_MODEL_ID,
    DEFAULT_VOICE_SETTINGS,
    VOICE_ENV_VAR,
)
from braidio.conversation import (  # noqa: F401
    ConversationCast,
    DEFAULT_CAST,
    render_dialogue,
    render_turns_sequential,
)
from braidio.delivery import (  # noqa: F401
    Delivery,
    DELIVERIES,
    BASELINE,
    V2_TUNED,
    V2_AGGRESSIVE,
    V2_PRESENTER,
    V2_NARRATOR,
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

# --- music bed (instrumental underscore) ---
from braidio.music import (  # noqa: F401
    MusicBed,
    bed_for_intensity,
    BED_GAIN_BY_INTENSITY,
)

# --- ready-made format templates (standard-named presets) ---
from braidio.formats import (  # noqa: F401
    Format,
    render_format,
    FORMATS,
    SOLO_EXPLAINER,
    DEEP_DIVE,
    INTERVIEW,
    SONG_EXPLODER,
    PANEL,
    DEBATE,
    DOCUMENTARY_VO,
)

# --- composition + weaving (audio) ---
from braidio.compose import compose_narration  # noqa: F401
from braidio.render import render_production  # noqa: F401
from braidio.weave import (  # noqa: F401
    TimelineItem,
    extract_padded,
    weave_timeline,
    layout_starts,
    duration_s,
)

# --- production kinds (pure) ---
from braidio.kinds import WeaveKind  # noqa: F401

# --- optional nw-app layer (graph bodies + provenance) --------------------
# Registers braidio's domain/render body schemas with lacing and exposes the
# provenance / partial-re-render helpers. Guarded: `import braidio` never needs
# lacing/nw. `HAS_GRAPH` / `HAS_NW` report what's available.
HAS_GRAPH = False
HAS_NW = False
try:  # needs lacing
    from braidio import bodies  # noqa: F401  (registers schemas)
    from braidio.provenance import (  # noqa: F401
        record_render,
        stale_after,
        descendants_of,
    )

    HAS_GRAPH = True
except ImportError:  # pragma: no cover - optional dep
    pass
try:  # needs nw
    from braidio.project import Project  # noqa: F401

    HAS_NW = True
except ImportError:  # pragma: no cover - optional dep
    pass

__all__ = [
    # production kinds
    "WeaveKind",
    "HAS_GRAPH",
    "HAS_NW",
    # script
    "Script",
    "Narration",
    "SegmentBeat",
    "Dialogue",
    "Beat",
    "narration_segments",
    # rights
    "Profile",
    "RightsPolicy",
    "RenderPlan",
    "PlannedBeat",
    "plan_production",
    "find_verbatim_text",
    "content_violations",
    "segment_is_publishable",
    "PUBLISHABLE_CLIP_RIGHTS",
    # render
    "render_production",
    # sources
    "SegmentSource",
    "ResolvedSegment",
    "Segment",
    "TimedLine",
    "TimedLineSegmentSource",
    "find_segment",
    "load_timing",
    "cut_quote",
    # tts
    "narrate",
    "resolve_voice_id",
    "DEFAULT_VOICE_ID",
    "DEFAULT_MODEL_ID",
    "DEFAULT_VOICE_SETTINGS",
    "VOICE_ENV_VAR",
    # delivery
    "Delivery",
    "DELIVERIES",
    "BASELINE",
    "V2_TUNED",
    "V2_AGGRESSIVE",
    "V2_PRESENTER",
    "V2_NARRATOR",
    "V3_NATURAL",
    "V3_CREATIVE",
    # multivoice
    "Voice",
    "POOL_4",
    "POOL_MANY",
    "POOLS",
    "strip_markup",
    "split_segments",
    "assign_voices",
    "group_turns",
    "render_multivoice",
    # config
    "WeaveConfig",
    "PRESETS",
    # music bed
    "MusicBed",
    "bed_for_intensity",
    "BED_GAIN_BY_INTENSITY",
    # formats (ready-made templates)
    "Format",
    "render_format",
    "FORMATS",
    "SOLO_EXPLAINER",
    "DEEP_DIVE",
    "INTERVIEW",
    "SONG_EXPLODER",
    "PANEL",
    "DEBATE",
    "DOCUMENTARY_VO",
    # compose + weave
    "compose_narration",
    "TimelineItem",
    "extract_padded",
    "weave_timeline",
    "layout_starts",
    "duration_s",
]
