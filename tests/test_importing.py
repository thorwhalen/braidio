"""Offline tests for the finished-production importer (braidio.importing).

Entirely synthetic: the fixtures are a handful of byte-strings on disk, because
nothing in the import path decodes an image or probes audio — geometry and
durations come from the manifest, and the only thing the bytes are used for is
the content-addressed artifact id. So no ffmpeg, no PIL, no network, no cost.

The real production manifests are **local data, not fixtures**: they live under
the user's data folder, carry paths into read-only source folders, and are far
too large to commit. The import of those is a verb, run by hand; what is
pinned here is the behaviour that makes running it safe.

Several tests are deliberate **negative controls** — they fail against the
obvious wrong implementation, which is the only reason they are worth having:

- ``test_a_manifest_that_says_auto_still_imports_as_push_in`` fails against an
  importer that passes ``move`` through, which is the version a reasonable
  person writes and which silently produces a different film.
- ``test_crop_is_converted_from_ltrb_not_passed_through`` fails against an
  importer that writes the manifest's 4-tuple as a Rect. Note that
  ``RectV1``'s unit-square validator catches only the minority of crops whose
  left+right exceeds 1, so "it validated" is not evidence here.
- ``test_a_no_op_reimport_rewrites_nothing`` fails against an importer that is
  merely *deduplicated* (right counts, every node rewritten), which looks
  idempotent in a census and stales every rendered cut underneath.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_NW, reason="nw (and lacing) not available"
)


def _needs_illustration():
    try:
        import illustration.licensing  # noqa: F401
    except ImportError:
        return True
    return False


needs_illustration = pytest.mark.skipif(
    _needs_illustration(), reason="illustration (licence normalization) not available"
)


# --- fixtures ---------------------------------------------------------------


def _doc(**overrides):
    """A minimal two-panel, one-cut production manifest."""
    doc = {
        "production": "demo",
        "title": "A Demo Production",
        "source_dir": "demo",
        "rights": {
            "position": "private",
            "why": "The audio embeds a commercial master.",
            "measured": "2 stills, both CC.",
        },
        "episode_audio": {"path": "ep.mp3", "duration_s": 20.0},
        "stills": [
            {
                "key": "one#1",
                "path": "one.jpg",
                "width": 800,
                "height": 600,
                "title": "A Photograph Of One Thing",
                "license": "CC BY-SA 4.0",
                "license_url": "https://creativecommons.org/licenses/by-sa/4.0/",
                # a BARE AUTHOR with no licence in it — the real shape that
                # makes rendering `attribution` verbatim a licence failure
                "attribution": "EliziR",
                "source_page_url": "https://commons.wikimedia.org/wiki/File:One.jpg",
                "author": "EliziR",
                "labelled": True,
                "subject": "The first thing",
            },
            {
                "key": "two#2",
                "path": "two.jpg",
                "license": "CC0",
                "title": "Another Work",
                "author": "Nobody",
                "labelled": False,
                # fractional (left, top, right, bottom) — the source convention
                "crop": [0.1, 0.2, 0.9, 0.8],
            },
        ],
        "cuts": [
            {
                "label": "v1",
                "artifact": "out.mp4",
                "motion_artifact": "motion.mp4",
                "audio": {"path": "ep.mp3", "duration_s": 20.0},
                "duration_s": 20.0,
                "width": 1920,
                "height": 1080,
                "fps": 30,
                "profile": "personal",
                "settings": {"still_prep": "blurred fill"},
                "published": {
                    "platform": "youtube",
                    "video_id": "abc123",
                    "url": "https://youtu.be/abc123",
                    "privacy": "private",
                    "supersedes": None,
                },
                "panels": [
                    {
                        "still_key": "one#1",
                        "start": 0.0,
                        "end": 10.0,
                        "move": "push_in",
                        "zoom": 1.18,
                        "seed": 0,
                        "beat_id": "beat:0",
                        "order": 0,
                    },
                    {
                        # the source's never-realised "vary it"
                        "still_key": "two#2",
                        "start": 10.0,
                        "end": 20.0,
                        "move": "auto",
                        "zoom": 1.18,
                        "seed": 1,
                        "beat_id": "beat:3",
                        "order": 1,
                    },
                ],
                # The rendered episode's members, in play order — one of each
                # role the importer has to tell apart. Index 3 is the shape
                # that breaks a naive kind-list: the renderer writes a
                # narration beat's delivery STYLE into `kind`, so "archive" is
                # narration in an archival register, not a clip.
                "beats": [
                    {
                        "index": 0,
                        "kind": "narration",
                        "label": "The first thing that gets said, truncat",
                        "text": "The first thing that gets said, truncated in the label.",
                        "start": 0.0,
                        "end": 8.0,
                        "take": {
                            "path": "takes/part00.mp3",
                            "duration_s": 8.2,
                            "voice_id": "JBFqnCBsd6RMkjVDRZzb",
                            "model_id": "eleven_v3",
                        },
                    },
                    {
                        "index": 1,
                        "kind": "clip",
                        "label": "the hook",
                        "source": [30.0, 40.0],
                        "start": 8.0,
                        "end": 12.0,
                        "take": {"path": "takes/part01.mp3", "duration_s": 4.0},
                    },
                    {
                        "index": 2,
                        "kind": "scene-break",
                        "start": 12.0,
                        "end": 13.0,
                        "marker": "sting",
                    },
                    {
                        "index": 3,
                        "kind": "archive",
                        "label": "Second thing.",
                        "text": "Second thing.",
                        "start": 13.0,
                        "end": 20.0,
                        "take": {"path": "takes/part03.mp3", "duration_s": 6.9},
                    },
                ],
                "timeline": {
                    "title": "A Demo Production",
                    "duration": 20.0,
                    "totals": {"narration": 15.0, "clip": 4.0},
                    "settings": {"profile": "personal"},
                    "beats": [
                        {
                            "index": 0,
                            "kind": "narration",
                            "label": "The first thing that gets said, truncat",
                            "source": None,
                            "duration": 8.0,
                            "start": 0.0,
                            "end": 8.0,
                        }
                    ],
                },
                "labels": [
                    {
                        "kind": "title",
                        "start": 0.5,
                        "end": 4.0,
                        "headline": "A Demo",
                        "lines": ["the subtitle"],
                        "weight": 3,
                    },
                    {
                        "kind": "context",
                        "start": 12.0,
                        "end": 16.0,
                        "headline": "Context",
                        "lines": ["a card"],
                        "weight": 2,
                    },
                ],
            }
        ],
        "gaps": ["the published link for v0 is not on disk"],
        "_verification": {"panel_track": "2/2"},
    }
    doc.update(overrides)
    return doc


@pytest.fixture
def source(tmp_path):
    """A source folder with the files the manifest names (bytes are arbitrary)."""
    d = tmp_path / "src" / "demo"
    d.mkdir(parents=True)
    (d / "takes").mkdir()
    for name, blob in (
        ("ep.mp3", b"fake-audio-bytes"),
        ("one.jpg", b"fake-image-one"),
        ("two.jpg", b"fake-image-two"),
        ("out.mp4", b"fake-video"),
        ("motion.mp4", b"fake-motion-video"),
        ("takes/part00.mp3", b"fake-take-zero"),
        ("takes/part01.mp3", b"fake-take-one"),
        ("takes/part03.mp3", b"fake-take-three"),
    ):
        (d / name).write_bytes(blob)
    return tmp_path / "src"


def _cuts_with(**changes):
    """The fixture's single cut, with `changes` applied — for a one-field probe."""
    cut = dict(_doc()["cuts"][0])
    cut.update(changes)
    return [cut]


