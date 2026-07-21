"""Narration *delivery* presets — model + voice settings (issue #10, expressiveness).

A :class:`Delivery` bundles the ElevenLabs ``model_id`` and ``voice_settings``
that shape how expressive vs flat a narration reads. The renderer takes one so
we can A/B the same script under different deliveries and pick what has the most
relief without editing the script.

Presets here are a starting point tuned from ``docs/research/expressive-tts-
narration.md``; refine as we learn what sounds best. The key monotony levers:
lower ``stability`` and raise ``style`` add variation (at some cost in
consistency); ``eleven_v3`` adds inline audio tags for real expressive control.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Delivery:
    """A named narration delivery: which model + voice settings to synthesize with."""

    name: str
    model_id: str
    voice_settings: dict = field(default_factory=dict)
    supports_audio_tags: bool = False  # True for eleven_v3 (bracketed [tags])
    note: str = ""


# --- presets -----------------------------------------------------------------

BASELINE = Delivery(
    name="baseline",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.5,
        "similarity_boost": 0.75,
        "style": 0.0,
        "use_speaker_boost": True,
        "speed": 0.97,
    },
    note="Current default — even, safe, tends flat.",
)

# ★ Research-recommended default: v2, moderately loosened + annotated text.
V2_TUNED = Delivery(
    name="v2-tuned",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.35,
        "similarity_boost": 0.75,
        "style": 0.35,
        "use_speaker_boost": True,
        "speed": 0.98,
    },
    note="★ recommended: lower stability + raised style; pairs with annotated text.",
)

V2_AGGRESSIVE = Delivery(
    name="v2-aggressive",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.28,
        "similarity_boost": 0.75,
        "style": 0.45,
        "use_speaker_boost": True,
        "speed": 0.98,
    },
    note="More variation, more take-to-take variance; may over-emote.",
)

V3_NATURAL = Delivery(
    name="v3-natural",
    model_id="eleven_v3",
    voice_settings={"stability": 0.5, "use_speaker_boost": True},
    supports_audio_tags=True,
    note="Eleven v3, clean text (no tags) — v3's baseline is more dynamic.",
)

V3_CREATIVE = Delivery(
    name="v3-creative",
    model_id="eleven_v3",
    voice_settings={"stability": 0.3, "use_speaker_boost": True},
    supports_audio_tags=True,
    note="Eleven v3, low stability, driven by inline audio tags. Alpha; per-take variance.",
)

DELIVERIES: dict[str, Delivery] = {
    d.name: d
    for d in (BASELINE, V2_TUNED, V2_AGGRESSIVE, V3_NATURAL, V3_CREATIVE)
}
