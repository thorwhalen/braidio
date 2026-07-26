"""Render a :class:`~braidio.script.Script` into an audio file.

Walks the beats (filtered by the rights :class:`~braidio.rights.Profile`):
narration beats are synthesized (:mod:`braidio.tts`); segment beats are resolved
via a :class:`~braidio.sources.SegmentSource` and extracted (padded + faded).
Every part is loudness-normalized, then either woven on a timeline (clips tuck
under narration — :func:`braidio.weave.weave_timeline`) when a
:class:`~braidio.weave_config.WeaveConfig` enables it, or concatenated.

This is the no-graph fast path; the same core is reused by the nw-app
transforms (which add provenance + partial re-render).
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from mixing import concatenate_audio

from braidio.conversation import DEFAULT_CAST, ConversationCast, render_dialogue
from braidio.delivery import V2_TUNED, Delivery
from braidio.rights import (
    PUBLISHABLE_CLIP_RIGHTS,
    Profile,
    RightsPolicy,
    plan_production,
)
from braidio.script import Script
from braidio.sources import SegmentSource
from braidio.tts import narrate
from braidio.weave import TimelineItem, extract_padded, weave_timeline
from braidio.weave_config import WeaveConfig

_DEFAULT_LUFS = -16.0
_TRUE_PEAK = -1.5


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH (brew install ffmpeg).")


def _lead_gap(src: Path, dst: Path, *, gap_s: float) -> Path:
    """Prepend ``gap_s`` seconds of silence (breathing room before a beat)."""
    _require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    ms = int(round(gap_s * 1000))
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src), "-af", f"adelay={ms}:all=1", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def _loudnorm(src: Path, dst: Path, *, target_lufs: float = _DEFAULT_LUFS) -> Path:
    _require_ffmpeg()
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-i", str(src),
         "-af", f"loudnorm=I={target_lufs}:TP={_TRUE_PEAK}:LRA=11",
         "-ar", "44100", str(dst)],
        check=True, capture_output=True,
    )
    return dst


def render_production(
    script: Script,
    *,
    source: SegmentSource,
    api_key: str | None = None,
    config: WeaveConfig | None = None,
    profile: Profile = Profile.PERSONAL,
    rights: RightsPolicy | None = None,
    delivery: Delivery = V2_TUNED,
    cast: ConversationCast = DEFAULT_CAST,
    out_path: str | Path | None = None,
    voice_id: str | None = None,
    crossfade_s: float = 0.12,
    normalize: bool = True,
    music_bed=None,  # optional braidio.music.MusicBed — instrumental underscore
    tts_dir: str | Path = "data/tts",
    clips_dir: str | Path = "data/clips",
    episodes_dir: str | Path = "data/episodes",
) -> Path:
    """Render ``script`` under ``profile`` → a single audio file. Returns the path.

    Segment beats are resolved through ``source`` (a :class:`SegmentSource`).
    When ``config`` has ``clip_edge_overlap_s > 0``, a clip is ``placement="under"``,
    or a ``music_bed`` is given, the parts are woven on a timeline; otherwise they
    are concatenated. ``rights`` (if given) sets which segment rights are
    publishable. ``music_bed`` lays an instrumental underscore under the whole
    production (see :class:`braidio.music.MusicBed`).

    ``api_key`` is an optional per-request ElevenLabs key threaded to every
    synthesized beat — both narration (:func:`braidio.tts.narrate`) and dialogue
    (:func:`braidio.conversation.render_dialogue`). When ``None`` (default) each
    synthesizer falls back to ``$ELEVENLABS_API_KEY`` (unchanged behavior); an
    explicit key lets a caller (e.g. a per-user BYO-key request) override the
    environment without mutating it. Segment beats never call ElevenLabs, so the
    key does not touch them.
    """
    publishable = rights.publishable_clip_rights if rights else PUBLISHABLE_CLIP_RIGHTS
    plan = plan_production(script, profile, publishable_clip_rights=publishable)
    target_lufs = config.target_lufs if config is not None else _DEFAULT_LUFS
    duck_db = config.duck_db if config is not None else -15.0

    out = (
        Path(out_path)
        if out_path
        else Path(episodes_dir) / f"{script.id_slug}-{profile.value}.mp3"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    work = Path(tts_dir) / f"_render_{script.id_slug}_{profile.value}"
    work.mkdir(parents=True, exist_ok=True)

    # extraction pads: from config when present, else small defaults
    if config is not None:
        pre, post, fi, fo = (
            config.clip_pre_roll_s, config.clip_post_roll_s,
            config.clip_fade_in_s, config.clip_fade_out_s,
        )
    else:
        pre, post, fi, fo = 0.15, 0.35, 0.04, 0.04

    parts: list[Path] = []
    kinds: list[str] = []
    placements: list[str] = []  # "sequential" | "under" (per part, for the weave)
    for i, pb in enumerate(plan.beats):
        if pb.kind == "narration":
            orig = script.beats[pb.from_index]
            beat_voice = getattr(orig, "voice", None) or voice_id  # per-beat override
            beat_settings = getattr(orig, "voice_settings", None) or delivery.voice_settings
            raw = narrate(
                pb.content,
                Path(tts_dir) / f"{script.id_slug}-{profile.value}-{delivery.name}-beat{i:02d}.mp3",
                api_key=api_key,
                voice_id=beat_voice,
                model_id=delivery.model_id,
                voice_settings=beat_settings,
            )
            # breathing room before a register change (Narration.lead_gap_s)
            gap = getattr(orig, "lead_gap_s", 0.0)
            if gap and gap > 0:
                raw = _lead_gap(raw, Path(tts_dir) / f"{script.id_slug}-lead{i:02d}.mp3", gap_s=gap)
        elif pb.kind == "dialogue":
            raw = render_dialogue(
                list(pb.turns), cast,
                api_key=api_key,
                out_path=Path(tts_dir) / f"{script.id_slug}-{profile.value}-dlg{i:02d}.mp3",
            )
        else:  # segment
            rs = source.resolve(pb.content)
            if rs is None:
                raise LookupError(f"segment did not resolve: {pb.content[:50]!r}")
            raw = Path(clips_dir) / f"{script.id_slug}-seg{i:02d}.mp3"
            extract_padded(
                rs.asset_path, rs.start_s, rs.end_s, raw,
                pre_roll_s=pre, post_roll_s=post, fade_in_s=fi, fade_out_s=fo,
            )
        parts.append(
            _loudnorm(raw, work / f"part{i:02d}.mp3", target_lufs=target_lufs)
            if normalize else raw
        )
        # dialogue + narration are spoken → treated as "narration" on the timeline
        kinds.append("clip" if pb.kind == "clip" else "narration")
        # a "under" clip becomes a ducked underlay; "before"/"after" play clean
        seg_place = getattr(script.beats[pb.from_index], "placement", "before")
        placements.append("under" if (pb.kind == "clip" and seg_place == "under") else "sequential")

    has_under = "under" in placements
    edge_overlap = config.clip_edge_overlap_s if config is not None else 0.0
    crossfade = config.crossfade_s if config is not None else crossfade_s
    # a music bed also needs the mix path (even for narration-only productions)
    woven = music_bed is not None or ("clip" in kinds and (edge_overlap > 0 or has_under))

    if woven:
        items = [
            TimelineItem(k, str(p), placement=pl, duck_db=(duck_db if pl == "under" else 0.0))
            for k, p, pl in zip(kinds, parts, placements)
        ]
        weave_timeline(
            items, out,
            clip_edge_overlap_s=edge_overlap,
            narration_crossfade_s=crossfade,
            target_lufs=target_lufs,
            bed=music_bed,
        )
    else:
        concatenate_audio(*[str(p) for p in parts], output=str(out), crossfade=crossfade_s)
    return out
