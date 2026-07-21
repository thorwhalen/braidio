"""Segment sources: resolve a *reference* to a cuttable ``[start, end]`` window.

A production weaves in extracted segments of source media. *How* a reference
(a lyric quote, an audiobook passage, a news phrase, an SFX cue) maps to a
concrete ``[start, end]`` span of a source asset is pluggable via the
:class:`SegmentSource` protocol — the weave engine never needs to know it is
lyrics.

This module ships one generic implementation: :class:`TimedLineSegmentSource`,
a token-F1 matcher over time-aligned lines (:class:`TimedLine`). It answers a
reference by the best contiguous run of lines — handling exact, sub-line, and
multi-line references. Consumers bind it to their own timed lines + asset (e.g.
Hamilton binds LRCLIB line timings + owned song audio).

Also provides the lower-level resolver (:func:`find_segment`, :func:`load_timing`)
and the resolve-and-cut convenience (:func:`cut_quote`) used directly by the
Hamilton pilot; new code should prefer the :class:`SegmentSource` protocol +
:func:`braidio.weave.extract_padded`.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[^\w\s]")


def _norm(text: str) -> str:
    return _WS_RE.sub(" ", _PUNCT_RE.sub(" ", text.lower())).strip()


def _tokens(text: str) -> list[str]:
    return _norm(text).split()


@dataclass(frozen=True)
class TimedLine:
    """A source line with a ``[start_s, end_s)`` window (end may be None = tail)."""

    index: int
    start_s: float
    end_s: float | None
    text: str


@dataclass(frozen=True)
class Segment:
    """A resolved window for a reference, with the matched line span."""

    start_s: float
    end_s: float
    score: float  # token-F1 of the matched run against the reference (0..1)
    line_start: int
    line_end: int
    matched_text: str

    @property
    def duration_s(self) -> float:
        return round(self.end_s - self.start_s, 3)


@dataclass(frozen=True)
class ResolvedSegment:
    """A cuttable span of a source asset — what a :class:`SegmentSource` returns."""

    asset_path: Path
    start_s: float
    end_s: float
    score: float = 1.0
    matched_text: str = ""

    @property
    def duration_s(self) -> float:
        return round(self.end_s - self.start_s, 3)


@runtime_checkable
class SegmentSource(Protocol):
    """Resolve an opaque ``reference`` to a :class:`ResolvedSegment` (or None)."""

    def resolve(self, reference: str) -> ResolvedSegment | None: ...


def load_timing(path: str | Path) -> list[TimedLine]:
    """Load a ``{lines: [{index,start_s,end_s,text}]}`` JSON into `TimedLine`s."""
    rec = json.loads(Path(path).read_text())
    lines = rec["lines"] if isinstance(rec, dict) else rec
    return [
        TimedLine(
            index=int(l["index"]),
            start_s=float(l["start_s"]),
            end_s=None if l.get("end_s") is None else float(l["end_s"]),
            text=l["text"],
        )
        for l in lines
    ]


def _line_end(lines: list[TimedLine], i: int, *, song_end_s: float | None) -> float:
    line = lines[i]
    if line.end_s is not None:
        return line.end_s
    if i + 1 < len(lines):
        return lines[i + 1].start_s
    if song_end_s is not None:
        return song_end_s
    return line.start_s + 3.0


def find_segment(
    lines: list[TimedLine],
    quote: str,
    *,
    max_span: int = 12,
    min_score: float = 0.5,
    song_end_s: float | None = None,
) -> Segment | None:
    """Best contiguous run of timed lines matching ``quote``, or ``None``.

    Scores every run ``lines[i..j]`` (up to ``max_span`` lines) by token F1
    against the reference's tokens and returns the highest-scoring run clearing
    ``min_score``. Handles single-line, sub-line, and multi-line references.
    """
    q = set(_tokens(quote))
    if not q or not lines:
        return None

    best: Segment | None = None
    for i in range(len(lines)):
        acc: list[str] = []
        for j in range(i, min(i + max_span, len(lines))):
            acc += _tokens(lines[j].text)
            if not acc:
                continue
            aset = set(acc)
            inter = len(q & aset)
            if not inter:
                continue
            recall = inter / len(q)
            precision = inter / len(aset)
            f1 = 2 * precision * recall / (precision + recall)
            if best is None or f1 > best.score:
                best = Segment(
                    start_s=lines[i].start_s,
                    end_s=_line_end(lines, j, song_end_s=song_end_s),
                    score=round(f1, 4),
                    line_start=lines[i].index,
                    line_end=lines[j].index,
                    matched_text=" / ".join(lines[k].text for k in range(i, j + 1)),
                )
    if best is None or best.score < min_score:
        return None
    return best


class TimedLineSegmentSource:
    """A :class:`SegmentSource` over time-aligned lines + one source asset.

    Binds the generic :func:`find_segment` matcher to a concrete asset so the
    weave engine can ``resolve(reference) -> ResolvedSegment``.
    """

    def __init__(
        self,
        *,
        lines: list[TimedLine],
        asset_path: str | Path,
        song_end_s: float | None = None,
        min_score: float = 0.5,
    ) -> None:
        self._lines = lines
        self._asset = Path(asset_path)
        self._song_end = song_end_s
        self._min_score = min_score

    def resolve(self, reference: str) -> ResolvedSegment | None:
        seg = find_segment(
            self._lines, reference, min_score=self._min_score, song_end_s=self._song_end
        )
        if seg is None:
            return None
        return ResolvedSegment(
            asset_path=self._asset,
            start_s=seg.start_s,
            end_s=seg.end_s,
            score=seg.score,
            matched_text=seg.matched_text,
        )


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH (brew install ffmpeg).")


def cut_quote(
    audio_path: str | Path,
    lines: list[TimedLine],
    quote: str,
    out_path: str | Path,
    *,
    pad_pre_s: float = 0.15,
    pad_post_s: float = 0.35,
    fade_s: float = 0.04,
    min_score: float = 0.5,
    song_end_s: float | None = None,
) -> Segment:
    """Resolve ``quote`` → segment and cut it from ``audio_path`` (pad + fades).

    Convenience combining :func:`find_segment` + an ffmpeg cut. Returns the
    resolved :class:`Segment` (raises ``LookupError`` if unmatched). New code
    should prefer a :class:`SegmentSource` + :func:`braidio.weave.extract_padded`.
    """
    _require_ffmpeg()
    seg = find_segment(lines, quote, min_score=min_score, song_end_s=song_end_s)
    if seg is None:
        raise LookupError(f"Could not align reference to audio: {quote[:60]!r}")

    start = max(0.0, seg.start_s - pad_pre_s)
    end = seg.end_s + pad_post_s
    dur = end - start
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    fade_out_start = max(0.0, dur - fade_s)
    subprocess.run(
        [
            "ffmpeg", "-y", "-ss", f"{start:.3f}", "-i", str(audio_path),
            "-t", f"{dur:.3f}",
            "-af", f"afade=t=in:st=0:d={fade_s},afade=t=out:st={fade_out_start:.3f}:d={fade_s}",
            str(out),
        ],
        check=True,
        capture_output=True,
    )
    return seg
