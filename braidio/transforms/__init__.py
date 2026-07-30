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
- ``weave_to_episode.default`` — all member renders (+ config) → one
  ``episode-render/v1`` (the ``projection_entrypoint`` — the delivered mix).

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


def weave_project(project, script, *, config=None, source=None):
    """Ingest ``script`` and run the whole commentary-weave chain, in order.

    Returns the completed ``episode-render/v1`` annotation (its body carries
    the assembled audio's ``url`` + ``artifact_id``). A thin synchronous
    projection over the registered Transforms' ``plan``/``execute`` contract —
    each ``plan`` resolves its own context (config / voice-assignment /
    source-media) from the graph, so the driver only supplies the primary
    input. A cost-gated / async runner (``nw.jobs``, reelee's planner) can
    drive the same Transforms via the genre.
    """
    import nw

    ing = ingest_script(project, script, config=config, source=source)
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

    members = tuple(render_by_authoring_id[auth.id] for _kind, auth in ing.ordered)
    return _run(episode, project, *members)


def _run(transform, project, *primary):
    """``plan`` then ``execute`` one transform over ``primary``; return its output."""
    inputs = TransformInputs(primary=tuple(primary))
    plan, skeleton = transform.plan(project, inputs)
    result = transform.execute(project, plan, skeleton)
    return result.annotations[0]
