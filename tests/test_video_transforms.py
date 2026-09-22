"""The picture track on the graph path (commentary-studio plan §3 + §5).

Offline and free: the audio boundaries are stubbed exactly as in
``tests/test_transforms.py``, the frame renderer (``braidio.video.render_video``)
and tituli's ffmpeg overlay are stubbed to write marker files, so no ElevenLabs,
no ffmpeg, no minutes of frames. Proves:

- the episode persists its timeline, and the reconstruction for a row written
  before that field existed equals the renderer's own;
- ``video_panels.plan`` cuts on the persisted timeline, pins each panel to a
  ``MediaRef`` span on the episode audio, mints seeds that survive reordering,
  honours a pick map, refuses an unknown key, and is idempotent per episode;
- ``video_cut.render``'s cache key moves when a panel's move changes and does
  NOT move when only a still's label changes — the two-transform split
  earning itself — and a label edit is served from the cache, not re-rendered;
- ``video_cut.finish`` composites labels through tituli, writes the SRT from
  the beats' own text, and its key DOES move on a label edit.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_NW, reason="nw (and lacing) not available"
)


# --- fixtures (mirroring tests/test_transforms.py) ---------------------------


class _FakeSource:
    def __init__(self, asset_path: Path, *, start_s: float = 1.0, end_s: float = 4.0):
        self._asset_path, self._start_s, self._end_s = asset_path, start_s, end_s

    def resolve(self, reference: str):
        from braidio.sources import ResolvedSegment

        return ResolvedSegment(
            asset_path=self._asset_path,
            start_s=self._start_s,
            end_s=self._end_s,
            score=1.0,
            matched_text=reference,
        )


def _write(out_path, tag: bytes) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tag)
    return p


@pytest.fixture
def patched_synthesis(monkeypatch):
    def _narrate(text, out, *, return_cache_status=False, **kw):
        p = _write(out, b"TTS")
        return (p, False) if return_cache_status else p

    monkeypatch.setattr(braidio, "narrate", _narrate)
    monkeypatch.setattr(
        braidio, "extract_padded", lambda a, s, e, out, **kw: _write(out, b"CLIP")
    )
    monkeypatch.setattr(
        braidio, "weave_timeline", lambda items, out, **kw: _write(out, b"EPISODE")
    )
    monkeypatch.setattr(
        braidio.structure, "prepare_sting", lambda st, out, **kw: _write(out, b"STING")
    )
    monkeypatch.setattr(
        braidio.structure, "prepare_pause", lambda s, out, **kw: _write(out, b"PAUSE")
    )
    # every rendered part probes as 8 s: long enough that plan_spans splits and
    # merges something, short enough to read
    monkeypatch.setattr(braidio, "duration_s", lambda path: 8.0)


@pytest.fixture
def project(tmp_path):
    return braidio.Project.init(tmp_path / "proj", title="test video")


@pytest.fixture
def episode(project, tmp_path, patched_synthesis):
    """A woven 4-member episode: narration, clip, scene break, narration."""
    song = tmp_path / "song.mp3"
    song.write_bytes(b"SONG")
    script = braidio.Script(
        title="Demo",
        id_slug="demo",
        beats=[
            braidio.Narration(
                text="Opening line about the song. Then a second sentence."
            ),
            braidio.SegmentBeat(reference="the famous hook", label="hook"),
            braidio.SceneBreak(label="act 2"),
            braidio.Narration(text="Closing thought on the hook."),
        ],
    )
    return braidio.weave_project(project, script, source=_FakeSource(song))


def _png(path: Path, size=(64, 48), color=(200, 40, 40)) -> Path:
    PIL = pytest.importorskip("PIL.Image")
    path.parent.mkdir(parents=True, exist_ok=True)
    PIL.new("RGB", size, color).save(path)
    return path


def add_still(project, path: Path, *, key: str, labelled: bool, subject=None, **rights):
    """Write a ``still/v1`` node for ``path`` (the Wave-2 importer's job, inlined)."""
    from lacing import Annotation, Artifact

    from braidio.bodies import STILL_V1, StillBodyV1
    from braidio.transforms._common import TIER_STILL, file_url, node_ref
    from braidio.transforms._ingest import _authored_provenance

    artifact = Artifact.from_path(
        path, kind="image", was_generated_by="test", was_attributed_to="test"
    )
    ann = Annotation(
        id=uuid.uuid4(),
        tier=TIER_STILL,
        reference=node_ref(TIER_STILL),
        body=StillBodyV1(
            key=key,
            artifact_id=artifact.asset_id,
            url=file_url(path),
            labelled=labelled,
            subject=subject,
            license=rights.pop("license", "cc-by-4.0"),
            author=rights.pop("author", "Someone"),
            **rights,
        ).model_dump(mode="json"),
        body_schema_uri=STILL_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(ann)
    return ann


@pytest.fixture
def stills(project, tmp_path):
    return [
        add_still(
            project,
            _png(tmp_path / "a.png"),
            key="a",
            labelled=True,
            subject="Alice, 1971",
        ),
        add_still(
            project,
            _png(tmp_path / "b.png", color=(40, 200, 40)),
            key="b",
            labelled=False,
        ),
        add_still(
            project,
            _png(tmp_path / "c.png", color=(40, 40, 200)),
            key="c",
            labelled=True,
            subject="Carol",
        ),
    ]


def _rewrite_in_place(project, ann, *, body: dict):
    """Replace ``ann``'s body under its id — what a real edit does (see
    tests/test_transforms.py for why this goes back through add_annotation)."""
    import nw
    from lacing.time import RationalTime

    updated = ann.model_copy(
        update={
            "body": body,
            "provenance": ann.provenance.model_copy(
                update={"generated_at_time": RationalTime.now()}
            ),
        }
    )
    with nw.open_project_stores(project.root) as stores:
        for store in stores:
            if store.remove(ann.id) is not None:
                break
    project.graph.add_annotation(updated)
    return updated


def _run(name, project, *primary, params=None, **kw):
    import nw
    from nw import TransformInputs

    t = nw.get_transform(name)
    plan, skel = t.plan(project, TransformInputs(primary=tuple(primary)), params=params)
    return t.execute(project, plan, skel, **kw)


def _plan(name, project, *primary, params=None):
    import nw
    from nw import TransformInputs

    return nw.get_transform(name).plan(
        project, TransformInputs(primary=tuple(primary)), params=params
    )


# --- the timeline ---------------------------------------------------------------


def test_episode_persists_its_timeline(project, episode):
    from braidio.timeline import TimelineBreakdown
    from braidio.transforms import episode_timeline

    persisted = episode.body["timeline"]
    assert persisted and len(persisted["beats"]) == 4
    tl = episode_timeline(project, episode)
    assert tl == TimelineBreakdown.from_dict(persisted)
    assert [b.kind for b in tl.beats] == [
        "narration",
        "clip",
        "scene-break",
        "narration",
    ]
    assert tl.beats[1].source_start == 1.0 and tl.beats[1].source_end == 4.0
    assert tl.beats[0].label.startswith("Opening line")
    assert tl.settings["profile"] == "personal"


def test_timeline_reconstruction_equals_the_renderers_own(project, episode):
    """A row written before ``timeline`` existed: reconstructed from
    ``ordered_member_ids`` + member durations through the SAME function the
    render used, so the cut points are identical."""
    from braidio.transforms import episode_timeline

    legacy = episode.model_copy(
        update={"body": {k: v for k, v in episode.body.items() if k != "timeline"}}
    )
    assert "timeline" not in legacy.body
    assert episode_timeline(project, legacy).to_dict() == episode.body["timeline"]


def test_timeline_reconstruction_reproduces_the_renderer_arithmetic_when_files_are_gone(
    project, episode, monkeypatch
):
    """The two traps: a segment's body holds the UNPADDED window (the rendered
    clip is longer, by the pads + floor), and a scene break carries no
    duration at all (its pause comes from the production structure). With the
    rendered files gone the reconstruction reproduces the render arithmetic."""
    from braidio.transforms import episode_timeline
    from braidio.transforms._common import url_to_path

    index = {str(a.id): a for a in __import__("nw").iter_all_annotations(project.root)}
    members = [index[m] for m in episode.body["ordered_member_ids"]]
    url_to_path(members[1].body["url"]).unlink()  # the clip
    (project.root / "data" / "breaks" / f"{members[2].id}.mp3").unlink()
    legacy = episode.model_copy(
        update={"body": {k: v for k, v in episode.body.items() if k != "timeline"}}
    )
    tl = episode_timeline(project, legacy)
    # clip: [1.0, 4.0] padded by the default 0.4 / 0.3 → 3.7 s (over the 2.2 floor)
    assert tl.beats[1].duration == pytest.approx(3.7)
    # scene break with no sting: the structure's default pause
    assert tl.beats[2].duration == pytest.approx(braidio.DEFAULT_STRUCTURE.pause_s)
    # spoken takes: the body's own duration_s
    assert tl.beats[0].duration == pytest.approx(members[0].body["duration_s"])


# --- video_panels.plan --------------------------------------------------------------


def test_panels_plan_cuts_on_the_persisted_timeline(project, episode, stills):
    from braidio.transforms import VIDEO_PANELS_TRANSFORM, episode_timeline
    from braidio.video import plan_spans

    result = _run(VIDEO_PANELS_TRANSFORM, project, episode)
    panels = list(result.annotations)
    spans = plan_spans(episode_timeline(project, episode))
    assert len(panels) == len(spans) > 1
    audio_id = episode.body["artifact_id"]
    for panel, span in zip(panels, spans):
        assert panel.reference.kind == "media" and panel.reference.asset_id == audio_id
        iv = panel.reference.interval
        assert iv.start.to_seconds() == pytest.approx(span.start, abs=1e-3)
        assert iv.end.to_seconds() == pytest.approx(span.end, abs=1e-3)
        assert uuid.UUID(panel.body["still_id"]) in {s.id for s in stills}
        assert episode.id in panel.provenance.was_derived_from
    assert [p.body["order"] for p in panels] == list(range(len(panels)))
    # gapless
    for a, b in zip(panels, panels[1:]):
        assert a.reference.interval.end == b.reference.interval.start


def test_panel_seeds_are_minted_from_the_beat_not_the_ordinal(project, episode, stills):
    from braidio.transforms import VIDEO_PANELS_TRANSFORM, mint_seed

    _plan1 = _plan(VIDEO_PANELS_TRANSFORM, project, episode)[1]
    _plan2 = _plan(VIDEO_PANELS_TRANSFORM, project, episode)[1]
    assert [p.body["seed"] for p in _plan1] == [p.body["seed"] for p in _plan2]
    # the seed is a function of (beat_id, index within beat) — never of `order`
    within: dict = {}
    for p in _plan1:
        k = within.get(p.body["beat_id"], 0)
        within[p.body["beat_id"]] = k + 1
        assert p.body["seed"] == mint_seed(p.body["beat_id"], k)
    assert len({p.body["seed"] for p in _plan1}) == len(_plan1)


def test_panels_plan_honours_picks_and_refuses_an_unknown_key(project, episode, stills):
    from braidio.transforms import VIDEO_PANELS_TRANSFORM, picks_from_panels
    from braidio.transforms._common import graph_index

    first_beat = _plan(VIDEO_PANELS_TRANSFORM, project, episode)[1][0].body["beat_id"]
    skels = _plan(
        VIDEO_PANELS_TRANSFORM, project, episode, params={"picks": {first_beat: ["c"]}}
    )[1]
    by_id = {s.id: s for s in stills}
    for p in skels:
        if p.body["beat_id"] == first_beat:
            assert by_id[uuid.UUID(p.body["still_id"])].body["key"] == "c"
    # and the pick map round-trips out of a track, for carrying choices forward
    assert picks_from_panels(skels, graph_index(project))[first_beat][0] == "c"
    with pytest.raises(ValueError, match="does not hold"):
        _plan(
            VIDEO_PANELS_TRANSFORM,
            project,
            episode,
            params={"picks": {first_beat: ["nope"]}},
        )


def test_panels_plan_is_idempotent_by_value_and_a_track_is_an_identity(
    project, episode, stills
):
    import nw

    from braidio.transforms import (
        VIDEO_PANELS_TRANSFORM,
        panels_for_episode,
        picks_from_panels,
        tracks_for_episode,
    )
    from braidio.transforms._common import graph_index

    first = _run(VIDEO_PANELS_TRANSFORM, project, episode).annotations
    second = _run(VIDEO_PANELS_TRANSFORM, project, episode).annotations
    assert [a.id for a in first] == [a.id for a in second]
    assert len({a.body["track_id"] for a in first}) == 1
    assert len(nw.annotations_at_tier(project.root, "video-panels")) == len(first)

    # a plan that says something else (different picks) is NOT the same track:
    # it is written beside the first, never over it, and becomes the latest
    beat = first[0].body["beat_id"]
    other = (
        "c" if picks_from_panels(first, graph_index(project))[beat][0] != "c" else "b"
    )
    third = _run(
        VIDEO_PANELS_TRANSFORM, project, episode, params={"picks": {beat: [other]}}
    ).annotations
    assert {a.id for a in third}.isdisjoint({a.id for a in first})
    assert len(tracks_for_episode(project, episode.id)) == 2
    latest = panels_for_episode(project, episode.id)
    assert [a.id for a in latest] == [a.id for a in third]
    assert [a.body["order"] for a in latest] == list(range(len(third)))
    # a named track is retrievable whole, and picks read from ONE track
    assert [
        a.id
        for a in panels_for_episode(
            project, episode.id, track_id=first[0].body["track_id"]
        )
    ] == [a.id for a in first]
    assert all(
        len(v) <= 2 for v in picks_from_panels(latest, graph_index(project)).values()
    )

    # force writes a new track even for the same value
    forced = _run(VIDEO_PANELS_TRANSFORM, project, episode, force=True).annotations
    assert {a.id for a in forced}.isdisjoint(
        {a.id for a in first} | {a.id for a in third}
    )
    assert len(tracks_for_episode(project, episode.id)) == 3


# --- video_cut.render ----------------------------------------------------------------


@pytest.fixture
def patched_render(monkeypatch):
    calls: list[dict] = []

    def _render_video(panels, *, audio_path, out_path, size, fps, workdir=None, **kw):
        calls.append({"panels": panels, "size": size, "fps": fps})
        return _write(out_path, b"MOTION" + str(len(calls)).encode())

    monkeypatch.setattr(braidio.video, "render_video", _render_video)
    return calls


@pytest.fixture
def panels(project, episode, stills):
    from braidio.transforms import VIDEO_PANELS_TRANSFORM

    return list(_run(VIDEO_PANELS_TRANSFORM, project, episode).annotations)


def test_render_produces_a_motion_cut(project, episode, stills, panels, patched_render):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM

    result = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)
    cut = result.annotations[0]
    assert cut.tier == "video-cuts" and cut.body["stage"] == "motion"
    assert cut.body["audio_artifact_id"] == episode.body["artifact_id"]
    assert cut.body["panel_ids"] == [str(p.id) for p in panels]
    assert cut.body["artifact_id"] and cut.body["url"].endswith("_motion.mp4")
    assert result.artifacts[0].kind == "video"
    assert len(patched_render) == 1
    assert len(patched_render[0]["panels"]) == len(panels)
    # provenance reaches the panels, their stills and the episode
    parents = set(cut.provenance.was_derived_from)
    assert {p.id for p in panels} <= parents and episode.id in parents
    assert {uuid.UUID(p.body["still_id"]) for p in panels} <= parents


def test_render_cache_key_moves_on_a_move_and_not_on_a_label(
    project, episode, stills, panels, patched_render
):
    """The two-transform split earning itself: what reaches a pixel is in the
    motion key; the still's label is not."""
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM
    from braidio.transforms._common import graph_index

    key0 = _plan(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)[1][0].body["cache_key"]

    # edit a still's label (subject) only
    still = graph_index(project)[uuid.UUID(panels[0].body["still_id"])]
    _rewrite_in_place(
        project, still, body={**still.body, "subject": "Someone else entirely"}
    )
    panels = [graph_index(project)[p.id] for p in panels]
    key_after_label = _plan(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)[1][0].body[
        "cache_key"
    ]
    assert key_after_label == key0

    # now change a panel's move
    new_move = "drift_left" if panels[0].body["move"] != "drift_left" else "push_in"
    edited = _rewrite_in_place(
        project, panels[0], body={**panels[0].body, "move": new_move}
    )
    key_after_move = _plan(VIDEO_CUT_RENDER_TRANSFORM, project, edited, *panels[1:])[1][
        0
    ].body["cache_key"]
    assert key_after_move != key0


def test_a_label_edit_is_served_from_the_motion_cache_not_re_rendered(
    project, episode, stills, panels, patched_render
):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM
    from braidio.transforms._common import graph_index

    first = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    assert len(patched_render) == 1
    still = graph_index(project)[uuid.UUID(panels[0].body["still_id"])]
    _rewrite_in_place(project, still, body={**still.body, "subject": "Renamed"})
    panels = [graph_index(project)[p.id] for p in panels]
    import nw

    stale_before = {
        v.annotation.id for v in nw.stale_verdicts_all(project.root) if v.is_stale
    }
    assert first.id in stale_before  # nw's transitive verdict: the still's digest moved
    second = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    # the plan re-derives to the same key, so the existing cut is RE-VERIFIED
    # under its own id — no render, no twin node, and the verdict clears
    assert len(patched_render) == 1
    assert second.id == first.id
    assert second.body["artifact_id"] == first.body["artifact_id"]
    assert len(nw.annotations_at_tier(project.root, "video-cuts")) == 1
    stale_after = {
        v.annotation.id for v in nw.stale_verdicts_all(project.root) if v.is_stale
    }
    assert first.id not in stale_after
    # and an unchanged re-run is the same node (idempotent)
    third = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    assert third.id == second.id and len(patched_render) == 1


def test_a_move_edit_re_renders(project, episode, stills, panels, patched_render):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM

    _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)
    edited = _rewrite_in_place(project, panels[0], body={**panels[0].body, "zoom": 1.4})
    _run(VIDEO_CUT_RENDER_TRANSFORM, project, edited, *panels[1:])
    assert len(patched_render) == 2


