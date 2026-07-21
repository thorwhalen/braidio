"""WeaveConfig — every editing choice for weaving narration + segments (#20).

One frozen config object that exposes **all** the knobs (casting, turns, pacing,
timing, clip weaving, loudness) so a composer picks combinations rather than
inheriting one hardcoded style (the "enable all choices" mandate of #18/#28).

Defaults come from ``docs/research/podcast-audio-weaving-editing.md``. This
module is deliberately **Hamilton-agnostic** — no Genius/LRCLIB/episode imports —
so it can move to the reusable weave package unchanged (#19). It references the
generic voice pools/ids only.

The config is designed to serialize cleanly (:meth:`WeaveConfig.to_dict`) into a
``render-config`` provenance node (#26), so a render is reproducible from its
recorded choices.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Any, Mapping

from braidio.multivoice import POOL_4, POOL_MANY
from braidio.tts import DEFAULT_VOICE_ID

# Research-recommended base narration settings (v2-tuned).
_DEFAULT_VOICE_SETTINGS: dict[str, Any] = {
    "stability": 0.35,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True,
}


@dataclass(frozen=True)
class WeaveConfig:
    """All editing choices for a narration+segment weave. Frozen + serializable."""

    # --- Casting ------------------------------------------------------------
    voices: tuple[str, ...] = (DEFAULT_VOICE_ID,)  # 1 id = single; >1 = cycled pool
    pool_label: str = "single"
    voice_seed: int = 7
    avoid_immediate_repeat: bool = True

    # --- Delivery (TTS) -----------------------------------------------------
    model_id: str = "eleven_multilingual_v2"
    voice_settings: Mapping[str, Any] = field(
        default_factory=lambda: dict(_DEFAULT_VOICE_SETTINGS)
    )

    # --- Segmentation / turns ----------------------------------------------
    segmentation_unit: str = "sentence"  # sentence | clause | paragraph | beat
    min_turn: int = 2  # segments a voice speaks before switching
    max_turn: int = 4

    # --- Pacing -------------------------------------------------------------
    speed_base: float = 1.0
    speed_jitter: float = 0.04  # ± per turn

    # --- Timing between turns ----------------------------------------------
    crossfade_s: float = 0.12
    gap_turn_s: float = 0.0  # silence between turns (mutually exclusive w/ crossfade)
    overlap_turn_s: float = 0.0  # speaker interruption (#22 — not yet rendered)

    # --- Clip weaving (#21) -------------------------------------------------
    clip_pre_roll_s: float = 0.4  # extend extraction before the words
    clip_post_roll_s: float = 0.3  # …and after — capture words cleanly
    clip_fade_in_s: float = 0.5
    clip_fade_out_s: float = 0.8
    clip_edge_overlap_s: float = 0.5  # tuck faded clip edges under narration
    duck_db: float = -15.0  # duck clip under speech (speech dominant)

    # --- Global mix ---------------------------------------------------------
    target_lufs: float = -16.0
    true_peak_dbtp: float = -1.0
    sample_rate: int = 44100

    def __post_init__(self) -> None:
        if not self.voices:
            raise ValueError("WeaveConfig.voices must have at least one voice id")
        if not (1 <= self.min_turn <= self.max_turn):
            raise ValueError("require 1 <= min_turn <= max_turn")

    @property
    def is_multivoice(self) -> bool:
        return len(self.voices) > 1

    def with_(self, **changes: Any) -> "WeaveConfig":
        """Return a copy with fields overridden (e.g. ``cfg.with_(min_turn=1)``)."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        """Stable serialization for a ``render-config`` provenance node (#26)."""
        d = asdict(self)
        d["voices"] = list(self.voices)
        d["voice_settings"] = dict(self.voice_settings)
        return d


# --- Presets -----------------------------------------------------------------

_POOL_4_IDS = tuple(v.id for v in POOL_4)
_POOL_MANY_IDS = tuple(v.id for v in POOL_MANY)

SINGLE_NARRATOR = WeaveConfig(
    voices=(DEFAULT_VOICE_ID,), pool_label="single"
)

DOCUMENTARY_LYRICS = WeaveConfig(  # the research default: one narrator, tight turns
    voices=(DEFAULT_VOICE_ID,), pool_label="single", min_turn=1, max_turn=3
)

PANEL_4 = WeaveConfig(
    voices=_POOL_4_IDS, pool_label="panel-4", min_turn=2, max_turn=4
)

INTERVIEW_MANY = WeaveConfig(  # Hamilton's chosen default
    voices=_POOL_MANY_IDS, pool_label="interview-many", min_turn=2, max_turn=4
)

PRESETS: dict[str, WeaveConfig] = {
    "single_narrator": SINGLE_NARRATOR,
    "documentary_lyrics": DOCUMENTARY_LYRICS,
    "panel_4": PANEL_4,
    "interview_many": INTERVIEW_MANY,
}
