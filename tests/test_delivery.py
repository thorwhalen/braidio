"""Tests for delivery presets. Audio-free / API-free."""

from __future__ import annotations

from braidio.delivery import BASELINE, DELIVERIES, Delivery


def test_presets_well_formed():
    for name, d in DELIVERIES.items():
        assert isinstance(d, Delivery) and d.name == name
        assert d.model_id and isinstance(d.voice_settings, dict)
    assert DELIVERIES["v3-creative"].supports_audio_tags
    assert not BASELINE.supports_audio_tags


def test_baseline_matches_flat_default():
    vs = BASELINE.voice_settings
    assert vs["stability"] == 0.5 and vs["style"] == 0.0


def test_register_presets_narration_and_conversational():
    from braidio.delivery import CONVERSATIONAL, NARRATION, V2_TUNED

    assert DELIVERIES["narration"] is NARRATION
    assert DELIVERIES["conversational"] is CONVERSATIONAL
    # narration = the reading register, kept in lock-step with V2_TUNED
    assert NARRATION.model_id == "eleven_multilingual_v2"
    assert NARRATION.voice_settings == V2_TUNED.voice_settings
    # conversational = eleven_v3, loosened stability, audio tags on
    assert CONVERSATIONAL.model_id == "eleven_v3"
    assert CONVERSATIONAL.supports_audio_tags
    assert CONVERSATIONAL.voice_settings["stability"] == 0.35
