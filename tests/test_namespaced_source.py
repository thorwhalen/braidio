"""Tests for :class:`braidio.sources.NamespacedSegmentSource`.

Routing one reference to one of several recordings of the same work is the
only way a script can say *which* take a quote should be cut from — a token
matcher scores a lyric line equally well in every recording of it.
"""

import pytest

from braidio.sources import (
    NamespacedSegmentSource,
    SegmentSource,
    TimedLine,
    TimedLineSegmentSource,
)


def _two_recordings():
    lines = [
        TimedLine(0, 0.0, 2.0, "hello darkness my old friend"),
        TimedLine(1, 2.0, 4.0, "and in the naked light i saw"),
    ]
    studio = TimedLineSegmentSource(lines=lines, asset_path="studio.mp3")
    live = TimedLineSegmentSource(
        lines=[TimedLine(l.index, l.start_s + 10, l.end_s + 10, l.text) for l in lines],
        asset_path="live.mp3",
    )
    return NamespacedSegmentSource({"1966": studio, "1981": live})


def test_identical_references_route_to_different_assets():
    src = _two_recordings()
    a = src.resolve("1966: and in the naked light i saw")
    b = src.resolve("1981: and in the naked light i saw")
    assert a.asset_path.name == "studio.mp3" and a.start_s == 2.0
    assert b.asset_path.name == "live.mp3" and b.start_s == 12.0


def test_prefix_matching_is_case_and_space_insensitive():
    src = NamespacedSegmentSource(
        {
            " Studio ": TimedLineSegmentSource(
                lines=[TimedLine(0, 0.0, 2.0, "hello darkness")], asset_path="s.mp3"
            )
        }
    )
    assert src.namespaces == ["studio"]
    assert src.resolve("STUDIO: hello darkness").asset_path.name == "s.mp3"


def test_unknown_prefix_raises_rather_than_falling_through():
    src = _two_recordings()
    with pytest.raises(KeyError):
        src.resolve("1970: hello darkness my old friend")
    with pytest.raises(KeyError):
        src.resolve("hello darkness my old friend")  # unprefixed, no default


def test_default_namespace_accepts_unprefixed_references():
    src = NamespacedSegmentSource(
        {
            "a": TimedLineSegmentSource(
                lines=[TimedLine(0, 0.0, 2.0, "hello darkness")], asset_path="a.mp3"
            ),
            "b": TimedLineSegmentSource(
                lines=[TimedLine(0, 5.0, 7.0, "hello darkness")], asset_path="b.mp3"
            ),
        },
        default="b",
    )
    assert src.resolve("hello darkness").asset_path.name == "b.mp3"
    assert src.resolve("a: hello darkness").asset_path.name == "a.mp3"


def test_empty_sources_and_unknown_default_are_rejected():
    with pytest.raises(ValueError):
        NamespacedSegmentSource({})
    with pytest.raises(KeyError):
        NamespacedSegmentSource(
            {
                "a": TimedLineSegmentSource(
                    lines=[TimedLine(0, 0.0, 1.0, "x")], asset_path="a.mp3"
                )
            },
            default="nope",
        )


def test_satisfies_the_segment_source_protocol():
    assert isinstance(_two_recordings(), SegmentSource)
