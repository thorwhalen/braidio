"""Tests for the ready-made format templates. Audio-free / API-free."""

from __future__ import annotations

import pytest

from braidio.conversation import ConversationCast
from braidio.delivery import Delivery
from braidio.formats import (
    DEEP_DIVE,
    DOCUMENTARY_VO,
    FORMATS,
    PANEL,
    SOLO_EXPLAINER,
    SONG_EXPLODER,
    Format,
    describe_asset_application,
    render_format,
)
from braidio.script import SceneBreak, Script
from braidio.weave_config import WeaveConfig

_VALID_PLACEMENTS = {"before", "under", "after"}
_VALID_BEDS = {"continuous", "light", "sparse", "none"}


def test_presets_well_formed():
    assert set(FORMATS) == {
        "solo_explainer", "deep_dive", "interview", "interview_host_removed",
        "panel", "debate", "documentary_vo",
    }
    for fid, f in FORMATS.items():
        assert isinstance(f, Format) and f.id == fid
        assert f.name and f.summary  # every preset is self-describing
        assert isinstance(f.narration_delivery, Delivery)
        assert isinstance(f.weave, WeaveConfig)
        assert f.clip_placement in _VALID_PLACEMENTS
        assert f.music_bed in _VALID_BEDS
        assert f.cast is None or isinstance(f.cast, ConversationCast)


def test_voice_count_matches_shape():
    # solo / host-removed have no dialogue spine; group formats do.
    assert SOLO_EXPLAINER.cast is None
    assert SONG_EXPLODER.cast is None and SONG_EXPLODER.music_bed == "none"
    assert set(DEEP_DIVE.cast.roles) == {"host_a", "host_b"}
    assert len(PANEL.cast.roles) == 4  # moderator + 3 panelists
    # panel voices are distinct (legibility with many voices)
    assert len(set(PANEL.cast.roles.values())) == 4


def test_render_format_wires_defaults(monkeypatch):
    """render_format passes the format's cast/voice/delivery/weave to the engine,
    and per-call overrides win."""
    captured = {}

    def fake_render_production(script, **kwargs):
        captured.update(kwargs)
        captured["script"] = script
        return "OUT"

    import braidio.render as render_mod

    monkeypatch.setattr(render_mod, "render_production", fake_render_production)

    out = render_format(DEEP_DIVE, "SCRIPT", source="SRC", out_path="x.mp3")
    assert out == "OUT"
    assert captured["script"] == "SCRIPT"
    assert captured["source"] == "SRC"
    assert captured["cast"] is DEEP_DIVE.cast
    assert captured["voice_id"] == DEEP_DIVE.narration_voice
    assert captured["delivery"] is DEEP_DIVE.narration_delivery
    assert captured["config"] is DEEP_DIVE.weave

    # solo has no cast → the cast kwarg is omitted (engine default applies)
    captured.clear()
    render_format(SOLO_EXPLAINER, "S", source="SRC")
    assert "cast" not in captured
    assert captured["voice_id"] == SOLO_EXPLAINER.narration_voice

    # overrides win
    captured.clear()
    render_format(DOCUMENTARY_VO, "S", source="SRC", voice_id="OVERRIDE")
    assert captured["voice_id"] == "OVERRIDE"


def test_render_format_refuses_bed_asset_under_music_bed_none():
    # braidio#43: a music_bed="none" format never renders a bed, so bed_asset
    # must be refused BEFORE any render (the caller would otherwise pay for a
    # bed the format silently drops).
    assert SONG_EXPLODER.music_bed == "none"
    with pytest.raises(ValueError, match="music_bed='none'|music_bed=.none."):
        render_format(SONG_EXPLODER, "S", source=None, bed_asset="bed.wav")


def test_render_format_bed_asset_still_works_for_a_bedded_format(monkeypatch):
    captured = {}
    import braidio.render as render_mod

    monkeypatch.setattr(
        render_mod,
        "render_production",
        lambda script, **kw: captured.update(kw) or "OUT",
    )
    render_format(SOLO_EXPLAINER, "S", source=None, bed_asset="bed.wav")
    assert captured["music_bed"].asset_path == "bed.wav"


def test_describe_asset_application_bed_none_format():
    result = describe_asset_application(SONG_EXPLODER, "S", bed_asset="bed.wav")
    assert result["bed_applied"] is False
    assert "music_bed" in result["bed_ignored_reason"]
    assert result["sting_applied"] is None  # no sting_asset supplied


def test_describe_asset_application_bed_applied_when_intensity_has_a_gain():
    result = describe_asset_application(SOLO_EXPLAINER, "S", bed_asset="bed.wav")
    assert result["bed_applied"] is True
    assert result["bed_ignored_reason"] is None


def test_describe_asset_application_sting_ignored_without_a_playing_scene_break():
    # SONG_EXPLODER's default scene_marker is "none" and this script has no
    # scene_break at all — the sting is legitimately unused, not refused.
    script = Script(title="t", id_slug="01", beats=[])
    result = describe_asset_application(SONG_EXPLODER, script, sting_asset="hit.wav")
    assert result["sting_applied"] is False
    reason = result["sting_ignored_reason"]
    assert "sting" in reason or "marker" in reason
    assert result["bed_applied"] is None  # no bed_asset supplied


def test_describe_asset_application_sting_applied_via_per_beat_override():
    # a SceneBreak.marker override plays the sting even under a "none" default.
    script = Script(title="t", id_slug="01", beats=[SceneBreak(marker="sting")])
    result = describe_asset_application(SONG_EXPLODER, script, sting_asset="hit.wav")
    assert result["sting_applied"] is True
    assert result["sting_ignored_reason"] is None


def test_describe_asset_application_sting_applied_under_default_sting_marker():
    script = Script(title="t", id_slug="01", beats=[SceneBreak()])
    result = describe_asset_application(DEEP_DIVE, script, sting_asset="hit.wav")
    assert result["sting_applied"] is True


def test_format_render_method_delegates(monkeypatch):
    captured = {}
    import braidio.formats as fmt_mod

    monkeypatch.setattr(
        fmt_mod, "render_format",
        lambda fmt, script, **kw: captured.update({"fmt": fmt, "script": script, **kw}) or "OK",
    )
    assert PANEL.render("S", source="SRC") == "OK"
    assert captured["fmt"] is PANEL and captured["script"] == "S"
