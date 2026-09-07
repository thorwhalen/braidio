"""Structural music (braidio#25): scene stings + fade-to-spotlight.

Offline. The audio tests synthesize every input with ffmpeg's lavfi sources
(a sine tone, digital silence) and inspect the *decoded* PCM of the render —
never the encoded bytes, never a real TTS call (``narrate`` is replaced by a
tone writer). The characterization tests pin the seam's default: a script with
no scene break and no spotlit clip must render the same decoded audio as the
plain weave, and the bed's single-region renderer must equal the old
whole-span renderer.
"""

from __future__ import annotations

import shutil
import subprocess
from array import array
from dataclasses import replace
from math import sqrt
from pathlib import Path

import pytest

import braidio
from braidio import (
    DEFAULT_STRUCTURE,
    MusicBed,
    MusicStructure,
    Narration,
    SceneBreak,
    Script,
    SegmentBeat,
    Sting,
    TimelineItem,
    estimate_cost,
    weave_timeline,
)
from braidio.music import BedRegion, bed_regions, prepare_bed, prepare_bed_regions
from braidio.rights import Profile, content_violations, plan_production
from braidio.sources import ResolvedSegment

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

RATE = 44100
# Below this RMS (16-bit full scale) a window counts as silent; above the other
# it counts as carrying a tone. Wide apart so codec noise can't flip a verdict.
SILENT_RMS = 30.0
AUDIBLE_RMS = 300.0


# --- synthetic audio helpers (lavfi only) -------------------------------------


def _lavfi(path: Path, src: str, duration_s: float, *, channels: int = 2) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            src,
            "-t",
            f"{duration_s:.3f}",
            "-ac",
            str(channels),
            str(path),
        ],
        check=True,
        capture_output=True,
    )
    return path


def _tone(path: Path, hz: float, duration_s: float) -> Path:
    return _lavfi(path, f"sine=frequency={hz}:sample_rate={RATE}", duration_s)


def _silence(path: Path, duration_s: float) -> Path:
    return _lavfi(path, f"anullsrc=r={RATE}:cl=stereo", duration_s)


def _decode(path: Path) -> array:
    """Decoded mono 16-bit PCM at RATE — what a listener's DAC would get."""
    r = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "quiet",
            "-i",
            str(path),
            "-f",
            "s16le",
            "-ac",
            "1",
            "-ar",
            str(RATE),
            "-",
        ],
        check=True,
        capture_output=True,
    )
    pcm = array("h")
    pcm.frombytes(r.stdout)
    return pcm


def _rms(pcm: array, start_s: float, end_s: float) -> float:
    lo, hi = int(start_s * RATE), int(end_s * RATE)
    window = pcm[lo:hi]
    assert window, f"window [{start_s}, {end_s}) is outside the decoded audio"
    return sqrt(sum(x * x for x in window) / len(window))


def _seconds(pcm: array) -> float:
    return len(pcm) / RATE


class _FixedSource:
    """A SegmentSource resolving every reference to one window of one asset."""

    def __init__(self, asset_path: Path, *, start_s: float, end_s: float):
        self.asset_path, self.start_s, self.end_s = asset_path, start_s, end_s

    def resolve(self, reference: str):
        return ResolvedSegment(
            asset_path=self.asset_path,
            start_s=self.start_s,
            end_s=self.end_s,
            matched_text=reference,
        )


@pytest.fixture
def silent_narration(monkeypatch):
    """narrate() → a fixed length of silence, so only the music is audible.

    Any real synthesis would be a bug: the stub never touches the network.
    """
    import braidio.render as render_mod

    def fake_narrate(text, out_path, **kw):
        return _silence(Path(out_path), 1.0)

    monkeypatch.setattr(render_mod, "narrate", fake_narrate)


def _render(script, tmp_path, **kw):
    """render_production with every non-structural post-step disabled."""
    kw.setdefault("source", None)
    kw.setdefault("normalize", False)
    return braidio.render_production(
        script,
        out_path=tmp_path / f"out-{len(list(tmp_path.iterdir()))}.mp3",
        end_fade_s=0.0,
        end_silence_s=0.0,
        tts_dir=tmp_path / "tts",
        clips_dir=tmp_path / "clips",
        **kw,
    )


