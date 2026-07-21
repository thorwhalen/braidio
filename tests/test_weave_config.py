"""Tests for WeaveConfig + config-driven compose wiring. Audio-free."""

from __future__ import annotations

import json

import pytest

from braidio.weave_config import PRESETS, WeaveConfig, INTERVIEW_MANY, SINGLE_NARRATOR
from braidio.compose import _pool_from_config


def test_presets_wellformed():
    assert set(PRESETS) == {"single_narrator", "documentary_lyrics", "panel_4", "interview_many"}
    assert not SINGLE_NARRATOR.is_multivoice
    assert INTERVIEW_MANY.is_multivoice and len(INTERVIEW_MANY.voices) >= 8


def test_validation():
    with pytest.raises(ValueError):
        WeaveConfig(voices=())
    with pytest.raises(ValueError):
        WeaveConfig(min_turn=3, max_turn=2)


def test_to_dict_is_json_serializable():
    d = INTERVIEW_MANY.to_dict()
    s = json.dumps(d)
    assert isinstance(d["voices"], list) and isinstance(d["voice_settings"], dict)
    assert json.loads(s)["min_turn"] == INTERVIEW_MANY.min_turn


def test_with_override_is_immutable():
    base = SINGLE_NARRATOR
    changed = base.with_(min_turn=1, max_turn=1)
    assert changed.min_turn == 1 and base.min_turn == 2
    assert changed is not base


def test_config_carries_clip_and_loudness_knobs():
    c = WeaveConfig()
    assert c.clip_pre_roll_s == 0.4 and c.clip_post_roll_s == 0.3
    assert c.duck_db == -15.0 and c.target_lufs == -16.0


def test_pool_from_config_resolves_names_with_fallback():
    pool = _pool_from_config(INTERVIEW_MANY)
    assert len(pool) == len(INTERVIEW_MANY.voices)
    assert all(v.name for v in pool)
    solo = _pool_from_config(SINGLE_NARRATOR)
    assert len(solo) == 1 and solo[0].name == "George"
    unknown = _pool_from_config(WeaveConfig(voices=("zz_unknown_id",)))
    assert len(unknown) == 1 and unknown[0].id == "zz_unknown_id"