def _manifest(tmp_path, **overrides):
    from braidio.importing import load_manifest

    tmp_path = Path(tmp_path)
    tmp_path.mkdir(parents=True, exist_ok=True)
    p = tmp_path / "manifest.json"
    p.write_text(json.dumps(_doc(**overrides)))
    return load_manifest(p)


def _run(tmp_path, source, **kwargs):
    from braidio.importing import import_production

    return import_production(
        _manifest(tmp_path, **kwargs.pop("overrides", {})),
        tmp_path / "project",
        source_root=source,
        **kwargs,
    )


def _annotations(root, tier):
    import nw

    return nw.annotations_at_tier(Path(root), tier)


# --- rule 1: the move -------------------------------------------------------


@needs_illustration
def test_a_manifest_that_says_auto_still_imports_as_push_in(tmp_path, source):
    """NEGATIVE CONTROL. Passing ``move`` through is the natural implementation
    and is wrong: ``auto`` reaches ``burns.choose_move``, which picks from a
    weighted pool, so ~40% of panels would acquire a directional drift no
    finished film ever had (braidio#72). One manifest panel says ``auto``."""
    from braidio.importing import IMPORTED_MOVE
    from braidio.transforms._common import TIER_VIDEO_PANEL

    _run(tmp_path, source)
    panels = _annotations(tmp_path / "project", TIER_VIDEO_PANEL)
    assert len(panels) == 2
    assert {p.body["move"] for p in panels} == {IMPORTED_MOVE} == {"push_in"}


@needs_illustration
def test_the_unrealised_intent_is_recorded_rather_than_dropped(tmp_path, source):
    """Reality is written, but the authored 'vary it' is not lost: it is on the
    project's notes and on every cut's settings, citing the issue."""
    import nw
    from braidio.transforms._common import TIER_VIDEO_CUT

    report = _run(tmp_path, source)
    assert any("braidio#72" in n for n in report.notes)
    spec = nw.Project(tmp_path / "project").read_spec()
    assert "braidio#72" in spec.notes
    cut = _annotations(tmp_path / "project", TIER_VIDEO_CUT)[0]
    assert "braidio#72" in cut.body["settings"]["import"]["move_note"]


# --- rule 2: the library zoom default ---------------------------------------


def test_the_recorded_zoom_default_is_asserted():
    """The one failure that is invisible afterwards: panels whose zoom was
    never recorded took the library default, so if it has moved the manifest
    is already wrong."""
    from braidio.importing import ImportError_, assert_recorded_zoom_default

    assert_recorded_zoom_default()  # today's library still matches
    with pytest.raises(ImportError_, match="Panel.zoom"):
        assert_recorded_zoom_default(1.14)


@needs_illustration
def test_the_import_refuses_when_the_library_zoom_default_has_moved(
    tmp_path, source, monkeypatch
):
    """NEGATIVE CONTROL for the call site, not the function. Deleting the
    assertion from ``import_production`` leaves every other test green: the
    manifest's zoom is simply written, and nothing anywhere notices that the
    number it was read from has changed underneath it."""
    from braidio.importing import ImportError_
    from braidio.video import Panel

    field = Panel.__dataclass_fields__["zoom"]
    monkeypatch.setattr(field, "default", 1.14, raising=False)
    with pytest.raises(ImportError_, match="Panel.zoom"):
        _run(tmp_path, source)


@needs_illustration
def test_zoom_is_written_explicitly_on_every_panel(tmp_path, source):
    from braidio.transforms._common import TIER_VIDEO_PANEL

    _run(tmp_path, source)
    panels = _annotations(tmp_path / "project", TIER_VIDEO_PANEL)
    assert {p.body["zoom"] for p in panels} == {1.18}


# --- rule 3: licences -------------------------------------------------------


@needs_illustration
def test_an_unrecognised_licence_is_refused(tmp_path, source):
    """Unknown survives normalization unchanged and would then silently fail a
    downstream allowlist with no error at all — so it fails here instead."""
    from braidio.importing import ImportError_

    doc = _doc()
    doc["stills"][0]["license"] = "WTFPL-9.9"
    with pytest.raises(ImportError_, match="recognise"):
        _run(tmp_path, source, overrides=doc)


@needs_illustration
def test_the_stored_licence_is_the_canonical_code_not_the_spelling(tmp_path, source):
    """The STORED code is canonical, because that is the one a gate compares.

    A **negative control** for the version this replaced, which stored the
    provider's spelling on the grounds that a credit reading "by-sa" is
    useless. That was true and the conclusion was wrong: an unrecognised
    spelling survives ``normalize_license`` unchanged, so a published-profile
    gate comparing "CC BY-SA 4.0" against "by-sa" matches **nothing** and
    reports no error at all — fewer hits, no signal. The spelling is not lost;
    it moves to ``license_label``, and the next test proves the credit still
    reads it.
    """
    from braidio.transforms._common import TIER_STILL

    report = _run(tmp_path, source)
    stills = {s.body["key"]: s for s in _annotations(tmp_path / "project", TIER_STILL)}
    body = stills["one#1"].body
    assert body["license"] == "by-sa"
    assert body["license_label"] == "CC BY-SA 4.0"
    assert report.license_codes["one#1"] == "by-sa"
    # cc0 normalizes from a different spelling on the second still
    assert stills["two#2"].body["license"] == "cc0"
    assert stills["two#2"].body["license_label"] == "CC0"


