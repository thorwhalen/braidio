"""Register braidio's ``commentary_weave`` production genre with nw.

A one-file declarative registration over nw's genre-agnostic substrate: the
:class:`nw.Genre` references braidio's render Transforms + body schemas *by
name*, carrying no engine of its own. Importing :mod:`braidio.transforms`
first (which registers the Transforms) makes ``is_ready()`` true.

Per the federation directive, braidio (the focused package) self-registers
its ``nw.Genre``; the reelee studio host adds the app-layer ``GenreProfile``
(Templates from braidio's Formats, flavors, cost, intake) on top.
"""

from __future__ import annotations

from nw import Genre, register_genre

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
    )
)
