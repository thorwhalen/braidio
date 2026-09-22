"""The picture-track bodies (commentary-studio plan §3): round-trips, the
additive fields, and the three field-level decisions that are the point.
"""

from __future__ import annotations

import json

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_GRAPH, reason="lacing (the graph layer) not available"
)


def _still(**overrides) -> dict:
    base = dict(
        key="central-park-1971",
        artifact_id="a" * 64,
        url="file:///tmp/x.jpg",
        width=1280,
        height=853,
        license="cc-by-sa-2.0",
        license_url="https://creativecommons.org/licenses/by-sa/2.0/",
        attribution="EliziR",
        source_page_url="https://commons.wikimedia.org/wiki/File:x.jpg",
        author="EliziR",
        author_url="https://commons.wikimedia.org/wiki/User:EliziR",
        cacheable=True,
        labelled=True,
        subject="The Beach Boys in Central Park, 1971 — not this concert",
        about="A genuine large concert in the right park, the wrong year.",
        crop={"x": 0.0, "y": 0.05, "w": 1.0, "h": 0.9},
        note="Right-shaped, wrong-specific: honest only while labelled.",
    )
    base.update(overrides)
    return base


# --- round trips --------------------------------------------------------------


@pytest.mark.parametrize(
    "uri, body",
    [
        ("annot://schema/still/v1", _still()),
        (
            "annot://schema/video-panel/v1",
            dict(
                still_id="0f4c6a2e-8b1d-4b6e-9c3a-2d1e5f7a9b0c",
                move="push_in",
                zoom=1.2,
                focus={"x": 0.2, "y": 0.1, "w": 0.5, "h": 0.5},
                path=None,
                seed=1234567,
                beat_id="0003",
                order=2,
                track_id="t1",
            ),
        ),
        (
            "annot://schema/video-cut/v1",
            dict(
                label="v2",
                stage="delivered",
                profile="personal",
                audio_artifact_id="b" * 64,
                panel_ids=["p1", "p2"],
                cache_key="k",
                artifact_id="c" * 64,
                url="file:///tmp/cut.mp4",
                duration_s=181.4,
                width=1920,
                height=1080,
                fps=30,
                captions_artifact_id="d" * 64,
                settings={"size": [1920, 1080], "fps": 30, "credits_s": 11.0},
                published={
                    "platform": "youtube",
                    "video_id": "abc",
                    "privacy": "private",
                },
            ),
        ),
        (
            "annot://schema/label-track/v1",
            dict(
                kind="context",
                lines=["What Hamilton is", "…"],
                headline="Before we go on",
                weight=2,
            ),
        ),
    ],
)
def test_body_round_trips_through_json(uri, body):
    from lacing.schema import get_body_schema, validate

    model = get_body_schema(uri)
    validate(body, uri)
    obj = model(**body)
    wire = json.loads(json.dumps(obj.model_dump(mode="json")))
    assert model(**wire) == obj
    # and forward-building is by model_copy, the house rule
    assert obj.model_copy(update={}) == obj


# --- the two additive fields --------------------------------------------------


def test_the_two_added_fields_are_additive_so_old_rows_still_load():
    """A narration-render or episode-render written before these fields
    existed carries neither key. It must still load, and read as the
    synthesised, timeline-less row it was — pinned because a required field
    here would force a lacing migration on every stored project."""
    from lacing.schema import validate

    from braidio.bodies import EpisodeRenderBodyV1, NarrationRenderBodyV1

    old_take = {
        "cache_key": "k",
        "artifact_id": "a" * 64,
        "url": "file:///x",
        "duration_s": 3.0,
    }
    validate(old_take, "annot://schema/narration-render/v1")
    assert NarrationRenderBodyV1(**old_take).source == "tts"

    old_episode = {"profile": "personal", "ordered_member_ids": ["a", "b"]}
    validate(old_episode, "annot://schema/episode-render/v1")
    assert EpisodeRenderBodyV1(**old_episode).timeline is None

    # and the new values round-trip when present
    assert NarrationRenderBodyV1(**old_take, source="upload").source == "upload"
    tl = {"title": "", "beats": [], "settings": None}
    assert EpisodeRenderBodyV1(**old_episode, timeline=tl).timeline == tl


# --- still: the editorial decision is explicit ----------------------------------


def test_labelled_without_a_subject_raises():
    from braidio.bodies import StillBodyV1

    with pytest.raises(ValueError, match="labelled=True but no subject"):
        StillBodyV1(**_still(subject=None))
    with pytest.raises(ValueError, match="labelled=True but no subject"):
        StillBodyV1(**_still(subject="   "))


def test_a_missing_labelled_decision_raises():
    """Neither True nor False stated: the body is refused. An unlabelled still
    beside a labelled one is an implicit claim, so the decision is required."""
    from braidio.bodies import StillBodyV1

    body = _still()
    del body["labelled"]
    with pytest.raises(ValueError):
        StillBodyV1(**body)


def test_unlabelled_is_a_deliberate_statement_not_an_absence():
    from braidio.bodies import StillBodyV1

    still = StillBodyV1(**_still(labelled=False, subject=None))
    assert still.labelled is False
    # a subject may be recorded and still not shown — two axes, not one
    assert StillBodyV1(**_still(labelled=False)).subject


