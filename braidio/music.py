"""Music bed — an instrumental underscore laid under the whole production, ducked.

The bed is the spanning generalization of a per-clip ``under`` placement: instead
of one clip beneath one talk beat, an app-supplied **instrumental** asset runs
beneath the entire timeline at reduced gain, entering after speech onset and
fading at the ends (the conventions from
``docs/research/commentary-formats-and-styles.md``: bed 10–15 dB under voice,
~1.5s fade-in, *posted* after the start; beds must be instrumental).

braidio ships **no music** — the caller supplies the asset (a licensed/owned
instrumental). A :class:`~braidio.formats.Format`'s ``music_bed`` *intensity*
(continuous / light / sparse / none) picks a sensible gain via
:data:`BED_GAIN_BY_INTENSITY`; :func:`render_format` builds the bed for you when
given a ``bed_asset``.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

# Bed gain (dB under the mixed voice) by a Format's music_bed intensity.
# None means "no bed" for that intensity.
BED_GAIN_BY_INTENSITY: dict[str, float | None] = {
    "continuous": -20.0,
    "light": -24.0,
    "sparse": -28.0,
    "none": None,
}


@dataclass(frozen=True)
class MusicBed:
    """An instrumental underscore spanning the production, mixed under the talk.

    ``asset_path`` is an app-supplied instrumental. ``gain_db`` sets how far under
    the voice it sits; ``lead_in_s`` posts the bed *after* speech onset so its
    entrance feels motivated; ``start_s`` is the in-point into the asset;
    ``loop`` repeats the asset to cover a timeline longer than it.
    """

    asset_path: str
    gain_db: float = -22.0
    fade_in_s: float = 1.5
    fade_out_s: float = 2.0
    lead_in_s: float = 2.0
    start_s: float = 0.0
    loop: bool = True


def bed_for_intensity(asset_path: str, intensity: str, **overrides) -> MusicBed | None:
    """Build a :class:`MusicBed` at the gain for a Format ``music_bed`` intensity.

    Returns ``None`` for ``"none"`` (or an unknown intensity), so callers can do
    ``bed = bed_for_intensity(asset, fmt.music_bed)`` and skip when falsy.
    """
    gain = BED_GAIN_BY_INTENSITY.get(intensity)
    if gain is None:
        return None
    return MusicBed(asset_path=asset_path, gain_db=gain, **overrides)


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH (brew install ffmpeg).")


def prepare_bed(bed: MusicBed, target_s: float, out_path: str | Path, *, sample_rate: int = 44100) -> Path:
    """Render ``bed`` to a ready-to-mix underscore of length ``target_s - lead_in_s``.

    Seeks to ``bed.start_s`` (looping if needed), trims to the covered length, and
    bakes in fades + ``gain_db`` + stereo. The caller mixes the result delayed by
    ``bed.lead_in_s``. Returns ``out_path``.
    """
    _require_ffmpeg()
    length = max(0.05, target_s - bed.lead_in_s)
    fo_start = max(0.0, length - bed.fade_out_s)
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    pre_input: list[str] = []
    if bed.loop:
        pre_input += ["-stream_loop", "-1"]
    if bed.start_s > 0:
        pre_input += ["-ss", f"{bed.start_s:.3f}"]
    af = (
        f"afade=t=in:st=0:d={bed.fade_in_s},"
        f"afade=t=out:st={fo_start:.3f}:d={bed.fade_out_s},"
        f"volume={bed.gain_db}dB,"
        f"aformat=sample_rates={sample_rate}:channel_layouts=stereo"
    )
    subprocess.run(
        ["ffmpeg", "-y", *pre_input, "-i", str(bed.asset_path), "-t", f"{length:.3f}",
         "-af", af, str(out)],
        check=True, capture_output=True,
    )
    return out
