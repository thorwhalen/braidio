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
    """One part on the weave timeline.

    ``placement`` ``"sequential"`` (default — narration, and clean ``before`` /
    ``after`` clips) lays the part in its own slot. ``"under"`` overlays the part
    beneath the *following* sequential part (it does not consume its own slot),
    attenuated by ``duck_db`` — a ducked underlay (a clip talked over, or later a
    music bed).
    """

    kind: str  # "narration" | "clip"
    path: str
    placement: str = "sequential"  # "sequential" | "under"
    duck_db: float = 0.0  # attenuation applied when placement == "under" (e.g. -15)


def layout_placed(
    kinds: list[str],
    durs: list[float],
    placements: list[str],
    *,
    clip_edge_overlap_s: float,
    narration_crossfade_s: float,
) -> list[float]:
    """Start offset (s) of each part, placement-aware. Pure function.

    Sequential parts advance a running cursor: a clip (or a part following a clip)
    starts ``clip_edge_overlap_s`` before the cursor so its faded edges tuck under
    the neighbour; narration-after-narration overlaps by ``narration_crossfade_s``.
    An ``"under"`` part starts *at* the cursor (concurrent with the next
    sequential part) and does **not** advance it — so it overlays what follows.
    Clamped ≥ 0.
    """
    starts: list[float] = [0.0] * len(kinds)
    cursor = 0.0
    prev_seq_kind: str | None = None
    for i, kind in enumerate(kinds):
        if placements[i] == "under":
            starts[i] = cursor  # overlay the following sequential part; cursor unchanged
            continue
        if prev_seq_kind is None:
            start = 0.0
        elif kind == "clip" or prev_seq_kind == "clip":
            start = max(0.0, cursor - clip_edge_overlap_s)
        else:
            start = max(0.0, cursor - narration_crossfade_s)
        starts[i] = start
        cursor = start + durs[i]
        prev_seq_kind = kind
    return starts


def layout_starts(
    kinds: list[str],
    durs: list[float],
    *,
    clip_edge_overlap_s: float,
    narration_crossfade_s: float,
) -> list[float]:
    """Start offset (s) of each part (all sequential). Thin wrapper over
    :func:`layout_placed` — kept for callers that don't use placement."""
    return layout_placed(
        kinds, durs, ["sequential"] * len(kinds),
        clip_edge_overlap_s=clip_edge_overlap_s,
        narration_crossfade_s=narration_crossfade_s,
    )


def weave_timeline(
    items: list[TimelineItem],
    out_path: str | Path,
    *,
    clip_edge_overlap_s: float = 0.5,
    narration_crossfade_s: float = 0.12,
    target_lufs: float = -16.0,
    true_peak: float = -1.0,
    sample_rate: int = 44100,
    bed=None,  # optional braidio.music.MusicBed — instrumental underscore under all
) -> Path:
    """Place items on a timeline and mix. Clips overlap neighbours by
    ``clip_edge_overlap_s`` (their faded edges tuck under narration); narration
    parts butt-join with a small crossfade. Returns ``out_path``.

    ``bed`` (a :class:`~braidio.music.MusicBed`) lays an instrumental underscore
    under the whole production: it's rendered to cover the timeline, attenuated,
    and mixed in posted by ``bed.lead_in_s``. Falls back to a plain concat feel
    when ``clip_edge_overlap_s == 0`` and there's nothing to overlay.
    """
    _require_ffmpeg()
    if not items:
        raise ValueError("weave_timeline needs at least one item")

    durs = [duration_s(it.path) for it in items]
    starts = layout_placed(
        [it.kind for it in items], durs, [it.placement for it in items],
        clip_edge_overlap_s=clip_edge_overlap_s,
        narration_crossfade_s=narration_crossfade_s,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Build one amix graph: (duck →) delay each input to its start, then sum.
    inputs: list[str] = []
    for it in items:
        inputs += ["-i", it.path]
    filters: list[str] = []
    labels: list[str] = []
    for i, (start, it) in enumerate(zip(starts, items)):
        delay_ms = int(round(start * 1000))
        lbl = f"a{i}"
        # normalize every input to stereo @ sample_rate so amix keeps stereo
        # (narration is mono, song clips are stereo) — else it collapses to mono.
        chain = (
            f"[{i}:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo"
        )
        # ducked underlay: attenuate before delaying so it sits beneath the talk.
        if it.placement == "under" and it.duck_db:
            chain += f",volume={it.duck_db}dB"
        chain += f",adelay={delay_ms}:all=1[{lbl}]"
        filters.append(chain)
        labels.append(f"[{lbl}]")

    # Optional music bed: prepare it to cover the timeline, then mix it in posted.
    if bed is not None:
        from braidio.music import prepare_bed

        total_s = max(s + d for s, d in zip(starts, durs))
        bed_path = prepare_bed(bed, total_s, out.parent / f"_bed_{out.stem}.mp3", sample_rate=sample_rate)
        idx = len(items)
        inputs += ["-i", str(bed_path)]
        lead_ms = int(round(bed.lead_in_s * 1000))
        filters.append(
            f"[{idx}:a]aformat=sample_rates={sample_rate}:channel_layouts=stereo,"
            f"adelay={lead_ms}:all=1[bed]"
        )
        labels.append("[bed]")

    n_inputs = len(labels)
    mix = (
        "".join(labels)
        + f"amix=inputs={n_inputs}:normalize=0:dropout_transition=0[m]"
    )
    norm = f"[m]loudnorm=I={target_lufs}:TP={true_peak}:LRA=11[out]"
    filtergraph = ";".join(filters + [mix, norm])

    subprocess.run(
        ["ffmpeg", "-y", *inputs, "-filter_complex", filtergraph,
         "-map", "[out]", "-ar", str(sample_rate), "-ac", "2", "-b:a", "192k",
         str(out)],
        check=True, capture_output=True,
    )
    return out