@needs_illustration
def test_every_stored_licence_survives_an_allowlist_that_uses_the_canon(
    tmp_path, source
):
    """The point of storing the code: ``illustration``'s own gate matches.

    This is the test that would have caught the defect. It runs the stored
    bodies through ``license_allowlist`` — the real gate, not a re-derived
    one — and asserts both stills survive. Against the previous behaviour
    (raw spellings stored) it returns an empty list while raising nothing,
    which is exactly how the bug stayed invisible.
    """
    from illustration.licensing import normalize_license
    from braidio.transforms._common import TIER_STILL

    _run(tmp_path, source)
    stored = [s.body["license"] for s in _annotations(tmp_path / "project", TIER_STILL)]
    assert stored, "no stills imported"
    # The gate normalizes both sides; a stored value that is ALREADY canonical
    # is a fixed point, which is the property that makes the comparison work.
    assert all(normalize_license(code) == code for code in stored), stored
    assert set(stored) <= {"by", "by-sa", "cc0", "pdm"}, stored


@needs_illustration
def test_the_credit_is_composed_from_the_parts_not_the_attribution(tmp_path, source):
    """``attribution`` comes back as a bare author for a minority of Wikimedia
    hits; shipping it as the credit fails the licence's one condition."""
    from braidio.bodies._video import credit_line
    from braidio.transforms._common import TIER_STILL

    _run(tmp_path, source)
    stills = {s.body["key"]: s for s in _annotations(tmp_path / "project", TIER_STILL)}
    body = stills["one#1"].body
    assert body["attribution"] == "EliziR"  # kept for the record
    line = credit_line(body)
    assert "CC BY-SA 4.0" in line and "A Photograph Of One Thing" in line
    assert line != body["attribution"]


@needs_illustration
def test_the_title_is_the_works_own_never_the_editorial_subject(tmp_path, source):
    from braidio.transforms._common import TIER_STILL

    _run(tmp_path, source)
    stills = {s.body["key"]: s for s in _annotations(tmp_path / "project", TIER_STILL)}
    assert stills["one#1"].body["title"] == "A Photograph Of One Thing"
    assert stills["one#1"].body["subject"] == "The first thing"


@needs_illustration
def test_untitled_stills_are_reported_because_they_credit_silently(tmp_path, source):
    doc = _doc()
    doc["stills"][0].pop("title")
    report = _run(tmp_path, source, overrides=doc)
    assert report.untitled_stills == ["one#1"]


# --- rule 4: card weights ---------------------------------------------------


@needs_illustration
def test_a_weight_one_context_card_is_refused(tmp_path, source):
    """video_cut.finish resolves overlays at PLAN time; a weight-1 card over a
    labelled still is a collision, so the cut would be refused before a frame
    is rendered — at the point where it is least obvious why."""
    from braidio.importing import ImportError_

    doc = _doc()
    doc["cuts"][0]["labels"][1]["weight"] = 1
    with pytest.raises(ImportError_, match="weight >= 2"):
        _run(tmp_path, source, overrides=doc)


# --- geometry ---------------------------------------------------------------


@needs_illustration
def test_crop_is_converted_from_ltrb_not_passed_through(tmp_path, source):
    """NEGATIVE CONTROL. Both productions that crop record fractional
    (left, top, right, bottom); RectV1 — and the renderer that applies it — is
    (x, y, w, h). Writing the tuple through mis-frames the still, and RectV1's
    unit-square check catches only the crops whose left+right exceeds 1."""
    from braidio.transforms._common import TIER_STILL

    _run(tmp_path, source)
    stills = {s.body["key"]: s for s in _annotations(tmp_path / "project", TIER_STILL)}
    crop = stills["two#2"].body["crop"]
    # manifest said (0.1, 0.2, 0.9, 0.8)
    assert crop == {"x": 0.1, "y": 0.2, "w": 0.8, "h": 0.6}
    assert crop["w"] != 0.9 and crop["h"] != 0.8  # i.e. not passed through


def test_a_crop_that_is_not_ltrb_is_refused():
    from braidio.importing._writer import ImportError_, _rect_from_ltrb

    with pytest.raises(ImportError_, match="left, top, right"):
        _rect_from_ltrb((0.9, 0.0, 0.1, 1.0))  # right < left


# --- identity and idempotency ----------------------------------------------


@needs_illustration
def test_a_no_op_reimport_rewrites_nothing(tmp_path, source):
    """NEGATIVE CONTROL for the difference between *deduplicated* and
    *idempotent*. An importer that removes-and-rewrites every node produces an
    identical census while moving every ``generated_at_time``, which stales
    every rendered cut underneath it for no reason at all."""
    import nw
    from braidio.transforms._common import TIER_STILL, TIER_VIDEO_PANEL

    root = tmp_path / "project"
    first = _run(tmp_path, source)
    stamps = {
        str(a.id): a.provenance.generated_at_time.to_seconds()
        for a in nw.iter_all_annotations(root)
    }
    second = _run(tmp_path, source)
    after = {
        str(a.id): a.provenance.generated_at_time.to_seconds()
        for a in nw.iter_all_annotations(root)
    }

    assert first.stills_written == 2 and first.stills_unchanged == 0
    assert second.stills_written == 0 and second.stills_unchanged == 2
    assert set(stamps) == set(after), "annotation ids are not stable across runs"
    assert [k for k in stamps if stamps[k] != after[k]] == []
    assert len(_annotations(root, TIER_VIDEO_PANEL)) == 2
    assert len(_annotations(root, TIER_STILL)) == 2


@needs_illustration
def test_one_track_per_cut(tmp_path, source):
    """A cut's panels share one ``track_id``; two cuts are two tracks, never
    one merged track and never a second track over the same cut."""
    from braidio.transforms._common import TIER_VIDEO_PANEL

    doc = _doc()
    second = json.loads(json.dumps(doc["cuts"][0]))
    second["label"] = "v2"
    doc["cuts"].append(second)
    _run(tmp_path, source, overrides=doc)
    panels = _annotations(tmp_path / "project", TIER_VIDEO_PANEL)
    tracks = {p.body["track_id"] for p in panels}
    assert len(panels) == 4 and len(tracks) == 2


@needs_illustration
def test_beat_ids_are_renumbered_into_braidios_spelling(tmp_path, source):
    """'beat:3' -> '0003'. Leaving the source spelling would make a later
    re-plan's pick map (keyed on braidio's beat_id) silently match nothing and
    fall back to cycling the pool — a different set of pictures, no error."""
    from braidio.transforms._common import TIER_VIDEO_PANEL

    report = _run(tmp_path, source)
    panels = sorted(
        _annotations(tmp_path / "project", TIER_VIDEO_PANEL),
        key=lambda p: p.body["order"],
    )
    assert [p.body["beat_id"] for p in panels] == ["0000", "0003"]
    assert report.beat_ids_renumbered == 2


# --- cuts, rights, and what must never be claimed ---------------------------