# --- the model ---------------------------------------------------------------


def test_scene_break_defaults_and_validates_marker():
    assert SceneBreak().marker is None and SceneBreak().label == ""
    assert SceneBreak(marker="none", label="rebuttal").marker == "none"
    with pytest.raises(ValueError):
        SceneBreak(marker="fanfare")


def test_segment_spotlight_defaults_to_deferred():
    assert SegmentBeat("ref").spotlight is None
    assert SegmentBeat("ref", spotlight=True).spotlight is True


def test_music_structure_resolves_beat_overrides_over_format_defaults():
    st = MusicStructure(
        sting=Sting("s.wav"), scene_marker="sting", spotlight_clips=True
    )
    assert st.marker_for(SceneBreak()) == "sting"
    assert st.marker_for(SceneBreak(marker="none")) == "none"
    assert st.plays_sting(SceneBreak()) and not st.plays_sting(
        SceneBreak(marker="none")
    )
    assert st.spotlight_for(SegmentBeat("r")) is True
    assert st.spotlight_for(SegmentBeat("r", spotlight=False)) is False
    # no sting asset → a "sting" break cannot play one, whatever it asks for
    assert not MusicStructure(scene_marker="sting").plays_sting(SceneBreak())
    with pytest.raises(ValueError):
        MusicStructure(scene_marker="swell")


def test_default_structure_is_inert():
    assert DEFAULT_STRUCTURE.sting is None
    assert DEFAULT_STRUCTURE.spotlight_clips is False
    assert not DEFAULT_STRUCTURE.plays_sting(SceneBreak())
    assert DEFAULT_STRUCTURE.spotlight_for(SegmentBeat("r")) is False


def test_scene_break_is_planned_under_both_profiles_and_costs_nothing():
    script = Script(
        title="t",
        id_slug="01",
        beats=[Narration("a" * 10), SceneBreak(label="act 2"), Narration("b" * 10)],
    )
    for profile in (Profile.PERSONAL, Profile.PUBLISHED):
        plan = plan_production(script, profile)
        assert [b.kind for b in plan.beats] == ["narration", "scene_break", "narration"]
        assert plan.beats[1].from_index == 1
    assert content_violations(plan_production(script, Profile.PUBLISHED), ["x"]) == []
    est = estimate_cost(script)
    assert est.characters == 20 and len(est.lines) == 2


def test_every_format_declares_its_structure():
    for fmt in braidio.FORMATS.values():
        assert isinstance(fmt.structure, MusicStructure)
        assert (
            fmt.structure.sting is None
        )  # the asset is the caller's, never the preset's
    assert braidio.SOLO_EXPLAINER.structure.spotlight_clips is True
    assert braidio.SONG_EXPLODER.structure.scene_marker == "none"
    assert braidio.DEBATE.structure.scene_marker == "sting"


def test_render_format_threads_structure_and_builds_the_sting(monkeypatch):
    import braidio.render as render_mod

    captured = {}
    monkeypatch.setattr(
        render_mod,
        "render_production",
        lambda script, **kw: captured.update(kw) or "OUT",
    )
    braidio.render_format(braidio.PANEL, "S", source=None)
    assert captured["structure"] is braidio.PANEL.structure

    captured.clear()
    braidio.render_format(braidio.PANEL, "S", source=None, sting_asset="hit.wav")
    st = captured["structure"]
    assert st.sting == Sting("hit.wav")
    assert replace(st, sting=None) == braidio.PANEL.structure

    captured.clear()  # an explicit structure override wins over the asset
    mine = MusicStructure(scene_marker="none")
    braidio.render_format(
        braidio.PANEL, "S", source=None, sting_asset="h", structure=mine
    )
    assert captured["structure"] is mine


# --- bed regions (pure) ------------------------------------------------------

_BED = MusicBed(
    "bed.wav", fade_in_s=1.5, fade_out_s=2.0, lead_in_s=2.0, spotlight_fade_s=0.6
)


def test_no_spotlight_is_one_whole_span_region_with_the_beds_own_fades():
    assert bed_regions(_BED, 30.0, []) == [BedRegion(2.0, 30.0, 1.5, 2.0)]


