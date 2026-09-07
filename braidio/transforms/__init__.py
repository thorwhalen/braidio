"""braidio's concrete ``nw.Transform`` pipeline — registered on import.

The ``Transform`` *abstraction* lives in ``nw`` (per the federation prime
directive); this package holds braidio's concrete audio-render instances and
registers them with ``nw.transforms`` as a side effect of import. It turns the
authoring graph (narrative beats, audio clips, a weave-config) into
render-provenance nodes, all written **through** ``project.graph`` so
``nw.stale_after`` drives partial re-render — one freshness engine, not
braidio's parallel standalone ``record_render`` store.

The chain (``sources → segments → weave``):

- ``beat_to_voice_assignment.default`` — narrative beat (+ weave-config) →
  ``voice-assignment/v1`` (deterministic; no synthesis).
- ``narration_render.tts`` — narrative beat (+ voice-assignment + config) →
  ``narration-render/v1`` (ElevenLabs TTS; cached by an explicit ``cache_key``).
- ``segment_extraction.ffmpeg`` — audio clip (+ source-media + config) →
  ``segment-extraction/v1`` (ffmpeg cut+pad; cached).
- ``weave_to_episode.default`` — all member renders, plus any scene-break
  nodes (+ config, + the production-structure and render-profile nodes when
  there are any) → one ``episode-render/v1`` (the ``projection_entrypoint`` —
  the delivered mix).

The rights :class:`~braidio.rights.Profile` is applied once, at ingest, by the
same :func:`braidio.rights.plan_production` the no-graph path runs — so a beat
the profile refuses never becomes a node, and no Transform re-decides rights.

:func:`weave_project` is the synchronous convenience driver; the Transforms
are independently registered so nw / reelee can drive them via the
``commentary_weave`` genre (see :mod:`braidio.genre`).
"""

from __future__ import annotations

from nw import TransformInputs

from braidio.transforms._ingest import ingest_script, IngestedScript
from braidio.transforms import _voice, _narration, _segment, _episode  # noqa: F401

# Registered transform names (the genre references these).
VOICE_ASSIGNMENT_TRANSFORM = _voice.NAME
NARRATION_RENDER_TRANSFORM = _narration.NAME
SEGMENT_EXTRACTION_TRANSFORM = _segment.NAME
EPISODE_TRANSFORM = _episode.NAME

__all__ = [
    "ingest_script",
    "IngestedScript",
    "weave_project",
    "VOICE_ASSIGNMENT_TRANSFORM",
    "NARRATION_RENDER_TRANSFORM",
    "SEGMENT_EXTRACTION_TRANSFORM",
    "EPISODE_TRANSFORM",
]


def weave_project(
    project,
    script,
    *,
    config=None,
    source=None,
    fmt=None,
    structure=None,
    bed=None,
    profile=None,
    rights=None,
):
    """Ingest ``script`` and run the whole commentary-weave chain, in order.

    Returns the completed ``episode-render/v1`` annotation (its body carries
    the assembled audio's ``url`` + ``artifact_id``). A thin synchronous
    projection over the registered Transforms' ``plan``/``execute`` contract —
    each ``plan`` resolves its own context (config / voice-assignment /
    source-media / production-structure) from the graph, so the driver only
    supplies the primary input. A cost-gated / async runner (``nw.jobs``,
    reelee's planner) can drive the same Transforms via the genre.

    ``fmt`` (a :class:`~braidio.formats.Format`) supplies the format's declared
    defaults — its ``weave`` config and its ``structure`` — for whichever of
    ``config`` / ``structure`` the caller left out; an explicit argument always
    wins. ``bed`` is the app-supplied music bed (:class:`~braidio.music.MusicBed`).
    With no format, no structure and no bed, this is the plain weave it always
    was (thorwhalen/braidio#39).

    ``profile`` (a :class:`~braidio.rights.Profile`) and ``rights`` (a
    :class:`~braidio.rights.RightsPolicy`) are the rights seam, and they mean
    exactly what they mean on :func:`braidio.render.render_production`: the
    script is filtered through :func:`~braidio.rights.plan_production` at
    ingest, so a segment the profile refuses is never extracted and never
    reaches the mix. ``None`` leaves the profile undeclared, which resolves to
    :data:`~braidio.rights.DEFAULT_PROFILE` — the fast path's default, and the
    behaviour every project had before (thorwhalen/braidio#47).
    """
    import nw

    if fmt is not None:
        config = config if config is not None else fmt.weave
        structure = structure if structure is not None else fmt.structure

    ing = ingest_script(
        project,
        script,
        config=config,
        source=source,
        structure=structure,
        bed=bed,
        profile=profile,
        rights=rights,
    )
    voice = nw.get_transform(VOICE_ASSIGNMENT_TRANSFORM)
    narration = nw.get_transform(NARRATION_RENDER_TRANSFORM)
    segment = nw.get_transform(SEGMENT_EXTRACTION_TRANSFORM)
    episode = nw.get_transform(EPISODE_TRANSFORM)

    render_by_authoring_id = {}
    for beat in ing.narration_beats:
        _run(voice, project, beat)
        render_by_authoring_id[beat.id] = _run(narration, project, beat)
    for clip in ing.audio_clips:
        render_by_authoring_id[clip.id] = _run(segment, project, clip)

    # A scene break renders no node of its own — the authoring annotation IS
    # the member, and the episode transform turns it into a sting or a pause.
    members = tuple(
        auth if kind == "scene_break" else render_by_authoring_id[auth.id]
        for kind, auth in ing.ordered
    )
    return _run(episode, project, *members)


def _run(transform, project, *primary):
    """``plan`` then ``execute`` one transform over ``primary``; return its output."""
    inputs = TransformInputs(primary=tuple(primary))
    plan, skeleton = transform.plan(project, inputs)
    result = transform.execute(project, plan, skeleton)
    return result.annotations[0]