@needs_illustration
def test_an_imported_cut_carries_no_cache_key(tmp_path, source):
    """braidio did not render it, so no key describes its pixels — and
    ``nw.transforms.cached_output`` must never be able to answer a fresh
    render with the shipped file."""
    from braidio.transforms._common import TIER_VIDEO_CUT

    _run(tmp_path, source)
    cuts = _annotations(tmp_path / "project", TIER_VIDEO_CUT)
    stages = sorted(c.body["stage"] for c in cuts)
    assert stages == ["delivered", "motion"], "both stages must be exercised here"
    assert all(c.body["cache_key"] is None for c in cuts)
    assert all(c.body["artifact_id"] for c in cuts)


@needs_illustration
def test_the_published_record_survives(tmp_path, source):
    from braidio.transforms._common import TIER_VIDEO_CUT

    report = _run(tmp_path, source)
    cut = [
        c
        for c in _annotations(tmp_path / "project", TIER_VIDEO_CUT)
        if c.body["stage"] == "delivered"
    ][0]
    assert cut.body["published"]["video_id"] == "abc123"
    assert report.published_links["v1"] == "https://youtu.be/abc123"


@needs_illustration
def test_the_rights_position_reaches_the_project_and_every_cut(tmp_path, source):
    """Plan §10: carry the finding into the graph and show it next to the cut."""
    import nw
    from braidio.transforms._common import TIER_RENDER_PROFILE, TIER_VIDEO_CUT

    report = _run(tmp_path, source)
    assert report.rights_position == "private"
    spec = nw.Project(tmp_path / "project").read_spec()
    assert "commercial master" in spec.notes
    cut = _annotations(tmp_path / "project", TIER_VIDEO_CUT)[0]
    assert cut.body["settings"]["rights"]["position"] == "private"
    profiles = _annotations(tmp_path / "project", TIER_RENDER_PROFILE)
    assert len(profiles) == 1 and profiles[0].body["profile"] == "personal"


@needs_illustration
def test_a_private_production_may_not_import_a_published_cut(tmp_path, source):
    """The importer never promotes what the source did not."""
    from braidio.importing import ImportError_

    doc = _doc()
    doc["cuts"][0]["profile"] = "published"
    with pytest.raises(ImportError_, match="never promotes"):
        _run(tmp_path, source, overrides=doc)


@needs_illustration
def test_panels_derive_from_exactly_one_episode(tmp_path, source):
    """``video_cut.render`` refuses a track whose panels name more than one
    episode, so the import has to get this right or no cut can ever render."""
    import uuid

    from braidio.transforms._common import TIER_EPISODE_RENDER, TIER_VIDEO_PANEL
    from braidio.transforms._video_cut import _episode_of
    import nw

    _run(tmp_path, source)
    root = tmp_path / "project"
    index = {a.id: a for a in nw.iter_all_annotations(root)}
    panels = _annotations(root, TIER_VIDEO_PANEL)
    episode = _episode_of(panels, index)
    assert episode.tier == TIER_EPISODE_RENDER
    assert episode.body["artifact_id"]
    assert uuid.UUID(str(panels[0].body["still_id"])) in index


# --- validation and the free door -------------------------------------------


@needs_illustration
def test_a_missing_still_file_is_refused_before_anything_is_written(tmp_path, source):
    from braidio.importing import ImportError_

    (source / "demo" / "one.jpg").unlink()
    with pytest.raises(ImportError_, match="not on disk"):
        _run(tmp_path, source)
    assert not (tmp_path / "project").exists()


@needs_illustration
def test_dry_run_validates_and_writes_nothing(tmp_path, source):
    report = _run(tmp_path, source, dry_run=True)
    assert report.production == "demo"
    assert report.gaps  # carried, never hidden
    assert not (tmp_path / "project").exists()


@needs_illustration
def test_the_cli_door_runs_the_same_verb(tmp_path, source):
    from braidio.importing.__main__ import main

    (tmp_path / "manifest.json").write_text(json.dumps(_doc()))
    code = main(
        [
            str(tmp_path / "manifest.json"),
            str(tmp_path / "project"),
            "--source-root",
            str(source),
            "--json",
        ]
    )
    assert code == 0
    assert (tmp_path / "project" / "project.json").exists()


@needs_illustration
def test_the_cli_reports_a_refusal_without_a_traceback(tmp_path, source, capsys):
    doc = _doc()
    doc["cuts"][0]["labels"][1]["weight"] = 1
    (tmp_path / "manifest.json").write_text(json.dumps(doc))
    from braidio.importing.__main__ import main

    code = main(
        [
            str(tmp_path / "manifest.json"),
            str(tmp_path / "project"),
            "--source-root",
            str(source),
        ]
    )
    assert code == 2
    assert "import refused" in capsys.readouterr().err


# --- media ------------------------------------------------------------------


@needs_illustration
def test_media_is_copied_into_the_project_so_it_is_self_contained(tmp_path, source):
    from braidio.transforms._common import TIER_STILL, url_to_path

    _run(tmp_path, source)
    root = (tmp_path / "project").resolve()
    for still in _annotations(tmp_path / "project", TIER_STILL):
        path = url_to_path(still.body["url"])
        assert path.exists()
        assert root in path.parents, "still bytes must live inside the project"


@needs_illustration
def test_no_copy_media_references_the_source_in_place(tmp_path, source):
    from braidio.transforms._common import TIER_STILL, url_to_path

    report = _run(tmp_path, source, copy_media=False)
    assert report.media_copied == 0
    still = _annotations(tmp_path / "project", TIER_STILL)[0]
    assert source.resolve() in url_to_path(still.body["url"]).parents


# --- gap 1: the narration is addressable ------------------------------------


@needs_illustration
def test_a_narration_segment_is_a_thing_you_can_point_at_and_play(tmp_path, source):
    """The headline. Before this, the only audio node an imported production
    had was the finished mix, so 'replace this narration' had no referent."""
    from braidio.transforms._common import (
        TIER_NARRATION_RENDER,
        TIER_NARRATIVE_BEAT,
        url_to_path,
    )

    report = _run(tmp_path, source)
    beats = _annotations(tmp_path / "project", TIER_NARRATIVE_BEAT)
    takes = _annotations(tmp_path / "project", TIER_NARRATION_RENDER)
    assert len(beats) == 2, "two narration beats (index 0 and the archive one)"
    assert len(takes) == 2
    for take in takes:
        # pointable
        assert take.body["artifact_id"], "a take with no artifact is not playable"
        # playable
        path = url_to_path(take.body["url"])
        assert path.is_file() and path.stat().st_size > 0
        # and known to be synthesized, which is what makes a replacement
        # distinguishable from the thing it replaced
        assert take.body["source"] == "tts"
        assert take.body["duration_s"] > 0
    # a "take" is a NARRATION take; the clip beat has audio too but it is
    # an extraction, not something anyone re-records
    assert report.takes_by_cut == {"v1": 2}, report.takes_by_cut
    assert report.beats_by_cut == {"v1": 4}, report.beats_by_cut
    texts = sorted(b.body["text"] for b in beats)
    assert texts[0] == "Second thing."
    assert texts[1].startswith("The first thing that gets said, truncated")