# --- video_cut.finish -------------------------------------------------------------------


@pytest.fixture
def patched_overlay(monkeypatch):
    pytest.importorskip("tituli")
    import tituli.video

    calls: list[list] = []

    def _overlay(video, overlays, dst, **kw):
        calls.append(list(overlays))
        return _write(dst, Path(video).read_bytes() + b"+TEXT")

    monkeypatch.setattr(tituli.video, "overlay", _overlay)
    return calls


def _add_label_track(project, episode, *, start, end, **body):
    from lacing import Annotation, MediaRef, TimeInterval

    from braidio.bodies import LABEL_TRACK_V1, LabelTrackBodyV1
    from braidio.transforms._common import TIER_LABEL_TRACK
    from braidio.transforms._ingest import _authored_provenance

    ann = Annotation(
        id=uuid.uuid4(),
        tier=TIER_LABEL_TRACK,
        reference=MediaRef(
            asset_id=episode.body["artifact_id"],
            interval=TimeInterval.from_seconds(start, end, rate=1000),
        ),
        body=LabelTrackBodyV1(**body).model_dump(mode="json"),
        body_schema_uri=LABEL_TRACK_V1,
        provenance=_authored_provenance(),
    )
    project.graph.add_annotation(ann)
    return ann


def test_finish_composites_labels_and_writes_captions(
    project, episode, stills, panels, patched_render, patched_overlay
):
    from tituli import Label, UNLABELLED

    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    card = _add_label_track(
        project,
        episode,
        start=0.0,
        end=4.0,
        kind="title",
        headline="Demo",
        lines=["a film"],
    )
    result = _run(VIDEO_CUT_FINISH_TRANSFORM, project, motion, params={"label": "v1"})
    cut = result.annotations[0]
    assert cut.body["stage"] == "delivered" and cut.body["label"] == "v1"
    assert cut.body["panel_ids"] == motion.body["panel_ids"]
    assert cut.body["audio_artifact_id"] == motion.body["audio_artifact_id"]
    # the captions sidecar is from the beats' own text, never ASR
    srt = Path(cut.body["url"][len("file://") :]).with_suffix(".srt")
    assert cut.body["captions_artifact_id"] and srt.exists()
    assert "Opening line about the song." in srt.read_text()
    # tituli got the card and one label per LABELLED still; the unlabelled
    # still contributed nothing rather than a blank
    (overlays,) = patched_overlay
    payloads = [o.payload for o in overlays]
    assert any(isinstance(p, dict) and p.get("kind") == "title" for p in payloads)
    labels = [p for p in payloads if isinstance(p, Label)]
    assert labels and all(l.text in {"Alice, 1971", "Carol"} for l in labels)
    assert all(p is not UNLABELLED for p in payloads)
    # provenance: the motion cut, the card, the panels and the stills
    parents = set(cut.provenance.was_derived_from)
    assert motion.id in parents and card.id in parents
    assert {p.id for p in panels} <= parents


