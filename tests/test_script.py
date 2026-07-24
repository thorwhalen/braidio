"""Tests for the composition model (Script/beats). Audio-free / API-free."""

from __future__ import annotations

import pytest

from braidio.script import CLIP_PLACEMENTS, Narration, SegmentBeat


def test_segment_placement_defaults_and_validates():
    assert SegmentBeat("ref").placement == "before"  # default: clean set-up→clip
    for p in CLIP_PLACEMENTS:
        assert SegmentBeat("ref", placement=p).placement == p
    with pytest.raises(ValueError):
        SegmentBeat("ref", placement="beside")


def test_narration_per_beat_overrides():
    n = Narration("hi", voice="V", voice_settings={"stability": 0.5}, lead_gap_s=0.4)
    assert n.voice == "V" and n.voice_settings == {"stability": 0.5} and n.lead_gap_s == 0.4
    assert Narration("hi").voice is None and Narration("hi").voice_settings is None
