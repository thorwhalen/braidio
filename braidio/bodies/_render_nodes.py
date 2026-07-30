"""Render-provenance body schemas — record the render *choices* + outputs.

These make a render traceable and **partially re-renderable**: each output node
records what it was derived from (via the annotation's
``provenance.was_derived_from``) plus a **cache key** hashing the inputs that
actually affect the audio. Change one beat or one parameter → only its
descendants are stale (see :mod:`braidio.provenance`). See the design in
``misc/docs/Extraction and nw-App Design.md`` and nw's render-provenance doc.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

from lacing.schema import register_body_schema

WEAVE_CONFIG_V1 = "annot://schema/weave-config/v1"
SOURCE_MEDIA_V1 = "annot://schema/source-media/v1"
VOICE_ASSIGNMENT_V1 = "annot://schema/voice-assignment/v1"
NARRATION_RENDER_V1 = "annot://schema/narration-render/v1"
SEGMENT_EXTRACTION_V1 = "annot://schema/segment-extraction/v1"
EPISODE_RENDER_V1 = "annot://schema/episode-render/v1"


class WeaveConfigBodyV1(BaseModel):
    """A frozen snapshot of every render choice (``WeaveConfig.to_dict()``)."""

    model_config = {"frozen": True, "extra": "forbid"}

    config: dict[str, Any] = Field(..., description="The full WeaveConfig snapshot.")


class SourceMediaBodyV1(BaseModel):
    """A pointer to an imported source asset (its content-addressed artifact)."""

    model_config = {"frozen": True, "extra": "forbid"}

    label: str = Field(
        ..., description="Human label for the source (e.g. a song title)."
    )
    asset_id: str = Field(
        ..., description="lacing Artifact asset_id of the source media."
    )
    rights: str = Field("owned-local", description="Rights posture of the source.")


class VoiceAssignmentBodyV1(BaseModel):
    """Which voice a turn got (+ pool + seed) — a render choice."""

    model_config = {"frozen": True, "extra": "forbid"}

    voice_id: str = Field(..., description="Voice id used for this turn.")
    pool_label: str = Field("single", description="Pool the voice was drawn from.")
    seed: int = Field(0, description="Assignment seed (for reproducibility).")


class NarrationRenderBodyV1(BaseModel):
    """The audio Artifact for one synthesized narration turn + its cache key."""

    model_config = {"frozen": True, "extra": "forbid"}

    cache_key: str = Field(..., description="hash(text, voice, model, settings).")
    artifact_id: Optional[str] = Field(
        None, description="lacing Artifact asset_id (once rendered)."
    )
    url: Optional[str] = Field(
        None, description="file:// (or hosted) URL of the rendered audio."
    )
    duration_s: float = Field(0.0, description="Rendered duration, seconds.")


class SegmentExtractionBodyV1(BaseModel):
    """The cut+padded audio Artifact for one segment + its cache key."""

    model_config = {"frozen": True, "extra": "forbid"}

    cache_key: str = Field(
        ..., description="hash(source asset, start, end, pads, fades)."
    )
    start_s: float = Field(..., description="Padded extraction start (seconds).")
    end_s: float = Field(..., description="Padded extraction end (seconds).")
    artifact_id: Optional[str] = Field(None, description="lacing Artifact asset_id.")
    url: Optional[str] = Field(
        None, description="file:// (or hosted) URL of the extracted audio."
    )


class EpisodeRenderBodyV1(BaseModel):
    """The assembled output Artifact for an episode + its profile."""

    model_config = {"frozen": True, "extra": "forbid"}

    profile: str = Field(..., description="Render profile: personal | published.")
    ordered_member_ids: tuple[str, ...] = Field(
        default_factory=tuple, description="Ids of the member render nodes, in order."
    )
    artifact_id: Optional[str] = Field(None, description="lacing Artifact of the mix.")
    url: Optional[str] = Field(
        None, description="file:// (or hosted) URL of the assembled episode audio."
    )
    duration_s: float = Field(0.0, description="Total duration, seconds.")


RENDER_SCHEMAS: dict[str, type[BaseModel]] = {
    WEAVE_CONFIG_V1: WeaveConfigBodyV1,
    SOURCE_MEDIA_V1: SourceMediaBodyV1,
    VOICE_ASSIGNMENT_V1: VoiceAssignmentBodyV1,
    NARRATION_RENDER_V1: NarrationRenderBodyV1,
    SEGMENT_EXTRACTION_V1: SegmentExtractionBodyV1,
    EPISODE_RENDER_V1: EpisodeRenderBodyV1,
}

for _uri, _model in RENDER_SCHEMAS.items():
    register_body_schema(_uri, _model)