def test_finish_key_moves_on_a_label_edit(
    project, episode, stills, panels, patched_render, patched_overlay
):
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )
    from braidio.transforms._common import graph_index

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    key0 = _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion)[1][0].body["cache_key"]
    still = graph_index(project)[uuid.UUID(panels[0].body["still_id"])]
    _rewrite_in_place(project, still, body={**still.body, "subject": "Renamed"})
    key1 = _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion)[1][0].body["cache_key"]
    assert key1 != key0


def test_finish_refuses_a_credits_roll_over_an_unlicensed_still(
    project, episode, tmp_path, patched_render, patched_overlay
):
    """Credits are a licence obligation: a still with no licence cannot be
    credited, and the plan says so before any frame is touched."""
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
        VIDEO_PANELS_TRANSFORM,
    )

    add_still(project, _png(tmp_path / "u.png"), key="u", labelled=False, license=None)
    panels = list(_run(VIDEO_PANELS_TRANSFORM, project, episode).annotations)
    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    with pytest.raises(ValueError, match="no licence recorded"):
        _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion, params={"credits_s": 8.0})


# --- the move -------------------------------------------------------------------------


def test_every_move_resolves_to_a_burns_path(tmp_path):
    pytest.importorskip("burns")
    from burns import BurnsPath

    from braidio.bodies import MOVES
    from braidio.transforms import path_for_panel, resolve_move

    image = _png(tmp_path / "m.png", size=(160, 90))
    for i, move in enumerate(MOVES):
        path = resolve_move(move, image=str(image), aspect=16 / 9, zoom=1.2, seed=i)
        assert isinstance(path, BurnsPath) and path.output_aspect == pytest.approx(
            16 / 9
        )
    # the stored path is the other front door, and wins
    stored = resolve_move("push_in", image=str(image), aspect=16 / 9, seed=3).to_dict()
    body = {"move": "hold", "zoom": 1.0, "seed": 0, "path": stored}
    assert path_for_panel(body, image=str(image), aspect=16 / 9) == BurnsPath.from_dict(
        stored
    )
    # a focus box (a RectV1 dump on the panel) is honoured on the pushes — the
    # panel door converts it to the (x, y, w, h) tuple burns takes
    focused = {
        "move": "push_in",
        "zoom": 1.2,
        "seed": 0,
        "focus": {"x": 0.1, "y": 0.1, "w": 0.3, "h": 0.3},
    }
    assert isinstance(
        path_for_panel(focused, image=str(image), aspect=16 / 9), BurnsPath
    )
    assert isinstance(
        resolve_move(
            "push_in", image=str(image), aspect=16 / 9, focus=(0.1, 0.1, 0.3, 0.3)
        ),
        BurnsPath,
    )


