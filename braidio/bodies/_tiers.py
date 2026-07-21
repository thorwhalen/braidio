"""Generic tiers for a commentary-weave production + its render nodes.

Standoff layers (no temporal nesting); a consumer adds its own structural spine
(e.g. Hamilton's ``songs → sections → lyric-lines → words``). Add to a store
with :func:`register_tiers`.
"""

from __future__ import annotations

from lacing.tier import Tier

# Authoring layers.
_COMMENTARY = Tier("commentary")
_SOURCES = Tier("sources")
_AUDIO_CLIPS = Tier("audio-clips")
_NARRATIVE_BEATS = Tier("narrative-beats")
# Render-provenance layers.
_WEAVE_CONFIGS = Tier("weave-configs")
_SOURCE_MEDIA = Tier("source-media")
_VOICE_ASSIGNMENTS = Tier("voice-assignments")
_NARRATION_RENDERS = Tier("narration-renders")
_SEGMENT_EXTRACTIONS = Tier("segment-extractions")
_EPISODE_RENDERS = Tier("episode-renders")

TIERS: tuple[Tier, ...] = (
    _COMMENTARY, _SOURCES, _AUDIO_CLIPS, _NARRATIVE_BEATS,
    _WEAVE_CONFIGS, _SOURCE_MEDIA, _VOICE_ASSIGNMENTS,
    _NARRATION_RENDERS, _SEGMENT_EXTRACTIONS, _EPISODE_RENDERS,
)
"""braidio's generic + render tiers."""


def register_tiers(store) -> None:
    """Add every tier in :data:`TIERS` to ``store`` (has ``add_tier``)."""
    for tier in TIERS:
        store.add_tier(tier)
