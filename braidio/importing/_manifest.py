"""The import manifest — one shape three finished productions normalize into.

The three commentary videos this package exists to bring forward each recorded
their picture track a different way: hand-authored absolute seconds in a python
module, a derived ``<stem>-panels.json``, and — for the hardest — no driver at
all, only the frames it left behind. The archaeology that normalized them is
*not* re-done here. It produced one JSON shape, and this module is that shape
as a validated model, so the importer has a single target and each production
keeps exactly one entry point (the extractor that writes its manifest).

Every model is ``extra="forbid"``: an unrecognised key means the extractor and
the importer have drifted, and finding that out at validation is the whole
point of having a schema rather than passing dicts around.

Two fields carry decisions rather than data, and both are commented where they
are declared:

- ``StillRecord.title`` is TASL's **T** — the work's own title, what a credit
  reads — and is **never** the editorial ``subject``. It is optional because an
  untitled still credits without one rather than failing; the importer reports
  the count so that silence is loud.
- ``PanelRecord.move`` is what the *source* recorded, not what gets written.
  See :mod:`braidio.importing._writer` — every imported panel is ``push_in``.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field

#: Rights positions a production may declare. ``private`` is the only one the
#: three finished productions take, each for a reasoned audio-rights finding
#: recorded in its own README. Nothing here may promote a cut to publishable.
RIGHTS_POSITIONS: tuple[str, ...] = ("private", "unlisted", "public")


class RightsPosition(BaseModel):
    """A production's rights finding, argued rather than assumed (plan §10)."""

    model_config = {"frozen": True, "extra": "forbid"}

    position: str = Field(..., description="private | unlisted | public.")
    why: str = Field(..., description="The argument, in the production's own words.")
    measured: str = Field(
        "", description="What was counted — durations, licences, clip rights."
    )


class AudioRef(BaseModel):
    """The episode audio a cut was made against.

    A production may have **several**: Two Silences renders one mix per cut, so
    'the episode audio' is per-cut, not per-project. ``padded_*`` is Hamilton's
    credits-padded variant (its credits roll was appended as a burns panel, so
    the film is longer than the mix).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    path: str = Field(..., description="Relative to the manifest's source_dir.")
    duration_s: float = Field(..., ge=0.0)
    note: Optional[str] = None
    padded_path: Optional[str] = None
    padded_duration_s: Optional[float] = None


class StillRecord(BaseModel):
    """One image with its rights and its editorial label — the still/v1 input."""

    model_config = {"frozen": True, "extra": "forbid"}

    key: str
    path: str = Field(..., description="Relative to source_dir; never absolute.")
    width: Optional[int] = None
    height: Optional[int] = None
    # TASL's T. Not the subject: a credit roll reading the editorial caption
    # credits the wrong thing, and nothing downstream would notice.
    title: Optional[str] = None
    # --- rights: illustration.RIGHTS_FIELDS, by name ---
    license: Optional[str] = None
    license_url: Optional[str] = None
    attribution: Optional[str] = Field(
        None,
        description=(
            "The provider's string, kept for the record. NEVER a credit line — "
            "for a minority of Wikimedia hits it is a bare author with no "
            "licence in it, and three used Two Silences stills are exactly that."
        ),
    )
    source_page_url: Optional[str] = None
    author: Optional[str] = None
    author_url: Optional[str] = None
    cacheable: Optional[bool] = None
    # --- the editorial decision ---
    labelled: bool
    subject: Optional[str] = None
    about: Optional[str] = None
    # FRACTIONAL (left, top, right, bottom) — the source convention, witnessed
    # in both productions that crop (actually-romantic/video.py's CROPS, "l, t,
    # r, b = CROPS[slot]"; Hamilton's stills.py "a fractional (left, top,
    # right, bottom) box"). braidio's RectV1 is (x, y, w, h), so the importer
    # CONVERTS — see _writer._rect_from_ltrb. Writing this list through as a
    # Rect would mis-frame every cropped still, and the unit-square validator
    # catches only the one whose left+right happens to exceed 1.
    crop: Optional[tuple[float, float, float, float]] = None
    note: Optional[str] = None


class PanelRecord(BaseModel):
    """A still over a span of one cut's episode audio."""

    model_config = {"frozen": True, "extra": "forbid"}

    still_key: str
    start: float = Field(..., ge=0.0)
    end: float = Field(..., gt=0.0)
    # What the SOURCE recorded ('push_in' or 'auto'). The importer does not
    # write this value — see _writer.IMPORTED_MOVE and braidio#72.
    move: str
    zoom: float = Field(..., gt=0.0)
    # An explicit RectV1 mapping — ``{"x":…, "y":…, "w":…, "h":…}`` — and NOT
    # the ``crop`` field's (left, top, right, bottom) 4-tuple. None of the
    # three productions authors a focus, so there is no source convention to
    # inherit and guessing one would be inventing geometry.
    focus: Optional[dict[str, float]] = None
    seed: int = 0
    beat_id: Optional[str] = Field(
        None, description="'beat:N' — the timeline member index, or None."
    )
    order: int = Field(..., ge=0)