def test_finish_refuses_a_motion_cut_whose_frames_would_differ(
    project, episode, stills, panels, patched_render, patched_overlay
):
    """A still swap after the motion was rendered: finish must not composite
    the new still's label over the old still's frames."""
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    other = next(s for s in stills if s.id != uuid.UUID(panels[0].body["still_id"]))
    _rewrite_in_place(
        project, panels[0], body={**panels[0].body, "still_id": str(other.id)}
    )
    with pytest.raises(ValueError, match="out of date"):
        _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion)


def test_finish_fails_an_overlay_collision_at_plan_time(
    project, episode, stills, panels, patched_render, patched_overlay
):
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    _add_label_track(
        project, episode, start=0.0, end=6.0, kind="context", headline="A", lines=["x"]
    )
    _add_label_track(
        project, episode, start=3.0, end=9.0, kind="context", headline="B", lines=["y"]
    )
    with pytest.raises(ValueError, match="collide"):
        _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion)
    assert patched_overlay == []  # nothing was rendered


def test_a_fresh_cut_whose_file_is_gone_is_re_rendered(
    project, episode, stills, panels, patched_render
):
    """The fresh-equivalent door, with no edit at all: a node is not a cut."""
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM
    from braidio.transforms._common import url_to_path

    first = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    url_to_path(first.body["url"]).unlink()
    second = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    assert len(patched_render) == 2
    assert url_to_path(second.body["url"]).exists()


