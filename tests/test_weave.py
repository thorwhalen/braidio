"""Tests for the timeline weaver placement math. Audio-free."""

from __future__ import annotations

from braidio.weave import TimelineItem, layout_starts


def test_narration_only_butt_joins_with_crossfade():
    starts = layout_starts(
        ["narration", "narration", "narration"], [2.0, 2.0, 2.0],
        clip_edge_overlap_s=0.5, narration_crossfade_s=0.1,
    )
    assert starts[0] == 0.0
    assert round(starts[1], 3) == 1.9
    assert round(starts[2], 3) == 3.8


def test_clip_overlaps_both_neighbours():
    kinds = ["narration", "clip", "narration"]
    durs = [3.0, 4.0, 3.0]
    starts = layout_starts(kinds, durs, clip_edge_overlap_s=0.5, narration_crossfade_s=0.1)
    assert round(starts[1], 3) == 2.5
    assert round(starts[2], 3) == 6.0
    total = starts[-1] + durs[-1]
    assert round(total, 3) == 9.0


def test_no_negative_starts():
    assert layout_starts(["clip"], [2.0], clip_edge_overlap_s=0.5, narration_crossfade_s=0.1) == [0.0]


def test_timeline_item_shape():
    it = TimelineItem("clip", "/tmp/x.mp3")
    assert it.kind == "clip" and it.path.endswith(".mp3")
