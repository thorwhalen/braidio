"""Tests for the ready-made format templates. Audio-free / API-free."""

from __future__ import annotations

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
    render_format,
)
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


def test_format_render_method_delegates(monkeypatch):
    captured = {}
    import braidio.formats as fmt_mod

    monkeypatch.setattr(
        fmt_mod, "render_format",
        lambda fmt, script, **kw: captured.update({"fmt": fmt, "script": script, **kw}) or "OK",
    )
    assert PANEL.render("S", source="SRC") == "OK"
    assert captured["fmt"] is PANEL and captured["script"] == "S"
