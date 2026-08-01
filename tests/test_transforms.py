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

    (cfg_id,) = _tier_ids(project, "weave-configs")
    render_ids = (
        _tier_ids(project, "voice-assignments")
        | _tier_ids(project, "narration-renders")
        | _tier_ids(project, "segment-extractions")
        | _tier_ids(project, "episode-renders")
    )
    stale = {a.id for a in nw.stale_after(project.root, cfg_id)}
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
    stale = {a.id for a in nw.stale_after(project.root, beat.id)}
    # Change one narration beat → its voice-assignment, its narration-render,
    # and the episode re-stale (3 nodes) — not the other beat's renders.
    assert len(stale) == 3
    assert episode_id in stale


def test_stale_after_source_scope(project, script_and_source, patched_synthesis):
    import nw

    script, source = script_and_source
    braidio.weave_project(project, script, source=source)

    (source_media_id,) = _tier_ids(project, "source-media")
    (episode_id,) = _tier_ids(project, "episode-renders")
    stale = {a.id for a in nw.stale_after(project.root, source_media_id)}
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