@needs_illustration
def test_the_take_derives_from_the_beat_so_words_and_recording_are_linked(
    tmp_path, source
):
    """Editing the words has to reach the recording. That edge is the feature."""
    from braidio.transforms._common import TIER_NARRATION_RENDER, TIER_NARRATIVE_BEAT

    _run(tmp_path, source)
    beat_ids = {b.id for b in _annotations(tmp_path / "project", TIER_NARRATIVE_BEAT)}
    for take in _annotations(tmp_path / "project", TIER_NARRATION_RENDER):
        parents = set(take.provenance.was_derived_from)
        assert parents & beat_ids, (
            "a take with no beat parent is an orphan recording: editing the "
            "narration would leave it reading fresh"
        )


@needs_illustration
def test_an_archive_beat_is_narration_in_a_style_not_a_clip(tmp_path, source):
    """**Negative control.** The renderer writes a narration beat's delivery
    STYLE into the timeline's ``kind``, so a kind-list that matches only
    ``"narration"`` files Two Silences' nine ``archive`` beats as something
    else — or drops them, which silently shortens the play order."""
    from braidio.transforms._common import TIER_NARRATIVE_BEAT

    _run(tmp_path, source)
    beats = {
        b.body["beat_id"]: b.body
        for b in _annotations(tmp_path / "project", TIER_NARRATIVE_BEAT)
    }
    assert "0003" in beats, "the archive beat must be narration"
    assert beats["0003"]["style"] == "archive", "and must keep its style"
    assert beats["0000"]["style"] is None, "plain narration carries no style"


@needs_illustration
def test_a_clip_is_never_imported_as_a_replaceable_narration_take(tmp_path, source):
    """A clip mis-filed as narration becomes a segment a surface offers to
    re-synthesize — and on these productions that clip is a commercial
    master. The contradiction is refused, not resolved."""
    from braidio.importing import ImportError_
    from braidio.transforms._common import TIER_SEGMENT_EXTRACTION

    _run(tmp_path, source)
    segs = _annotations(tmp_path / "project", TIER_SEGMENT_EXTRACTION)
    assert len(segs) == 1
    assert (segs[0].body["start_s"], segs[0].body["end_s"]) == (30.0, 40.0)

    # the dangerous shape: a source span under a narration kind
    beats = [dict(b) for b in _doc()["cuts"][0]["beats"]]
    beats[1]["kind"] = "narration"
    second = tmp_path / "second"
    with pytest.raises(ImportError_, match="reads as narration"):
        _run(second, source, overrides={"cuts": _cuts_with(beats=beats)})


@needs_illustration
def test_the_episode_names_every_member_in_play_order(tmp_path, source):
    """``ordered_member_ids`` is the play order; a list missing a member is
    not one. Four beats in, four members out, in index order."""
    from braidio.transforms._common import (
        TIER_EPISODE_RENDER,
        TIER_NARRATION_RENDER,
        TIER_SCENE_BREAK,
        TIER_SEGMENT_EXTRACTION,
    )

    _run(tmp_path, source)
    root = tmp_path / "project"
    episode = _annotations(root, TIER_EPISODE_RENDER)[0]
    members = episode.body["ordered_member_ids"]
    assert len(members) == 4, members

    takes = {str(a.id) for a in _annotations(root, TIER_NARRATION_RENDER)}
    segs = {str(a.id) for a in _annotations(root, TIER_SEGMENT_EXTRACTION)}
    breaks = {str(a.id) for a in _annotations(root, TIER_SCENE_BREAK)}
    assert members[0] in takes
    assert members[1] in segs
    assert members[2] in breaks
    assert members[3] in takes
    # and the episode derives from them, which is what makes a replaced take
    # read as stale downstream instead of as a change nothing notices
    assert set(episode.provenance.was_derived_from) == {
        __import__("uuid").UUID(m) for m in members
    }


@needs_illustration
def test_replacing_a_take_stales_the_panels_that_were_cut_against_it(tmp_path, source):
    """What replacing a narration segment actually COSTS, asserted rather
    than asserted-in-prose: the panels are downstream of the take, so a
    replacement is a re-weave of the cut, not an in-place edit."""
    import nw
    from braidio.transforms._common import TIER_NARRATION_RENDER, TIER_VIDEO_PANEL

    _run(tmp_path, source)
    root = tmp_path / "project"
    take = _annotations(root, TIER_NARRATION_RENDER)[0]
    panels = {a.id for a in _annotations(root, TIER_VIDEO_PANEL)}
    reachable = {a.id for a in nw.descendants_of(root, take.id)}
    assert panels <= reachable, (
        "every panel must be downstream of the narration take; if it is not, "
        "a surface could offer the replacement as a cheap edit"
    )


@needs_illustration
def test_a_beat_with_no_surviving_text_imports_empty_and_is_counted(tmp_path, source):
    """**Negative control.** The tempting fallback is the timeline's
    48-character snippet, which is a truncation a re-synthesis would speak as
    though it were the script. Empty is the honest record, and the count is
    where the loss is visible."""
    from braidio.transforms._common import TIER_NARRATIVE_BEAT

    doc = _doc()
    doc["cuts"][0]["beats"][0].pop("text")
    report = _run(tmp_path, source, overrides=doc)
    beats = {
        b.body["beat_id"]: b.body
        for b in _annotations(tmp_path / "project", TIER_NARRATIVE_BEAT)
    }
    assert beats["0000"]["text"] == ""
    assert "The first thing" not in beats["0000"]["text"]
    assert report.beats_without_text == ["v1/0"]


@needs_illustration
def test_an_imported_take_can_never_be_served_from_a_render_cache(tmp_path, source):
    """``cached_output`` scans a tier for a matching ``cache_key``. A computed
    key is a 64-char SHA-256 digest, so an imported one must not be able to
    look like one — else a later render adopts a shipped take as its output."""
    import re

    from braidio.importing import IMPORTED_CACHE_KEY_PREFIX
    from braidio.transforms._common import (
        TIER_NARRATION_RENDER,
        TIER_SEGMENT_EXTRACTION,
    )

    _run(tmp_path, source)
    root = tmp_path / "project"
    keys = [
        a.body["cache_key"]
        for a in _annotations(root, TIER_NARRATION_RENDER)
        + _annotations(root, TIER_SEGMENT_EXTRACTION)
    ]
    assert keys
    for key in keys:
        assert key.startswith(IMPORTED_CACHE_KEY_PREFIX)
        assert not re.fullmatch(r"[0-9a-f]{64}", key), key