def test_a_spotlight_splits_the_bed_with_a_quick_drop_and_a_slow_resume():
    regions = bed_regions(_BED, 30.0, [(10.0, 14.0)])
    assert regions == [
        BedRegion(2.0, 10.0, fade_in_s=1.5, fade_out_s=0.6),  # silent by the clip
        BedRegion(14.0, 30.0, fade_in_s=1.5, fade_out_s=2.0),  # back in after it
    ]
    assert regions[0].length_s == 8.0


def test_spotlight_windows_are_merged_clamped_and_empty_regions_dropped():
    # overlapping windows merge; one at the very top leaves no leading region;
    # one running past the end leaves no trailing region
    regions = bed_regions(_BED, 20.0, [(0.0, 5.0), (4.0, 6.0), (18.0, 25.0)])
    assert regions == [BedRegion(6.0, 18.0, fade_in_s=1.5, fade_out_s=0.6)]
    assert bed_regions(_BED, 20.0, [(1.0, 25.0)]) == []


# --- characterization: the default reproduces today's output ------------------


@needs_ffmpeg
def test_single_region_bed_decodes_identically_to_prepare_bed(tmp_path):
    """The bed renderer was refactored into spans; the whole-span case must be
    the same audio the old single-file path produced."""
    asset = _tone(tmp_path / "bed.wav", 110, 3.0)
    bed = MusicBed(str(asset), gain_db=-12.0, lead_in_s=1.0, start_s=0.5)
    whole = prepare_bed(bed, 8.0, tmp_path / "whole.mp3")
    [(region, start_s)] = prepare_bed_regions(
        bed, bed_regions(bed, 8.0, []), tmp_path, stem="region"
    )
    assert start_s == bed.lead_in_s
    assert _decode(whole) == _decode(region)


@needs_ffmpeg
def test_default_structure_renders_the_plain_weave_exactly(tmp_path, silent_narration):
    """A script with no scene break and no spotlit clip, rendered under a format
    that *does* declare stings + spotlight, decodes identically to the plain
    weave of the same parts — the seam's default is a no-op."""
    bed = MusicBed(str(_tone(tmp_path / "bed.wav", 110, 3.0)), lead_in_s=0.5)
    script = Script(title="t", id_slug="c", beats=[Narration("one"), Narration("two")])

    plain = weave_timeline(
        [
            TimelineItem("narration", str(_silence(tmp_path / "p0.mp3", 1.0))),
            TimelineItem("narration", str(_silence(tmp_path / "p1.mp3", 1.0))),
        ],
        tmp_path / "plain.mp3",
        clip_edge_overlap_s=0.0,
        narration_crossfade_s=0.12,
        bed=bed,
    )
    by_default = _render(script, tmp_path, music_bed=bed)
    declared = _render(
        script, tmp_path, music_bed=bed, structure=braidio.SOLO_EXPLAINER.structure
    )
    with_asset = _render(
        script,
        tmp_path,
        music_bed=bed,
        structure=MusicStructure(
            sting=Sting(str(_tone(tmp_path / "hit.wav", 880, 1.0))),
            spotlight_clips=True,
        ),
    )
    reference = _decode(plain)
    assert reference and _rms(reference, 0.6, 1.9) > AUDIBLE_RMS  # the bed is there
    assert _decode(by_default) == reference
    assert _decode(declared) == reference
    assert _decode(with_asset) == reference


# --- behaviour: stings + spotlight ------------------------------------------


@needs_ffmpeg
def test_scene_break_plays_the_sting_between_the_talk(tmp_path, silent_narration):
    sting = Sting(
        str(_tone(tmp_path / "hit.wav", 880, 1.0)),
        gain_db=0.0,
        max_len_s=1.0,
        fade_out_s=0.2,
        gap_after_s=0.0,
    )
    script = Script(
        title="t",
        id_slug="s",
        beats=[Narration("one"), SceneBreak(label="act 2"), Narration("two")],
    )
    out, tl = _render(
        script,
        tmp_path,
        structure=MusicStructure(sting=sting),
        return_timeline=True,
    )
    pcm = _decode(out)
    assert _seconds(pcm) == pytest.approx(3.0, abs=0.3)
    assert _rms(pcm, 0.1, 0.8) < SILENT_RMS  # talk (silent here)
    assert _rms(pcm, 1.1, 1.7) > AUDIBLE_RMS  # the sting
    assert _rms(pcm, 2.2, 2.9) < SILENT_RMS  # talk again
    assert [s.kind for s in tl.beats] == ["narration", "sting", "narration"]
    assert tl.beats[1].label == "act 2"


