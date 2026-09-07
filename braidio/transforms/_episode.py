"""``weave_to_episode.default`` — weave member renders into one episode.

A **batch** local-render Transform (N inputs → 1 output): it consumes all the
narration-render + segment-extraction nodes (in order), weaves them with
``braidio.weave_timeline`` (duck/crossfade/loudness from the weave-config),
and emits one ``episode-render/v1`` referencing the assembled audio. It
derives from ``[*members, weave-config]``, so any member re-render (or a
config change) re-stales the episode — the top of the partial-re-render DAG.

**Structural music** (thorwhalen/braidio#39) rides the same list: a
``scene-break/v1`` node is a member with no render node of its own, and the
weave turns it into a sting or a pause via ``braidio.structure`` — the same
primitives the no-graph path uses, never a forked DSP. When the project carries
a ``production-structure/v1`` node the episode also derives from it, so
swapping the sting asset or flipping fade-to-spotlight re-stales exactly the
episode; when it does not, nothing about the plan or the render changes.

This is the genre's ``projection_entrypoint``: the step that turns the graph
into the delivered artifact.
"""

from __future__ import annotations

import uuid

from falaw import Plan
from lacing import Annotation
from nw import BaseTransform, TransformInputs, TransformResult, register_transform
from nw.transforms._provenance import derive_provenance

from braidio.weave import TimelineItem
from braidio.bodies._domain import SCENE_BREAK_V1
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    PRODUCTION_STRUCTURE_V1,
    NARRATION_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    EPISODE_RENDER_V1,
    EpisodeRenderBodyV1,
)
from braidio.transforms._common import (
    TIER_AUDIO_CLIP,
    TIER_WEAVE_CONFIG,
    TIER_PRODUCTION_STRUCTURE,
    TIER_NARRATION_RENDER,
    TIER_SCENE_BREAK,
    TIER_EPISODE_RENDER,
    singleton,
    optional_singleton,
    graph_index,
    resolve_parents,
    require_tier,
    node_ref,
    audio_artifact,
    safe_duration,
    file_url,
    url_to_path,
)

NAME = "weave_to_episode.default"

# Weave defaults, applied when the weave-config snapshot omits a knob. They
# mirror braidio.weave.weave_timeline's own signature defaults.
_DEFAULT_CLIP_EDGE_OVERLAP_S = 0.5
_DEFAULT_CROSSFADE_S = 0.12
_DEFAULT_TARGET_LUFS = -16.0
_DEFAULT_TRUE_PEAK = -1.0
_DEFAULT_SAMPLE_RATE = 44100


def _structure_and_bed(node: Annotation | None):
    """``(MusicStructure, MusicBed | None)`` from a ``production-structure`` node.

    ``None`` (no such node) resolves to braidio's inert default structure and no
    bed — the pre-structure behaviour, reconstructed rather than special-cased
    at every use site.
    """
    from braidio.music import MusicBed
    from braidio.structure import DEFAULT_STRUCTURE, MusicStructure, Sting

    if node is None:
        return DEFAULT_STRUCTURE, None
    body = node.body
    sting = None
    if body.get("sting_url"):
        sting = Sting(str(url_to_path(body["sting_url"])), **(body.get("sting") or {}))
    bed = None
    if body.get("bed_url"):
        bed = MusicBed(str(url_to_path(body["bed_url"])), **(body.get("bed") or {}))
    return MusicStructure(sting=sting, **(body.get("structure") or {})), bed


