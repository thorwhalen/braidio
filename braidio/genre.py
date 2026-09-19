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

# `register_genre_project_factory` (nw >= 0.0.15) also acts as an explicit version
# guard: on a too-old nw this import fails, and braidio/__init__'s HAS_NW guard then
# degrades commentary_weave out of the catalog (braidio pins the nw floor in its extras).
from nw import Genre, Template, register_genre, register_genre_project_factory

from braidio.formats import FORMATS
from braidio.bodies._domain import (
    NARRATIVE_BEAT_V1,
    DIALOGUE_BEAT_V1,
    SCENE_BREAK_V1,
    AUDIO_CLIP_V1,
)
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    PRODUCTION_STRUCTURE_V1,
    DIALOGUE_CAST_V1,
    SOURCE_MEDIA_V1,
    VOICE_ASSIGNMENT_V1,
    NARRATION_RENDER_V1,
    DIALOGUE_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    EPISODE_RENDER_V1,
)
from braidio.bodies._video import (
    STILL_V1,
    VIDEO_PANEL_V1,
    VIDEO_CUT_V1,
    LABEL_TRACK_V1,
)
from braidio.transforms import (
    VOICE_ASSIGNMENT_TRANSFORM,
    NARRATION_RENDER_TRANSFORM,
    DIALOGUE_RENDER_TRANSFORM,
    SEGMENT_EXTRACTION_TRANSFORM,
    EPISODE_TRANSFORM,
    VIDEO_PANELS_TRANSFORM,
    VIDEO_CUT_RENDER_TRANSFORM,
    VIDEO_CUT_FINISH_TRANSFORM,
)

COMMENTARY_WEAVE_SLUG = "commentary_weave"

COMMENTARY_WEAVE: Genre = register_genre(
    Genre(
        slug=COMMENTARY_WEAVE_SLUG,
        title="Commentary Weave",
        description=(
            "Weave narration with extracted source segments into an audio "
            "episode: take sources, cut them into segments, and weave them "
            "(with narration) into a produced audio artifact — and, as a "
            "delivery of that episode, a commentary video: a picture track of "
            "stills with authored camera moves, cut to the narration."
        ),
        body_schema_uris=(
            NARRATIVE_BEAT_V1,
            DIALOGUE_BEAT_V1,
            SCENE_BREAK_V1,
            AUDIO_CLIP_V1,
            WEAVE_CONFIG_V1,
            PRODUCTION_STRUCTURE_V1,
            DIALOGUE_CAST_V1,
            SOURCE_MEDIA_V1,
            VOICE_ASSIGNMENT_V1,
            NARRATION_RENDER_V1,
            DIALOGUE_RENDER_V1,
            SEGMENT_EXTRACTION_V1,
            EPISODE_RENDER_V1,
            # The picture track (commentary-studio plan §3): a video is a
            # delivery of the same production, so it lives in the same genre.
            STILL_V1,
            VIDEO_PANEL_V1,
            VIDEO_CUT_V1,
            LABEL_TRACK_V1,
        ),
        transform_names=(
            VOICE_ASSIGNMENT_TRANSFORM,
            NARRATION_RENDER_TRANSFORM,
            DIALOGUE_RENDER_TRANSFORM,
            SEGMENT_EXTRACTION_TRANSFORM,
            EPISODE_TRANSFORM,
            VIDEO_PANELS_TRANSFORM,
            VIDEO_CUT_RENDER_TRANSFORM,
            VIDEO_CUT_FINISH_TRANSFORM,
        ),
        # The episode is still the projection entrypoint: the audio is the
        # production; a cut is a delivery made from it (plan §0, "Genre").
        projection_entrypoint=EPISODE_TRANSFORM,
        # Early / API-unstable (braidio 0.0.x). Audio was v1; the video delivery
        # (still/video-panel/video-cut/label-track + the three video_* transforms)
        # landed with the commentary-studio plan. See thorwhalen/reelee#227, braidio#6.
        status="experimental",
        # Intake answers this genre covers — audio, and the video delivery of it
        # — and the cost-gate discriminator: braidio's only *spend* is
        # per-character ElevenLabs TTS (see braidio.cost); the video passes are
        # local CPU, free but minutes long.
        intake_kinds=("podcast", "audio-essay", "commentary", "commentary-video"),
        cost_profile="tts",
        # "Start from scratch" → the simplest format (one presenter over exhibits).
        defaults={"format_id": "solo_explainer"},
        # The 7 braidio Formats as Templates ("subgenres"). params carries the
        # Format id; braidio resolves it back to a Format at render time. Only the
        # user-facing id/name/summary cross into nw — render internals stay in
        # braidio.formats. A video is a DELIVERY, orthogonal to format, so it
        # adds no template: every format can be cut to a picture track.
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


def _commentary_weave_project_factory(
    caller, project_id, *, title, template, params, projects_dir=None
):
    """Create a ``commentary_weave`` project where the CALLER asks, else in braidio's.

    The nw project-factory (thorwhalen/braidio#18) a host calls via
    ``nw.create_genre_project`` so a host can create commentary projects it doesn't
    natively host. braidio's Format is applied at render time, so there is no
    initializer — the ``format_id`` rides in the returned info + ``create``'s envelope.

    Two placements, and which one runs is the caller's decision, never this
    factory's (nw#84 — *a genre project factory places a project where its caller
    asks; it does not own the location*):

    - ``projects_dir`` given — create at ``projects_dir/<project_id>``. This is the
      path a host that will **serve** the project takes: reelee hands its own
      per-caller projects dir, so the commentary project is a sibling of that
      caller's other projects, its lister lists it and its project header can name
      it. Under braidio's own data home it would be addressable by braidio's tools
      and by nothing of the host's — two surfaces showing different projects under
      the same name, which is the shape users read as data loss.
    - ``projects_dir=None`` — the caller-space contract as before: braidio's own
      per-user workspace at ``{braidio data home}/projects/{caller}/{project_id}/``.
      This is what braidio's own MCP connector gets, and it is unchanged.

    ``Workspace`` is imported **lazily** and only on the second path, so
    ``import braidio.genre`` stays fastmcp-free (a top-level
    ``braidio.mcp.workspace`` import would pull fastmcp via ``braidio.mcp`` and flip
    braidio's ``HAS_NW`` off) — and so the host-placed create never needs the MCP
    extra installed at all.
    """
    if projects_dir is not None:
        from braidio.project import create_project_at

        proj = create_project_at(projects_dir, project_id, title=title)
    else:
        from braidio.mcp.workspace import Workspace

        proj = Workspace.for_email(caller).create_project(project_id, title=title)
    return {
        "project": proj,
        "project_id": project_id,
        "title": title,
        "format_id": params.get("format_id"),
    }


register_genre_project_factory(COMMENTARY_WEAVE_SLUG, _commentary_weave_project_factory)
