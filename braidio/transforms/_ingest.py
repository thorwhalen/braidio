"""Ingest a braidio :class:`~braidio.script.Script` into an nw project graph.

The script is first filtered through :func:`braidio.rights.plan_production` —
the *same* rights filter the no-graph fast path
(:func:`braidio.render.render_production`) runs, not a second copy of it — so a
beat the profile refuses is never ingested, never extracted, and never paid
for, and a beat it substitutes is ingested as the substitute
(thorwhalen/braidio#47).

This writes the **authoring** layer the render Transforms consume:

- one ``render-profile/v1`` snapshot when the production declares a profile —
  the rights decision plus what it dropped/substituted;
- one ``weave-config/v1`` snapshot (the singleton render-choices node);
- one ``production-structure/v1`` snapshot when the production declares
  structural music (stings / fade-to-spotlight / a music bed) — written only
  then, so a format that declares none leaves the graph untouched;
- one ``narrative-beat/v1`` per :class:`~braidio.script.Narration`;
- one ``scene-break/v1`` per :class:`~braidio.script.SceneBreak` — the
  structural boundary, ordered with the rest of the spine (thorwhalen/braidio#39);
- a ``source-media/v1`` + ``audio-clip/v1`` pair per
  :class:`~braidio.script.SegmentBeat` (its playable window resolved via a
  :class:`~braidio.sources.SegmentSource`).

Everything is written **through** ``project.graph.add_annotation`` so the
whole pipeline (authoring → render) lives in one graph that
``nw.stale_after`` can traverse. :class:`~braidio.script.Dialogue` beats are
not yet ingested (a documented follow-up — they need ``render_dialogue``
wiring and a turns-carrying beat body).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from lacing import Annotation, MediaRef, TimeInterval

from braidio.rights import (
    DEFAULT_PROFILE,
    PUBLISHABLE_CLIP_RIGHTS,
    Profile,
    RenderPlan,
    RightsPolicy,
    plan_production,
)
from braidio.script import Script, SegmentBeat
from braidio.weave_config import WeaveConfig
from braidio.bodies._domain import (
    NARRATIVE_BEAT_V1,
    NarrativeBeatBodyV1,
    SCENE_BREAK_V1,
    SceneBreakBodyV1,
    AUDIO_CLIP_V1,
    AudioClipBodyV1,
)
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    WeaveConfigBodyV1,
    PRODUCTION_STRUCTURE_V1,
    ProductionStructureBodyV1,
    RENDER_PROFILE_V1,
    RenderProfileBodyV1,
    SOURCE_MEDIA_V1,
    SourceMediaBodyV1,
)
from braidio.transforms._common import (
    TIER_WEAVE_CONFIG,
    TIER_PRODUCTION_STRUCTURE,
    TIER_RENDER_PROFILE,
    TIER_NARRATIVE_BEAT,
    TIER_SCENE_BREAK,
    TIER_SOURCE_MEDIA,
    TIER_AUDIO_CLIP,
    asset_ref,
    node_ref,
    _RATE,
)


@dataclass(frozen=True)
class IngestedScript:
    """Handles to the authoring nodes an ingest wrote, in script order."""

    config: Annotation
    narration_beats: tuple[Annotation, ...]
    audio_clips: tuple[Annotation, ...]
    scene_breaks: tuple[Annotation, ...] = ()
    #: The singleton ``production-structure/v1`` node, when the production
    #: declared structural music; ``None`` when it declared none.
    structure: Annotation | None = None
    #: ``(kind, authoring_annotation)`` in script order — ``kind`` is
    #: ``"narration"``, ``"segment"`` or ``"scene_break"``. The episode is
    #: assembled in this order.
    ordered: tuple[tuple[str, Annotation], ...] = ()
    #: The singleton ``render-profile/v1`` node, when the production declared a
    #: rights profile; ``None`` when it declared none.
    render_profile: Annotation | None = None
    #: The rights plan the ingest actually followed — its ``dropped`` /
    #: ``substituted`` are what the profile refused and swapped.
    plan: RenderPlan | None = None


def ingest_script(
    project,
    script: Script,
    *,
    config: WeaveConfig | None = None,
    source=None,
    structure=None,
    bed=None,
    profile: Profile | None = None,
    rights: RightsPolicy | None = None,
) -> IngestedScript:
    """Write ``script``'s authoring nodes into ``project``'s graph.

    ``config`` defaults to a plain :class:`WeaveConfig`. ``source`` (a
    :class:`~braidio.sources.SegmentSource`) is required iff the script has
    :class:`SegmentBeat`\\ s — it resolves each reference to a playable window.

    ``structure`` (a :class:`~braidio.structure.MusicStructure`, typically a
    format's declared one) and ``bed`` (a :class:`~braidio.music.MusicBed`) are
    the production's structural music. Given either, one
    ``production-structure/v1`` node records the decision — including the
    content-addressed ids of the app-supplied sting/bed assets — so the episode
    transform can play a sting at each scene break and drop the bed under a
    spotlit exhibit. Given neither, nothing is written and the render is
    byte-for-byte what it was before this layer existed.

    ``profile`` (a :class:`~braidio.rights.Profile`) is the production's rights
    projection and ``rights`` (a :class:`~braidio.rights.RightsPolicy`) the
    caller-injected set of publishable segment rights. The script is filtered
    through :func:`~braidio.rights.plan_production` exactly as
    :func:`braidio.render.render_production` filters it, so a beat the profile
    refuses never reaches the graph — and is therefore never extracted, never
    synthesized and never paid for. ``profile=None`` means *undeclared*: the
    filter still runs, under :data:`~braidio.rights.DEFAULT_PROFILE` (the same
    default the fast path uses), which passes every beat through unchanged, and
    no ``render-profile/v1`` node is written.
    """
    config = config or WeaveConfig()
    publishable = rights.publishable_clip_rights if rights else PUBLISHABLE_CLIP_RIGHTS
    plan = plan_production(
        script,
        profile if profile is not None else DEFAULT_PROFILE,
        publishable_clip_rights=publishable,
    )

    cfg = Annotation(
        id=uuid.uuid4(),
        tier=TIER_WEAVE_CONFIG,
        reference=node_ref(TIER_WEAVE_CONFIG),
        body=WeaveConfigBodyV1(config=config.to_dict()).model_dump(),
        body_schema_uri=WEAVE_CONFIG_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(cfg)
    structure_node = _ingest_structure(project, structure=structure, bed=bed)
    profile_node = _ingest_render_profile(
        project, profile=profile, publishable=publishable, plan=plan
    )

    narration_beats: list[Annotation] = []
    audio_clips: list[Annotation] = []
    scene_breaks: list[Annotation] = []
    ordered: list[tuple[str, Annotation]] = []

    # The rights plan, not the raw script: a beat the profile dropped is simply
    # absent here, and a substituted one arrives already rewritten. ``orig`` is
    # the beat it came from — the authored one still carries the knobs (label,
    # style, marker, spotlight) that the plan does not repeat.
    for planned in plan.beats:
        orig = script.beats[planned.from_index]
        beat_id = f"{planned.from_index:04d}"
        if planned.kind == "narration":
            ann = Annotation(
                id=uuid.uuid4(),
                tier=TIER_NARRATIVE_BEAT,
                reference=node_ref(TIER_NARRATIVE_BEAT),
                body=NarrativeBeatBodyV1(
                    beat_id=beat_id,
                    # the profile's resolved text: the authored narration, a
                    # ``published_text`` rewrite, or a segment's substitute.
                    text=planned.content,
                    style=getattr(orig, "style", None),
                ).model_dump(),
                body_schema_uri=NARRATIVE_BEAT_V1,
                provenance=_authored_provenance(),
            )
            project.graph.add_annotation(ann)
            narration_beats.append(ann)
            ordered.append(("narration", ann))
        elif planned.kind == "clip":
            clip = _ingest_segment(project, orig, source=source)
            audio_clips.append(clip)
            ordered.append(("segment", clip))
        elif planned.kind == "dialogue":
            raise NotImplementedError(
                "Dialogue beats are not yet ingested into the graph pipeline "
                "(follow-up: render_dialogue wiring). Use Narration for v1."
            )
        elif planned.kind == "scene_break":
            ann = Annotation(
                id=uuid.uuid4(),
                tier=TIER_SCENE_BREAK,
                reference=node_ref(TIER_SCENE_BREAK),
                body=SceneBreakBodyV1(
                    beat_id=beat_id, label=orig.label, marker=orig.marker
                ).model_dump(),
                body_schema_uri=SCENE_BREAK_V1,
                provenance=_authored_provenance(),
            )
            project.graph.add_annotation(ann)
            scene_breaks.append(ann)
            ordered.append(("scene_break", ann))
        else:  # pragma: no cover — PlannedBeat.kind is a closed set
            raise TypeError(f"unknown planned-beat kind {planned.kind!r}")

    return IngestedScript(
        config=cfg,
        narration_beats=tuple(narration_beats),
        audio_clips=tuple(audio_clips),
        scene_breaks=tuple(scene_breaks),
        structure=structure_node,
        ordered=tuple(ordered),
        render_profile=profile_node,
        plan=plan,
    )


def _ingest_render_profile(
    project, *, profile: Profile | None, publishable: frozenset[str], plan: RenderPlan
) -> Annotation | None:
    """Write the singleton ``render-profile/v1`` node, or ``None``.

    Absent a declared ``profile`` the production made no rights choice, so
    nothing is written — the same convention the production-structure node
    follows, and what keeps a profile-less legacy project's graph, provenance
    and render exactly as they were.
    """
    if profile is None:
        return None

    ann = Annotation(
        id=uuid.uuid4(),
        tier=TIER_RENDER_PROFILE,
        reference=node_ref(TIER_RENDER_PROFILE),
        body=RenderProfileBodyV1(
            profile=profile.value,
            publishable_clip_rights=tuple(sorted(publishable)),
            dropped=tuple(plan.dropped),
            substituted=tuple(plan.substituted),
        ).model_dump(),
        body_schema_uri=RENDER_PROFILE_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(ann)
    return ann


def _ingest_structure(project, *, structure, bed) -> Annotation | None:
    """Write the singleton ``production-structure/v1`` node, or ``None``.

    Absent both a structure and a bed the production declared no structural
    music, so the node is not written at all — that is what keeps a format
    without structure identical to the pre-structure graph (and render).
    """
    if structure is None and bed is None:
        return None

    from braidio.structure import DEFAULT_STRUCTURE

    structure = structure if structure is not None else DEFAULT_STRUCTURE
    sting_id, sting_url = (
        asset_ref(structure.sting.asset_path) if structure.sting else (None, None)
    )
    bed_id, bed_url = asset_ref(bed.asset_path) if bed else (None, None)
    ann = Annotation(
        id=uuid.uuid4(),
        tier=TIER_PRODUCTION_STRUCTURE,
        reference=node_ref(TIER_PRODUCTION_STRUCTURE),
        body=ProductionStructureBodyV1(
            structure=_knobs(structure, drop="sting"),
            sting=(
                _knobs(structure.sting, drop="asset_path") if structure.sting else None
            ),
            sting_asset_id=sting_id,
            sting_url=sting_url,
            bed=_knobs(bed, drop="asset_path") if bed else None,
            bed_asset_id=bed_id,
            bed_url=bed_url,
        ).model_dump(),
        body_schema_uri=PRODUCTION_STRUCTURE_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(ann)
    return ann


def _knobs(obj, *, drop: str) -> dict:
    """``obj``'s dataclass fields as a dict, minus ``drop`` (its asset field).

    The asset is recorded as a content-addressed id + a URL, never as whatever
    locator the caller happened to be holding.
    """
    from dataclasses import asdict

    return {k: v for k, v in asdict(obj).items() if k != drop}


def _ingest_segment(project, beat: SegmentBeat, *, source) -> Annotation:
    """Write the source-media + audio-clip pair for one segment beat."""
    if source is None:
        raise ValueError(
            "ingest_script: a SegmentSource is required to resolve SegmentBeats "
            f"(beat {beat.reference!r}); pass source=..."
        )
    resolved = source.resolve(beat.reference)
    if resolved is None:
        raise ValueError(
            f"ingest_script: SegmentSource could not resolve {beat.reference!r}"
        )

    label = beat.label or beat.reference
    src = Annotation(
        id=uuid.uuid4(),
        tier=TIER_SOURCE_MEDIA,
        reference=node_ref(TIER_SOURCE_MEDIA),
        body=SourceMediaBodyV1(
            label=label,
            asset_id=str(resolved.asset_path),
            rights=beat.rights,
        ).model_dump(),
        body_schema_uri=SOURCE_MEDIA_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(src)

    clip = Annotation(
        id=uuid.uuid4(),
        tier=TIER_AUDIO_CLIP,
        # The playable window lives on the clip's MediaRef interval — the
        # segment-extraction Transform reads start/end from here.
        reference=MediaRef(
            asset_id=str(resolved.asset_path),
            interval=TimeInterval.from_seconds(
                resolved.start_s, resolved.end_s, rate=_RATE
            ),
        ),
        body=AudioClipBodyV1(
            source_node_id=str(src.id),
            label=label,
            rights=beat.rights,
            spotlight=beat.spotlight,
        ).model_dump(),
        body_schema_uri=AUDIO_CLIP_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(clip)
    return clip


def _authored_provenance():
    """Provenance for a hand-authored (not transform-derived) node."""
    from lacing import Provenance, RationalTime

    return Provenance(
        was_generated_by="braidio:ingest",
        was_attributed_to="agent:braidio",
        was_derived_from=[],
        generated_at_time=RationalTime.now(rate=_RATE),
        activity="ingest",
    )
