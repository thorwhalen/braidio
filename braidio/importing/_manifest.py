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
  See :mod:`braidio.importing._writer` — every imported panel is ``push_in`` —
  unless the manifest declares ``moves="rendered"``: a film framed through
  ``burns.resolve_move`` whose moves are the delivered pixels, written as is.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

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


class FootageRecord(BaseModel):
    """A recorded video panels may play as straight cuts (a screen recording).

    Declared once, like a still, and named by ``key`` from each panel that
    plays a stretch of it (:class:`PanelFootage`).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    key: str
    path: str = Field(..., description="Relative to source_dir; never absolute.")
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[int] = None
    duration_s: Optional[float] = Field(None, ge=0.0)
    note: Optional[str] = None


class PanelFootage(BaseModel):
    """Which footage a panel plays, from where. It plays for the panel's span."""

    model_config = {"frozen": True, "extra": "forbid"}

    key: str
    in_s: float = Field(0.0, ge=0.0)


class PanelRecord(BaseModel):
    """A still over a span of one cut's episode audio — or footage, with the
    still as its poster."""

    model_config = {"frozen": True, "extra": "forbid"}

    still_key: str
    start: float = Field(..., ge=0.0)
    end: float = Field(..., gt=0.0)
    # Under ``moves="source"`` (the default): what the SOURCE recorded
    # ('push_in' or 'auto'), which the importer does not write — see
    # _writer.IMPORTED_MOVE and braidio#72. Under ``moves="rendered"``: the
    # burns move the delivered cut was actually rendered with, written as is.
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
    # Set: the panel plays this footage as a straight cut and its move is not
    # rendered (the still stays its poster). None: a still under a move.
    footage: Optional[PanelFootage] = None


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


class TakeRecord(BaseModel):
    """The audio a listener actually hears for one beat — the recording.

    A *take* is the replaceable unit. ``source`` is why the field exists at
    all: an imported take is ``"tts"`` (a machine said it), and the only other
    value is ``"upload"`` (a person recorded it). Without the distinction a
    replacement is indistinguishable from the thing it replaced, and "put the
    robot back" is not a question anything can answer.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    path: str = Field(..., description="Relative to source_dir; never absolute.")
    duration_s: Optional[float] = Field(None, ge=0.0)
    voice_id: Optional[str] = None
    model_id: Optional[str] = None
    source: str = Field(
        "tts",
        description="'tts' | 'upload'. Every imported take is 'tts'.",
    )


class BeatRecord(BaseModel):
    """One member of a rendered episode — the unit a panel is cut against.

    This is the *render's own* beat, read off the persisted timeline
    (``TimelineBreakdown.to_dict()``), not the authored script's. The two
    agree in order but not necessarily in count: a rights profile can drop a
    beat before it is rendered, and it is the rendered sequence the panels and
    cards were timed against.

    ``text`` is the **full** narration, recovered from the authored script.
    The timeline's own ``label`` is a 48-character snippet, which is enough to
    *match* a script beat to a rendered one and not enough to edit. A beat
    whose script did not survive carries ``text=None`` and is still
    addressable and playable — just not re-synthesizable without retyping it,
    which is the honest state rather than a guess.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    index: int = Field(..., ge=0, description="Position in the rendered episode.")
    kind: str = Field(
        ...,
        description=(
            "'narration' (or a delivery style standing in for it), 'clip', "
            "'archive', 'scene-break', 'sting', 'dialogue'."
        ),
    )
    label: str = Field("", description="The timeline's snippet — display only.")
    text: Optional[str] = Field(
        None, description="Full narration text, when the script survives."
    )
    start: float = Field(..., ge=0.0, description="Start in the rendered mix.")
    end: float = Field(..., ge=0.0)
    # The clip's span in its SOURCE media, which is a different timebase from
    # (start, end) — those are positions in the mix. A clip carries both; a
    # narration beat carries only the latter.
    source: Optional[tuple[float, float]] = None
    marker: Optional[str] = Field(
        None, description="scene-break only: 'sting' | 'none'."
    )
    take: Optional[TakeRecord] = Field(
        None, description="The rendered audio for this beat, when it survives."
    )


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
    # Additive (default empty / None), so a manifest written before the
    # narration layer existed still validates and simply imports a picture
    # track with an undecomposed mix — which is exactly what it records.
    beats: tuple[BeatRecord, ...] = Field(
        default_factory=tuple,
        description="The rendered episode's members, in play order.",
    )
    timeline: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "The render's own TimelineBreakdown.to_dict(), carried verbatim "
            "onto the episode node. `beats` is this file's normalized view of "
            "it; this is the record the renderer wrote."
        ),
    )


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
    footage: tuple[FootageRecord, ...] = Field(
        default_factory=tuple,
        description="Recorded video that footage panels cut from (see PanelFootage).",
    )
    cuts: tuple[CutRecord, ...]
    gaps: tuple[str, ...] = Field(
        default_factory=tuple,
        description="What the archaeology could NOT settle. Carried, never hidden.",
    )
    moves: Literal["source", "rendered"] = Field(
        "source",
        description=(
            "What the panels' `move` fields mean. 'source' (the default): the "
            "source's own vocabulary, whose alternation was never realised, so "
            "every panel is imported as push_in (braidio#72). 'rendered': each "
            "`move` is the burns move the delivered cut was rendered with — a "
            "producer that framed its film through burns.resolve_move (walkthru's "
            "reelee target does) — so it is written as recorded."
        ),
    )
    # Leading underscore: evidence from the extraction, kept with the data.
    verification: dict[str, Any] = Field(default_factory=dict, alias="_verification")

    @property
    def still_keys(self) -> frozenset[str]:
        return frozenset(s.key for s in self.stills)

    @property
    def footage_keys(self) -> frozenset[str]:
        return frozenset(f.key for f in self.footage)


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