def test_a_cached_cut_whose_file_is_gone_is_not_adopted(
    project, episode, stills, panels, patched_render
):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM
    from braidio.transforms._common import graph_index, url_to_path

    first = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    url_to_path(first.body["url"]).unlink()
    still = graph_index(project)[uuid.UUID(panels[0].body["still_id"])]
    _rewrite_in_place(project, still, body={**still.body, "subject": "Renamed"})
    panels = [graph_index(project)[p.id] for p in panels]
    second = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    assert len(patched_render) == 2  # re-rendered: the product is the file
    assert url_to_path(second.body["url"]).exists()


def test_published_profile_refuses_an_unlicensed_still(
    project, episode, tmp_path, stills, patched_render
):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM, VIDEO_PANELS_TRANSFORM

    add_still(project, _png(tmp_path / "u.png"), key="u", labelled=False, license=None)
    panels = list(
        _run(VIDEO_PANELS_TRANSFORM, project, episode, force=True).annotations
    )
    _rewrite_in_place(project, episode, body={**episode.body, "profile": "published"})
    with pytest.raises(ValueError, match="published"):
        _plan(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)


def test_an_edited_track_is_still_the_track_a_re_plan_returns(project, episode, stills):
    """Editing a panel's move must not make the next re-plan write a new
    track and hide the edit behind 'the latest'."""
    from braidio.transforms import VIDEO_PANELS_TRANSFORM, panels_for_episode

    first = list(_run(VIDEO_PANELS_TRANSFORM, project, episode).annotations)
    _rewrite_in_place(project, first[0], body={**first[0].body, "move": "drift_left"})
    again = _run(VIDEO_PANELS_TRANSFORM, project, episode).annotations
    assert [a.id for a in again] == [a.id for a in first]
    assert panels_for_episode(project, episode.id)[0].body["move"] == "drift_left"


