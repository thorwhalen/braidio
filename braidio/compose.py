"""Config-driven narration composition (#20) — the reusable entrypoint.

Turn a list of narration segments + a :class:`WeaveConfig` into audio. Dispatches
single-voice and multi-voice uniformly (single = a pool of one), reading *every*
knob from the config. This is the seed of the reusable weave engine (#18/#19):
it has no Hamilton-specifics — it takes plain text segments and a config.

Clip weaving (padded extraction + ducking) is composed separately (#21); this
module renders the narration track.
"""

from __future__ import annotations

from pathlib import Path

from braidio.multivoice import POOL_MANY, Voice, render_multivoice
from braidio.tts import DEFAULT_VOICE_ID
from braidio.weave_config import WeaveConfig

# Registry so pooled ids render with human-readable turn labels; unknown ids
# fall back to the id itself.
_KNOWN_VOICES: dict[str, Voice] = {v.id: v for v in POOL_MANY}
_KNOWN_VOICES.setdefault(
    DEFAULT_VOICE_ID, Voice(DEFAULT_VOICE_ID, "George", "M", "British", "storyteller")
)


def _pool_from_config(config: WeaveConfig) -> list[Voice]:
    return [_KNOWN_VOICES.get(vid, Voice(vid, vid[:6], "?")) for vid in config.voices]


def compose_narration(
    segments: list[str],
    config: WeaveConfig,
    *,
    out_path: str | Path,
    api_key: str | None = None,
    work_dir: str | Path = "data/tts/compose",
) -> list[tuple[Voice, str]]:
    """Render ``segments`` under ``config`` → ``out_path``.

    Single-voice and multi-voice go through the same turn-based path (a single
    voice is just a one-voice pool). Returns the ``(voice, turn_text)``
    assignment for reporting / provenance.

    ``api_key`` is an optional per-request ElevenLabs key threaded to
    :func:`braidio.multivoice.render_multivoice` (and thence every synthesized
    turn); ``None`` (default) keeps the ``$ELEVENLABS_API_KEY`` fallback.
    """
    return render_multivoice(
        segments,
        _pool_from_config(config),
        out_path=out_path,
        api_key=api_key,
        work_dir=work_dir,
        seed=config.voice_seed,
        min_turn=config.min_turn,
        max_turn=config.max_turn,
        avoid_immediate_repeat=config.avoid_immediate_repeat,
        model_id=config.model_id,
        base_settings=dict(config.voice_settings),
        speed_base=config.speed_base,
        speed_jitter=config.speed_jitter,
        crossfade_s=config.crossfade_s,
        gap_s=config.gap_turn_s,
        target_lufs=config.target_lufs,
    )
