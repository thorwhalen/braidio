"""Cost model for braidio's paid operations (ElevenLabs TTS).

braidio's only spend is ElevenLabs synthesis — :func:`braidio.narrate` /
:func:`braidio.text_to_dialogue` and the renderers built on them — billed by
ElevenLabs **per character** of submitted text. Everything else (ffmpeg
extraction, weaving, loudness normalization) is local and free.

This module is the single source of truth that turns text into an honest USD
figure, so:

- renders can populate ``lacing.Artifact.cost_usd`` (previously hardcoded
  ``0.0``) and a usage ledger can record real dollars per call, and
- a free :func:`estimate_cost` can preview a whole :class:`braidio.Script`
  before any synthesis is paid for.

Characters are always counted exactly; the USD conversion uses a **configurable**
per-1000-character rate (env :data:`RATE_ENV_VAR`, a per-model table, or the
module default) — never a magic number at the call site (open/closed). Honest-cost
rule (as in ``falaw``): when no rate is known the USD is ``None`` — *unpriced*, not
a fake ``0.0`` — while the exact character count is still reported.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional, Union

from braidio.script import Script, Narration, Dialogue, SegmentBeat
from braidio.tts import DEFAULT_MODEL_ID, DIALOGUE_MODEL_ID

#: Env var overriding the USD-per-1000-characters rate for every model.
RATE_ENV_VAR = "BRAIDIO_TTS_USD_PER_1K_CHARS"

#: Default USD per 1000 characters when nothing else is configured. Approximate:
#: ElevenLabs bills per credit and the $/credit depends on your plan, so set
#: :data:`RATE_ENV_VAR` to your plan's real rate for exact ledgers. Kept slightly
#: conservative so budgets over-estimate rather than under-estimate spend.
DEFAULT_USD_PER_1K_CHARS: float = 0.30

#: Per-model rate overrides (USD per 1000 chars). ElevenLabs prices some models
#: differently (e.g. the ``eleven_v3`` dialogue model); extend as rates are
#: confirmed. An entry here wins over :data:`DEFAULT_USD_PER_1K_CHARS` but not
#: over the env override.
MODEL_USD_PER_1K_CHARS: dict[str, float] = {}

#: Env values (case-insensitive) that explicitly mark the rate as *unknown* so
#: costs report ``None`` (unpriced) instead of a default.
_UNPRICED_SENTINELS = ("", "none", "unpriced", "unknown")


def usd_per_1k_chars(model_id: Optional[str] = None) -> Optional[float]:
    """Resolved USD-per-1000-characters rate: env → per-model table → default.

    Returns ``None`` only when the rate is explicitly disabled (env set to one of
    :data:`_UNPRICED_SENTINELS` or an unparseable value), signalling *unpriced*
    rather than free.

    >>> import os
    >>> _ = os.environ.pop(RATE_ENV_VAR, None)
    >>> usd_per_1k_chars() == DEFAULT_USD_PER_1K_CHARS
    True
    >>> os.environ[RATE_ENV_VAR] = "0.5"
    >>> usd_per_1k_chars()
    0.5
    >>> os.environ[RATE_ENV_VAR] = "none"
    >>> usd_per_1k_chars() is None
    True
    >>> del os.environ[RATE_ENV_VAR]
    """
    env = os.environ.get(RATE_ENV_VAR)
    if env is not None:
        if env.strip().lower() in _UNPRICED_SENTINELS:
            return None
        try:
            return float(env)
        except ValueError:
            return None
    if model_id and model_id in MODEL_USD_PER_1K_CHARS:
        return MODEL_USD_PER_1K_CHARS[model_id]
    return DEFAULT_USD_PER_1K_CHARS


def billable_chars(text: Optional[str]) -> int:
    """Characters ElevenLabs bills for ``text`` (the whole submitted string).

    ElevenLabs charges for everything sent — including ``eleven_v3`` audio tags
    like ``[excited]`` — so this is just ``len(text)``. A named function keeps the
    billing definition in one place if it ever needs to change.

    >>> billable_chars("hello")
    5
    >>> billable_chars(None)
    0
    """
    return len(text or "")


def tts_cost_usd(
    text: Optional[str], *, model_id: Optional[str] = None
) -> Optional[float]:
    """Honest USD cost to synthesize ``text``; ``0.0`` for empty, ``None`` if unpriced.

    >>> tts_cost_usd("")
    0.0
    >>> _ = os.environ.pop(RATE_ENV_VAR, None)
    >>> round(tts_cost_usd("x" * 1000), 4) == round(DEFAULT_USD_PER_1K_CHARS, 4)
    True
    """
    chars = billable_chars(text)
    if chars == 0:
        return 0.0
    rate = usd_per_1k_chars(model_id)
    if rate is None:
        return None
    return round(chars / 1000 * rate, 6)


@dataclass(frozen=True)
class CostItem:
    """One billable unit of an estimate (a narration beat or a dialogue beat)."""

    label: str
    kind: str  # 'narration' | 'dialogue'
    characters: int
    usd: Optional[float]
    model_id: str


@dataclass(frozen=True)
class CostEstimate:
    """A production's estimated TTS spend, exact on characters, honest on dollars.

    ``usd`` is the sum of the *priced* items; ``unpriced`` is ``True`` when some
    billable text had no configured rate (so ``usd`` is a lower bound). ``0`` items
    (e.g. an all-segment script) gives ``characters=0, usd=0.0, unpriced=False``.
    """

    characters: int
    usd: Optional[float]
    unpriced: bool
    items: tuple[CostItem, ...] = ()

    @property
    def summary(self) -> str:
        """One-line human summary (handy for a CLI/MCP preview)."""
        dollars = "unknown" if self.usd is None else f"${self.usd:.4f}"
        tail = " (+ unpriced parts)" if self.unpriced else ""
        return f"{self.characters:,} chars → {dollars}{tail}"


def _script_items(script: Script, *, published: bool) -> list[CostItem]:
    """Billable items of ``script``. ``published`` uses rights-safe substitutes.

    Narration uses ``published_text`` (when set) under the published profile;
    SegmentBeats are free clips *except* when the published profile substitutes a
    synthesized narration (``published_substitute``). Bare segment beats cost $0.
    """
    items: list[CostItem] = []
    for i, beat in enumerate(script.beats):
        if isinstance(beat, Narration):
            text = (beat.published_text or beat.text) if published else beat.text
            items.append(
                CostItem(
                    label=f"beat[{i}] narration",
                    kind="narration",
                    characters=billable_chars(text),
                    usd=tts_cost_usd(text, model_id=DEFAULT_MODEL_ID),
                    model_id=DEFAULT_MODEL_ID,
                )
            )
        elif isinstance(beat, Dialogue):
            text = "".join(t for _role, t in beat.turns)
            items.append(
                CostItem(
                    label=(
                        f"beat[{i}] dialogue ({beat.label})"
                        if beat.label
                        else f"beat[{i}] dialogue"
                    ),
                    kind="dialogue",
                    characters=billable_chars(text),
                    usd=tts_cost_usd(text, model_id=DIALOGUE_MODEL_ID),
                    model_id=DIALOGUE_MODEL_ID,
                )
            )
        elif isinstance(beat, SegmentBeat) and published and beat.published_substitute:
            text = beat.published_substitute
            items.append(
                CostItem(
                    label=f"beat[{i}] published-substitute",
                    kind="narration",
                    characters=billable_chars(text),
                    usd=tts_cost_usd(text, model_id=DEFAULT_MODEL_ID),
                    model_id=DEFAULT_MODEL_ID,
                )
            )
        # bare SegmentBeat (default profile) = free extracted media; no item.
    return items


def estimate_cost(
    source: Union[Script, str],
    *,
    model_id: Optional[str] = None,
    published: bool = False,
) -> CostEstimate:
    """Estimate ElevenLabs spend for a :class:`braidio.Script` or a raw string.

    Free/local work (segment extraction, weaving) contributes nothing. ``published``
    estimates the published cut (rights-safe rewrites + synthesized clip
    substitutes). The returned :class:`CostEstimate` reports exact characters and an
    honest dollar sum (a lower bound when some text is :func:`unpriced <usd_per_1k_chars>`).

    >>> from braidio import Script, Narration, SegmentBeat
    >>> _ = os.environ.pop(RATE_ENV_VAR, None)
    >>> s = Script(title="x", id_slug="01", beats=[
    ...     Narration(text="a" * 500), SegmentBeat(reference="clip:1")])
    >>> est = estimate_cost(s)
    >>> est.characters  # only the narration counts; the clip is free
    500
    >>> est.unpriced
    False
    """
    if isinstance(source, str):
        items = [
            CostItem(
                label="text",
                kind="narration",
                characters=billable_chars(source),
                usd=tts_cost_usd(source, model_id=model_id or DEFAULT_MODEL_ID),
                model_id=model_id or DEFAULT_MODEL_ID,
            )
        ]
    else:
        items = _script_items(source, published=published)

    characters = sum(it.characters for it in items)
    priced = [it.usd for it in items if it.usd is not None]
    unpriced = any(it.characters > 0 and it.usd is None for it in items)
    usd = round(sum(priced), 6) if priced else (None if unpriced else 0.0)
    return CostEstimate(
        characters=characters, usd=usd, unpriced=unpriced, items=tuple(items)
    )
