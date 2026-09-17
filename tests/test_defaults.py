"""The package default is expressive, and the user can override and persist it.

Two things are being pinned here at once, and they pull against each other:

* out of the box braidio must render a voice that sounds alive — the old v2
  default could not render ``[audio tags]`` at all, which capped every
  production at the flat end before an author wrote a word;
* but a default nobody can change is its own problem, so the resolution order
  explicit > env > config file > package default has to actually hold.
"""

import json

import pytest

import braidio
from braidio.defaults import (
    PACKAGE_DEFAULT_DELIVERY,
    config_path,
    default_delivery,
    default_voice_id,
    describe_defaults,
    user_config,
)
from braidio.delivery import V3_NARRATOR, V3_PRESENTER, Delivery


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Never read the developer's real config while testing."""
    monkeypatch.setenv("BRAIDIO_CONFIG", str(tmp_path / "config.json"))
    monkeypatch.delenv("BRAIDIO_DELIVERY", raising=False)
    monkeypatch.delenv("BRAIDIO_VOICE_ID", raising=False)
    return tmp_path / "config.json"


# --- the package default -----------------------------------------------------


def test_package_default_can_render_audio_tags():
    """The whole point. v2 cannot, and tags are the expressiveness lever."""
    assert PACKAGE_DEFAULT_DELIVERY.supports_audio_tags
    assert PACKAGE_DEFAULT_DELIVERY.model_id == "eleven_v3"


def test_package_default_sits_at_the_expressive_end():
    assert PACKAGE_DEFAULT_DELIVERY.voice_settings["stability"] == 0.0


def test_every_shipped_format_can_render_audio_tags():
    from braidio.formats import FORMATS

    flat = [
        fid
        for fid, f in FORMATS.items()
        if not f.narration_delivery.supports_audio_tags
    ]
    assert not flat, f"formats that cannot render tags: {flat}"


def test_the_narration_model_default_is_v3():
    assert braidio.DEFAULT_MODEL_ID == "eleven_v3"


def test_weave_config_default_settings_are_v3_shaped():
    """v3 silently ignores style/similarity_boost/speed — do not advertise them."""
    from braidio.weave_config import WeaveConfig

    settings = WeaveConfig().voice_settings
    assert "stability" in settings
    assert not ({"style", "similarity_boost", "speed"} & set(settings))


# --- the override chain ------------------------------------------------------


def test_no_config_gives_the_package_default():
    assert default_delivery() is PACKAGE_DEFAULT_DELIVERY


def test_an_explicit_delivery_object_wins():
    assert default_delivery(V3_NARRATOR) is V3_NARRATOR


def test_an_explicit_delivery_name_wins():
    assert default_delivery("v3-narrator").name == "v3-narrator"


def test_the_config_file_is_honoured(_isolated_config):
    _isolated_config.write_text(json.dumps({"delivery": "v3-narrator"}))
    assert default_delivery().name == "v3-narrator"


def test_the_environment_beats_the_config_file(_isolated_config, monkeypatch):
    _isolated_config.write_text(json.dumps({"delivery": "v3-narrator"}))
    monkeypatch.setenv("BRAIDIO_DELIVERY", "v3-creative")
    assert default_delivery().name == "v3-creative"


def test_an_explicit_argument_beats_the_environment(_isolated_config, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DELIVERY", "v3-creative")
    assert default_delivery(V3_PRESENTER) is V3_PRESENTER


def test_a_persisted_voice_id_is_returned(_isolated_config):
    _isolated_config.write_text(json.dumps({"voice_id": "abc123"}))
    assert default_voice_id() == "abc123"
    assert default_voice_id("explicit") == "explicit"


def test_voice_settings_alone_ride_on_the_default_model(_isolated_config):
    _isolated_config.write_text(json.dumps({"voice_settings": {"stability": 0.5}}))
    d = default_delivery()
    assert d.model_id == PACKAGE_DEFAULT_DELIVERY.model_id
    assert d.voice_settings == {"stability": 0.5}
    assert d.supports_audio_tags


# --- failure modes -----------------------------------------------------------


def test_a_malformed_config_warns_once_and_is_ignored(_isolated_config):
    _isolated_config.write_text("{not json at all")
    with pytest.warns(UserWarning, match="unreadable config"):
        assert user_config() == {}
    assert default_delivery() is PACKAGE_DEFAULT_DELIVERY


def test_an_unknown_delivery_name_warns_and_falls_back(_isolated_config):
    _isolated_config.write_text(json.dumps({"delivery": "v9-nonexistent"}))
    with pytest.warns(UserWarning, match="unknown delivery"):
        assert default_delivery() is PACKAGE_DEFAULT_DELIVERY


def test_a_config_that_is_not_an_object_is_ignored(_isolated_config):
    _isolated_config.write_text(json.dumps(["not", "a", "mapping"]))
    assert user_config() == {}


def test_describe_defaults_says_where_each_part_came_from(
    _isolated_config, monkeypatch
):
    _isolated_config.write_text(json.dumps({"voice_id": "abc123"}))
    monkeypatch.setenv("BRAIDIO_DELIVERY", "v3-narrator")
    text = describe_defaults()
    assert "v3-narrator" in text
    assert "abc123" in text
    assert "BRAIDIO_DELIVERY" in text
    assert str(config_path()) in text


def test_resolution_is_read_at_call_time_not_import_time(_isolated_config):
    """A config edit must take effect without reimporting braidio."""
    assert default_delivery() is PACKAGE_DEFAULT_DELIVERY
    _isolated_config.write_text(json.dumps({"delivery": "v3-narrator"}))
    assert default_delivery().name == "v3-narrator"


def test_render_production_accepts_a_delivery_name(_isolated_config):
    """The signature widened from Delivery to Delivery | str | None."""
    import inspect

    sig = inspect.signature(braidio.render_production)
    assert sig.parameters["delivery"].default is None


def test_exported_from_the_package_root():
    assert isinstance(braidio.default_delivery(), Delivery)
    assert braidio.PACKAGE_DEFAULT_DELIVERY.model_id == "eleven_v3"
