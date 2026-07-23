"""ElevenLabs narration synthesis.

Thin wrapper over :func:`mixing.text_to_speech` (the ElevenLabs entry point,
with on-disk caching) applying a voice preset: the ``eleven_multilingual_v2``
quality model and a locked voice + settings so a whole production sounds like
one narrator.

Voice defaults to "George — Warm, Captivating Storyteller"; override with the
``BRAIDIO_TTS_VOICE`` env var (:data:`VOICE_ENV_VAR`) or the ``voice_id`` arg.
"""

from __future__ import annotations

import os
from pathlib import Path

from mixing import text_to_speech

# "George — Warm, Captivating Storyteller" (ElevenLabs premade voice).
DEFAULT_VOICE_ID = "JBFqnCBsd6RMkjVDRZzb"
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
VOICE_ENV_VAR = "BRAIDIO_TTS_VOICE"

# Preset from research: neutral-expressive documentary narration.
DEFAULT_VOICE_SETTINGS: dict[str, float | bool] = {
    "stability": 0.5,
    "similarity_boost": 0.75,
    "style": 0.0,
    "use_speaker_boost": True,
    "speed": 0.97,
}


def resolve_voice_id(voice_id: str | None = None) -> str:
    """Voice id from arg → :data:`VOICE_ENV_VAR` env → default."""
    return voice_id or os.environ.get(VOICE_ENV_VAR) or DEFAULT_VOICE_ID


def narrate(
    text: str,
    out_path: str | Path,
    *,
    voice_id: str | None = None,
    model_id: str = DEFAULT_MODEL_ID,
    voice_settings: dict | None = None,
    output_format: str = "mp3_44100_128",
    refresh: bool = False,
) -> Path:
    """Synthesize ``text`` to ``out_path`` (mp3). Returns the path.

    Caching is handled by ``mixing.text_to_speech`` (keyed on text+voice+model);
    pass ``refresh=True`` to regenerate.
    """
    audio = text_to_speech(
        text,
        resolve_voice_id(voice_id),
        model_id=model_id,
        output_format=output_format,
        voice_settings=voice_settings or DEFAULT_VOICE_SETTINGS,
        refresh=refresh,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    return out


DIALOGUE_MODEL_ID = "eleven_v3"
DIALOGUE_CACHE_ENV_KEY = "BRAIDIO_DIALOGUE_CACHE_DIR"


def _dialogue_cache_dir():
    from mixing import _cache

    return _cache.default_cache_dir("braidio-dialogue", env_key=DIALOGUE_CACHE_ENV_KEY)


def text_to_dialogue(
    turns,
    *,
    model_id: str = DIALOGUE_MODEL_ID,
    output_format: str = "mp3_44100_128",
    settings: dict | None = None,
    seed: int | None = None,
    api_key: str | None = None,
    cache=True,
    refresh: bool = False,
) -> bytes:
    """Synthesize a multi-speaker exchange in ONE pass (ElevenLabs Text-to-Dialogue).

    Unlike per-line :func:`narrate`, this renders the whole conversation together
    so prosody is conditioned across turns — the key to sounding like people
    *talking to each other* rather than alternating monologues (see braidio#1 /
    ``docs/research/conversational-vs-narration-tts.md``). ``eleven_v3`` only.

    **Cached** (like :func:`narrate`/``mixing.text_to_speech``): the result is
    keyed on the SHA-256 of every parameter that affects the audio (turns,
    voices, model, settings, seed, format). A cache hit returns the *same* bytes
    instantly — no API call, deterministic master, and the basis for partial
    re-render (change one exchange → only its key changes). ``cache=True``
    (default) uses :data:`DIALOGUE_CACHE_ENV_KEY` / the default cache dir;
    ``cache=False`` disables it; a path uses that dir. ``refresh=True`` forces a
    re-render (to re-roll a v3 take). Because v3 is nondeterministic, caching a
    seedless call freezes one random take — pass a ``seed`` for reproducibility.

    Args:
        turns: ordered ``(voice_id, text)`` pairs (or ``{"voice_id", "text"}``).
            Keep each request under ~2000 chars total (API limit).
        settings: optional model settings dict (e.g. ``{"stability": 0.45}``).

    Returns: raw audio bytes in ``output_format``.
    """
    import json

    from mixing import _cache

    inputs = []
    for t in turns:
        if isinstance(t, (tuple, list)):
            inputs.append({"voice_id": t[0], "text": t[1]})
        else:
            inputs.append({"voice_id": t["voice_id"], "text": t["text"]})

    cache_dir = _cache.resolve_cache_dir(cache, default_factory=_dialogue_cache_dir)
    key = None
    if cache_dir is not None:
        key = _cache.sha256_key(
            "text_to_dialogue",
            json.dumps(inputs, sort_keys=True, ensure_ascii=False),
            model_id,
            output_format,
            json.dumps(settings or {}, sort_keys=True),
            "" if seed is None else str(seed),
        )
        if not refresh:
            cached = _cache.read_cache(cache_dir, key, suffix=".audio")
            if cached is not None:
                return cached

    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(
        api_key=api_key or os.environ.get("ELEVENLABS_API_KEY") or os.environ.get("ELEVEN_API_KEY")
    )
    kwargs = {"inputs": inputs, "model_id": model_id, "output_format": output_format}
    if settings is not None:
        kwargs["settings"] = settings
    if seed is not None:
        kwargs["seed"] = seed
    audio = b"".join(client.text_to_dialogue.convert(**kwargs))

    if cache_dir is not None and key is not None:
        _cache.write_cache(cache_dir, key, audio, suffix=".audio")
    return audio