@needs_illustration
def test_the_render_s_own_timeline_reaches_the_episode(tmp_path, source):
    """``episode_timeline`` prefers a persisted breakdown and RECONSTRUCTS
    otherwise — and an imported episode has no weave-config to reconstruct
    from, so without this the panels are cut against an empty timeline."""
    from braidio.transforms import episode_timeline
    from braidio.transforms._common import TIER_EPISODE_RENDER
    from braidio.project import Project

    _run(tmp_path, source)
    root = tmp_path / "project"
    episode = _annotations(root, TIER_EPISODE_RENDER)[0]
    assert episode.body["timeline"], "the render's own record must be carried"
    breakdown = episode_timeline(Project(root), episode)
    assert breakdown.beats, "a reconstructed-from-nothing timeline is empty"
    assert breakdown.title == "A Demo Production"


# --- gap 2: a fresh import is retrievable -----------------------------------


@needs_illustration
def test_every_imported_artifact_is_registered_and_its_bytes_are_there(
    tmp_path, source
):
    """The gap this closes: the graph named every artifact by content id and
    nothing registered it, so every id 404'd. A row without a blob behind it
    is worse than no row — the host's route has already promised a 200."""
    from braidio.importing._catalog import blobs_dir, iter_rows, registered_ids
    from braidio.transforms._common import (
        TIER_EPISODE_RENDER,
        TIER_NARRATION_RENDER,
        TIER_STILL,
        TIER_VIDEO_CUT,
    )

    _run(tmp_path, source)
    root = tmp_path / "project"
    registered = registered_ids(root)
    assert registered, "nothing registered at all"

    wanted = set()
    for tier in (TIER_STILL, TIER_EPISODE_RENDER, TIER_NARRATION_RENDER):
        for ann in _annotations(root, tier):
            if ann.body.get("artifact_id"):
                wanted.add(ann.body["artifact_id"])
    delivered = [
        a
        for a in _annotations(root, TIER_VIDEO_CUT)
        if a.body["stage"] == "delivered" and a.body.get("artifact_id")
    ]
    wanted |= {a.body["artifact_id"] for a in delivered}

    missing = sorted(wanted - registered)
    assert not missing, (
        f"{len(missing)} artifact ids the graph names and no row answers"
    )

    for row in iter_rows(root):
        blob = blobs_dir(root) / row["content_hash"]
        assert blob.is_file(), f"row {row['id']} has no bytes behind it"


@needs_illustration
def test_the_catalog_id_is_the_id_the_graph_already_recorded(tmp_path, source):
    """**Negative control.** The host mints opaque ids for what it ingests
    itself; registering under one of those yields a populated catalog that
    answers nothing the project actually asks for, and every census passes."""
    from braidio.importing._catalog import iter_rows

    _run(tmp_path, source)
    for row in iter_rows(tmp_path / "project"):
        assert row["id"] == row["content_hash"], row["id"]
        assert len(row["id"]) == 64 and not row["id"].startswith("art-")


@needs_illustration
def test_a_catalog_row_never_carries_a_file_url(tmp_path, source):
    """A row registered by hand with a ``file://`` URL reached an ``<img
    src>`` and put the owner's home directory into the page's DOM. The row's
    url is the host's own route, which is also the only one a consumer on
    another machine can follow."""
    from braidio.importing._catalog import iter_rows

    _run(tmp_path, source)
    rows = list(iter_rows(tmp_path / "project"))
    assert rows
    for row in rows:
        assert row["url"] == f"/api/artifacts/{row['id']}/bytes"
        assert "file:" not in json.dumps(row)
        assert str(Path.home()) not in json.dumps(row)


@needs_illustration
def test_blobs_are_hardlinked_so_registering_costs_no_disk(tmp_path, source):
    """Not merely cheap — *correct*: the filename is the digest, so a shared
    inode can only ever be rewritten with identical bytes."""
    from braidio.importing._catalog import blobs_dir
    from braidio.transforms._common import TIER_STILL, url_to_path

    _run(tmp_path, source)
    root = tmp_path / "project"
    still = _annotations(root, TIER_STILL)[0]
    media = url_to_path(still.body["url"])
    blob = blobs_dir(root) / still.body["artifact_id"]
    assert blob.stat().st_ino == media.stat().st_ino, "blob must share the inode"
    assert blob.stat().st_nlink >= 2


@needs_illustration
def test_a_cross_device_blob_store_refuses_rather_than_copying(
    tmp_path, source, monkeypatch
):
    """A silent copy here is the whole production a second time. EXDEV is a
    refusal, and only an explicit opt-in turns it into a copy."""
    import os

    from braidio.importing import CrossDeviceCatalog

    real_link = os.link

    def _exdev(src, dst, *a, **kw):
        if "artifacts" in str(dst):  # only the blob store, not media placement
            raise OSError(18, "Invalid cross-device link")
        return real_link(src, dst, *a, **kw)

    monkeypatch.setattr(os, "link", _exdev)
    with pytest.raises(CrossDeviceCatalog, match="allow_cross_device_copy"):
        _run(tmp_path, source)

    report = _run(tmp_path / "b", source, allow_cross_device_copy=True)
    assert report.catalog.cross_device is True
    assert report.catalog.blobs_copied > 0
    assert report.catalog.bytes_copied > 0


@needs_illustration
def test_registration_can_be_declined_and_says_what_that_costs(tmp_path, source):
    from braidio.importing._catalog import registered_ids

    report = _run(tmp_path, source, register_artifacts=False)
    assert registered_ids(tmp_path / "project") == frozenset()
    assert report.catalog.unregistered, "declining must be reported, not silent"


@needs_illustration
def test_an_srt_is_reported_unregistered_rather_than_coerced(tmp_path, source):
    """The catalog holds image/video/audio/json. Coercing an .srt into one of
    them makes the host's ``Literal`` reject the row at READ time, which
    breaks the whole catalog to serve one file it cannot serve anyway."""
    doc = _doc()
    (source / "demo" / "cc.srt").write_bytes(b"1\n00:00:00,000 --> 00:00:01,000\nhi\n")
    report = _run(tmp_path, source, overrides={"cuts": _cuts_with(captions="cc.srt")})
    reasons = " ".join(r for _, r in report.catalog.unregistered)
    assert "text" in reasons, report.catalog.unregistered


# --- gap 2b: the finished cuts are watchable, not just readable -------------


