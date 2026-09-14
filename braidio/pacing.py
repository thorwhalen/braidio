"""Intra-beat narration pacing — how one narration beat becomes spoken *turns*.

A narration beat used to be exactly one TTS call: one prosodic arc, one speed,
and no silence anywhere inside it. That is the mechanical read — a human varies
tempo within a paragraph and pauses *proportionally to how strongly a boundary
closes* (a paragraph break is not a comma).

This module is the pure, deterministic planner for that. It takes the beat's
text and the pacing knobs off a :class:`~braidio.weave_config.WeaveConfig` and
returns a list of :class:`NarrationTurn` — what to synthesize, how fast, and how
much silence to leave after it. No audio, no API, no I/O: the renderer
(:func:`braidio.render.render_production`) executes the plan.

Two research findings drive the design
(``misc/docs/research/notebooklm-and-conversational-pacing.md``):

- **Boundary-proportional pauses.** Punctuation is the engine's pause
  instruction, and a pause is only human when the boundary that earns it is
  strong. :data:`BOUNDARIES` is that table.
- **Final lengthening.** The robotic signature is *pause without lengthening* —
  a clipped last word followed by dead air. So each boundary carries a
  ``speed_scale`` as well as a ``gap_scale``, and they stay correlated.

The ``unit="beat"`` plan is empty by construction: that is the historical
one-call-per-beat behavior, and it is the default, so nothing paces unless a
:class:`WeaveConfig` asks for it.

>>> turns = plan_turns("One. Two. Three.", unit="sentence", min_turn=1, max_turn=1)
>>> [t.text for t in turns]
['One.', 'Two.', 'Three.']
>>> plan_turns("One. Two.", unit="beat")
[]
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Mapping

#: How a beat's text is cut into the units a turn is built from. ``"beat"``
#: means "don't cut at all" — one TTS call per beat, the historical behavior.
SEGMENTATION_UNITS = ("beat", "paragraph", "sentence", "clause")

#: ElevenLabs clamps ``voice_settings.speed`` to this range in practice; a
#: jittered speed outside it is silently useless, so the planner clamps.
SPEED_RANGE = (0.7, 1.2)

_PARAGRAPH_SPLIT = re.compile(r"\n\s*\n+")
# Sentence-final .?! (and …), allowing a closing quote/bracket after it.
_SENTENCE_SPLIT = re.compile(r'(?<=[.!?…])["\'”’)\]]*\s+')
# Clause-final , ; : — allowing the same trailing closers.
_CLAUSE_SPLIT = re.compile(r'(?<=[,;:])["\'”’)\]]*\s+')
_WS = re.compile(r"[ \t]+")


@dataclass(frozen=True)
class Boundary:
    """How strongly a unit's trailing punctuation closes.

    ``gap_scale`` multiplies the base gap (``WeaveConfig.gap_turn_s``) and
    ``speed_scale`` multiplies the turn's speed — *final lengthening*, the thing
    that keeps a pause from sounding like a dropout. The two are deliberately
    correlated: a stronger boundary gets both a longer silence and a slower
    approach to it.
    """

    name: str
    gap_scale: float
    speed_scale: float


#: The boundary table. Scales are relative to ``"sentence"`` (== the configured
#: ``gap_turn_s``), from the punctuation→break-strength table in
#: ``misc/docs/research/notebooklm-and-conversational-pacing.md``.
BOUNDARIES: Mapping[str, Boundary] = {
    "paragraph": Boundary("paragraph", 2.2, 0.96),
    "ellipsis": Boundary("ellipsis", 1.4, 0.97),
    "sentence": Boundary("sentence", 1.0, 0.98),
    "clause": Boundary("clause", 0.5, 0.99),
    "flowing": Boundary("flowing", 0.35, 1.0),  # em-dash: connect-through
    "none": Boundary("none", 0.25, 1.0),  # no punctuation: words run together
}

_TERMINAL_CLOSERS = "\"'”’)]»"


@dataclass(frozen=True)
class NarrationTurn:
    """One synthesizable chunk of a narration beat, with its pacing.

    ``speed`` is ``None`` when the delivery's model has no speed control (eleven
    v3) — the renderer then leaves ``voice_settings["speed"]`` alone rather than
    sending a parameter the model is documented not to honor.
    """

    text: str
    gap_after_s: float = 0.0
    speed: float | None = None
    boundary: str = "sentence"


def classify_boundary(text: str) -> str:
    """Name the boundary implied by ``text``'s trailing punctuation.

    >>> classify_boundary("So that's the charge sheet.")
    'sentence'
    >>> classify_boundary('He said "no," and left,')
    'clause'
    >>> classify_boundary("and then —")
    'flowing'
    >>> classify_boundary("well…")
    'ellipsis'
    >>> classify_boundary("no punctuation here")
    'none'
    """
    tail = text.rstrip().rstrip(_TERMINAL_CLOSERS).rstrip()
    if tail.endswith("…") or tail.endswith("..."):
        return "ellipsis"
    if tail.endswith((".", "!", "?")):
        return "sentence"
    if tail.endswith((",", ";", ":")):
        return "clause"
    if tail.endswith(("—", "–", "-")):
        return "flowing"
    return "none"


def split_paragraphs(text: str) -> list[str]:
    """Split ``text`` on blank lines, collapsing runs of spaces within each."""
    parts = (
        _WS.sub(" ", p.replace("\n", " ")).strip() for p in _PARAGRAPH_SPLIT.split(text)
    )
    return [p for p in parts if p]


def split_units(text: str, *, unit: str = "sentence") -> list[list[str]]:
    """Cut ``text`` into ``unit``-sized pieces, grouped by paragraph.

    Returns a list of paragraphs, each a list of units, so a caller can keep
    turns from straddling a paragraph break (which would swallow the strongest
    pause in the beat). ``unit="beat"`` returns one paragraph of one unit.

    >>> split_units("A one. A two.\\n\\nB one.", unit="sentence")
    [['A one.', 'A two.'], ['B one.']]
    >>> split_units("Yes, really. No.", unit="clause")
    [['Yes,', 'really.', 'No.']]
    """
    if unit not in SEGMENTATION_UNITS:
        raise ValueError(f"unit must be one of {SEGMENTATION_UNITS}, got {unit!r}")
    paragraphs = split_paragraphs(text)
    if unit == "beat":
        return [[" ".join(paragraphs)]] if paragraphs else []
    if unit == "paragraph":
        return [[p] for p in paragraphs]
    out: list[list[str]] = []
    for para in paragraphs:
        sentences = [s.strip() for s in _SENTENCE_SPLIT.split(para) if s.strip()]
        if unit == "clause":
            units = [
                c.strip()
                for s in sentences
                for c in _CLAUSE_SPLIT.split(s)
                if c.strip()
            ]
        else:
            units = sentences
        if units:
            out.append(units)
    return out


def _group(
    units: list[str], *, min_turn: int, max_turn: int, rng: random.Random
) -> list[str]:
    """Join consecutive ``units`` into turns of ``min_turn..max_turn`` units."""
    turns: list[str] = []
    i = 0
    while i < len(units):
        k = rng.randint(min_turn, max_turn)
        turns.append(" ".join(units[i : i + k]))
        i += k
    return turns


def plan_turns(
    text: str,
    *,
    unit: str = "sentence",
    min_turn: int = 1,
    max_turn: int = 3,
    seed: int = 7,
    gap_s: float = 0.0,
    speed_base: float | None = 1.0,
    speed_jitter: float = 0.0,
    gap_scale_cap_s: float = 3.0,
) -> list[NarrationTurn]:
    """Plan how to speak one narration beat. Pure and deterministic in ``seed``.

    Returns ``[]`` for ``unit="beat"`` (and for empty text) — the caller's signal
    to keep the historical single-call path, byte for byte. Otherwise each
    returned :class:`NarrationTurn` is one TTS call, with the silence to append
    after it and the speed to read it at.

    ``gap_s`` is the *sentence-boundary* gap; every other boundary scales off it
    via :data:`BOUNDARIES`, capped at ``gap_scale_cap_s`` (long silences read as
    a dropout, and the engines are unstable past ~3 s). The final turn of the
    beat never gets a trailing gap — the beat boundary belongs to the renderer's
    crossfade and to the next beat's ``Narration.lead_gap_s``.

    ``speed_base=None`` plans no speed at all (eleven v3, which has no speed
    control); a float centers a per-turn jitter of ``±speed_jitter`` on it,
    scaled by the boundary's final lengthening and clamped to :data:`SPEED_RANGE`.

    >>> turns = plan_turns("One. Two. Three. Four.", min_turn=2, max_turn=2, gap_s=0.3)
    >>> [(t.text, t.gap_after_s) for t in turns]
    [('One. Two.', 0.3), ('Three. Four.', 0.0)]
    >>> plan_turns("A.\\n\\nB.", gap_s=0.2)[0].gap_after_s  # paragraph > sentence
    0.44
    """
    paragraphs = split_units(text, unit=unit)
    if unit == "beat" or not paragraphs:
        return []
    if min_turn < 1 or max_turn < min_turn:
        raise ValueError("require 1 <= min_turn <= max_turn")
    rng = random.Random(seed * 17 + 3)
    grouped: list[tuple[str, bool]] = []  # (turn text, is last of its paragraph)
    for para in paragraphs:
        turns = _group(para, min_turn=min_turn, max_turn=max_turn, rng=rng)
        grouped.extend((t, j == len(turns) - 1) for j, t in enumerate(turns))

    jitter_rng = random.Random(seed * 31 + 1)
    out: list[NarrationTurn] = []
    for i, (turn_text, ends_paragraph) in enumerate(grouped):
        last = i == len(grouped) - 1
        name = (
            "paragraph"
            if (ends_paragraph and not last)
            else classify_boundary(turn_text)
        )
        boundary = BOUNDARIES[name]
        speed = None
        if speed_base is not None:
            jittered = speed_base + jitter_rng.uniform(-speed_jitter, speed_jitter)
            speed = round(
                min(
                    max(jittered * boundary.speed_scale, SPEED_RANGE[0]), SPEED_RANGE[1]
                ),
                3,
            )
        gap = (
            0.0 if last else min(round(gap_s * boundary.gap_scale, 3), gap_scale_cap_s)
        )
        out.append(
            NarrationTurn(turn_text, gap_after_s=gap, speed=speed, boundary=name)
        )
    return out


def planned_gap_total_s(turns: list[NarrationTurn]) -> float:
    """Total silence a plan inserts inside the beat (for reporting / tests).

    >>> planned_gap_total_s(plan_turns("A. B. C.", min_turn=1, max_turn=1, gap_s=0.3))
    0.6
    """
    return round(sum(t.gap_after_s for t in turns), 3)
