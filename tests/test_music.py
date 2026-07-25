"""Tests for the music-bed model. Audio-free / API-free (no ffmpeg)."""

from __future__ import annotations

from braidio.music import BED_GAIN_BY_INTENSITY, MusicBed, bed_for_intensity


def test_bed_defaults():
    b = MusicBed("bed.mp3")
    assert b.asset_path == "bed.mp3"
    assert b.gain_db < 0 and b.lead_in_s > 0 and b.loop is True


def test_bed_for_intensity_maps_gain_and_skips_none():
    for intensity, gain in BED_GAIN_BY_INTENSITY.items():
        bed = bed_for_intensity("bed.mp3", intensity)
        if gain is None:  # "none" → no bed
            assert bed is None
        else:
            assert isinstance(bed, MusicBed) and bed.gain_db == gain
    # louder → quieter across the intensity ladder
    assert (
        BED_GAIN_BY_INTENSITY["continuous"]
        > BED_GAIN_BY_INTENSITY["light"]
        > BED_GAIN_BY_INTENSITY["sparse"]
    )
    # unknown intensity is treated as "no bed", not an error
    assert bed_for_intensity("bed.mp3", "bogus") is None


def test_bed_for_intensity_passes_overrides():
    bed = bed_for_intensity("bed.mp3", "light", lead_in_s=3.0, start_s=8.0)
    assert bed.lead_in_s == 3.0 and bed.start_s == 8.0
