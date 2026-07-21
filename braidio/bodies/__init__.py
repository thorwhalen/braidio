"""braidio's lacing body schemas + tiers (the nw-app domain vocabulary).

Importing this package **registers every schema** with lacing (side effect of
importing the submodules). Requires ``lacing``; it is imported lazily by
``braidio/__init__.py`` only when available, so the functional core never
needs it.
"""

from __future__ import annotations

from braidio.bodies._domain import (  # noqa: F401  (import registers)
    COMMENTARY_V1,
    SOURCE_V1,
    AUDIO_CLIP_V1,
    NARRATIVE_BEAT_V1,
    EPISODE_V1,
    CommentaryBodyV1,
    SourceBodyV1,
    AudioClipBodyV1,
    NarrativeBeatBodyV1,
    EpisodeBodyV1,
    DOMAIN_SCHEMAS,
)
from braidio.bodies._render_nodes import (  # noqa: F401  (import registers)
    WEAVE_CONFIG_V1,
    SOURCE_MEDIA_V1,
    VOICE_ASSIGNMENT_V1,
    NARRATION_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    EPISODE_RENDER_V1,
    WeaveConfigBodyV1,
    SourceMediaBodyV1,
    VoiceAssignmentBodyV1,
    NarrationRenderBodyV1,
    SegmentExtractionBodyV1,
    EpisodeRenderBodyV1,
    RENDER_SCHEMAS,
)
from braidio.bodies._tiers import TIERS, register_tiers  # noqa: F401

# All schema URIs braidio registers (domain + render).
SCHEMA_URIS: dict = {**DOMAIN_SCHEMAS, **RENDER_SCHEMAS}
