"""Register braidio's ``commentary_weave`` production genre with nw.

A one-file declarative registration over nw's genre-agnostic substrate: the
:class:`nw.Genre` references braidio's render Transforms + body schemas *by
name*, carrying no engine of its own. Importing :mod:`braidio.transforms`
first (which registers the Transforms) makes ``is_ready()`` true.

The genre is **self-describing**: braidio's 7 :data:`~braidio.formats.FORMATS`
presets become the genre's :class:`nw.Template`\\ s (each carrying an opaque
``params={"format_id": ...}`` the braidio host resolves back to a ``Format``),
alongside its ``intake_kinds`` and a ``cost_profile`` routing tag. So any host —
braidio's own MCP connector today, the unified reelee AV connector tomorrow — can
expose the full genre (identity + templates + intake + cost) straight from
``nw.genres``, with no app-layer profile needed (thorwhalen/braidio#6).
"""

from __future__ import annotations

from nw import Genre, Template, register_genre

from braidio.formats import FORMATS
from braidio.bodies._domain import NARRATIVE_BEAT_V1, AUDIO_CLIP_V1
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    SOURCE_MEDIA_V1,
    VOICE_ASSIGNMENT_V1,
    NARRATION_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    EPISODE_RENDER_V1,
)
from braidio.transforms import (
    VOICE_ASSIGNMENT_TRANSFORM,
    NARRATION_RENDER_TRANSFORM,
    SEGMENT_EXTRACTION_TRANSFORM,
    EPISODE_TRANSFORM,
)

COMMENTARY_WEAVE_SLUG = "commentary_weave"

COMMENTARY_WEAVE: Genre = register_genre(
    Genre(
        slug=COMMENTARY_WEAVE_SLUG,
        title="Commentary Weave",
        description=(
            "Weave narration with extracted source segments into an audio "
            "episode: take sources, cut them into segments, and weave them "
            "(with narration) into a produced audio artifact."
        ),
        body_schema_uris=(
            NARRATIVE_BEAT_V1,
            AUDIO_CLIP_V1,
            WEAVE_CONFIG_V1,
            SOURCE_MEDIA_V1,
            VOICE_ASSIGNMENT_V1,
            NARRATION_RENDER_V1,
            SEGMENT_EXTRACTION_V1,
            EPISODE_RENDER_V1,
        ),
        transform_names=(
            VOICE_ASSIGNMENT_TRANSFORM,
            NARRATION_RENDER_TRANSFORM,
            SEGMENT_EXTRACTION_TRANSFORM,
            EPISODE_TRANSFORM,
        ),
        projection_entrypoint=EPISODE_TRANSFORM,
        # Early / API-unstable (braidio 0.0.x). Audio-only v1; audiovisual and
        # Dialogue beats are follow-ups. See thorwhalen/reelee#227, braidio#6.
        status="experimental",
        # Intake answers this audio genre covers, and the cost-gate discriminator
        # (braidio's only spend is per-character ElevenLabs TTS — see braidio.cost).
        intake_kinds=("podcast", "audio-essay", "commentary"),
        cost_profile="tts",
        # "Start from scratch" → the simplest format (one presenter over exhibits).
        defaults={"format_id": "solo_explainer"},
        # The 7 braidio Formats as Templates ("subgenres"). params carries the
        # Format id; braidio resolves it back to a Format at render time. Only the
        # user-facing id/name/summary cross into nw — render internals stay in
        # braidio.formats.
        templates=tuple(
            Template(
                slug=fmt.id,
                title=fmt.name,
                description=fmt.summary,
                params={"format_id": fmt.id},
            )
            for fmt in FORMATS.values()
        ),
    )
)
