"""Text preparation for scripts — clean OCR'd source, tidy authored lines.

Small, reusable helpers a commentary production reaches for repeatedly:

- :func:`clean_ocr` — normalize text extracted from PDFs/scans (ligatures,
  soft-hyphens, doubled hyphens, whitespace) so a TTS voice reads it cleanly.
- :func:`strip_speaker_labels` — drop a leaked ``"Host: "`` / ``"Chris: "``
  prefix that a writing model sometimes prepends and that would otherwise be
  read aloud.

These were duplicated in ad-hoc rendering scripts; they belong here so any
consumer (Hamilton and the next app) shares one implementation.
"""

from __future__ import annotations

import re

#: Latin ligatures that OCR emits as single code points.
LIGATURES: dict[str, str] = {
    "ﬁ": "fi", "ﬂ": "fl", "ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "ft", "ﬆ": "st",
}
_SOFT_HYPHEN = "­"
_SPEAKER_LABEL = re.compile(r"^\s*(?:[A-Z][a-z]+|Host|Narrator|Presenter|Speaker)\s*:\s+")
_WS = re.compile(r"\s+")


def clean_ocr(text: str, *, collapse_whitespace: bool = True) -> str:
    """Normalize OCR/PDF-extracted text for clean narration.

    Expands ligatures, removes soft-hyphens (used at scan line-breaks), turns a
    doubled hyphen ``--`` into an em-dash (so TTS phrases it as a pause), and
    (by default) collapses runs of whitespace to single spaces.
    """
    for a, b in LIGATURES.items():
        text = text.replace(a, b)
    text = text.replace(_SOFT_HYPHEN, "")
    text = text.replace("--", "—")
    if collapse_whitespace:
        text = _WS.sub(" ", text).strip()
    return text


def strip_speaker_labels(text: str) -> str:
    """Remove a leading speaker-label prefix (e.g. ``"Chris: "``) if present.

    Only strips a single leading ``Word:`` / ``Host:`` style label so it isn't
    read aloud; leaves colons that are part of the sentence untouched.
    """
    return _SPEAKER_LABEL.sub("", text, count=1)
