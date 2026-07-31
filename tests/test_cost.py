"""Tests for :mod:`braidio.cost` — the ElevenLabs TTS cost model.

Covers the configurable rate (env override / disable / bad value), per-character
cost, and the Script-aware :func:`braidio.estimate_cost` (narration + dialogue are
billed, segments are free; the published profile synthesizes clip substitutes).
"""

import pytest

from braidio import Script, Narration, Dialogue, SegmentBeat
from braidio.cost import (
    RATE_ENV_VAR,
    DEFAULT_USD_PER_1K_CHARS,
    CostEstimate,
    billable_chars,
    usd_per_1k_chars,
    tts_cost_usd,
    estimate_cost,
)


@pytest.fixture(autouse=True)
def _clear_rate_env(monkeypatch):
    """Start each test with the rate env var unset (module default in effect)."""
    monkeypatch.delenv(RATE_ENV_VAR, raising=False)


# --- rate resolution ---------------------------------------------------------


def test_billable_chars_counts_whole_string():
    assert billable_chars("hello") == 5
    assert billable_chars("") == 0
    assert billable_chars(None) == 0


def test_default_rate_when_env_unset():
    assert usd_per_1k_chars() == DEFAULT_USD_PER_1K_CHARS


def test_env_overrides_rate(monkeypatch):
    monkeypatch.setenv(RATE_ENV_VAR, "0.5")
    assert usd_per_1k_chars() == 0.5


def test_env_can_disable_pricing(monkeypatch):
    monkeypatch.setenv(RATE_ENV_VAR, "none")
    assert usd_per_1k_chars() is None


def test_bad_env_rate_is_unpriced(monkeypatch):
    monkeypatch.setenv(RATE_ENV_VAR, "not-a-number")
    assert usd_per_1k_chars() is None


# --- per-text cost -----------------------------------------------------------


def test_tts_cost_empty_is_zero_not_none():
    assert tts_cost_usd("") == 0.0


def test_tts_cost_scales_with_chars():
    assert tts_cost_usd("x" * 1000) == pytest.approx(DEFAULT_USD_PER_1K_CHARS)
    assert tts_cost_usd("x" * 2000) == pytest.approx(2 * DEFAULT_USD_PER_1K_CHARS)


def test_tts_cost_unpriced_returns_none_but_empty_still_zero(monkeypatch):
    monkeypatch.setenv(RATE_ENV_VAR, "none")
    assert tts_cost_usd("some real text") is None
    assert tts_cost_usd("") == 0.0


# --- estimate over a Script --------------------------------------------------


def test_estimate_str():
    est = estimate_cost("a" * 500)
    assert isinstance(est, CostEstimate)
    assert est.characters == 500
    assert est.usd == pytest.approx(0.5 * DEFAULT_USD_PER_1K_CHARS)
    assert est.unpriced is False


def test_estimate_script_bills_narration_and_dialogue_only():
    script = Script(
        title="t",
        id_slug="01",
        beats=[
            Narration(text="a" * 100),
            SegmentBeat(reference="clip:1"),  # extracted media = free
            Dialogue(turns=(("A", "b" * 30), ("B", "c" * 20))),
        ],
    )
    est = estimate_cost(script)
    assert est.characters == 100 + 50  # narration + dialogue turns; clip is free
    assert est.usd == pytest.approx(0.150 * DEFAULT_USD_PER_1K_CHARS)
    assert len(est.items) == 2  # the segment beat contributes no billable item
    assert {it.kind for it in est.items} == {"narration", "dialogue"}


def test_estimate_all_segments_is_free():
    script = Script(
        title="t",
        id_slug="01",
        beats=[SegmentBeat(reference="a"), SegmentBeat(reference="b")],
    )
    est = estimate_cost(script)
    assert est.characters == 0
    assert est.usd == 0.0
    assert est.unpriced is False


def test_estimate_unpriced_flags_but_still_counts_chars(monkeypatch):
    monkeypatch.setenv(RATE_ENV_VAR, "none")
    script = Script(title="t", id_slug="01", beats=[Narration(text="x" * 100)])
    est = estimate_cost(script)
    assert est.characters == 100
    assert est.unpriced is True
    assert est.usd is None


def test_estimate_published_profile_synthesizes_clip_substitute():
    script = Script(
        title="t",
        id_slug="01",
        beats=[SegmentBeat(reference="clip:1", published_substitute="y" * 40)],
    )
    assert estimate_cost(script).characters == 0  # personal cut plays the clip free
    assert estimate_cost(script, published=True).characters == 40  # substitute is TTS


def test_estimate_summary_is_human_readable():
    est = estimate_cost("a" * 1000)
    assert "1,000 chars" in est.summary
    assert "$" in est.summary
