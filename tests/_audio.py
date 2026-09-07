"""Synthetic-audio helpers shared by the offline render tests.

Every input is synthesized with ffmpeg's ``lavfi`` sources (a sine tone, digital
silence) and every assertion is made on the *decoded* PCM of a render — never on
encoded bytes, never against a real TTS call. Nothing here touches a network or
a paid API.
"""

from __future__ import annotations

import shutil
import subprocess
from array import array
from math import sqrt
from pathlib import Path

import pytest

needs_ffmpeg = pytest.mark.skipif(
    shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None,
    reason="ffmpeg/ffprobe not on PATH",
)

RATE = 44100
# Below this RMS (16-bit full scale) a window counts as silent; above the other
# it counts as carrying a tone. Wide apart so codec noise can't flip a verdict.
SILENT_RMS = 30.0
AUDIBLE_RMS = 300.0


def lavfi(path: Path, src: str, duration_s: float, *, channels: int = 2) -> Path:
    """Synthesize ``duration_s`` of the ``lavfi`` source ``src`` into ``path``."""
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


def tone(path: Path, hz: float, duration_s: float) -> Path:
    """A sine tone — audible material a window's RMS can detect."""
    return lavfi(path, f"sine=frequency={hz}:sample_rate={RATE}", duration_s)


def silence(path: Path, duration_s: float) -> Path:
    """Digital silence — stand-in narration, so only the music is audible."""
    return lavfi(path, f"anullsrc=r={RATE}:cl=stereo", duration_s)


def decode(path: Path) -> array:
    """Decoded mono 16-bit PCM at :data:`RATE` — what a listener's DAC would get."""
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


def rms(pcm: array, start_s: float, end_s: float) -> float:
    """RMS level of the ``[start_s, end_s)`` window of decoded ``pcm``."""
    lo, hi = int(start_s * RATE), int(end_s * RATE)
    window = pcm[lo:hi]
    assert window, f"window [{start_s}, {end_s}) is outside the decoded audio"
    return sqrt(sum(x * x for x in window) / len(window))


def seconds(pcm: array) -> float:
    """Duration of decoded ``pcm``, in seconds."""
    return len(pcm) / RATE


class FixedSource:
    """A SegmentSource resolving every reference to one window of one asset."""

    def __init__(self, asset_path: Path, *, start_s: float, end_s: float):
        self.asset_path, self.start_s, self.end_s = asset_path, start_s, end_s

    def resolve(self, reference: str):
        from braidio.sources import ResolvedSegment

        return ResolvedSegment(
            asset_path=self.asset_path,
            start_s=self.start_s,
            end_s=self.end_s,
            matched_text=reference,
        )
