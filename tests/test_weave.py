"""Tests for the timeline weaver placement math. Audio-free."""

from __future__ import annotations

from braidio.weave import TimelineItem, layout_placed, layout_starts


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
    assert it.placement == "sequential" and it.duck_db == 0.0


def test_under_clip_overlays_following_without_advancing_cursor():
    kinds = ["narration", "clip", "narration"]
    durs = [3.0, 5.0, 4.0]
    placements = ["sequential", "under", "sequential"]
    starts = layout_placed(
        kinds, durs, placements, clip_edge_overlap_s=0.5, narration_crossfade_s=0.1
    )
    assert starts[0] == 0.0  # narration0: 0..3
    assert round(starts[1], 3) == 3.0  # under clip starts at the cursor, concurrent
    # the following narration ignores the under-clip (cursor not advanced): it
    # butt-joins narration0 with a crossfade → the clip plays *under* it
    assert round(starts[2], 3) == 2.9
    end = max(s + d for s, d in zip(starts, durs))
    assert round(end, 3) == 8.0  # the long under-clip tail defines the length


def test_layout_starts_matches_all_sequential_layout_placed():
    kinds = ["narration", "clip", "narration"]
    durs = [3.0, 4.0, 3.0]
    a = layout_starts(kinds, durs, clip_edge_overlap_s=0.5, narration_crossfade_s=0.1)
    b = layout_placed(
        kinds, durs, ["sequential"] * 3, clip_edge_overlap_s=0.5, narration_crossfade_s=0.1
    )
    assert a == b