def test_finish_stamps_and_gates_the_episodes_current_profile(
    project, episode, stills, panels, patched_render, patched_overlay
):
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )
    from braidio.transforms._common import graph_index

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    _rewrite_in_place(project, episode, body={**episode.body, "profile": "published"})
    cut = _run(VIDEO_CUT_FINISH_TRANSFORM, project, motion).annotations[0]
    assert cut.body["profile"] == "published"  # as the episode stands NOW
    still = graph_index(project)[uuid.UUID(panels[0].body["still_id"])]
    _rewrite_in_place(project, still, body={**still.body, "license": None})
    with pytest.raises(ValueError, match="published"):
        _plan(VIDEO_CUT_FINISH_TRANSFORM, project, motion)


def test_a_stored_path_for_another_aspect_fails_the_render_plan(
    project, episode, stills, panels
):
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM

    four_three = {
        "version": 1,
        "keyframes": [
            {"t": 0.0, "rect": {"x": 0, "y": 0, "w": 1, "h": 1}},
            {"t": 1.0, "rect": {"x": 0.1, "y": 0.1, "w": 0.8, "h": 0.8}},
        ],
        "interp": "linear",
        "easing": "ease-in-out",
        "output_aspect": 4 / 3,
    }
    edited = _rewrite_in_place(
        project, panels[0], body={**panels[0].body, "path": four_three}
    )
    with pytest.raises(ValueError, match="aspect"):
        _plan(VIDEO_CUT_RENDER_TRANSFORM, project, edited, *panels[1:])