@needs_illustration
def test_the_delivered_cut_comes_into_the_project_and_is_retrievable(tmp_path, source):
    """The seeding blocker: a cut left at its source path is a film a reader
    "can read and cannot watch", and on the server that path does not exist
    at all."""
    from braidio.importing._catalog import registered_ids
    from braidio.transforms._common import TIER_VIDEO_CUT, url_to_path

    _run(tmp_path, source)
    root = (tmp_path / "project").resolve()
    delivered = [
        a for a in _annotations(root, TIER_VIDEO_CUT) if a.body["stage"] == "delivered"
    ]
    assert delivered
    for cut in delivered:
        path = url_to_path(cut.body["url"])
        assert root in path.parents, "the delivered cut must live in the project"
        assert path.parent.name == "cuts", "where braidio.downloads looks for it"
        # named the way video_cut.render names one, so the deliverable lister
        # reads the right stage off it
        assert path.stem == str(cut.id)
        assert cut.body["artifact_id"] in registered_ids(root)


@needs_illustration
def test_the_motion_pass_stays_out_by_default_and_the_report_says_so(tmp_path, source):
    """A motion pass is a resumable intermediate, not a deliverable, and
    carrying every one roughly doubles the weight. Excluded by default —
    and *reported*, because an unretrievable artifact is one a caller will
    ask for and not get."""
    from braidio.importing._catalog import registered_ids
    from braidio.transforms._common import TIER_VIDEO_CUT

    report = _run(tmp_path, source)
    root = tmp_path / "project"
    motion = [
        a for a in _annotations(root, TIER_VIDEO_CUT) if a.body["stage"] == "motion"
    ]
    assert motion, "the motion node is still recorded"
    assert motion[0].body["artifact_id"] not in registered_ids(root)
    assert any("motion" in reason for _, reason in report.catalog.unregistered)

    full = _run(tmp_path / "all", source, materialize_cuts="all")
    root2 = tmp_path / "all" / "project"
    motion2 = [
        a for a in _annotations(root2, TIER_VIDEO_CUT) if a.body["stage"] == "motion"
    ]
    assert motion2[0].body["artifact_id"] in registered_ids(root2)
    assert full.catalog.rows_written > report.catalog.rows_written


@needs_illustration
def test_materialize_cuts_none_restores_the_old_behaviour_and_names_the_cost(
    tmp_path, source
):
    from braidio.transforms._common import TIER_VIDEO_CUT, url_to_path

    report = _run(tmp_path, source, materialize_cuts="none")
    root = (tmp_path / "project").resolve()
    delivered = [
        a for a in _annotations(root, TIER_VIDEO_CUT) if a.body["stage"] == "delivered"
    ]
    assert source.resolve() in url_to_path(delivered[0].body["url"]).parents
    assert any(
        "no surface can serve it" in reason for _, reason in report.catalog.unregistered
    )


def _host_model():
    """The host's own artifact record, when the host is importable.

    braidio cannot depend on it — the dependency runs the other way — so this
    is the only check that can actually catch drift in the wire contract, and
    it is a dev-machine check by nature. CI pins the field list instead
    (``test_the_catalog_row_declares_every_field_the_host_requires``).
    """
    try:
        from reelee.artifacts import Artifact
    except Exception:  # pragma: no cover - environment-dependent
        return None
    return Artifact


@needs_illustration
@pytest.mark.skipif(_host_model() is None, reason="reelee (the host) not importable")
def test_a_row_braidio_writes_loads_through_the_hosts_own_model(tmp_path, source):
    """The wire contract, checked against the authority rather than a copy.

    The host validates ``extra="forbid"``, so an omitted field and an added
    one are both fatal, and neither is visible from inside braidio.
    """
    from braidio.importing._catalog import iter_rows

    Artifact = _host_model()
    _run(tmp_path, source)
    rows = list(iter_rows(tmp_path / "project"))
    assert rows
    for row in rows:
        record = Artifact.model_validate(row)
        assert record.id == record.content_hash
        assert record.url.startswith("/api/artifacts/")


def test_the_catalog_row_declares_every_field_the_host_requires():
    """What CI pins when the host is not importable.

    A literal, on purpose: this list *is* the contract braidio is promising
    to honour, so changing it has to be a deliberate edit rather than a
    silent consequence of editing the builder.
    """
    from braidio.importing._catalog import CatalogRow

    assert CatalogRow.FIELDS == (
        "id",
        "kind",
        "url",
        "width",
        "height",
        "duration_seconds",
        "cost_usd",
        "provenance",
        "content_hash",
    )
    assert CatalogRow.PROVENANCE_FIELDS == (
        "source",
        "model",
        "request_id",
        "prompt",
        "generated_at",
        "triggered_by",
        "filename",
    )
    row = CatalogRow.build("ab" * 32, kind="image", generated_at="2026-01-01T00:00:00Z")
    assert tuple(sorted(row)) == tuple(sorted(CatalogRow.FIELDS))
    assert tuple(sorted(row["provenance"])) == tuple(
        sorted(CatalogRow.PROVENANCE_FIELDS)
    )


def test_the_catalog_digest_is_the_one_lacing_computes():
    """The id is a lacing ``asset_id``. If these two ever disagree, every row
    is registered under an id the graph does not use."""
    import tempfile

    from lacing.artifact import hash_file as lacing_hash

    from braidio.importing._catalog import hash_file

    with tempfile.TemporaryDirectory() as d:
        p = Path(d, "x.bin")
        p.write_bytes(b"some bytes" * 1000)
        assert hash_file(p) == lacing_hash(p)


# --- the manifest's own stale gap text --------------------------------------


@needs_illustration
def test_a_manifest_still_claiming_drift_to_auto_is_corrected_in_the_report(
    tmp_path, source
):
    """A reading hazard, not a behavioural one — the importer writes
    ``push_in`` regardless. But a gap note that contradicts the code is how a
    later reader re-derives the wrong answer with the manifest in hand."""
    report = _run(
        tmp_path,
        source,
        overrides={"gaps": ["MOVE ENCODING. push -> push_in; drift -> auto."]},
    )
    assert any("CORRECTION" in g and "braidio#72" in g for g in report.gaps)

    clean = _run(
        tmp_path / "clean", source, overrides={"gaps": ["nothing about motion"]}
    )
    assert not any("CORRECTION" in g for g in clean.gaps)


