"""Tests for multi-voice casting primitives. Audio-free / API-free."""

from __future__ import annotations

import pytest

from braidio.multivoice import (
    POOL_4,
    POOL_MANY,
    assign_voices,
    group_turns,
    split_segments,
    strip_markup,
)


def test_pools_are_varied_and_wellformed():
    assert len(POOL_4) == 4
    assert {v.gender for v in POOL_4} == {"M", "F"}
    assert sum(v.gender == "M" for v in POOL_4) == 2
    assert len({v.id for v in POOL_MANY}) == len(POOL_MANY) >= 8


def test_split_segments_strips_markup_and_keeps_ellipses():
    text = 'A first thought… still going. <break time="0.4s"/> [curious] A SECOND one!'
    segs = split_segments(text)
    assert segs == ["A first thought… still going.", "A SECOND one!"]
    assert "<break" not in " ".join(segs) and "[curious]" not in " ".join(segs)


def test_strip_markup():
    assert strip_markup('x <break time="1s"/> y [curious] z').split() == ["x", "y", "z"]


def test_assign_voices_no_immediate_repeats_and_deterministic():
    a = assign_voices(30, POOL_4, seed=7)
    b = assign_voices(30, POOL_4, seed=7)
    assert [v.name for v in a] == [v.name for v in b]
    assert all(a[i] is not a[i - 1] for i in range(1, len(a)))
    assert {v.name for v in a} == {v.name for v in POOL_4}


def test_group_turns_sizes_and_coverage():
    segs = [f"s{i}." for i in range(20)]
    turns = group_turns(segs, min_turn=3, max_turn=3, seed=1)
    assert len(turns) == 7
    assert " ".join(turns).split() == segs
    assert len(group_turns(segs, min_turn=2, max_turn=3, seed=1)) < len(segs)
    assert group_turns(segs, min_turn=1, max_turn=1) == segs


def test_group_turns_validates_range():
    with pytest.raises(ValueError):
        group_turns(["a."], min_turn=3, max_turn=2)
