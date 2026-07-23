"""Conversational register: render an exchange as people *talking to each other*.

The second delivery register beside narration (braidio#1). A
:class:`ConversationCast` maps role labels (``"A"``/``"B"``) to contrasting
**conversational** ElevenLabs voices. :func:`render_dialogue` synthesizes the
whole exchange in **one pass** via :func:`braidio.tts.text_to_dialogue` (eleven_v3)
so prosody is conditioned across turns — the key to not sounding narrated.
:func:`render_turns_sequential` is the per-line baseline (each turn synthesized
alone, then concatenated) used for A/B comparison.

Casting note: use conversational-labelled voices, not narrator voices; loosen
settings so v3 audio tags fire. The scripted exchange itself must carry the
disfluency (backchannels, interruptions, fragments) — the model won't invent it.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from braidio.tts import narrate, text_to_dialogue

# Curated conversational voices (casual, not narrator).
JESSICA = "cgSgspJ2msm6clMCkdW9"  # playful, bright, warm (F)
WILL = "bIHbv24MWmeRgasZH58o"     # relaxed optimist (M)
CHRIS = "iP95p4xoKVk53GoZ742B"    # charming, down-to-earth (M)
LAURA = "FGY2WhTYpPnrIDTdsKH5"    # enthusiast, quirky attitude (F)


@dataclass(frozen=True)
class ConversationCast:
    """Role → voice mapping + model/settings for a conversational exchange.

    Default cast: **Jessica** (playful/bright, F) + **Chris** (charming/
    down-to-earth, M) — snappier than the "relaxed" voices. ``stability=0.45``
    is the research sweet spot for a lively but coherent read (never 1.0/Robust,
    which mutes v3 tags; ~0.1 is too unstable). See braidio#1 + the pacing doc.
    """

    roles: dict[str, str] = field(default_factory=lambda: {"A": JESSICA, "B": CHRIS})
    model_id: str = "eleven_v3"
    settings: dict | None = field(default_factory=lambda: {"stability": 0.45})


DEFAULT_CAST = ConversationCast()


def _require_ffmpeg() -> None:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH.")


def render_dialogue(
    turns: list[tuple[str, str]],
    cast: ConversationCast = DEFAULT_CAST,
    *,
    out_path: str | Path,
    output_format: str = "mp3_44100_128",
    seed: int | None = None,
    cache=True,
    refresh: bool = False,
) -> Path:
    """One-pass render of ``turns`` (``[(role, text), …]``) via Text-to-Dialogue.

    Cached by default (see :func:`braidio.tts.text_to_dialogue`): an unchanged
    exchange renders instantly on re-run. ``refresh=True`` re-rolls the take.
    """
    vturns = [(cast.roles[role], text) for role, text in turns]
    audio = text_to_dialogue(
        vturns, model_id=cast.model_id, settings=cast.settings,
        seed=seed, output_format=output_format, cache=cache, refresh=refresh,
    )
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(audio)
    return out


def _concat_with_gaps(parts: list[Path], out: Path, *, gap_s: float, sample_rate: int = 44100) -> Path:
    """Concatenate audio parts with ``gap_s`` seconds of silence between them."""
    from mixing import concatenate_audio

    _require_ffmpeg()
    out.parent.mkdir(parents=True, exist_ok=True)
    if gap_s <= 0:
        concatenate_audio(*[str(p) for p in parts], output=str(out), crossfade=0.0)
        return out
    sil = out.parent / "_gap.mp3"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i", f"anullsrc=r={sample_rate}:cl=stereo",
         "-t", f"{gap_s:.3f}", str(sil)],
        check=True, capture_output=True,
    )
    interleaved: list[str] = []
    for i, p in enumerate(parts):
        if i:
            interleaved.append(str(sil))
        interleaved.append(str(p))
    concatenate_audio(*interleaved, output=str(out), crossfade=0.0)
    return out


def render_turns_sequential(
    turns: list[tuple[str, str]],
    cast: ConversationCast = DEFAULT_CAST,
    *,
    out_path: str | Path,
    work_dir: str | Path = "data/tts/conversation",
    voice_settings: dict | None = None,
    gap_s: float = 0.25,
) -> Path:
    """Per-line baseline: synthesize each turn alone (its role's voice) and
    concatenate with ``gap_s`` gaps. Prosody is NOT shared across turns — this is
    what tends to sound like alternating monologues (the thing to beat)."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    parts: list[Path] = []
    for i, (role, text) in enumerate(turns):
        raw = narrate(
            text, work / f"turn{i:02d}-{role}.mp3",
            voice_id=cast.roles[role], model_id=cast.model_id, voice_settings=voice_settings,
        )
        parts.append(raw)
    out = Path(out_path)
    return _concat_with_gaps(parts, out, gap_s=gap_s)