class LabelRecord(BaseModel):
    """A timed editorial card that is not per-still (title, context, tag)."""

    model_config = {"frozen": True, "extra": "forbid"}

    kind: str
    start: float = Field(..., ge=0.0)
    end: float = Field(..., gt=0.0)
    lines: tuple[str, ...] = ()
    headline: Optional[str] = None
    weight: int = Field(2, ge=1)
    slot: Optional[str] = None


class CutRecord(BaseModel):
    """One finished rendering, with the panels and cards it was made from."""

    model_config = {"frozen": True, "extra": "forbid"}

    label: str
    artifact: str = Field(..., description="The DELIVERED mp4, relative to source_dir.")
    motion_artifact: Optional[str] = Field(
        None, description="The text-free motion pass, when one survives."
    )
    audio: AudioRef
    duration_s: float = Field(..., ge=0.0)
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    profile: str = "personal"
    captions: Optional[str] = Field(None, description="The shipped .srt sidecar.")
    settings: dict[str, Any] = Field(default_factory=dict)
    published: Optional[dict[str, Any]] = None
    panels: tuple[PanelRecord, ...] = ()
    labels: tuple[LabelRecord, ...] = ()


class ProductionManifest(BaseModel):
    """A finished production, normalized — the importer's only input shape."""

    model_config = {"frozen": True, "extra": "forbid"}

    production: str = Field(..., description="Slug; the import's identity namespace.")
    title: str
    source_dir: str = Field(..., description="Relative to the caller's source root.")
    rights: RightsPosition
    episode_audio: AudioRef = Field(
        ..., description="The production's canonical mix (a cut may use another)."
    )
    stills: tuple[StillRecord, ...]
    cuts: tuple[CutRecord, ...]
    gaps: tuple[str, ...] = Field(
        default_factory=tuple,
        description="What the archaeology could NOT settle. Carried, never hidden.",
    )
    # Leading underscore: evidence from the extraction, kept with the data.
    verification: dict[str, Any] = Field(default_factory=dict, alias="_verification")

    @property
    def still_keys(self) -> frozenset[str]:
        return frozenset(s.key for s in self.stills)


def load_manifest(path) -> ProductionManifest:
    """Read and validate a manifest JSON file.

    >>> import json, tempfile, pathlib
    >>> doc = dict(
    ...     production="demo", title="Demo", source_dir="demo",
    ...     rights=dict(position="private", why="test"),
    ...     episode_audio=dict(path="ep.mp3", duration_s=1.0),
    ...     stills=[dict(key="a", path="a.jpg", labelled=False)],
    ...     cuts=[],
    ... )
    >>> with tempfile.TemporaryDirectory() as d:
    ...     p = pathlib.Path(d, "m.json"); _ = p.write_text(json.dumps(doc))
    ...     m = load_manifest(p)
    >>> m.production, len(m.stills), m.rights.position
    ('demo', 1, 'private')
    """
    import json
    from pathlib import Path

    return ProductionManifest.model_validate(
        json.loads(Path(path).read_text(encoding="utf-8"))
    )
