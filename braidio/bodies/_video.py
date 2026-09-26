"""The picture-track body schemas — a commentary video as graph data.

Four bodies turn "this still, for this interval, with this motion" from three
arguments to one render call into persisted, addressable, provenanced
annotations (the commentary-studio plan, §3):

- ``still/v1`` — an image, its rights and its editorial label, in **one**
  record. Replaces the three incompatible sidecar manifests the finished
  productions carried.
- ``video-panel/v1`` — a still shown over an interval of the episode, with an
  **authored** camera move. The interval lives on the annotation's
  ``reference`` (a :class:`lacing.MediaRef` on the episode audio), so "which
  panel covers *t*?" is an Allen-relation query. This is the thing a user
  edits.
- ``video-cut/v1`` — a rendered video with provenance back to the panels and
  the audio it was cut against. "A version of an actual rendering."
- ``label-track/v1`` — the timed editorial cards that are not per-still (title,
  context, recording tag), pinned to an interval the same way a panel is.

Three field-level decisions here are the point, not details; each was a
measured defect in a real production:

- **``still.labelled`` is explicit, never inferred.** ``labelled=True`` needs a
  ``subject``; ``labelled=False`` is tituli's ``UNLABELLED`` — "this picture
  deliberately names nobody". A body that states no decision fails validation,
  because an unlabelled still beside a labelled one is an implicit claim (a
  photograph of a genuine concert that is *not* the concert under discussion
  is honest only while it says so on screen).
- **The seven rights fields are named exactly as ``illustration.RIGHTS_FIELDS``
  names them**, so no consumer needs a rename table. And the credit line is
  **composed from the parts** (:func:`credit_line`), never the provider's
  ``attribution`` string trusted whole — that string comes back as a bare
  author with no licence for a minority of Wikimedia hits.
- **``video_panel.still_id`` is the still's *annotation* id, not its artifact
  id.** Changing which still is shown and changing the still's bytes are two
  different edits. Related: ``lacing.annotation_value_digest`` never covers
  bytes, so re-pointing an artifact record in place stales nothing and ships
  the wrong picture silently. New bytes ⇒ a new artifact id ⇒ a new still (or
  a patched one) ⇒ the panel derives from it and reads stale.

Registered with lacing on import, like the other two body modules.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from lacing.schema import register_body_schema

STILL_V1 = "annot://schema/still/v1"
VIDEO_PANEL_V1 = "annot://schema/video-panel/v1"
VIDEO_CUT_V1 = "annot://schema/video-cut/v1"
LABEL_TRACK_V1 = "annot://schema/label-track/v1"

#: The camera-move vocabulary a panel's ``move`` is drawn from. **Owned by
#: burns** (``burns.MOVES``, plan §4 — authored geometry is a camera, and a
#: camera is burns'); this copy is what the body validates against so a typo
#: fails at authoring time rather than five minutes into a render. Keep it
#: byte-equal to burns'; ``tests/test_video_bodies.py`` pins the equality when
#: burns ships the name.
MOVES: tuple[str, ...] = (
    "push_in",
    "pull_out",
    "drift_left",
    "drift_right",
    "drift_up",
    "drift_down",
    "hold",
    "auto",
)
DEFAULT_MOVE = "auto"
DEFAULT_ZOOM = 1.18

CUT_STAGES: tuple[str, ...] = ("motion", "delivered")
"""``motion`` is the frames alone (the expensive pass); ``delivered`` is the
motion cut with labels, captions and credits composited (the cheap pass)."""

CUT_PROFILES: tuple[str, ...] = ("personal", "published")

PanelRole = Literal["literal", "contextual", "decorative"]
#: What a placement claims about its picture, strongest first.
PANEL_ROLES: tuple[str, ...] = ("literal", "contextual", "decorative")
LABEL_KINDS: tuple[str, ...] = ("title", "context", "tag", "note")

#: The rights record — **exactly** ``illustration.RIGHTS_FIELDS``, by name.
RIGHTS_FIELDS: tuple[str, ...] = (
    "license",
    "license_url",
    "attribution",
    "source_page_url",
    "author",
    "author_url",
    "cacheable",
)


class RectV1(BaseModel):
    """A normalized ``(x, y, w, h)`` region of an image, top-left origin.

    The same convention (and the same key names) as ``burns.Rect`` and the
    ``rect`` entries in ``BurnsPath.to_dict()``, so a crop or a focus box
    crosses into burns without a rename.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    x: float = Field(..., ge=0.0, le=1.0)
    y: float = Field(..., ge=0.0, le=1.0)
    w: float = Field(..., gt=0.0, le=1.0)
    h: float = Field(..., gt=0.0, le=1.0)

    @model_validator(mode="after")
    def _inside_the_image(self) -> "RectV1":
        if self.x + self.w > 1.0 + 1e-9 or self.y + self.h > 1.0 + 1e-9:
            raise ValueError(
                f"RectV1 must lie inside the unit square, got "
                f"x+w={self.x + self.w:.4f}, y+h={self.y + self.h:.4f}"
            )
        return self