def test_finish_leaves_no_staging_file_where_the_lister_looks(
    project, episode, stills, panels, patched_render, patched_overlay, monkeypatch
):
    """A crash mid-chain must not leave an mp4 directly in data/cuts."""
    import tituli.video

    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]
    _add_label_track(project, episode, start=0.0, end=4.0, kind="title", headline="T")

    def _overlay_then_die(video, overlays, dst, **kw):
        _write(dst, b"PARTIAL")
        raise RuntimeError("ffmpeg died")

    monkeypatch.setattr(tituli.video, "overlay", _overlay_then_die)
    with pytest.raises(RuntimeError):
        _run(VIDEO_CUT_FINISH_TRANSFORM, project, motion)
    cuts = project.root / "data" / "cuts"
    assert [p.name for p in cuts.iterdir() if p.suffix == ".mp4"] == [
        Path(motion.body["url"]).name
    ]


def test_a_caption_overflow_names_the_still_and_the_delivery(
    project, episode, stills, panels, patched_render, monkeypatch
):
    """thorwhalen/braidio#77 item 4: whatever the eventual fix for the fit
    itself, the error at least has to say which still and which delivery —
    tituli's own message names only the truncated text. Fires regardless of
    (1)-(3) because it wraps the SAME ``TextDoesNotFit`` tituli always
    raises."""
    pytest.importorskip("tituli")
    import tituli.video
    from tituli.compose import TextDoesNotFit

    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
    )

    motion = _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels).annotations[0]

    def _overlay_overflows(video, overlays, dst, **kw):
        # still "a" is labelled with subject "Alice, 1971" (see the `stills`
        # fixture) — this is exactly the text tituli could not set.
        raise TextDoesNotFit("Alice, 1971", 0.022, 4, 3)

    monkeypatch.setattr(tituli.video, "overlay", _overlay_overflows)
    with pytest.raises(TextDoesNotFit) as exc_info:
        _run(VIDEO_CUT_FINISH_TRANSFORM, project, motion)
    message = str(exc_info.value)
    assert "'a'" in message  # the still's key, not just the truncated text
    assert "1920x1080" in message  # the delivery's size
    # tituli's own structured attributes survive, for a programmatic catcher
    assert exc_info.value.text == "Alice, 1971"
    assert exc_info.value.max_lines == 3


