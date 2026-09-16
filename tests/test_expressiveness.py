"""Tests for the expressiveness gate.

The gate exists because a real production came out flat. Its script had ten
inline tags in 1371 words -- 0.73 per 100, half the floor -- while dutifully
varying ``voice_settings["stability"]`` between 0.30 and 0.65, which is worth
about 2 Hz of pitch range. The listener's word was "somniferous".
"""

import pytest

import braidio
from braidio.style import (
    TAG_RATE_CEILING,
    TAG_RATE_FLOOR,
    audio_tag_rate,
    audio_tags,
    audit_expressiveness,
)

FLAT = (
    "The record that made them famous was a record they did not make. "
    "Listen to what the drums do to it. The tempo cannot change, because it is "
    "locked to a performance recorded fifteen months earlier."
)

LIVELY = (
    "[laughs] The record that made them famous? They didn't make it. "
    "[pause] Listen to what the drums do to it. The tempo can't change — "
    "[dryly] it's nailed to a take from fifteen months earlier — and at one "
    "point you can hear the band easing off so the voices catch up."
)

CAMP = (
    "[laughs] The record [excited] that made them [gasps] famous? "
    "[incredulous] They [sighs] didn't [whispers] make it."
)


def test_tags_are_extracted_in_order():
    assert audio_tags(LIVELY) == ["[laughs]", "[pause]", "[dryly]"]


def test_flat_script_is_flagged_below_the_floor():
    assert audio_tag_rate(FLAT) == 0.0
    findings = audit_expressiveness(FLAT)
    assert findings and "below" in findings[0]


def test_lively_script_passes():
    rate = audio_tag_rate(LIVELY)
    assert TAG_RATE_FLOOR <= rate <= TAG_RATE_CEILING
    assert audit_expressiveness(LIVELY) == []


def test_tag_on_every_clause_is_flagged_as_camp():
    findings = audit_expressiveness(CAMP)
    assert findings and any("above" in f for f in findings)


def test_one_gesture_repeated_is_its_own_monotony():
    monotone = " ".join(["[pause] A sentence here."] * 12)
    findings = audit_expressiveness(monotone)
    assert any("distinct tags" in f for f in findings)


def test_rate_is_per_hundred_words_by_default():
    text = "[pause] " + " ".join(["word"] * 100)
    assert audio_tag_rate(text) == pytest.approx(100 / 101 * 1, rel=1e-6)


def test_empty_text_does_not_divide_by_zero():
    assert audio_tag_rate("") == 0.0


def test_helpers_are_exported_from_the_package_root():
    assert braidio.audio_tag_rate is audio_tag_rate
    assert braidio.audit_expressiveness is audit_expressiveness
    assert braidio.TAG_RATE_FLOOR == TAG_RATE_FLOOR


def test_presenter_delivery_sits_at_the_expressive_end():
    # Not a style preference: stability 1.0 suppresses tags, and tags are the
    # lever that actually works.
    assert braidio.V3_PRESENTER.voice_settings["stability"] == 0.0
    assert braidio.V3_PRESENTER.supports_audio_tags


def test_v2_deliveries_still_cannot_render_tags():
    # audio_tag_rate is a lie on a model that renders tags as literal text.
    assert not braidio.V2_TUNED.supports_audio_tags
    assert not braidio.BASELINE.supports_audio_tags
