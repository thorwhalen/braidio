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
    config: WeaveConfig | None = None,
    profile: Profile = Profile.PERSONAL,
    rights: RightsPolicy | None = None,
    delivery: Delivery = V2_TUNED,
    out_path: str | Path | None = None,
    voice_id: str | None = None,
    crossfade_s: float = 0.12,
    normalize: bool = True,
    tts_dir: str | Path = "data/tts",
    clips_dir: str | Path = "data/clips",
    episodes_dir: str | Path = "data/episodes",
) -> Path:
    """Render ``script`` under ``profile`` → a single audio file. Returns the path.

    Segment beats are resolved through ``source`` (a :class:`SegmentSource`).
    When ``config`` has ``clip_edge_overlap_s > 0`` the segments are woven with
    speech-dominant overlap; otherwise parts are concatenated. ``rights`` (if
    given) sets which segment rights are publishable.
    """
    publishable = rights.publishable_clip_rights if rights else PUBLISHABLE_CLIP_RIGHTS
    plan = plan_production(script, profile, publishable_clip_rights=publishable)
    woven = config is not None and config.clip_edge_overlap_s > 0
    target_lufs = config.target_lufs if config is not None else _DEFAULT_LUFS

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
    for i, pb in enumerate(plan.beats):
        if pb.kind == "narration":
            raw = narrate(
                pb.content,
                Path(tts_dir) / f"{script.id_slug}-{profile.value}-{delivery.name}-beat{i:02d}.mp3",
                voice_id=voice_id,
                model_id=delivery.model_id,
                voice_settings=delivery.voice_settings,
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
        kinds.append(pb.kind)

    if woven and "clip" in kinds:
        items = [TimelineItem(k, str(p)) for k, p in zip(kinds, parts)]
        weave_timeline(
            items, out,
            clip_edge_overlap_s=config.clip_edge_overlap_s,
            narration_crossfade_s=config.crossfade_s,
            target_lufs=target_lufs,
        )
    else:
        concatenate_audio(*[str(p) for p in parts], output=str(out), crossfade=crossfade_s)
    return out