# --- still: rights are illustration's, and the credit is composed ---------------


def test_rights_fields_are_named_exactly_as_illustration_names_them():
    illustration = pytest.importorskip("illustration")
    from braidio.bodies import RIGHTS_FIELDS, StillBodyV1

    assert RIGHTS_FIELDS == illustration.RIGHTS_FIELDS
    assert set(RIGHTS_FIELDS) <= set(StillBodyV1.model_fields)


def test_credit_line_is_composed_from_the_parts_never_the_attribution_string():
    """A provider's ``attribution`` can be the bare author with no licence
    named; the credit must name the licence anyway, and must refuse when
    there is none to name."""
    from braidio.bodies import credit_line

    line = credit_line(_still(attribution="EliziR"))
    assert "cc-by-sa-2.0" in line and "EliziR" in line
    assert line != "EliziR"
    with pytest.raises(ValueError, match="no licence recorded"):
        credit_line(_still(license=None))


def test_credit_line_names_the_work_not_the_editorial_subject_or_the_slot():
    """TASL: the credit's T is the work's title. The editorial ``subject``
    ("… — not this concert") is a label, and ``key`` is a slot name; neither
    belongs in an end roll."""
    from braidio.bodies import credit_line

    line = credit_line(_still(title="Beach Boys, Central Park"))
    assert line == (
        "Beach Boys, Central Park — EliziR — "
        "https://commons.wikimedia.org/wiki/File:x.jpg — cc-by-sa-2.0"
    )
    untitled = credit_line(_still())
    assert "not this concert" not in untitled and "central-park-1971" not in untitled
    assert untitled.startswith("EliziR — https://")


# --- panel: the vocabulary and the seed ------------------------------------------


def test_panel_move_must_be_in_the_vocabulary():
    from braidio.bodies import MOVES, VideoPanelBodyV1

    with pytest.raises(ValueError, match="not one of"):
        VideoPanelBodyV1(
            still_id="s", move="zoom_wildly", seed=1, order=0, track_id="t"
        )
    for move in MOVES:
        assert (
            VideoPanelBodyV1(
                still_id="s", move=move, seed=1, order=0, track_id="t"
            ).move
            == move
        )


def test_move_vocabulary_matches_burns():
    """No longer soft on whether burns ships ``MOVES``: braidio's declared
    floor is ``burns>=0.0.15`` (thorwhalen/braidio#74 item 5), which always
    has it, so the old ``hasattr`` skip greened in exactly the environment
    where the two vocabularies had drifted apart and never actually compared
    them. The only remaining skip is burns being absent altogether — the
    ``video`` extra is genuinely optional."""
    burns = pytest.importorskip("burns")
    from braidio.bodies import MOVES

    assert tuple(MOVES) == tuple(burns.MOVES)


def test_panel_seed_and_order_are_required_and_distinct():
    from braidio.bodies import VideoPanelBodyV1

    with pytest.raises(ValueError):
        VideoPanelBodyV1(still_id="s", order=0, track_id="t")  # no seed
    with pytest.raises(ValueError):
        VideoPanelBodyV1(still_id="s", seed=5, track_id="t")  # no order
    with pytest.raises(ValueError):
        VideoPanelBodyV1(still_id="s", seed=5, order=0)  # no track: no identity


def test_still_id_is_an_annotation_id_not_an_artifact_id():
    """Documented on the field: a 64-hex artifact id is *accepted* by the
    type, so the guard is the docstring + this test naming the rule."""
    from braidio.bodies import VideoPanelBodyV1

    field = VideoPanelBodyV1.model_fields["still_id"]
    assert "ANNOTATION id" in (field.description or "")


# --- cut + label track: the enums ---------------------------------------------------


def test_cut_stage_and_profile_are_validated():
    from braidio.bodies import VideoCutBodyV1

    ok = dict(label="v1", profile="personal", audio_artifact_id="a")
    assert VideoCutBodyV1(stage="motion", **ok).stage == "motion"
    with pytest.raises(ValueError, match="stage"):
        VideoCutBodyV1(stage="final", **ok)
    with pytest.raises(ValueError, match="profile"):
        VideoCutBodyV1(
            stage="motion", label="v1", profile="public", audio_artifact_id="a"
        )


def test_label_track_kind_and_content_are_validated():
    from braidio.bodies import LabelTrackBodyV1

    with pytest.raises(ValueError, match="kind"):
        LabelTrackBodyV1(kind="banner", lines=["x"])
    with pytest.raises(ValueError, match="headline or lines"):
        LabelTrackBodyV1(kind="title")
    assert LabelTrackBodyV1(kind="tag", headline="Live, 1981").weight == 2


def test_rect_must_lie_inside_the_unit_square():
    from braidio.bodies import RectV1

    with pytest.raises(ValueError):
        RectV1(x=0.5, y=0.0, w=0.6, h=0.5)
    assert RectV1(x=0.5, y=0.0, w=0.5, h=1.0).w == 0.5
