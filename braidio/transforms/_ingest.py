"""Ingest a braidio :class:`~braidio.script.Script` into an nw project graph.

This writes the **authoring** layer the render Transforms consume:

- one ``weave-config/v1`` snapshot (the singleton render-choices node);
- one ``narrative-beat/v1`` per :class:`~braidio.script.Narration`;
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

from braidio.script import Script, Narration, SegmentBeat, Dialogue
from braidio.weave_config import WeaveConfig
from braidio.bodies._domain import (
    NARRATIVE_BEAT_V1,
    NarrativeBeatBodyV1,
    AUDIO_CLIP_V1,
    AudioClipBodyV1,
)
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    WeaveConfigBodyV1,
    SOURCE_MEDIA_V1,
    SourceMediaBodyV1,
)
from braidio.transforms._common import (
    TIER_WEAVE_CONFIG,
    TIER_NARRATIVE_BEAT,
    TIER_SOURCE_MEDIA,
    TIER_AUDIO_CLIP,
    node_ref,
    _RATE,
)


@dataclass(frozen=True)
class IngestedScript:
    """Handles to the authoring nodes an ingest wrote, in script order."""

    config: Annotation
    narration_beats: tuple[Annotation, ...]
    audio_clips: tuple[Annotation, ...]
    #: ``(kind, authoring_annotation)`` in script order — ``kind`` is
    #: ``"narration"`` or ``"segment"``. The episode is assembled in this order.
    ordered: tuple[tuple[str, Annotation], ...]


def ingest_script(
    project,
    script: Script,
    *,
    config: WeaveConfig | None = None,
    source=None,
) -> IngestedScript:
    """Write ``script``'s authoring nodes into ``project``'s graph.

    ``config`` defaults to a plain :class:`WeaveConfig`. ``source`` (a
    :class:`~braidio.sources.SegmentSource`) is required iff the script has
    :class:`SegmentBeat`\\ s — it resolves each reference to a playable window.
    """
    config = config or WeaveConfig()

    cfg = Annotation(
        id=uuid.uuid4(),
        tier=TIER_WEAVE_CONFIG,
        reference=node_ref(TIER_WEAVE_CONFIG),
        body=WeaveConfigBodyV1(config=config.to_dict()).model_dump(),
        body_schema_uri=WEAVE_CONFIG_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(cfg)

    narration_beats: list[Annotation] = []
    audio_clips: list[Annotation] = []
    ordered: list[tuple[str, Annotation]] = []

    for i, beat in enumerate(script.beats):
        if isinstance(beat, Narration):
            ann = Annotation(
                id=uuid.uuid4(),
                tier=TIER_NARRATIVE_BEAT,
                reference=node_ref(TIER_NARRATIVE_BEAT),
                body=NarrativeBeatBodyV1(
                    beat_id=f"{i:04d}",
                    text=beat.text,
                    style=beat.style,
                ).model_dump(),
                body_schema_uri=NARRATIVE_BEAT_V1,
                provenance=_authored_provenance(),
            )
            project.graph.add_annotation(ann)
            narration_beats.append(ann)
            ordered.append(("narration", ann))
        elif isinstance(beat, SegmentBeat):
            clip = _ingest_segment(project, beat, source=source)
            audio_clips.append(clip)
            ordered.append(("segment", clip))
        elif isinstance(beat, Dialogue):
            raise NotImplementedError(
                "Dialogue beats are not yet ingested into the graph pipeline "
                "(follow-up: render_dialogue wiring). Use Narration for v1."
            )
        else:  # pragma: no cover — Beat is a closed union
            raise TypeError(f"unknown beat type {type(beat).__name__}")

    return IngestedScript(
        config=cfg,
        narration_beats=tuple(narration_beats),
        audio_clips=tuple(audio_clips),
        ordered=tuple(ordered),
    )


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
