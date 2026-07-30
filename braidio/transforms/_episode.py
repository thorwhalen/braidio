"""``weave_to_episode.default`` — weave member renders into one episode.

A **batch** local-render Transform (N inputs → 1 output): it consumes all the
narration-render + segment-extraction nodes (in order), weaves them with
``braidio.weave_timeline`` (duck/crossfade/loudness from the weave-config),
and emits one ``episode-render/v1`` referencing the assembled audio. It
derives from ``[*members, weave-config]``, so any member re-render (or a
config change) re-stales the episode — the top of the partial-re-render DAG.

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
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    NARRATION_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    EPISODE_RENDER_V1,
    EpisodeRenderBodyV1,
)
from braidio.transforms._common import (
    TIER_WEAVE_CONFIG,
    TIER_NARRATION_RENDER,
    TIER_EPISODE_RENDER,
    singleton,
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
_VERSION = "1"


@register_transform(NAME)
class WeaveToEpisode(BaseTransform):
    """All member renders (+ weave-config) → one ``episode-render/v1``."""

    name = NAME
    input_kinds = (NARRATION_RENDER_V1, SEGMENT_EXTRACTION_V1, WEAVE_CONFIG_V1)
    output_kind = EPISODE_RENDER_V1
    is_batch = True

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        members = tuple(inputs.primary)
        cfg = singleton(project, TIER_WEAVE_CONFIG)
        ordered_member_ids = tuple(str(a.id) for a in members)

        full = TransformInputs(primary=members, context={WEAVE_CONFIG_V1: (cfg,)})
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_EPISODE_RENDER,
            reference=node_ref(TIER_EPISODE_RENDER),
            body=EpisodeRenderBodyV1(
                profile="personal", ordered_member_ids=ordered_member_ids
            ).model_dump(),
            body_schema_uri=EPISODE_RENDER_V1,
            provenance=derive_provenance(
                self.name, _VERSION, full, attributed_to="agent:braidio"
            ),
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

        items = [
            TimelineItem(
                kind=("narration" if m.tier == TIER_NARRATION_RENDER else "clip"),
                path=str(url_to_path(m.body["url"])),
                placement="sequential",
            )
            for m in members
        ]

        cfg = require_tier(resolve_parents(skel, index), TIER_WEAVE_CONFIG)
        config = cfg.body.get("config", {})

        out_path = project.root / "data" / "episodes" / f"{skel.id}.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        braidio.weave_timeline(
            items,
            out_path,
            clip_edge_overlap_s=float(config.get("clip_edge_overlap_s", 0.5)),
            narration_crossfade_s=float(config.get("crossfade_s", 0.12)),
            target_lufs=float(config.get("target_lufs", -16.0)),
            true_peak=float(config.get("true_peak_dbtp", -1.0)),
            sample_rate=int(config.get("sample_rate", 44100)),
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
