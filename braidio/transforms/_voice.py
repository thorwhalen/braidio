"""``beat_to_voice_assignment.default`` — assign a voice to a narrative beat.

A deterministic, no-synthesis Transform: given a narrative beat and the
weave-config (the voice pool + seed), it records which voice the beat's
narration will use. It derives from ``[beat, weave-config]`` so a pool/seed
change re-stales every voice-assignment (and, transitively, the narration
renders that read them) — the freshness edge braidio's ``record_render``
models, now on the nw project graph.

v1 uses a simple deterministic pick from the pool; sophisticated casting
(``braidio.assign_voices`` avoid-immediate-repeat over the whole script) is a
documented follow-up.
"""

from __future__ import annotations

import uuid
from typing import Optional

from falaw import Plan
from lacing import Annotation
from nw import BaseTransform, TransformInputs, TransformResult, register_transform
from nw.transforms._provenance import derive_provenance

from braidio.bodies._domain import NARRATIVE_BEAT_V1
from braidio.bodies._render_nodes import (
    WEAVE_CONFIG_V1,
    VOICE_ASSIGNMENT_V1,
    VoiceAssignmentBodyV1,
)
from braidio.tts import DEFAULT_VOICE_ID
from braidio.transforms._common import (
    TIER_VOICE_ASSIGNMENT,
    singleton,
)

NAME = "beat_to_voice_assignment.default"


def _pick_voice(voices: list[str], *, seed: int, ordinal: int) -> str:
    """Deterministic voice for beat ``ordinal`` from ``voices`` (+ ``seed``)."""
    if not voices:
        return DEFAULT_VOICE_ID
    if len(voices) == 1:
        return voices[0]
    return voices[(seed + ordinal) % len(voices)]


@register_transform(NAME)
class BeatToVoiceAssignment(BaseTransform):
    """Narrative beat (+ weave-config) → ``voice-assignment/v1``."""

    name = NAME
    input_kinds = (NARRATIVE_BEAT_V1, WEAVE_CONFIG_V1)
    output_kind = VOICE_ASSIGNMENT_V1

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        beat = inputs.primary[0]
        cfg = singleton(project, "weave-configs")
        config = cfg.body.get("config", {})
        voices = list(config.get("voices") or [DEFAULT_VOICE_ID])
        seed = int(config.get("voice_seed", 0))
        pool_label = config.get("pool_label", "single")
        ordinal = int(beat.body.get("beat_id", "0") or 0)
        voice_id = _pick_voice(voices, seed=seed, ordinal=ordinal)

        full = TransformInputs(primary=(beat,), context={WEAVE_CONFIG_V1: (cfg,)})
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_VOICE_ASSIGNMENT,
            reference=beat.reference,
            body=VoiceAssignmentBodyV1(
                voice_id=voice_id, pool_label=pool_label, seed=seed
            ).model_dump(),
            body_schema_uri=VOICE_ASSIGNMENT_V1,
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
        # No synthesis — a voice assignment is pure data. Override execute()
        # because the BaseTransform default maps fal artifacts onto skeletons
        # (there are none here).
        ann = skeleton[0]
        project.graph.add_annotation(ann)
        return TransformResult(
            annotations=(ann,),
            artifacts=(),
            cost_usd_actual=0.0,
            cache_hit_savings_usd=0.0,
        )
