"""Style audit — flag the recycled rhetorical tics in commentary text.

The companion, in code, to ``misc/docs/style/anti-platitude-checklist.md``: scan
authored commentary for the empty structural platitudes a writing model falls
back on, so a production can self-check (and measure) instead of eyeballing.

    from braidio.style import audit_platitudes, platitude_rate
    findings = audit_platitudes(commentary_text)   # [{pattern, match, start}, …]
    rate = platitude_rate(commentary_text)          # flagged hits per 1000 words

Not every match is a crime — the guide says these moves are fine *sparingly*; the
value is the RATE and which patterns dominate. Chiasmus ("the X that did Y is the
X that does Z") isn't reliably regex-detectable and is intentionally omitted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: name → compiled pattern for the detectable overused moves.
PLATITUDE_PATTERNS: dict[str, re.Pattern] = {
    "director-cue": re.compile(
        r"\b(?:listen to|notice|watch|catch)\s+(?:how|what|the)\b", re.I
    ),
    "heres-the": re.compile(r"\bhere'?s the\b", re.I),
    "reduction": re.compile(
        r"\b(?:that'?s the whole|the whole \w+ in|in "
        r"(?:two|three|four|five|six|seven|eight|nine|ten|\d+) words)\b",
        re.I,
    ),
    "negation-just": re.compile(r"\bisn'?t just\b", re.I),
    "machinery-naming": re.compile(
        r"\bthe (?:turn|tell|button|trick|move|thesis)\b", re.I
    ),
}


@dataclass(frozen=True)
class Finding:
    """One flagged platitude."""

    pattern: str
    match: str
    start: int


def audit_platitudes(text: str) -> list[Finding]:
    """Return every :class:`Finding` in ``text``, in document order."""
    found: list[Finding] = []
    for name, rx in PLATITUDE_PATTERNS.items():
        for m in rx.finditer(text):
            found.append(Finding(name, m.group(0), m.start()))
    found.sort(key=lambda f: f.start)
    return found


def platitude_rate(text: str, *, per: int = 1000) -> float:
    """Flagged hits per ``per`` words (default 1000). 0.0 for empty text."""
    words = len(text.split())
    if not words:
        return 0.0
    return round(per * len(audit_platitudes(text)) / words, 2)
