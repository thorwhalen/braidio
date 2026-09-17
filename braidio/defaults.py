"""User-overridable, persisted defaults for how braidio renders a voice.

**Why this module exists.** The package default used to be
``eleven_multilingual_v2``, a model that cannot render inline ``[audio tags]``
*at all*. Since tag density is the main lever on whether a read sounds alive
(measured: plain text 70.8 Hz of pitch range, densely tagged 124.4 Hz, while
``stability`` across its whole range moves it only 85 -> 72 Hz), the old default
capped every production at the flat end before an author had written a word. One
listener's verdict on such a render was "somniferous".

So the package default is now the expressive one. But a default nobody can
change is just a different imposition, hence the resolution order:

    explicit argument  >  environment variable  >  user config file  >  package default

The config file is JSON at ``$BRAIDIO_CONFIG``, else
``$XDG_CONFIG_HOME/braidio/config.json``, else ``~/.config/braidio/config.json``:

.. code-block:: json

    {
      "delivery": "v3-presenter",
      "voice_id": "iP95p4xoKVk53GoZ742B",
      "voice_settings": {"stability": 0.0, "use_speaker_boost": true}
    }

Every key is optional; what you leave out keeps the package default. Nothing
here touches the network, and a malformed file is reported once and then ignored
rather than taking a render down with it.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from typing import Any

from braidio.delivery import DELIVERIES, V3_PRESENTER, Delivery

__all__ = [
    "PACKAGE_DEFAULT_DELIVERY",
    "config_path",
    "user_config",
    "default_delivery",
    "default_voice_id",
    "default_voice_settings",
    "describe_defaults",
]

#: What braidio uses when nothing else says otherwise. ``eleven_v3`` so inline
#: ``[audio tags]`` fire, at the expressive end of ``stability``.
PACKAGE_DEFAULT_DELIVERY: Delivery = V3_PRESENTER

_ENV_CONFIG = "BRAIDIO_CONFIG"
_ENV_DELIVERY = "BRAIDIO_DELIVERY"
_ENV_VOICE = "BRAIDIO_VOICE_ID"

_warned: set[str] = set()


def config_path() -> Path:
    """Where the user's persisted defaults live (the file need not exist)."""
    explicit = os.environ.get(_ENV_CONFIG)
    if explicit:
        return Path(explicit).expanduser()
    base = os.environ.get("XDG_CONFIG_HOME") or "~/.config"
    return Path(base).expanduser() / "braidio" / "config.json"


def user_config() -> dict[str, Any]:
    """The user's persisted defaults, or ``{}``.

    A missing file is normal. A malformed one warns *once* per path and is then
    treated as absent.
    """
    path = config_path()
    try:
        if not path.is_file():
            return {}
        data = json.loads(path.read_text())
    except Exception as exc:  # unreadable, not JSON, whatever
        key = str(path)
        if key not in _warned:
            _warned.add(key)
            warnings.warn(
                f"braidio: ignoring unreadable config {path}: {exc}", stacklevel=2
            )
        return {}
    return data if isinstance(data, dict) else {}


def _known_delivery(name: str) -> Delivery | None:
    if name in DELIVERIES:
        return DELIVERIES[name]
    if name not in _warned:
        _warned.add(name)
        warnings.warn(
            f"braidio: unknown delivery {name!r}; known: {sorted(DELIVERIES)}. "
            f"Falling back to {PACKAGE_DEFAULT_DELIVERY.name}.",
            stacklevel=3,
        )
    return None


def default_delivery(explicit: Delivery | str | None = None) -> Delivery:
    """Resolve the delivery to render with.

    Args:
        explicit: a :class:`~braidio.delivery.Delivery`, or the name of one
            (see :data:`braidio.delivery.DELIVERIES`). Wins over everything.

    Examples:
        >>> default_delivery(V3_PRESENTER) is V3_PRESENTER
        True
        >>> default_delivery("v3-narrator").name
        'v3-narrator'
    """
    if isinstance(explicit, Delivery):
        return explicit
    for candidate in (
        explicit,
        os.environ.get(_ENV_DELIVERY),
        user_config().get("delivery"),
    ):
        if candidate and (found := _known_delivery(candidate)) is not None:
            return found

    settings = user_config().get("voice_settings")
    if isinstance(settings, dict) and settings:
        # Someone who pins settings but not a delivery gets their settings on
        # the package default's model.
        return Delivery(
            name=f"{PACKAGE_DEFAULT_DELIVERY.name}+user",
            model_id=PACKAGE_DEFAULT_DELIVERY.model_id,
            voice_settings=dict(settings),
            supports_audio_tags=PACKAGE_DEFAULT_DELIVERY.supports_audio_tags,
            supports_speed=PACKAGE_DEFAULT_DELIVERY.supports_speed,
            note="package default with voice_settings from the user config",
        )
    return PACKAGE_DEFAULT_DELIVERY


def default_voice_id(explicit: str | None = None) -> str | None:
    """Resolve the narration voice id, or ``None`` to let the caller decide."""
    return (
        explicit or os.environ.get(_ENV_VOICE) or user_config().get("voice_id") or None
    )


def default_voice_settings() -> dict[str, Any]:
    """The resolved delivery's voice settings, as a fresh dict."""
    return dict(default_delivery().voice_settings)


def describe_defaults() -> str:
    """What is in force, and where each part came from.

    Worth printing when a render does not sound the way somebody expected: the
    commonest cause is a config file they forgot they wrote.
    """
    path = config_path()
    cfg = user_config()
    d = default_delivery()
    lines = [
        f"delivery      : {d.name}  (model {d.model_id}, tags={d.supports_audio_tags})",
        f"voice_settings: {d.voice_settings}",
        f"voice_id      : {default_voice_id() or '(format / caller decides)'}",
        f"config file   : {path}"
        f"{'' if path.is_file() else '  (absent — package defaults)'}",
    ]
    if cfg:
        lines.append(f"from config   : {sorted(cfg)}")
    for var in (_ENV_CONFIG, _ENV_DELIVERY, _ENV_VOICE):
        if os.environ.get(var):
            lines.append(f"env override  : {var}={os.environ[var]}")
    return "\n".join(lines)