def test_motion_key_names_the_move_resolver(
    project, episode, stills, panels, monkeypatch
):
    """burns' resolve_move and the shim frame six of eight moves differently,
    so which one ran is part of the key: the day burns ships the name, cuts
    re-render rather than being served under a framing the panel no longer
    describes."""
    import braidio.transforms._video_cut as vc
    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM

    key0 = _plan(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)[1][0].body["cache_key"]
    monkeypatch.setattr(vc, "resolver_identity", lambda: "somebody.else")
    key1 = _plan(VIDEO_CUT_RENDER_TRANSFORM, project, *panels)[1][0].body["cache_key"]
    assert key1 != key0


def test_canvases_are_keyed_on_bytes_and_size_never_ordinal_or_stem(
    project, episode, tmp_path, monkeypatch
):
    """Two stills with one filename stem at the same ordinal, and one project
    cut at two sizes: the prepared canvas must follow the bytes and the
    frame, or a swapped still ships the old picture and a vertical cut reuses
    a landscape canvas (both reproduced by the adversarial review)."""
    pytest.importorskip("burns")
    import burns
    from PIL import Image

    from braidio.transforms import VIDEO_CUT_RENDER_TRANSFORM, VIDEO_PANELS_TRANSFORM

    captured: list[list] = []

    def _film(triples, *, saveas, fps, audio_path=None, **kw):
        captured.append(list(triples))
        return _write(saveas, b"FILM")

    monkeypatch.setattr(burns, "ken_burns_film", _film)
    red = add_still(
        project,
        _png(tmp_path / "a" / "portrait.png", size=(64, 96), color=(220, 30, 30)),
        key="red",
        labelled=False,
    )
    blue = add_still(
        project,
        _png(tmp_path / "b" / "portrait.png", size=(64, 96), color=(30, 30, 220)),
        key="blue",
        labelled=False,
    )
    panels = list(
        _run(
            VIDEO_PANELS_TRANSFORM,
            project,
            episode,
            params={"picks": {p: ["red"] for p in {"0000", "0001", "0003"}}},
        ).annotations
    )
    small = {"size": (96, 54), "fps": 6}
    _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels, params=small)
    # swap the first panel to the same-stem blue still and render again
    panels[0] = _rewrite_in_place(
        project, panels[0], body={**panels[0].body, "still_id": str(blue.id)}
    )
    _run(VIDEO_CUT_RENDER_TRANSFORM, project, *panels, params=small)
    canvas_red, canvas_blue = captured[0][0][0], captured[1][0][0]
    assert canvas_red != canvas_blue
    with Image.open(canvas_blue) as im:
        assert im.getpixel((48, 27))[2] > 150  # the blue still, not a stale red canvas
    # a vertical cut of the same panels does not reuse the landscape canvas
    _run(
        VIDEO_CUT_RENDER_TRANSFORM,
        project,
        *panels,
        params={"size": (54, 96), "fps": 6},
    )
    with Image.open(captured[2][0][0]) as im:
        assert im.size == (54, 96)


def test_clips_emit_no_caption(project, episode):
    """A clip's text is not known on the graph (only its label is stored),
    so it contributes no cue — a caption is a claim about what is heard."""
    from braidio.transforms._video_cut import _captions_srt

    srt = _captions_srt(project, episode, max_chars=42)
    assert "♪" not in srt and "♪ hook ♪" not in srt
    assert "Opening line" in srt and "Closing thought" in srt


# --- the genre -----------------------------------------------------------------------


def test_commentary_weave_genre_carries_the_picture_track():
    import nw

    from braidio.formats import FORMATS
    from braidio.transforms import (
        VIDEO_CUT_FINISH_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
        VIDEO_PANELS_TRANSFORM,
    )

    genre = nw.get_genre("commentary_weave")
    assert genre.is_ready()
    for uri in (
        "annot://schema/still/v1",
        "annot://schema/video-panel/v1",
        "annot://schema/video-cut/v1",
        "annot://schema/label-track/v1",
    ):
        assert uri in genre.body_schema_uris
    for name in (
        VIDEO_PANELS_TRANSFORM,
        VIDEO_CUT_RENDER_TRANSFORM,
        VIDEO_CUT_FINISH_TRANSFORM,
    ):
        assert name in genre.transform_names
    assert "commentary-video" in genre.intake_kinds
    # a video is a delivery, orthogonal to format: the templates are untouched
    assert {t.slug for t in genre.templates} == set(FORMATS)
    assert genre.projection_entrypoint == "weave_to_episode.default"
