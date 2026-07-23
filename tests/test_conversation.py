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


def test_dialogue_beat_plans_and_scans():
    """A Dialogue beat plans as a 'dialogue' PlannedBeat (turns preserved,
    text joined for the published verbatim-scan)."""
    from braidio import Script, Dialogue, Narration, Profile, plan_production, content_violations

    ep = Script(title="t", id_slug="1", beats=[
        Dialogue((("A", "hi there friend"), ("B", "hey, good to see you"))),
        Narration("some narration"),
    ])
    plan = plan_production(ep, Profile.PUBLISHED)
    kinds = [b.kind for b in plan.beats]
    assert "dialogue" in kinds
    d = next(b for b in plan.beats if b.kind == "dialogue")
    assert d.turns == (("A", "hi there friend"), ("B", "hey, good to see you"))
    assert "hi there friend" in d.content  # joined text for scanning

    # a dialogue that quotes forbidden text verbatim is caught in the published cut
    bad = Script(title="t", id_slug="1", beats=[
        Dialogue((("A", "the forbidden secret phrase appears right here now"),)),
    ])
    v = content_violations(
        plan_production(bad, Profile.PUBLISHED),
        ["the forbidden secret phrase appears right here now"],
    )
    assert v and "dialogue" in v[0]


def test_dialogue_cache_avoids_second_api_call(tmp_path, monkeypatch):
    """A cache hit returns identical bytes without a second API call; cache=False
    always calls; a changed input misses the cache."""
    import braidio.tts as tts

    calls = {"n": 0}

    class _Convert:
        def convert(self, **kwargs):
            calls["n"] += 1
            return [b"FAKE-DIALOGUE-AUDIO"]

    class _Client:
        def __init__(self, *a, **k):
            self.text_to_dialogue = _Convert()

    monkeypatch.setattr("elevenlabs.client.ElevenLabs", _Client)

    turns = [("v1", "hello there"), ("v2", "hey, what's up")]
    a = tts.text_to_dialogue(turns, cache=tmp_path, seed=1, refresh=True)  # 1 call (seeds cache)
    b = tts.text_to_dialogue(turns, cache=tmp_path, seed=1)                # cache HIT → 0 calls
    assert a == b == b"FAKE-DIALOGUE-AUDIO"
    assert calls["n"] == 1

    tts.text_to_dialogue(turns, cache=False, seed=1)  # cache disabled → always calls
    assert calls["n"] == 2

    tts.text_to_dialogue([("v1", "different"), ("v2", "text")], cache=tmp_path, seed=1)  # new key → miss
    assert calls["n"] == 3
