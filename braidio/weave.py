"""Weave narration + audio clips on a timeline (#21) — the reusable mix engine.

Two generic, Hamilton-agnostic primitives:

- :func:`extract_padded` — extract ``[start, end]`` from a source asset but
  **padded** by pre/post-roll (so the words are captured cleanly) with in/out
  fades on the padded edges. The padded, faded edges are what we tuck under the
  neighbouring narration.
- :func:`weave_timeline` — place ordered narration/clip parts on a timeline
  where each clip **overlaps its neighbours** by ``clip_edge_overlap_s`` and its
  faded padded edges duck under the speech, so **speech stays dominant**, then
  mix (``amix`` sum) and loudness-normalize.

This is the audio counterpart of a video timeline; it consumes plain file paths
+ numbers, no Genius/lyrics knowledge (that resolution lives in
``graph/align.py`` and the Hamilton adapters). Ducking here is achieved by
fade-shaped overlap; a dynamic sidechain duck (``duck_db``) is a documented
refinement (see #21 / the research).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise RuntimeError("ffmpeg/ffprobe not found on PATH (brew install ffmpeg).")


def duration_s(path: str | Path) -> float:
    _require_ffmpeg()
    r = subprocess.run(
        ["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", str(path)],
        capture_output=True, text=True, check=True,
    )
    return float(json.loads(r.stdout)["format"]["duration"])


def extract_padded(
    asset_path: str | Path,
    start_s: float,
    end_s: float,
    out_path: str | Path,
    *,
    pre_roll_s: float = 0.4,
    post_roll_s: float = 0.3,
    fade_in_s: float = 0.5,
    fade_out_s: float = 0.8,
) -> Path:
    """Extract ``[start_s-pre_roll, end_s+post_roll]`` with in/out fades.

    The target words sit in the middle; the padded, faded head/tail are the
    parts that overlap (tuck under) neighbouring narration in the weave.
    """
    _require_ffmpeg()
    start = max(0.0, start_s - pre_roll_s)
    end = end_s + post_roll_s
    dur = max(0.05, end - start)
    fo_start = max(0.0, dur - fade_out_s)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(asset_path),
         "-t", f"{dur:.3f}",
         "-af", f"afade=t=in:st=0:d={fade_in_s},afade=t=out:st={fo_start:.3f}:d={fade_out_s}",
         str(out)],
        check=True, capture_output=True,
    )
    return out


@dataclass(frozen=True)
class TimelineItem:
    """One part on the weave timeline."""

    kind: str  # "narration" | "clip"
    path: str


def layout_starts(
    kinds: list[str],
    durs: list[float],
    *,
    clip_edge_overlap_s: float,
    narration_crossfade_s: float,
) -> list[float]:
    """Start offset (s) of each part. Pure function of kinds + durations.

    A clip, or a part following a clip, starts ``clip_edge_overlap_s`` before the
    running cursor (so the clip's faded edges overlap its neighbours);
    narration-after-narration overlaps by ``narration_crossfade_s``. Clamped ≥ 0.
    """
    starts: list[float] = []
    cursor = 0.0
    for i, kind in enumerate(kinds):
        if i == 0:
            start = 0.0
        elif kind == "clip" or kinds[i - 1] == "clip":
            start = max(0.0, cursor - clip_edge_overlap_s)
        else:
            start = max(0.0, cursor - narration_crossfade_s)
        starts.append(start)
        cursor = start + durs[i]
    return starts


def weave_timeline(
    items: list[TimelineItem],
    out_path: str | Path,
    *,
    clip_edge_overlap_s: float = 0.5,
    narration_crossfade_s: float = 0.12,
    target_lufs: float = -16.0,
    true_peak: float = -1.0,
    sample_rate: int = 44100,
) -> Path:
    """Place items on a timeline and mix. Clips overlap neighbours by
    ``clip_edge_overlap_s`` (their faded edges tuck under narration); narration
    parts butt-join with a small crossfade. Returns ``out_path``.

    Falls back to a plain concat feel when ``clip_edge_overlap_s == 0``.
    """
    _require_ffmpeg()
    if not items:
        raise ValueError("weave_timeline needs at least one item")

    durs = [duration_s(it.path) for it in items]
    starts = layout_starts(
        [it.kind for it in items], durs,
        clip_edge_overlap_s=clip_edge_overlap_s,
        narration_crossfade_s=narration_crossfade_s,
    )

    # Build one amix graph: delay each input to its start, then sum.
    inputs: list[str] = []
    for it in items:
        inputs += ["-i", it.path]
    filters: list[str] = []
    labels: list[str] = []
    for i, start in enumerate(starts):
        delay_ms = int(round(start * 1000))
        lbl = f"a{i}"
        # normalize every input to stereo @ sample_rate so amix keeps stereo
        # (narration is mono, song clips are stereo) — else it collapses to mono.
        filters.append(
            f"[{i}:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
            f"adelay={delay_ms}:all=1[{lbl}]"
        )
        labels.append(f"[{lbl}]")
    mix = (
        "".join(labels)
        + f"amix=inputs={len(items)}:normalize=0:dropout_transition=0[m]"
    )
    norm = f"[m]loudnorm=I={target_lufs}:TP={true_peak}:LRA=11[out]"
    filtergraph = ";".join(filters + [mix, norm])

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filtergraph,
         "-map", "[out]", "-ar", str(sample_rate), "-ac", "2", "-b:a", "192k",
         str(out)],
        check=True, capture_output=True,
    )
    return out