class FootageRefV1(BaseModel):
    """Recorded video a panel plays as a straight cut, instead of a moved still.

    The media fields follow a still's (``artifact_id`` first, ``url`` as the
    fallback), so the file is found by content wherever the project lives.
    ``in_s`` is where in the footage the panel's span starts; the panel's own
    interval says how much of it plays.
    """

    model_config = {"frozen": True, "extra": "forbid"}

    artifact_id: str = Field(..., description="Content id of the video artifact.")
    url: Optional[str] = Field(
        None, description="Where it was recorded, as a fallback."
    )
    in_s: float = Field(0.0, ge=0.0, description="In-point in the footage, seconds.")


class StillBodyV1(BaseModel):
    """An image, its rights, and its editorial label — one record."""

    model_config = {"frozen": True, "extra": "forbid"}

    key: str = Field(
        ..., description="Stable slot name pick maps use (e.g. 'eliza-earl')."
    )
    artifact_id: str = Field(
        ..., description="lacing Artifact asset_id of the image bytes."
    )
    url: Optional[str] = Field(None, description="file:// (or hosted) URL.")
    width: Optional[int] = Field(None, ge=1)
    height: Optional[int] = Field(None, ge=1)
    title: Optional[str] = Field(
        None,
        description=(
            "The work's own title (TASL's T; illustration.ImageResult.title). "
            "What a credit names — never the editorial subject."
        ),
    )
    # --- rights: named exactly as illustration.RIGHTS_FIELDS ---
    license: Optional[str] = Field(
        None,
        description=(
            "The CANONICAL licence code — what a gate compares. "
            "`illustration.licensing.normalize_license`'s output: 'by', "
            "'by-sa', 'cc0', 'pdm'. Never a provider spelling."
        ),
    )
    # Additive (default None), so every row written before it exists still
    # loads and simply has no display spelling. The human form a credit should
    # read ("CC BY-SA 4.0"), kept BESIDE the canonical code rather than instead
    # of it: a gate that compares "CC BY-SA 4.0" against "by-sa" matches
    # nothing while looking like it works, and a credit reading "by-sa"
    # satisfies nobody. Two readers, two fields — thorwhalen/illustration#24.
    license_label: Optional[str] = Field(
        None,
        description=(
            "The licence as a human reads it ('CC BY-SA 4.0'). Display only; "
            "`credit_line` prefers it and falls back to `license`."
        ),
    )
    license_url: Optional[str] = Field(None)
    attribution: Optional[str] = Field(
        None,
        description=(
            "The provider's attribution string, kept for the record. NOT the "
            "credit line — compose that with credit_line()."
        ),
    )
    source_page_url: Optional[str] = Field(None)
    author: Optional[str] = Field(None)
    author_url: Optional[str] = Field(None)
    cacheable: Optional[bool] = Field(
        None, description="None = not recorded (distinct from False)."
    )
    # --- the editorial decision ---
    labelled: bool = Field(
        ...,
        description=(
            "Whether the subject is named on screen. True needs a subject; "
            "False is a deliberate 'this picture names nobody'."
        ),
    )
    subject: Optional[str] = Field(
        None, description="What a label would say ('Eliza Hamilton, 1787')."
    )
    about: Optional[str] = Field(None, description="The longer note.")
    crop: Optional[RectV1] = Field(
        None,
        description=(
            "Region to keep (scale bars, accession stamps read as a rights "
            "claim over the whole frame)."
        ),
    )
    note: Optional[str] = Field(
        None, description="Why this picture — the rejection reasoning, for a human."
    )

    @model_validator(mode="after")
    def _labelled_needs_a_subject(self) -> "StillBodyV1":
        if self.labelled and not (self.subject or "").strip():
            raise ValueError(
                f"still {self.key!r}: labelled=True but no subject. Say what the "
                "label reads, or set labelled=False to state that this picture "
                "deliberately names nobody."
            )
        return self


