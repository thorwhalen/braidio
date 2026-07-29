"""Tests for the timeline breakdown. Audio-free / API-free."""

from __future__ import annotations

from braidio.timeline import BeatSpan, TimelineBreakdown, build_timeline


def _sample():
    # commentary → clip → book-passage → clip → commentary
    return build_timeline(
        kinds=["narration", "clip", "book-passage", "clip", "narration"],
        durations=[30.0, 6.0, 34.0, 3.0, 20.0],
        placements=["sequential"] * 5,
        labels=["", "opening lines", "book-passage", "the line", ""],
        source_spans=[None, (4.9, 11.4), None, (53.7, 56.0), None],
        clip_edge_overlap_s=0.5, narration_crossfade_s=0.1,
        title="Sample",
    )


def test_totals_and_shares_group_by_kind():
    tl = _sample()
    assert tl.totals() == {"narration": 50.0, "clip": 9.0, "book-passage": 34.0}
    sh = tl.shares()
    assert round(sum(sh.values()), 6) == 1.0
    assert round(sh["clip"], 3) == round(9.0 / 93.0, 3)


def test_offsets_follow_the_weave_layout():
    tl = _sample()
    b = tl.beats
    assert b[0].start == 0.0                      # first narration at 0
    assert round(b[1].start, 2) == 29.5           # clip tucks 0.5s under the narration edge
    assert b[1].kind == "clip" and b[1].source_start == 4.9 and b[1].source_end == 11.4
    # end of each beat = start + duration
    assert b[2].end == round(b[2].start + 34.0, 3)
    # total duration = the max beat end
    assert tl.duration == max(x.end for x in b)


def test_source_span_only_on_clips():
    tl = _sample()
    for b in tl.beats:
        if b.kind == "clip":
            assert b.source_start is not None and b.source_end is not None
        else:
            assert b.source_start is None


def test_to_dict_roundtrips_the_shape():
    d = _sample().to_dict()
    assert d["title"] == "Sample" and len(d["beats"]) == 5
    assert d["totals"]["book-passage"] == 34.0
    assert d["beats"][1]["source"] == [4.9, 11.4]


def test_to_html_is_self_contained_and_has_the_data():
    html = _sample().to_html("My Episode", subtitle="a test")
    assert html.strip().startswith("<!doctype html>")
    assert "My Episode" in html and "a test" in html
    assert "<table" in html and "<style" in html
    assert "http" not in html  # no external resources (CSP-safe)


def test_empty_timeline_is_safe():
    tl = TimelineBreakdown()
    assert tl.totals() == {} and tl.duration == 0.0
    assert tl.shares() == {}
    assert "<!doctype html>" in tl.to_html("Empty")


def test_beatspan_end_property():
    b = BeatSpan(index=0, kind="clip", duration=2.5, start=10.0)
    assert b.end == 12.5