@needs_ffmpeg
def test_scene_break_without_a_sting_is_a_pause(tmp_path, silent_narration):
    script = Script(
        title="t", id_slug="p", beats=[Narration("one"), SceneBreak(), Narration("two")]
    )
    no_asset, tl = _render(script, tmp_path, return_timeline=True)
    assert _seconds(_decode(no_asset)) == pytest.approx(
        2.0 + DEFAULT_STRUCTURE.pause_s, abs=0.3
    )
    assert [s.kind for s in tl.beats] == ["narration", "scene-break", "narration"]

    # marked "none" → a pause even when the production has a sting
    quiet = Script(
        title="t",
        id_slug="q",
        beats=[Narration("one"), SceneBreak(marker="none"), Narration("two")],
    )
    sting = Sting(str(_tone(tmp_path / "hit.wav", 880, 1.0)), gain_db=0.0)
    out = _render(quiet, tmp_path, structure=MusicStructure(sting=sting, pause_s=0.4))
    pcm = _decode(out)
    assert _seconds(pcm) == pytest.approx(2.4, abs=0.3)
    assert _rms(pcm, 0.0, _seconds(pcm) - 0.05) < SILENT_RMS


@needs_ffmpeg
@pytest.mark.parametrize("via", ["beat_flag", "format_default"])
def test_spotlight_drops_the_bed_under_the_clip_and_brings_it_back(
    tmp_path, silent_narration, via
):
    """Talk and clip are silent, the bed is a tone: with spotlight the clip's
    window is the only silent stretch; without it the bed plays throughout."""
    bed = MusicBed(
        str(_tone(tmp_path / "bed.wav", 220, 3.0)),
        gain_db=0.0,
        lead_in_s=0.0,
        fade_in_s=0.1,
        fade_out_s=0.1,
        spotlight_fade_s=0.1,
    )
    source = _FixedSource(_silence(tmp_path / "src.wav", 4.0), start_s=0.5, end_s=1.5)
    if via == "beat_flag":
        clip, structure = SegmentBeat("x", spotlight=True), None
    else:
        clip, structure = SegmentBeat("x"), MusicStructure(spotlight_clips=True)
    script = Script(
        title="t", id_slug="sp", beats=[Narration("a"), clip, Narration("b")]
    )

    # config=None → no clip edge overlap, clip floor length 2.2 s:
    # narration 0–1, clip 1–3.2, narration 3.2–4.2
    lit = _decode(
        _render(script, tmp_path, source=source, music_bed=bed, structure=structure)
    )
    assert _rms(lit, 0.2, 0.8) > AUDIBLE_RMS  # bed under the set-up
    assert _rms(lit, 1.3, 2.9) < SILENT_RMS  # bed out under the exhibit
    assert _rms(lit, 3.6, 4.1) > AUDIBLE_RMS  # bed back under the payoff

    unlit_beat = SegmentBeat("x", spotlight=False)
    unlit = _decode(
        _render(
            replace(script, beats=[Narration("a"), unlit_beat, Narration("b")]),
            tmp_path,
            source=source,
            music_bed=bed,
            structure=structure,
        )
    )
    assert _rms(unlit, 1.3, 2.9) > AUDIBLE_RMS  # the per-beat False wins
    assert _seconds(unlit) == pytest.approx(_seconds(lit), abs=0.1)


@needs_ffmpeg
def test_spotlight_without_a_bed_is_inert(tmp_path, silent_narration):
    source = _FixedSource(_tone(tmp_path / "src.wav", 330, 4.0), start_s=0.5, end_s=1.5)
    beats = [Narration("a"), SegmentBeat("x", spotlight=True), Narration("b")]
    script = Script(title="t", id_slug="nb", beats=beats)
    lit = _decode(_render(script, tmp_path, source=source))
    plain = _decode(
        _render(
            replace(script, beats=[Narration("a"), SegmentBeat("x"), Narration("b")]),
            tmp_path,
            source=source,
        )
    )
    assert lit == plain
