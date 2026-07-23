"""Render profiles: enforce personal-vs-published rights as data.

Rights are encoded on the beats (``SegmentBeat.rights``, and — mechanically —
the presence of forbidden verbatim text in narration) and a **render profile**
filters the script into the beats that may actually render:

- ``PERSONAL``  — include everything, including owned/copyrighted segment audio.
- ``PUBLISHED`` — exclude any non-publishable segment audio and any beat
  carrying forbidden verbatim text; keep original narration, publishable
  segments, and short transformative substitutes.

The rule is enforced *mechanically*: :func:`plan_production` routes beats by
their ``rights`` flag, and :func:`find_verbatim_text` / :func:`content_violations`
scan the resulting published beats against a **caller-supplied** set of
forbidden texts (via :class:`RightsPolicy`) — so a leak is a test failure, not a
judgment call. braidio owns the scanner + profile filter; the consumer injects
*what* is forbidden (e.g. Hamilton injects the song's lyric lines).

Not legal advice.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Iterable

from braidio.script import Dialogue, Narration, Script, SegmentBeat

# Segment ``rights`` values safe to render in the published cut.
PUBLISHABLE_CLIP_RIGHTS: frozenset[str] = frozenset({"public-domain"})

_WORD_RE = re.compile(r"\w+")
_MARKUP_RE = re.compile(r"<[^>]*>|\[[^\]]*\]")  # SSML <break…> and v3 [audio tags]


def _strip_markup(text: str) -> str:
    """Drop SSML/audio-tag markup so delivery markup doesn't affect the scan."""
    return _MARKUP_RE.sub(" ", text)


class Profile(str, Enum):
    """Which projection of the production we render."""

    PERSONAL = "personal"
    PUBLISHED = "published"


@dataclass(frozen=True)
class RightsPolicy:
    """Injected rights configuration for the published profile.

    ``forbidden_texts`` yields the strings that must not appear verbatim in
    published narration (e.g. copyrighted lyric lines). ``publishable_clip_rights``
    is the set of segment ``rights`` values allowed in the published cut.
    """

    forbidden_texts: Callable[[Script], Iterable[str]] = lambda _s: ()
    publishable_clip_rights: frozenset[str] = PUBLISHABLE_CLIP_RIGHTS


@dataclass(frozen=True)
class PlannedBeat:
    """A beat resolved for a profile — what the renderer actually plays.

    ``kind`` is ``"narration"`` (synthesize ``content``) or ``"clip"`` (resolve
    ``content`` as a segment reference and cut audio). ``from_index`` points at
    the source beat; ``note`` records any substitution/drop reasoning.
    """

    kind: str  # "narration" | "clip" | "dialogue"
    content: str  # narration/dialogue text (for scanning); clip = the reference
    from_index: int
    note: str = ""
    turns: tuple | None = None  # (role, text) pairs, for dialogue beats


@dataclass
class RenderPlan:
    profile: Profile
    beats: list[PlannedBeat] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    substituted: list[str] = field(default_factory=list)


def segment_is_publishable(
    beat: SegmentBeat, publishable: frozenset[str] = PUBLISHABLE_CLIP_RIGHTS
) -> bool:
    return beat.rights in publishable


def plan_production(
    script: Script,
    profile: Profile,
    *,
    publishable_clip_rights: frozenset[str] = PUBLISHABLE_CLIP_RIGHTS,
) -> RenderPlan:
    """Filter ``script`` into the beats renderable under ``profile``."""
    plan = RenderPlan(profile=profile)
    for i, beat in enumerate(script.beats):
        if isinstance(beat, SegmentBeat):
            if profile is Profile.PERSONAL or segment_is_publishable(
                beat, publishable_clip_rights
            ):
                plan.beats.append(PlannedBeat("clip", beat.reference, i))
            elif beat.published_substitute:
                plan.beats.append(
                    PlannedBeat("narration", beat.published_substitute, i, "segment→substitute")
                )
                plan.substituted.append(beat.label or beat.reference[:40])
            else:
                plan.dropped.append(beat.label or beat.reference[:40])
        elif isinstance(beat, Narration):
            if profile is Profile.PUBLISHED and beat.published_text is not None:
                plan.beats.append(
                    PlannedBeat("narration", beat.published_text, i, "narration→published_text")
                )
                plan.substituted.append(f"narration[{i}]")
            else:
                plan.beats.append(PlannedBeat("narration", beat.text, i))
        elif isinstance(beat, Dialogue):
            # our commentary → always included; content is the joined text so the
            # published verbatim-scan can see it; turns carry the render input.
            plan.beats.append(
                PlannedBeat(
                    "dialogue",
                    " ".join(text for _role, text in beat.turns),
                    i,
                    turns=tuple(beat.turns),
                )
            )
        else:  # pragma: no cover - exhaustive
            raise TypeError(f"unknown beat type {type(beat).__name__}")
    return plan


# --- mechanical verbatim-text detection --------------------------------------


def _word_ngrams(text: str, n: int) -> set[tuple[str, ...]]:
    words = [w.lower() for w in _WORD_RE.findall(_strip_markup(text))]
    return {tuple(words[i : i + n]) for i in range(len(words) - n + 1)} if len(words) >= n else set()


def find_verbatim_text(
    text: str, forbidden: Iterable[str], *, min_words: int = 5
) -> list[str]:
    """Forbidden lines that appear (near-)verbatim in ``text``.

    A line counts as leaked if ``text`` shares a run of ``min_words`` consecutive
    words with it (case-insensitive, word-level). Single words and short common
    phrases don't trip it — only substantial verbatim quoting.
    """
    text_ngrams = _word_ngrams(text, min_words)
    if not text_ngrams:
        return []
    hits: list[str] = []
    for line in forbidden:
        line_ngrams = _word_ngrams(line, min_words)
        if line_ngrams and (line_ngrams & text_ngrams):
            hits.append(line)
    return hits


def content_violations(
    plan: RenderPlan, forbidden: Iterable[str], *, min_words: int = 5
) -> list[str]:
    """Rights violations in a *published* plan (empty list = clean).

    Fails if any planned beat plays non-publishable segment audio, or any
    narration beat contains forbidden verbatim text.
    """
    if plan.profile is not Profile.PUBLISHED:
        return []
    forbidden = list(forbidden)
    violations: list[str] = []
    for b in plan.beats:
        if b.kind == "clip":
            violations.append(f"beat {b.from_index}: segment audio present in published cut")
        elif b.kind in ("narration", "dialogue"):
            leaks = find_verbatim_text(b.content, forbidden, min_words=min_words)
            if leaks:
                violations.append(
                    f"beat {b.from_index}: verbatim forbidden text in {b.kind} → {leaks[0]!r}"
                )
    return violations
