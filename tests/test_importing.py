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
    for name, blob in (
        ("ep.mp3", b"fake-audio-bytes"),
        ("one.jpg", b"fake-image-one"),
        ("two.jpg", b"fake-image-two"),
        ("out.mp4", b"fake-video"),
        ("motion.mp4", b"fake-motion-video"),
    ):
        (d / name).write_bytes(blob)
    return tmp_path / "src"


def _manifest(tmp_path, **overrides):
    from braidio.importing import load_manifest

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
def test_the_recorded_spelling_is_kept_not_the_canonical_code(tmp_path, source):
    """Normalization is the GATE, not the value: a credit reading 'CC BY-SA
    4.0' is the useful one and 'by-sa' is not."""
    from braidio.transforms._common import TIER_STILL

    report = _run(tmp_path, source)
    stills = {s.body["key"]: s for s in _annotations(tmp_path / "project", TIER_STILL)}
    assert stills["one#1"].body["license"] == "CC BY-SA 4.0"
    assert report.license_codes["one#1"] == "by-sa"


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
