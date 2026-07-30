"""``narration_render.tts`` — synthesize one narration beat to audio.

A **local-render** Transform (no fal call): ``plan`` returns a zero-call
``Plan`` + a ``narration-render/v1`` skeleton carrying a ``cache_key`` over
the audio-affecting inputs; ``execute`` synthesizes via ``braidio.narrate``
(ElevenLabs), unless an identical ``cache_key`` already has an artifact
(compare-and-skip). It derives from ``[beat, voice-assignment, weave-config]``.

The skeleton's ``provenance.was_derived_from`` records exactly those inputs;
``execute`` re-resolves them from the graph (it receives no ``inputs``) and
writes the completed node through ``project.graph`` so ``nw.stale_after``
sees it.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

from falaw import Plan
from lacing import Annotation
from mixing._cache import sha256_key
from nw import BaseTransform, TransformInputs, TransformResult, register_transform
from nw.transforms._provenance import derive_provenance

from braidio.bodies._domain import NARRATIVE_BEAT_V1
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    VOICE_ASSIGNMENT_V1,
    NARRATION_RENDER_V1,
    NarrationRenderBodyV1,
)
from braidio.tts import DEFAULT_MODEL_ID, DEFAULT_VOICE_ID
from braidio.transforms._common import (
    TIER_NARRATIVE_BEAT,
    TIER_VOICE_ASSIGNMENT,
    TIER_WEAVE_CONFIG,
    TIER_NARRATION_RENDER,
    child_at_tier,
    singleton,
    graph_index,
    resolve_parents,
    require_tier,
    cached_output,
    audio_artifact,
    safe_duration,
    file_url,
)

NAME = "narration_render.tts"
_VERSION = "1"


def _narration_cache_key(text: str, voice_id: str, model_id: str, settings) -> str:
    return sha256_key(
        "narration",
        text,
        voice_id,
        model_id,
        json.dumps(settings or {}, sort_keys=True),
    )


@register_transform(NAME)
class NarrationRenderTTS(BaseTransform):
    """Narrative beat (+ voice-assignment + weave-config) → ``narration-render/v1``."""

    name = NAME
    input_kinds = (NARRATIVE_BEAT_V1, VOICE_ASSIGNMENT_V1, WEAVE_CONFIG_V1)
    output_kind = NARRATION_RENDER_V1

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        beat = inputs.primary[0]
        cfg = singleton(project, TIER_WEAVE_CONFIG)
        va = child_at_tier(project, TIER_VOICE_ASSIGNMENT, beat.id)

        config = cfg.body.get("config", {})
        voice_id = va.body.get("voice_id") or DEFAULT_VOICE_ID
        model_id = config.get("model_id", DEFAULT_MODEL_ID)
        settings = config.get("voice_settings", {})
        cache_key = _narration_cache_key(
            beat.body.get("text", ""), voice_id, model_id, settings
        )

        full = TransformInputs(
            primary=(beat,),
            context={VOICE_ASSIGNMENT_V1: (va,), WEAVE_CONFIG_V1: (cfg,)},
        )
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_NARRATION_RENDER,
            reference=beat.reference,
            body=NarrationRenderBodyV1(cache_key=cache_key).model_dump(),
            body_schema_uri=NARRATION_RENDER_V1,
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
        import braidio  # runtime attr access so tests can monkeypatch narrate

        skel = skeleton[0]
        cache_key = skel.body["cache_key"]
        if use_cache and not force:
            hit = cached_output(project, TIER_NARRATION_RENDER, cache_key)
            if hit is not None:
                return TransformResult(
                    annotations=(hit,), artifacts=(), cost_usd_actual=0.0
                )

        parents = resolve_parents(skel, graph_index(project))
        beat = require_tier(parents, TIER_NARRATIVE_BEAT)
        va = require_tier(parents, TIER_VOICE_ASSIGNMENT)
        cfg = require_tier(parents, TIER_WEAVE_CONFIG)
        config = cfg.body.get("config", {})

        out_path = project.root / "data" / "tts" / f"{skel.id}.mp3"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        braidio.narrate(
            beat.body.get("text", ""),
            out_path,
            api_key=None,  # resolved from env; key injection is a follow-up
            voice_id=va.body.get("voice_id") or DEFAULT_VOICE_ID,
            model_id=config.get("model_id", DEFAULT_MODEL_ID),
            voice_settings=config.get("voice_settings", {}),
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
