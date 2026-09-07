"""Offline tests for braidio's nw.Transform pipeline (thorwhalen/braidio#6).

Drives the whole ``commentary_weave`` chain (ingest → voice-assignment →
narration-render → segment-extraction → weave-to-episode) with the synthesis
boundaries (``narrate`` / ``extract_padded`` / ``weave_timeline``)
monkeypatched, so no ElevenLabs / ffmpeg runs. Asserts:

- every authoring + render node lands in the project graph;
- ``nw.stale_after`` (over ``project.graph``, not braidio's standalone store)
  returns exactly the right partial-re-render frontier for a config change, a
  narration-beat change, and a source change;
- the explicit ``cache_key`` compare-and-skip reuses an existing render;
- the ``commentary_weave`` genre is registered and ready.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_NW, reason="nw (and lacing) not available"
)


class _FakeSource:
    """A SegmentSource that resolves any reference to a fixed window."""

    def __init__(self, asset_path: Path, *, start_s: float = 1.0, end_s: float = 4.0):
        self._asset_path = asset_path
        self._start_s = start_s
        self._end_s = end_s

    def resolve(self, reference: str):
        from braidio.sources import ResolvedSegment

        return ResolvedSegment(
            asset_path=self._asset_path,
            start_s=self._start_s,
            end_s=self._end_s,
            score=1.0,
            matched_text=reference,
        )


@pytest.fixture
def patched_synthesis(monkeypatch):
    """Replace the audio boundaries with file-writing stubs (no real synth)."""

    def _write(out_path, tag: bytes):
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(tag)
        return p

    def _narrate(text, out, *, return_cache_status=False, **kw):
        p = _write(out, b"TTS")  # default: live synth (was_cached=False)
        return (p, False) if return_cache_status else p

    monkeypatch.setattr(braidio, "narrate", _narrate)
    monkeypatch.setattr(
        braidio,
        "extract_padded",
        lambda asset, start, end, out, **kw: _write(out, b"CLIP"),
    )
    monkeypatch.setattr(
        braidio, "weave_timeline", lambda items, out, **kw: _write(out, b"EPISODE")
    )
    # scene breaks: stub the two ffmpeg-backed structure primitives too, so this
    # module stays ffmpeg-free (the real-audio graph path is covered in
    # tests/test_transforms_structure.py).
    monkeypatch.setattr(
        braidio.structure, "prepare_sting", lambda st, out, **kw: _write(out, b"STING")
    )
    monkeypatch.setattr(
        braidio.structure, "prepare_pause", lambda s, out, **kw: _write(out, b"PAUSE")
    )
    monkeypatch.setattr(braidio, "duration_s", lambda path: 2.0)


@pytest.fixture
def project(tmp_path):
    return braidio.Project.init(tmp_path / "proj", title="test weave")


@pytest.fixture
def script_and_source(tmp_path):
    """A 3-beat script (narration, segment, narration) + a fake source."""
    song = tmp_path / "song.mp3"
    song.write_bytes(b"SONG")
    script = braidio.Script(
        title="Demo",
        id_slug="demo",
        beats=[
            braidio.Narration(text="Opening line about the song."),
            braidio.SegmentBeat(reference="the famous hook", label="hook"),
            braidio.Narration(text="Closing thought on the hook."),
        ],
    )
    return script, _FakeSource(song)


def _tier_ids(project, tier):
    import nw

    return {a.id for a in nw.annotations_at_tier(project.root, tier)}


def _rewrite_in_place(project, ann, *, body: dict):
    """Replace ``ann``'s body keeping its id — what a real edit does.

    ``nw.stale_after`` grew a verifying-trace early cutoff (nw#24): freshly
    derived nodes whose traces match their parents' *current* digests are
    fresh, so querying it right after a weave — with nothing changed — is
    correctly empty. To assert a re-render frontier the fixture must actually
    change the parent. ``store.add`` is a plain INSERT, so in-place update is
    remove-then-add; going back through ``add_annotation`` is the point — it
    re-records the trace (idiom from nw's tests/test_freshness.py).
    """
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


def test_weave_project_populates_graph(project, script_and_source, patched_synthesis):
    import nw

    script, source = script_and_source
    episode = braidio.weave_project(project, script, source=source)

    # The episode is complete: it references the assembled audio.
    assert episode.tier == "episode-renders"
    assert episode.body["artifact_id"]
    assert episode.body["url"].startswith("file://")
    assert len(episode.body["ordered_member_ids"]) == 3  # 2 narration + 1 segment

    # Every authoring + render node landed in the project graph.
    counts = {
        t: len(nw.annotations_at_tier(project.root, t))
        for t in (
            "weave-configs",
            "narrative-beats",
            "source-media",
            "audio-clips",
            "voice-assignments",
            "narration-renders",
            "segment-extractions",
            "episode-renders",
        )
    }
    assert counts == {
        "weave-configs": 1,
        "narrative-beats": 2,
        "source-media": 1,
        "audio-clips": 1,
        "voice-assignments": 2,
        "narration-renders": 2,
        "segment-extractions": 1,
        "episode-renders": 1,
    }

    # The produced audio files exist on disk.
    for nr in nw.annotations_at_tier(project.root, "narration-renders"):
        assert braidio.transforms._common.url_to_path(nr.body["url"]).exists()


def test_stale_after_config_restales_all_renders(
    project, script_and_source, patched_synthesis
):
    import nw

    script, source = script_and_source
    braidio.weave_project(project, script, source=source)

    (cfg,) = nw.annotations_at_tier(project.root, "weave-configs")
    render_ids = (
        _tier_ids(project, "voice-assignments")
        | _tier_ids(project, "narration-renders")
        | _tier_ids(project, "segment-extractions")
        | _tier_ids(project, "episode-renders")
    )
    # Actually change the config (a fresh weave is correctly all-fresh).
    _rewrite_in_place(
        project,
        cfg,
        body={**cfg.body, "config": {**cfg.body["config"], "voice_seed": 8}},
    )
    stale = {a.id for a in nw.stale_after(project.root, cfg.id)}
    # A weave-config change re-stales every render node, and nothing authoring.
    assert stale == render_ids
    assert stale.isdisjoint(
        _tier_ids(project, "narrative-beats") | _tier_ids(project, "source-media")
    )


def test_stale_after_narration_beat_scope(
    project, script_and_source, patched_synthesis
):
    import nw

    script, source = script_and_source
    braidio.weave_project(project, script, source=source)

    beats = nw.annotations_at_tier(project.root, "narrative-beats")
    beat = beats[0]
    (episode_id,) = _tier_ids(project, "episode-renders")
    # Actually change the beat's text (a fresh weave is correctly all-fresh).
    _rewrite_in_place(
        project, beat, body={**beat.body, "text": beat.body["text"] + " (edited)"}
    )
    stale = {a.id for a in nw.stale_after(project.root, beat.id)}
    # Change one narration beat → its voice-assignment, its narration-render,
    # and the episode re-stale (3 nodes) — not the other beat's renders.
    assert len(stale) == 3
    assert episode_id in stale


def test_stale_after_source_scope(project, script_and_source, patched_synthesis):
    import nw

    script, source = script_and_source
    braidio.weave_project(project, script, source=source)

    (source_media,) = nw.annotations_at_tier(project.root, "source-media")
    (episode_id,) = _tier_ids(project, "episode-renders")
    # Actually repoint the source (a fresh weave is correctly all-fresh).
    _rewrite_in_place(
        project,
        source_media,
        body={**source_media.body, "asset_id": source_media.body["asset_id"] + ".v2"},
    )
    stale = {a.id for a in nw.stale_after(project.root, source_media.id)}
    # A source change re-stales its segment-extraction + the episode only.
    assert stale == (_tier_ids(project, "segment-extractions") | {episode_id})


def test_narration_render_cache_skip(project, script_and_source, patched_synthesis):
    import nw
    from nw import TransformInputs

    script, source = script_and_source
    braidio.transforms.ingest_script(project, script, source=source)
    beat = nw.annotations_at_tier(project.root, "narrative-beats")[0]
    voice = nw.get_transform("beat_to_voice_assignment.default")
    narration = nw.get_transform("narration_render.tts")

    voice.execute(project, *voice.plan(project, TransformInputs(primary=(beat,))))
    plan1, skel1 = narration.plan(project, TransformInputs(primary=(beat,)))
    first = narration.execute(project, plan1, skel1).annotations[0]

    # A second render of the same beat hits the cache_key: no new node.
    plan2, skel2 = narration.plan(project, TransformInputs(primary=(beat,)))
    second = narration.execute(project, plan2, skel2).annotations[0]
    assert second.id == first.id
    assert len(nw.annotations_at_tier(project.root, "narration-renders")) == 1


def test_narration_render_reports_real_cost(
    project, script_and_source, patched_synthesis, monkeypatch
):
    # The whole point of the cost model: an actual synthesis reports real dollars
    # on both the TransformResult and the produced Artifact (not a fake 0.0).
    import nw
    from nw import TransformInputs
    from braidio.cost import RATE_ENV_VAR, tts_cost_usd

    monkeypatch.delenv(RATE_ENV_VAR, raising=False)  # default per-char rate

    script, source = script_and_source
    braidio.transforms.ingest_script(project, script, source=source)
    beat = nw.annotations_at_tier(project.root, "narrative-beats")[0]
    voice = nw.get_transform("beat_to_voice_assignment.default")
    narration = nw.get_transform("narration_render.tts")

    voice.execute(project, *voice.plan(project, TransformInputs(primary=(beat,))))
    plan1, skel1 = narration.plan(project, TransformInputs(primary=(beat,)))
    result = narration.execute(project, plan1, skel1)

    expected = tts_cost_usd(beat.body["text"])
    assert expected > 0  # the beat carries real narration text
    assert result.cost_usd_actual == pytest.approx(expected)
    assert result.artifacts[0].cost_usd == pytest.approx(expected)


def test_narration_render_cache_hit_reports_savings(
    project, script_and_source, patched_synthesis, monkeypatch
):
    # On a graph cache hit no synthesis happens ($0 spent), but the avoided cost
    # is reported as cache_hit_savings_usd — symmetric with the spend path.
    import nw
    from nw import TransformInputs
    from braidio.cost import RATE_ENV_VAR, tts_cost_usd

    monkeypatch.delenv(RATE_ENV_VAR, raising=False)
    script, source = script_and_source
    braidio.transforms.ingest_script(project, script, source=source)
    beat = nw.annotations_at_tier(project.root, "narrative-beats")[0]
    voice = nw.get_transform("beat_to_voice_assignment.default")
    narration = nw.get_transform("narration_render.tts")
    voice.execute(project, *voice.plan(project, TransformInputs(primary=(beat,))))

    narration.execute(
        project, *narration.plan(project, TransformInputs(primary=(beat,)))
    )
    hit = narration.execute(
        project, *narration.plan(project, TransformInputs(primary=(beat,)))
    )

    assert hit.artifacts == ()  # nothing produced on a hit
    assert hit.cost_usd_actual == 0.0  # nothing spent
    assert hit.cache_hit_savings_usd == pytest.approx(tts_cost_usd(beat.body["text"]))


def test_narration_render_mixing_cache_hit_reports_zero_actual(
    project, script_and_source, patched_synthesis, monkeypatch
):
    # braidio#8: the graph cache MISSES (fresh project) but mixing's on-disk cache
    # HITS — the synthesis branch runs yet real spend was $0. cost_usd_actual must
    # be 0 (the estimate would over-report), while the Artifact keeps the estimate.
    import nw
    from nw import TransformInputs
    from braidio.cost import RATE_ENV_VAR, tts_cost_usd

    monkeypatch.delenv(RATE_ENV_VAR, raising=False)

    def _cached_narrate(text, out, *, return_cache_status=False, **kw):
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"TTS")
        return (p, True) if return_cache_status else p  # was_cached=True

    monkeypatch.setattr(braidio, "narrate", _cached_narrate)

    script, source = script_and_source
    braidio.transforms.ingest_script(project, script, source=source)
    beat = nw.annotations_at_tier(project.root, "narrative-beats")[0]
    voice = nw.get_transform("beat_to_voice_assignment.default")
    narration = nw.get_transform("narration_render.tts")
    voice.execute(project, *voice.plan(project, TransformInputs(primary=(beat,))))

    result = narration.execute(
        project, *narration.plan(project, TransformInputs(primary=(beat,)))
    )
    expected = tts_cost_usd(beat.body["text"])
    assert expected > 0
    assert result.cost_usd_actual == 0.0  # real spend was $0 (mixing cache hit)
    assert result.cache_hit_savings_usd == pytest.approx(expected)
    assert result.artifacts[0].cost_usd == pytest.approx(expected)  # estimate kept


def test_narration_render_unpriced_cost(
    project, script_and_source, patched_synthesis, monkeypatch
):
    # Rate disabled: spend is honestly unpriced — Artifact.cost_usd is None (never a
    # fake 0.0), and cost_usd_actual falls back to 0.0 (nw's field is a plain float).
    import nw
    from nw import TransformInputs
    from braidio.cost import RATE_ENV_VAR

    monkeypatch.setenv(RATE_ENV_VAR, "none")
    script, source = script_and_source
    braidio.transforms.ingest_script(project, script, source=source)
    beat = nw.annotations_at_tier(project.root, "narrative-beats")[0]
    voice = nw.get_transform("beat_to_voice_assignment.default")
    narration = nw.get_transform("narration_render.tts")
    voice.execute(project, *voice.plan(project, TransformInputs(primary=(beat,))))
    result = narration.execute(
        project, *narration.plan(project, TransformInputs(primary=(beat,)))
    )

    assert result.artifacts[0].cost_usd is None
    assert result.cost_usd_actual == 0.0


def test_commentary_weave_genre_ready():
    import nw

    from braidio.formats import FORMATS

    genre = nw.get_genre("commentary_weave")
    assert genre.is_ready()
    assert genre.projection_entrypoint == "weave_to_episode.default"
    # braidio#6: the genre is self-describing — its 7 Formats are Templates,
    # plus intake_kinds + a cost_profile, so a host can expose it straight from nw.
    assert {t.slug for t in genre.templates} == set(FORMATS)
    assert all(t.params["format_id"] in FORMATS for t in genre.templates)
    assert genre.intake_kinds and genre.cost_profile == "tts"
    assert genre.defaults["format_id"] in FORMATS


# --- structural music in the graph path (braidio#39) ------------------------


def _script_with_break(script):
    """``script`` with a scene break between its first two beats."""
    from braidio import SceneBreak

    beats = list(script.beats)
    return braidio.Script(
        title=script.title,
        id_slug=script.id_slug,
        beats=[beats[0], SceneBreak(label="act 2"), *beats[1:]],
    )


def test_ingest_writes_scene_breaks_in_order(project, script_and_source):
    """The boundary is a node the episode can order between the beats — it used
    to be refused outright (NotImplementedError, no structural tier)."""
    script, source = script_and_source
    ingested = braidio.transforms.ingest_script(
        project, _script_with_break(script), source=source
    )
    assert [k for k, _ in ingested.ordered] == [
        "narration",
        "scene_break",
        "segment",
        "narration",
    ]
    (brk,) = ingested.scene_breaks
    assert brk.tier == "scene-breaks"
    assert brk.body["label"] == "act 2" and brk.body["marker"] is None
    # No structure was declared, so no production-structure node was written.
    assert ingested.structure is None
    assert _tier_ids(project, "production-structures") == set()


def test_ingest_records_the_structure_decision_with_asset_ids(
    project, script_and_source, tmp_path
):
    sting_asset = tmp_path / "hit.mp3"
    sting_asset.write_bytes(b"STING-ASSET")
    bed_asset = tmp_path / "bed.mp3"
    bed_asset.write_bytes(b"BED-ASSET")

    ingested = braidio.transforms.ingest_script(
        project,
        _script_with_break(script_and_source[0]),
        source=script_and_source[1],
        structure=braidio.MusicStructure(
            sting=braidio.Sting(str(sting_asset)), spotlight_clips=True
        ),
        bed=braidio.MusicBed(str(bed_asset)),
    )
    body = ingested.structure.body
    assert ingested.structure.tier == "production-structures"
    assert body["structure"]["spotlight_clips"] is True
    # The assets are recorded as content-addressed ids, not only as locations.
    assert body["sting_asset_id"] and body["bed_asset_id"]
    assert body["sting_asset_id"] != body["bed_asset_id"]
    assert body["sting_url"].endswith("hit.mp3")
    assert body["sting"]["gain_db"] == braidio.Sting(str(sting_asset)).gain_db
    assert "asset_path" not in body["sting"] and "asset_path" not in body["bed"]


def test_weave_project_places_the_break_between_the_renders(
    project, script_and_source, patched_synthesis, tmp_path
):
    import nw

    sting_asset = tmp_path / "hit.mp3"
    sting_asset.write_bytes(b"STING-ASSET")
    script, source = script_and_source
    episode = braidio.weave_project(
        project,
        _script_with_break(script),
        source=source,
        structure=braidio.MusicStructure(sting=braidio.Sting(str(sting_asset))),
    )
    members = [
        m
        for m in nw.iter_all_annotations(project.root)
        if str(m.id) in episode.body["ordered_member_ids"]
    ]
    by_id = {str(m.id): m.tier for m in members}
    assert [by_id[i] for i in episode.body["ordered_member_ids"]] == [
        "narration-renders",
        "scene-breaks",
        "segment-extractions",
        "narration-renders",
    ]
    # The break's audio was prepared into the project (not skipped).
    (brk,) = nw.annotations_at_tier(project.root, "scene-breaks")
    assert (project.root / "data" / "breaks" / f"{brk.id}.mp3").exists()


def test_structure_change_restales_only_the_episode(
    project, script_and_source, patched_synthesis, tmp_path
):
    """Swap the sting and only the episode is stale — the narration renders and
    the extraction keep their audio."""
    import nw

    sting_asset = tmp_path / "hit.mp3"
    sting_asset.write_bytes(b"STING-ASSET")
    script, source = script_and_source
    braidio.weave_project(
        project,
        _script_with_break(script),
        source=source,
        structure=braidio.MusicStructure(sting=braidio.Sting(str(sting_asset))),
    )
    (structure,) = nw.annotations_at_tier(project.root, "production-structures")
    (episode_id,) = _tier_ids(project, "episode-renders")
    _rewrite_in_place(
        project,
        structure,
        body={**structure.body, "sting_asset_id": "a" * 64},
    )
    stale = {a.id for a in nw.stale_after(project.root, structure.id)}
    assert stale == {episode_id}


def test_profile_change_restales_only_the_episode(
    project, script_and_source, patched_synthesis
):
    """The rights profile is a real graph input, so changing it re-stales the
    episode through ordinary freshness — no special case (braidio#47).

    Read this together with ``test_episode_refuses_members_its_profile_forbids``:
    the stale signal says *this episode no longer matches its inputs*, NOT
    "re-run the weave". Because the filter ran at ingest, only re-ingest can
    honour a changed profile, and re-weaving alone is refused rather than
    allowed to mislabel the old cut. (That re-ingest is itself blocked today by
    the once-per-project singleton — braidio#51.)
    """
    import nw

    script, source = script_and_source
    braidio.weave_project(
        project, script, source=source, profile=braidio.Profile.PERSONAL
    )
    (profile_node,) = nw.annotations_at_tier(project.root, "render-profiles")
    (episode_id,) = _tier_ids(project, "episode-renders")
    _rewrite_in_place(
        project, profile_node, body={**profile_node.body, "profile": "published"}
    )
    stale = {a.id for a in nw.stale_after(project.root, profile_node.id)}
    assert stale == {episode_id}


def test_episode_refuses_members_its_profile_forbids(
    project, script_and_source, patched_synthesis
):
    """A profile flipped after ingest must not produce a mislabelled episode.

    The filtering happens once, at ingest. Re-staling the episode alone
    therefore *invites* the wrong repair: re-run only ``weave_to_episode`` and
    it would weave the members the OLD profile chose while stamping the NEW
    profile's name on them — a published-labelled episode with an owned-local
    clip in it. The transform verifies its members against the profile it is
    about to claim, and refuses (braidio#47 review).
    """
    import nw

    script, source = script_and_source
    braidio.weave_project(
        project, script, source=source, profile=braidio.Profile.PERSONAL
    )
    (profile_node,) = nw.annotations_at_tier(project.root, "render-profiles")
    episode = nw.annotations_at_tier(project.root, "episode-renders")[-1]
    index = {a.id: a for a in nw.iter_all_annotations(project.root)}
    members = tuple(
        index[UUID(m)] for m in episode.body["ordered_member_ids"]
    )
    _rewrite_in_place(
        project, profile_node, body={**profile_node.body, "profile": "published"}
    )

    with pytest.raises(braidio.RightsViolation) as ei:
        nw.get_transform(braidio.transforms.EPISODE_TRANSFORM).plan(
            project, nw.TransformInputs(primary=members)
        )
    # names the beat and what to do about it, not just "invalid"
    assert "hook" in str(ei.value) and "re-ingest" in str(ei.value)


def test_no_declared_profile_writes_no_render_profile_node(
    project, script_and_source, patched_synthesis
):
    """The absence is load-bearing: an undeclared profile leaves the graph — and
    so the episode's provenance — exactly as it was before braidio#47, while the
    episode still reports the profile the fast path would have used."""
    import nw

    script, source = script_and_source
    episode = braidio.weave_project(project, script, source=source)

    assert nw.annotations_at_tier(project.root, "render-profiles") == []
    assert episode.body["profile"] == braidio.DEFAULT_PROFILE.value


def test_weave_project_applies_a_format_and_its_declared_structure(
    project, script_and_source, patched_synthesis
):
    """The reelee-shaped path: hand the genre's Format to the graph driver and
    its declared structure lands in the graph (braidio#39)."""
    import nw

    script, source = script_and_source
    braidio.weave_project(
        project, _script_with_break(script), source=source, fmt=braidio.SOLO_EXPLAINER
    )
    (structure,) = nw.annotations_at_tier(project.root, "production-structures")
    assert structure.body["structure"] == {
        "scene_marker": braidio.SOLO_EXPLAINER.structure.scene_marker,
        "spotlight_clips": braidio.SOLO_EXPLAINER.structure.spotlight_clips,
        "pause_s": braidio.SOLO_EXPLAINER.structure.pause_s,
    }
    assert structure.body["sting_asset_id"] is None  # no asset supplied
    (cfg,) = nw.annotations_at_tier(project.root, "weave-configs")
    assert cfg.body["config"] == braidio.SOLO_EXPLAINER.weave.to_dict()
