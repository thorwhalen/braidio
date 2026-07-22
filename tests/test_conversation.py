"""Tests for the conversational register (braidio#1). Audio-free / API-free."""

from __future__ import annotations

import braidio
from braidio.conversation import ConversationCast, DEFAULT_CAST


def test_default_cast_is_two_distinct_conversational_voices():
    assert set(DEFAULT_CAST.roles) == {"A", "B"}
    assert len(set(DEFAULT_CAST.roles.values())) == 2  # two distinct voices
    assert DEFAULT_CAST.model_id == "eleven_v3"  # dialogue needs v3


def test_cast_is_overridable():
    cast = ConversationCast(roles={"A": "v1", "B": "v2"}, model_id="eleven_v3", settings={"stability": "Creative"})
    assert cast.roles["A"] == "v1" and cast.settings["stability"] == "Creative"


def test_conversational_api_is_exported():
    for name in ("text_to_dialogue", "render_dialogue", "render_turns_sequential", "ConversationCast"):
        assert hasattr(braidio, name), name