@register_transform(NAME)
class WeaveToEpisode(BaseTransform):
    """All members — renders and scene breaks — (+ weave-config, + the
    production-structure node when there is one) → one ``episode-render/v1``."""

    name = NAME
    input_kinds = (
        NARRATION_RENDER_V1,
        SEGMENT_EXTRACTION_V1,
        SCENE_BREAK_V1,
        WEAVE_CONFIG_V1,
        PRODUCTION_STRUCTURE_V1,
    )
    output_kind = EPISODE_RENDER_V1
    is_batch = True

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        members = tuple(inputs.primary)
        cfg = singleton(project, TIER_WEAVE_CONFIG)
        structure = optional_singleton(project, TIER_PRODUCTION_STRUCTURE)
        ordered_member_ids = tuple(str(a.id) for a in members)

        context = {WEAVE_CONFIG_V1: (cfg,)}
        # Only a production that declared structural music derives from it, so
        # one that did not keeps exactly the provenance (and identity) it had.
        if structure is not None:
            context[PRODUCTION_STRUCTURE_V1] = (structure,)
        full = TransformInputs(primary=members, context=context)
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_EPISODE_RENDER,
            reference=node_ref(TIER_EPISODE_RENDER),
            body=EpisodeRenderBodyV1(
                profile="personal", ordered_member_ids=ordered_member_ids
            ).model_dump(),
            body_schema_uri=EPISODE_RENDER_V1,
            provenance=derive_provenance(self, full, attributed_to="agent:braidio"),
        )
        return Plan(calls=()), (skeleton,)

    def execute(
        self,
        project,
        plan: Plan,
        skeleton: tuple[Annotation, ...],
        *,
        use_cache: bool = True,
        force: bool = False,
    ) -> TransformResult:
        import braidio  # runtime attr access so tests can monkeypatch weave_timeline

        skel = skeleton[0]
        index = graph_index(project)
        member_ids = [uuid.UUID(s) for s in skel.body.get("ordered_member_ids", ())]
        members = [index[mid] for mid in member_ids if mid in index]

        parents = resolve_parents(skel, index)
        cfg = require_tier(parents, TIER_WEAVE_CONFIG)
        config = cfg.body.get("config", {})
        structure, bed = _structure_and_bed(
            next((a for a in parents if a.tier == TIER_PRODUCTION_STRUCTURE), None)
        )
        target_lufs = float(config.get("target_lufs", _DEFAULT_TARGET_LUFS))

        breaks_dir = project.root / "data" / "breaks"
        items = [
            self._item(
                m,
                index,
                structure=structure,
                bed=bed,
                target_lufs=target_lufs,
                breaks_dir=breaks_dir,
            )
            for m in members
        ]

        out_path = project.root / "data" / "episodes" / f"{skel.id}.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        braidio.weave_timeline(
            items,
            out_path,
            clip_edge_overlap_s=float(
                config.get("clip_edge_overlap_s", _DEFAULT_CLIP_EDGE_OVERLAP_S)
            ),
            narration_crossfade_s=float(
                config.get("crossfade_s", _DEFAULT_CROSSFADE_S)
            ),
            target_lufs=target_lufs,
            true_peak=float(config.get("true_peak_dbtp", _DEFAULT_TRUE_PEAK)),
            sample_rate=int(config.get("sample_rate", _DEFAULT_SAMPLE_RATE)),
            bed=bed,
        )
        duration = safe_duration(out_path)
        artifact = audio_artifact(
            out_path,
            transform_name=self.name,
            derived_from=skel.provenance.was_derived_from,
            duration_s=duration,
        )
        completed = skel.model_copy(
            update={
                "body": {
                    **skel.body,
                    "artifact_id": artifact.asset_id,
                    "url": file_url(out_path),
                    "duration_s": duration,
                }
            }
        )
        project.graph.add_annotation(completed)
        return TransformResult(
            annotations=(completed,),
            artifacts=(artifact,),
            cost_usd_actual=0.0,
            cache_hit_savings_usd=0.0,
        )

    def _item(
        self,
        member: Annotation,
        index: dict,
        *,
        structure,
        bed,
        target_lufs: float,
        breaks_dir,
    ) -> TimelineItem:
        """One timeline part for ``member`` — a rendered beat, or a scene break.

        A scene break has no render node: its audio is prepared here, by the
        same :mod:`braidio.structure` primitives the no-graph path uses.
        Fade-to-spotlight is resolved only when there is a bed to drop out, so a
        production without one does no extra graph work.
        """
        from braidio.structure import prepare_pause, prepare_sting

        if member.tier == TIER_SCENE_BREAK:
            out = breaks_dir / f"{member.id}.mp3"
            part = (
                prepare_sting(structure.sting, out, target_lufs=target_lufs)
                if structure.plays_sting_of(member.body.get("marker"))
                else prepare_pause(structure.pause_s, out)
            )
            return TimelineItem(kind="sting", path=str(part), placement="sequential")

        is_clip = member.tier != TIER_NARRATION_RENDER
        return TimelineItem(
            kind="clip" if is_clip else "narration",
            path=str(url_to_path(member.body["url"])),
            placement="sequential",
            spotlight=(
                is_clip
                and bed is not None
                and structure.spotlight_of(_clip_spotlight(member, index))
            ),
        )


def _clip_spotlight(extraction: Annotation, index: dict):
    """The ``spotlight`` override on the audio-clip an extraction came from."""
    clip = require_tier(resolve_parents(extraction, index), TIER_AUDIO_CLIP)
    return clip.body.get("spotlight")