@needs_illustration
def test_a_clip_with_no_recorded_source_span_says_so_rather_than_inventing_one(
    tmp_path, source
):
    """**Negative control.** ``start_s``/``end_s`` are required floats with no
    null, so the tempting fallback is ``(0.0, duration)`` — which reads exactly
    like a real cut from the head of the source. That is a false claim about
    where third-party material came from, and it is the last kind of claim
    worth guessing at. One production's driver never persisted the spans.
    """
    from braidio.transforms._common import TIER_SEGMENT_EXTRACTION

    beats = [dict(b) for b in _doc()["cuts"][0]["beats"]]
    beats[1].pop("source")
    report = _run(tmp_path, source, overrides={"cuts": _cuts_with(beats=beats)})
    seg = _annotations(tmp_path / "project", TIER_SEGMENT_EXTRACTION)[0]
    assert seg.body["source_span_recorded"] is False
    assert (seg.body["start_s"], seg.body["end_s"]) == (0.0, 0.0), (
        "an unknown span must not be dressed up as a cut from the head of the source"
    )
    assert report.segments_without_source == ["v1/1"]

    # and the recorded case still records
    kept = _run(tmp_path / "kept", source)
    seg2 = _annotations(tmp_path / "kept" / "project", TIER_SEGMENT_EXTRACTION)[0]
    assert seg2.body["source_span_recorded"] is True
    assert (seg2.body["start_s"], seg2.body["end_s"]) == (30.0, 40.0)


@needs_illustration
def test_a_no_op_reimport_does_not_churn_the_catalog_either(
    tmp_path, source, monkeypatch
):
    """The catalog's version of ``test_a_no_op_reimport_rewrites_nothing``.

    ``generated_at`` is when the artifact was FIRST registered; comparing it
    makes every re-import rewrite every row, and the row's mtime stops meaning
    anything.
    """
    from braidio.importing._catalog import catalog_dir

    first = _run(tmp_path, source)
    assert first.catalog.rows_written > 0
    stamps = {
        p.name: p.read_text() for p in catalog_dir(tmp_path / "project").glob("*.json")
    }
    # The clock MUST move between the runs, or this test passes against an
    # implementation that compares `generated_at` — both imports land in the
    # same second and the rows are byte-equal by accident. That is the
    # difference between a guard and a coincidence.
    from braidio.importing import _writer

    monkeypatch.setattr(_writer, "_utc_now_iso", lambda: "2099-12-31T23:59:59Z")
    second = _run(tmp_path, source)
    assert second.catalog.rows_written == 0
    assert second.catalog.rows_unchanged == first.catalog.rows_written
    assert second.catalog.blobs_linked == 0
    assert second.catalog.blobs_present == first.catalog.blobs_linked
    after = {
        p.name: p.read_text() for p in catalog_dir(tmp_path / "project").glob("*.json")
    }
    assert after == stamps, "a re-import must not rewrite a single row"


@needs_illustration
def test_no_row_is_written_when_the_blob_could_not_be_placed(
    tmp_path, source, monkeypatch
):
    """The ordering IS the correctness argument.

    The host's route looks the row up first and streams from the blob second,
    so a row with no bytes behind it is not a 404 — it is a 500 from inside a
    response that has already promised a 200. Writing the row last means a
    failure leaves nothing, which is the recoverable direction.
    """
    import os

    from braidio.importing._catalog import catalog_dir

    real_link = os.link

    def _no_space(src, dst, *a, **kw):
        if "artifacts" in str(dst):
            raise OSError(28, "No space left on device")
        return real_link(src, dst, *a, **kw)

    monkeypatch.setattr(os, "link", _no_space)
    # ENOSPC is not in the linkable-refusal allow-list, so it propagates —
    # it is a real failure, not a filesystem that cannot link.
    with pytest.raises(OSError, match="No space left"):
        _run(tmp_path, source)
    rows = list(catalog_dir(tmp_path / "project").glob("*.json"))
    assert rows == [], "a row was written for bytes that never landed"


@needs_illustration
def test_an_object_store_backend_refuses_rather_than_registering_into_the_void(
    tmp_path, source, monkeypatch
):
    """The one failure this module could not survive quietly.

    Everything else here fails loudly. Writing a perfectly correct catalog
    next to a project whose host resolves artifacts out of S3 produces an
    import that reports complete success and a project where every id still
    404s — this module's own defect, reintroduced one layer up.
    """
    from braidio.importing import CatalogBackendMismatch

    monkeypatch.setenv("REELEE_ARTIFACT_BACKEND", "aws")
    with pytest.raises(CatalogBackendMismatch, match="register_artifacts=False"):
        _run(tmp_path, source)
    assert not (tmp_path / "project").exists(), (
        "it must refuse before writing a node, not half-way through"
    )
    # the deliberate opt-out still works
    report = _run(tmp_path, source, register_artifacts=False)
    assert report.catalog.unregistered
    # and an unset / fs backend is unaffected
    monkeypatch.delenv("REELEE_ARTIFACT_BACKEND")
    assert _run(tmp_path / "fs", source).catalog.rows_written > 0


@needs_illustration
def test_two_mixes_with_one_file_name_are_refused_not_overwritten(tmp_path, source):
    """**Negative control** for a silent corruption.

    Each episode node's artifact is hashed from the destination *after* its
    own placement, so on a name clash the second node is correct and the
    first ends up pointing at the second's audio — with nothing raised, and
    every count in the report right.
    """
    from braidio.importing import ImportError_

    (source / "demo" / "other").mkdir(parents=True, exist_ok=True)
    (source / "demo" / "other" / "ep.mp3").write_bytes(b"a completely different mix")
    cut_a = dict(_doc()["cuts"][0])
    cut_b = dict(cut_a)
    cut_b["label"] = "v2"
    cut_b["audio"] = {"path": "other/ep.mp3", "duration_s": 20.0}
    with pytest.raises(ImportError_, match="share a file name"):
        _run(tmp_path, source, overrides={"cuts": [cut_a, cut_b]})


def test_registering_under_a_non_digest_id_is_refused_here_not_at_the_host():
    """The host validates `content_hash` as 64 lowercase hex. A row written
    under anything else is accepted by this module and refused when the host
    reads it back — a failure surfacing nowhere near its cause."""
    from braidio.importing._catalog import CatalogReport, register_artifact

    with pytest.raises(ValueError, match="64-character lowercase hex"):
        register_artifact(
            "/tmp/nowhere",
            "/tmp/nowhere/x.jpg",
            artifact_id="art-image-Ky3z",
            kind="image",
            generated_at="2026-01-01T00:00:00Z",
            report=CatalogReport(),
        )
    with pytest.raises(ValueError, match="64-character lowercase hex"):
        register_artifact(
            "/tmp/nowhere",
            "/tmp/nowhere/x.jpg",
            artifact_id="AB" * 32,  # uppercase: the host refuses it
            kind="image",
            generated_at="2026-01-01T00:00:00Z",
            report=CatalogReport(),
        )
