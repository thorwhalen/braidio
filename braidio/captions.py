"""Subtitles for a rendered production, built from the script it was rendered from.

A braidio render is one of the rare cases where the caption track needs no speech
recognition: the narration text is *authored*, and
:func:`~braidio.render.render_production` will hand back a
:class:`~braidio.timeline.TimelineBreakdown` saying exactly when each beat plays.
Transcribing the mix back into text would pay an ASR pass to recover something
that was never lost -- and do it worse (a measured pass on braidio's own output
turned "purse sets up hurts" into "Perse sets up herts").

So :func:`captions_for` joins the two: beat text from the ``Script``, beat timing
from the ``TimelineBreakdown``. Narration and dialogue beats are split into
sentence-sized cues timed *within* their beat in proportion to length; a
``SegmentBeat`` becomes one cue carrying its reference, marked as lyric/quote.

Pure and dependency-free -- part of the functional core, importable with nothing
installed beyond braidio itself.

Examples:
    >>> from braidio.script import Narration, Script
    >>> from braidio.timeline import build_timeline
    >>> script = Script(title="t", id_slug="01", beats=[Narration("One. Two.")])
    >>> tl = build_timeline(kinds=["narration"], durations=[4.0])
    >>> print(captions_for(script, tl))  # doctest: +ELLIPSIS
    1
    00:00:00,000 --> 00:00:02,000
    One.
    <BLANKLINE>
    2
    00:00:02,000 --> 00:00:04,000
    Two.
    <BLANKLINE>
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from braidio.script import Dialogue, Narration, SegmentBeat

__all__ = ["Cue", "captions_for", "cues_for", "format_srt"]

#: Sentence boundary: end punctuation followed by whitespace. The text is ours
#: (authored, not scraped), so a full NLP splitter would be ceremony.
_SENTENCE = re.compile(r"(?<=[.?!])\s+")

#: Wraps a segment beat's reference, so a lyric/quote reads as one in the player.
_QUOTE_MARK = "♪"  # ♪


@dataclass(frozen=True)
class Cue:
    """One subtitle: ``[start_s, end_s)`` and the text shown."""

    start_s: float
    end_s: float
    text: str

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s


def _sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENTENCE.split(text.strip())) if s]


def _beat_text(beat) -> tuple[str, bool]:
    """``(text, is_quote)`` for a beat, or ``("", False)`` to skip it."""
    if isinstance(beat, SegmentBeat):
        return beat.reference.strip(), True
    if isinstance(beat, Narration):
        return beat.text, False
    if isinstance(beat, Dialogue):
        # One cue stream; the speaker labels are the useful part on screen.
        return " ".join(f"{role}: {text}" for role, text in beat.turns), False
    return "", False


def cues_for(script, timeline, *, max_chars: int = 0) -> list[Cue]:
    """Subtitle cues for ``script`` as laid out by ``timeline``.

    Beats are matched by index, so a timeline built from the same script lines up
    even when some beats were dropped by a rights profile (a dropped beat simply
    has no span and contributes no cue).

    Cues never overlap. That matters because the weave *crossfades* consecutive
    beats, so a beat's ``start`` sits slightly before the previous beat's end;
    left alone that produces subtitles that fight each other. Each cue is clamped
    to begin where the previous one finished.

    Args:
        script: the :class:`~braidio.script.Script` that was rendered.
        timeline: the :class:`~braidio.timeline.TimelineBreakdown` from
            ``render_production(..., return_timeline=True)``.
        max_chars: if > 0, split sentences longer than this at whitespace, so no
            single cue overflows a player's two lines. 0 leaves sentences whole.

    Returns:
        Cues in playback order.
    """
    spans = {b.index: b for b in timeline.beats}
    raw: list[Cue] = []

    for i, beat in enumerate(script.beats):
        span = spans.get(i)
        if span is None:
            continue
        text, is_quote = _beat_text(beat)
        if not text:
            continue

        pieces = [text] if is_quote else _sentences(text)
        if max_chars > 0:
            pieces = [p for piece in pieces for p in _wrap(piece, max_chars)]
        if is_quote:
            pieces = [f"{_QUOTE_MARK} {p} {_QUOTE_MARK}" for p in pieces]

        total = sum(len(p) for p in pieces) or 1
        t = span.start
        for piece in pieces:
            share = span.duration * len(piece) / total
            raw.append(Cue(t, t + share, piece))
            t += share

    raw.sort(key=lambda c: c.start_s)
    out: list[Cue] = []
    for cue in raw:
        start = max(cue.start_s, out[-1].end_s if out else 0.0)
        if cue.end_s > start:
            out.append(Cue(start, cue.end_s, cue.text))
    return out


def _wrap(text: str, max_chars: int) -> list[str]:
    """Split ``text`` into <= ``max_chars`` chunks at whitespace."""
    words, line, out = text.split(), "", []
    for w in words:
        candidate = f"{line} {w}".strip()
        if line and len(candidate) > max_chars:
            out.append(line)
            line = w
        else:
            line = candidate
    if line:
        out.append(line)
    return out or [text]


def _timestamp(t: float) -> str:
    """SRT timestamp ``HH:MM:SS,mmm`` (comma, not period -- that is the format)."""
    t = max(t, 0.0)
    hours, rem = divmod(t, 3600)
    minutes, seconds = divmod(rem, 60)
    whole = int(seconds)
    return f"{int(hours):02d}:{int(minutes):02d}:{whole:02d},{round((seconds - whole) * 1000):03d}"


def format_srt(cues) -> str:
    """Render ``cues`` as an SRT document."""
    blocks = [
        f"{n}\n{_timestamp(c.start_s)} --> {_timestamp(c.end_s)}\n{c.text}\n"
        for n, c in enumerate(cues, 1)
    ]
    return "\n".join(blocks)


def captions_for(script, timeline, *, max_chars: int = 0) -> str:
    """The SRT document for ``script`` as laid out by ``timeline``."""
    return format_srt(cues_for(script, timeline, max_chars=max_chars))
