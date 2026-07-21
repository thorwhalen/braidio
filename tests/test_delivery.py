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
