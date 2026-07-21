"""Tests for the segment resolver + SegmentSource protocol. Audio-free."""

from __future__ import annotations

from braidio.sources import (
    ResolvedSegment,
    SegmentSource,
    TimedLine,
    TimedLineSegmentSource,
    find_segment,
)

LINES = [
    TimedLine(0, 3.48, 7.26, "How does a bastard, orphan, son of a whore"),
    TimedLine(1, 7.26, 11.23, "And a Scotsman, dropped in the middle of a forgotten"),
    TimedLine(2, 11.23, 15.83, "Spot in the Caribbean by providence, impoverished, in squalor"),
    TimedLine(3, 18.74, 22.27, "The ten-dollar Founding Father without a father"),
]


def test_exact_line_scores_one():
    seg = find_segment(LINES, "How does a bastard, orphan, son of a whore")
    assert seg is not None and seg.score == 1.0
    assert (seg.start_s, seg.end_s) == (3.48, 7.26)
    assert seg.line_start == seg.line_end == 0


def test_sub_line_maps_to_containing_line():
    seg = find_segment(LINES, "son of a whore")
    assert seg is not None and seg.line_start == 0 and seg.start_s == 3.48


def test_multi_line_union_window():
    seg = find_segment(LINES, "And a Scotsman dropped in the middle\nSpot in the Caribbean by providence")
    assert seg is not None and seg.line_start == 1 and seg.line_end == 2
    assert seg.start_s == 7.26 and seg.end_s == 15.83


def test_no_match_returns_none():
    assert find_segment(LINES, "zebra quantum helicopter") is None


def test_tail_line_end_falls_back_to_song_end():
    tail = [TimedLine(0, 200.0, None, "Who lives, who dies, who tells your story")]
    seg = find_segment(tail, "who tells your story", song_end_s=236.77)
    assert seg is not None and seg.end_s == 236.77


def test_timed_line_segment_source_protocol():
    src = TimedLineSegmentSource(lines=LINES, asset_path="/tmp/song.mp3", song_end_s=236.77)
    assert isinstance(src, SegmentSource)  # runtime_checkable structural match
    rs = src.resolve("The ten-dollar Founding Father without a father")
    assert isinstance(rs, ResolvedSegment)
    assert str(rs.asset_path) == "/tmp/song.mp3"
    assert (rs.start_s, rs.end_s) == (18.74, 22.27)
    assert src.resolve("nothing like this appears") is None
