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
    #: Whether the model honors ``voice_settings["speed"]``. **False for eleven
    #: v3**, which has no speed control at all ("Speed is not available for the
    #: Eleven v3 model"), so sending one there is undefined. The paced narration
    #: path (:mod:`braidio.pacing`) reads this: on a speedless model it plans no
    #: speed and varies tempo through real inter-turn silence, punctuation and
    #: audio tags instead.
    supports_speed: bool = True
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

# --- role deliveries: a *presenter* (lively) vs a *narrator* (grave) ----------
# Two deliveries meant to sit together in one production for tasteful contrast:
# the host/presenter reads livelier and a touch quicker; the documentary/book
# narrator reads steadier, flatter-styled and a touch slower (gravitas). Assign
# per beat via ``Narration.voice_settings`` (see braidio.render).

V2_PRESENTER = Delivery(
    name="v2-presenter",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.35,
        "similarity_boost": 0.75,
        "style": 0.35,
        "use_speaker_boost": True,
        "speed": 0.98,
    },
    note="Host/presenter commentary — lively (== v2-tuned), for the spine voice.",
)

V2_NARRATOR = Delivery(
    name="v2-narrator",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.5,
        "similarity_boost": 0.8,
        "style": 0.12,
        "use_speaker_boost": True,
        "speed": 0.94,
    },
    note="Documentary/book-read narrator — steadier, flatter style, a touch "
    "slower for gravitas. Modest contrast against v2-presenter.",
)

V3_NATURAL = Delivery(
    name="v3-natural",
    model_id="eleven_v3",
    voice_settings={"stability": 0.5, "use_speaker_boost": True},
    supports_audio_tags=True,
    supports_speed=False,
    note="Eleven v3, clean text (no tags) — v3's baseline is more dynamic.",
)

V3_CREATIVE = Delivery(
    name="v3-creative",
    model_id="eleven_v3",
    voice_settings={"stability": 0.3, "use_speaker_boost": True},
    supports_audio_tags=True,
    supports_speed=False,
    note="Eleven v3, low stability, driven by inline audio tags. Alpha; per-take variance.",
)

# --- v3 role deliveries: the defaults for the narration-heavy formats ---------
# The v2 pair above cannot render audio tags at all, so a solo script literally
# could not use ``[pause]`` / ``[dryly]`` out of the box. These are the same two
# roles on ``eleven_v3``, whose baseline is more dynamic and whose tags fire.
# Stability follows the research table: 0.5 ("Natural") is the balanced default,
# ~0.4 for a livelier presenter; never 1.0 ("Robust" mutes tags and IS the
# robotic voice). Neither model has a speed knob, so tempo variation comes from
# :mod:`braidio.pacing` (real inter-turn silence) plus punctuation and tags.

V3_PRESENTER = Delivery(
    name="v3-presenter",
    model_id="eleven_v3",
    voice_settings={"stability": 0.4, "use_speaker_boost": True},
    supports_audio_tags=True,
    supports_speed=False,
    note="Host/presenter commentary on v3 — livelier, audio tags fire. The "
    "narration-spine default (solo_explainer).",
)

V3_NARRATOR = Delivery(
    name="v3-narrator",
    model_id="eleven_v3",
    voice_settings={"stability": 0.5, "use_speaker_boost": True},
    supports_audio_tags=True,
    supports_speed=False,
    note="Documentary/book-read narrator on v3 — steadier than v3-presenter, "
    "still tag-responsive. Contrast partner to v3-presenter.",
)

# --- register presets: narration (reading) vs conversational (talking) --------
# The two named "registers" (issue #1). ``narration`` = the default reading
# register (kept in lock-step with V2_TUNED, render_production's default).
# ``conversational`` makes a single narrator sound like they're *talking*, not
# reading: eleven_v3 with loosened stability so inline audio tags / disfluencies
# written into the text actually fire. NOTE this is the *single-voice* register —
# distinct from the multi-speaker Dialogue path (render_dialogue / eleven_v3
# Text-to-Dialogue), which renders two voices in an exchange.

NARRATION = Delivery(
    name="narration",
    model_id="eleven_multilingual_v2",
    voice_settings={
        "stability": 0.35,
        "similarity_boost": 0.75,
        "style": 0.35,
        "use_speaker_boost": True,
        "speed": 0.98,
    },
    note="Default register: reading a script cleanly (voice settings == v2-tuned).",
)

CONVERSATIONAL = Delivery(
    name="conversational",
    model_id="eleven_v3",
    voice_settings={"stability": 0.35, "use_speaker_boost": True},
    supports_audio_tags=True,
    supports_speed=False,
    note="Register that sounds like talking, not reading: eleven_v3 with loosened "
    "stability so audio tags/disfluencies in the text fire. Pair with a "
    "conversationalized script (contractions, [tags], ellipses). Single-voice — "
    "for a two-host exchange use the Dialogue path instead.",
)

DELIVERIES: dict[str, Delivery] = {
    d.name: d
    for d in (
        BASELINE,
        V2_TUNED,
        V2_AGGRESSIVE,
        V2_PRESENTER,
        V2_NARRATOR,
        V3_NATURAL,
        V3_CREATIVE,
        V3_PRESENTER,
        V3_NARRATOR,
        NARRATION,
        CONVERSATIONAL,
    )
}
