"""Composition model — the ordered beats a render walks.

A :class:`Script` is an ordered list of beats, each either a :class:`Narration`
(spoken, synthesized) or a :class:`SegmentBeat` (a *reference* to a span of
source media to resolve and weave in). This is the generic, media-agnostic
projection a renderer consumes; how a reference maps to audio is a
:class:`braidio.sources.SegmentSource` concern, and what the beats are backed by
(lyrics, a graph, hand-authoring) is the consumer's concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Union


@dataclass(frozen=True)
class Narration:
    """A spoken narration beat (authored, synthesized by TTS).

    ``published_text`` is an optional rights-safe rewrite the published profile
    uses when the default ``text`` quotes forbidden (e.g. copyrighted) content;
    leave it ``None`` when the narration is already clean.
    """

    text: str
    style: str | None = None  # optional delivery hint (future use)
    published_text: str | None = None


@dataclass(frozen=True)
class SegmentBeat:
    """A span of source media to weave in, addressed by an opaque ``reference``.

    The renderer resolves ``reference`` → ``[start,end)`` via a
    :class:`~braidio.sources.SegmentSource` and cuts it. ``rights`` (e.g.
    ``owned-local`` / ``copyrighted`` / ``public-domain``) drives the render
    profile; ``published_substitute`` is a transformative narration the
    published profile swaps in when the segment's audio can't be used.
    """

    reference: str
    label: str = ""
    rights: str = "owned-local"
    published_substitute: str | None = None


Beat = Union[Narration, SegmentBeat]


@dataclass(frozen=True)
class Script:
    """An ordered production script."""

    title: str
    id_slug: str  # stable id for this production (e.g. "01"); no media semantics
    beats: list[Beat] = field(default_factory=list)


def narration_segments(script: Script) -> list[str]:
    """All narration (default text) of a script, as sentence-level segments."""
    from braidio.multivoice import split_segments

    segs: list[str] = []
    for beat in script.beats:
        if isinstance(beat, Narration):
            segs.extend(split_segments(beat.text))
    return segs