class VideoPanelBodyV1(BaseModel):
    """A still shown over an interval of the episode, with an authored move.

    The interval is on the annotation's ``reference``. ``seed`` is minted
    once and is what a resolved move varies on — never ``order``, which is for
    ordering only. That is the field that fixes the ordinal-seed defect
    (reordering one panel used to change the camera move on every panel after
    it).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    still_id: str = Field(
        ..., description="The still's ANNOTATION id (not its artifact id)."
    )
    move: str = Field(DEFAULT_MOVE, description="One of burns' MOVES.")
    zoom: float = Field(DEFAULT_ZOOM, gt=0.0)
    focus: Optional[RectV1] = Field(
        None,
        description=(
            "Override the saliency frame the move resolves on. Authored on the "
            "picture AS SHOWN — the still after its crop — in normalized "
            "coordinates of that image."
        ),
    )
    path: Optional[dict[str, Any]] = Field(
        None,
        description=(
            "A full BurnsPath.to_dict() override — the explicit front door for "
            "a hand-corrected move. When set, move/zoom/focus/seed are ignored."
        ),
    )
    seed: int = Field(..., description="Minted once; stable under reordering.")
    beat_id: Optional[str] = Field(
        None, description="Zero-padded id of the beat this panel sits under."
    )
    order: int = Field(..., ge=0, description="Position in the track. Never a seed.")
    track_id: str = Field(
        ...,
        description=(
            "The track this panel belongs to — minted once per plan run and "
            "shared by every panel it wrote. A cut lists panels; a track is "
            "how two plans over one episode stay apart."
        ),
    )
    # --- the placement decision (thorwhalen/braidio#85) ---------------------
    # All additive (default None/False): a panel written before them loads and
    # reads as "unexplained, unscored" — which is exactly what it was.
    anchor_text: Optional[str] = Field(
        None, description="The words spoken under this panel, as planned."
    )
    rationale: Optional[str] = Field(
        None,
        description=(
            "What in `anchor_text` the picture illustrates — the author's reason "
            "for the placement. None = nobody said why."
        ),
    )
    relevance: Optional[float] = Field(
        None,
        ge=0.0,
        le=1.0,
        description="How well the still relates to `anchor_text`, per `scorer`.",
    )
    scorer: Optional[str] = Field(
        None, description="Id of the relevance scorer that produced `relevance`."
    )
    role: Optional[PanelRole] = Field(
        None,
        description=(
            "'literal' (shows what is said), 'contextual' (shows its world), "
            "'decorative' (filler, admitted as such). None = unexplained."
        ),
    )
    disclaimed: bool = Field(
        False,
        description=(
            "The placement is honest only while the still's label is on screen "
            "(a right-shaped, wrong-specific picture). Its label then outranks "
            "any card in its slot at the panel's first appearance."
        ),
    )
    # Additive (thorwhalen/braidio footage panels): None is every panel before
    # it — a still under a move.
    footage: Optional[FootageRefV1] = Field(
        None,
        description=(
            "Play this recorded video over the panel's span as a straight cut. "
            "The still stays the panel's poster (a frame of the footage) and "
            "carries its rights: the licence gates and the credits read the "
            "still. move/zoom/focus are not rendered."
        ),
    )

    @model_validator(mode="after")
    def _move_in_vocabulary(self) -> "VideoPanelBodyV1":
        if self.move not in MOVES:
            raise ValueError(f"video-panel: move {self.move!r} is not one of {MOVES}")
        return self


class VideoCutBodyV1(BaseModel):
    """A rendered video with provenance to the panels and audio it used.

    Two stages share one body: a ``motion`` cut is the frames (minutes to
    render), a ``delivered`` cut is that motion with text composited (seconds).
    Editing a label re-runs only the second. ``cache_key`` is ``None`` on a
    cut braidio did not render (an import).
    """

    model_config = {"frozen": True, "extra": "forbid"}

    label: str = Field(..., description="'v2', '2 min', '1 min vertical'.")
    stage: str = Field(..., description="'motion' | 'delivered'.")
    profile: str = Field(..., description="Rights profile: personal | published.")
    audio_artifact_id: str = Field(
        ..., description="The episode audio this was cut against."
    )
    panel_ids: tuple[str, ...] = Field(
        default_factory=tuple, description="Panel annotation ids, in order."
    )
    cache_key: Optional[str] = Field(
        None, description="hash of everything that reaches the pixels."
    )
    artifact_id: Optional[str] = Field(None, description="lacing Artifact of the mp4.")
    url: Optional[str] = Field(None)
    duration_s: float = Field(0.0, ge=0.0)
    width: Optional[int] = Field(None, ge=1)
    height: Optional[int] = Field(None, ge=1)
    fps: Optional[int] = Field(None, ge=1)
    captions_artifact_id: Optional[str] = Field(
        None, description="The SRT sidecar, when one was written."
    )
    settings: dict[str, Any] = Field(
        default_factory=dict,
        description="size, fps, min/max_panel_s, credits duration, delivery…",
    )
    published: Optional[dict[str, Any]] = Field(
        None, description="{platform, video_id, url, privacy, supersedes}."
    )

    @model_validator(mode="after")
    def _enums(self) -> "VideoCutBodyV1":
        if self.stage not in CUT_STAGES:
            raise ValueError(f"video-cut: stage {self.stage!r} not in {CUT_STAGES}")
        if self.profile not in CUT_PROFILES:
            raise ValueError(
                f"video-cut: profile {self.profile!r} not in {CUT_PROFILES}"
            )
        return self


class LabelTrackBodyV1(BaseModel):
    """A timed editorial card that is not per-still. Interval on the reference."""

    model_config = {"frozen": True, "extra": "forbid"}

    kind: str = Field(..., description="'title' | 'context' | 'tag' | 'note'.")
    lines: tuple[str, ...] = Field(default_factory=tuple)
    headline: Optional[str] = Field(None)
    weight: int = Field(2, ge=1, description="tituli's suppression weight.")
    slot: Optional[str] = Field(
        None, description="tituli slot/anchor; None = the kind's default."
    )

    @model_validator(mode="after")
    def _kind_and_content(self) -> "LabelTrackBodyV1":
        if self.kind not in LABEL_KINDS:
            raise ValueError(f"label-track: kind {self.kind!r} not in {LABEL_KINDS}")
        if not self.lines and not (self.headline or "").strip():
            raise ValueError("label-track: a card needs a headline or lines")
        return self


def credit_line(still: StillBodyV1 | dict) -> str:
    """The credit for ``still``, composed from its rights fields — TASL order.

    Title (the work's own, never the editorial ``subject`` or the slot ``key``
    — a caveat like "not this concert" is a label, not what the picture is
    called), Author, Source (the page the bytes came from), Licence. A
    provider's ``attribution`` can come back as a bare author with no licence
    named while ``license`` / ``license_url`` on the same hit are correct, so
    rendering it as documented ships ``"EliziR"`` as the whole credit for a
    CC BY-SA image. This builds the line from the parts and **raises** when
    no licence is recorded: a credit that names no licence satisfies nothing.

    The licence it prints is ``license_label`` when one is recorded and
    ``license`` otherwise. ``license`` is the *canonical* code a gate compares
    (``'by-sa'``), which is not what a credit should read, so the display
    spelling is carried beside it rather than instead of it — a still that has
    only the canonical code still credits, just tersely.

    >>> credit_line(dict(key="k", artifact_id="a", labelled=False,
    ...     title="Portrait of Eliza Hamilton", author="Ralph Earl",
    ...     license="public-domain"))
    'Portrait of Eliza Hamilton — Ralph Earl — public-domain'
    >>> credit_line(dict(key="k", artifact_id="a", labelled=False,
    ...     title="A Photograph", author="EliziR",
    ...     license="by-sa", license_label="CC BY-SA 4.0"))
    'A Photograph — EliziR — CC BY-SA 4.0'
    >>> credit_line(dict(key="k", artifact_id="a", labelled=True, subject="Eliza",
    ...     author="Ralph Earl", license="public-domain",
    ...     source_page_url="https://commons.wikimedia.org/wiki/File:E.jpg"))
    'Ralph Earl — https://commons.wikimedia.org/wiki/File:E.jpg — public-domain'
    >>> credit_line(dict(key="k", artifact_id="a", labelled=False))
    Traceback (most recent call last):
        ...
    ValueError: still 'k': no licence recorded ...
    """
    body = still if isinstance(still, StillBodyV1) else StillBodyV1(**still)
    if not (body.license or "").strip():
        raise ValueError(
            f"still {body.key!r}: no licence recorded — a credit line that names "
            "no licence satisfies no attribution condition. Record `license` "
            "(and `license_url`) before this still can be credited."
        )
    shown = (body.license_label or "").strip() or body.license
    parts = [body.title, body.author, body.source_page_url, shown]
    return " — ".join(p.strip() for p in parts if p and p.strip())


VIDEO_SCHEMAS: dict[str, type[BaseModel]] = {
    STILL_V1: StillBodyV1,
    VIDEO_PANEL_V1: VideoPanelBodyV1,
    VIDEO_CUT_V1: VideoCutBodyV1,
    LABEL_TRACK_V1: LabelTrackBodyV1,
}

for _uri, _model in VIDEO_SCHEMAS.items():
    register_body_schema(_uri, _model)
