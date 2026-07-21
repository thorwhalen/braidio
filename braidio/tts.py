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
