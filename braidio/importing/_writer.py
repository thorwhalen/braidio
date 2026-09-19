"""Write a normalized production manifest into a real braidio project graph.

The verb is :func:`import_production`. It takes a
:class:`~braidio.importing._manifest.ProductionManifest` and a destination
project root and writes the stills, the episode audio (one node per distinct
mix — Two Silences renders a different mix per cut), the panel track for each
cut, the editorial cards, and the cut records with their ``published`` links.

**Idempotent by construction.** Every annotation id is a UUIDv5 of the
production slug plus a stable key, so a second run addresses the same nodes
rather than writing a second track beside the first. A node whose value is
unchanged is *left alone* rather than rewritten, because rewriting moves
``generated_at_time`` and would stale a rendered cut for no reason.

Four rules this module enforces rather than documents, each of which was a
measured defect in the three finished productions:

1. **Every imported panel is ``push_in``.** The source encodes a ``push`` /
   ``drift`` alternation, and it was a **no-op**: ``drift`` reached burns as
   ``mode="auto"``, whose only use of the index was ``push = index % 2 == 1``,
   and every project set style by the same ordinal it passed as the index — so
   both halves landed on push-in and all 265 panels of all three films push in
   (thorwhalen/braidio#72). Writing ``auto`` today would hand that panel to
   ``burns.choose_move``, which picks from a weighted pool and yields a real
   directional drift about 40% of the time: a substantially different film,
   arrived at by an import that believed it was being faithful. The
   never-realised intent is recorded as :data:`MOVE_IMPORT_NOTE` on the project
   and on every cut, so drift can be introduced **deliberately** later.
2. **The library's zoom default is asserted, not trusted.** 178 Two Silences
   panels carry a zoom that was never recorded in data — it was
   ``braidio.video.Panel``'s dataclass default, read off the source. If that
   default has moved, the extracted number is already wrong and this is the
   last place anyone would look, so :func:`assert_recorded_zoom_default` fails
   the import loudly.
3. **Every licence is normalized through ``illustration``, and an unknown one
   fails.** All 15 spellings across the three productions resolve to ``by`` /
   ``by-sa`` / ``cc0`` / ``pdm``, so a failure means something genuinely new
   rather than a gap in the table. The *recorded* spelling is what gets
   written — a credit reading "CC BY-SA 4.0" is the useful one — normalization
   is the gate, not the value.
4. **A context card is written with ``weight >= 2``.** ``video_cut.finish``
   refuses an overlay collision at plan time, and a weight-1 card over a
   labelled still is one, so a weight-1 context card would make the cut
   unrenderable at the point where it is least obvious why.

What it deliberately does **not** do: mark anything publishable the source did
not (every cut keeps its recorded profile, and the rights finding is carried as
project-level data), invent a beat it cannot witness, or copy the shipped mp4s
into the project — those are the *evidence* a re-render is checked against, not
an input to one, and they are large.
"""

from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional

from braidio.importing._manifest import (
    CutRecord,
    LabelRecord,
    ProductionManifest,
    StillRecord,
)

#: Namespace for every id this importer mints. Fixed forever: change it and a
#: re-import stops addressing the nodes the last one wrote, which is precisely
#: the "two tracks instead of one" failure idempotency exists to prevent.
IMPORT_NAMESPACE = uuid.UUID("6b1f8c7e-4a2d-5e93-9c11-b7a0d2e4f501")

#: The move every imported panel gets. See rule 1 in the module docstring.
IMPORTED_MOVE = "push_in"

#: braidio.video.Panel's zoom default as it stood when the three productions
#: were extracted. Asserted at import; see rule 2.
RECORDED_PANEL_ZOOM_DEFAULT = 1.18

MOVE_IMPORT_NOTE = (
    "Every panel imported as push_in. The source alternated push/drift by "
    "ordinal, but the alternation was a no-op on the render path: drift "
    "reached burns as mode='auto', whose only use of the index was "
    "push = (index % 2 == 1), and the same ordinal drove both — so all panels "
    "pushed in. See thorwhalen/braidio#72. burns.choose_move now picks from a "
    "weighted pool, so writing 'auto' would invent a drift the film never had. "
    "The intent to vary the motion is recorded here and is now expressible "
    "deliberately, per panel, through the move vocabulary."
)

#: Rights positions that are NOT a licence to publish. The importer never
#: promotes a cut; the position is carried so a surface can show it.
_NON_PUBLIC_POSITIONS = frozenset({"private", "unlisted"})

_UNSAFE_IN_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


class ImportError_(Exception):
    """Raised when a manifest cannot be imported faithfully."""


@dataclass
class ImportReport:
    """What one import did, and what it could not settle.

    Returned rather than logged, so a CLI, a test and a future MCP tool all
    read the same answer.
    """

    production: str
    project_root: Path
    title: str
    rights_position: str
    stills_written: int = 0
    stills_unchanged: int = 0
    episodes: int = 0
    panels_by_cut: dict[str, int] = field(default_factory=dict)
    labels_by_cut: dict[str, int] = field(default_factory=dict)
    cuts_written: list[str] = field(default_factory=list)
    published_links: dict[str, str] = field(default_factory=dict)
    #: Stills with no ``title`` — they credit WITHOUT one, silently, so the
    #: count is surfaced rather than left to be discovered in a credit roll.
    untitled_stills: list[str] = field(default_factory=list)
    #: Stills whose ``attribution`` names no licence: rendering it verbatim
    #: would fail the licence condition. ``credit_line`` composes instead.
    bare_attributions: list[str] = field(default_factory=list)
    license_codes: dict[str, str] = field(default_factory=dict)
    beat_ids_renumbered: int = 0
    media_copied: int = 0
    gaps: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def panels_total(self) -> int:
        return sum(self.panels_by_cut.values())

    def to_dict(self) -> dict[str, Any]:
        """A JSON-able summary (what the CLI's ``--json`` prints)."""
        return {
            "production": self.production,
            "project_root": str(self.project_root),
            "title": self.title,
            "rights_position": self.rights_position,
            "stills_written": self.stills_written,
            "stills_unchanged": self.stills_unchanged,
            "episodes": self.episodes,
            "panels_by_cut": dict(self.panels_by_cut),
            "panels_total": self.panels_total,
            "labels_by_cut": dict(self.labels_by_cut),
            "cuts_written": list(self.cuts_written),
            "published_links": dict(self.published_links),
            "untitled_stills": list(self.untitled_stills),
            "bare_attributions": list(self.bare_attributions),
            "license_codes": dict(self.license_codes),
            "beat_ids_renumbered": self.beat_ids_renumbered,
            "media_copied": self.media_copied,
            "gaps": list(self.gaps),
            "notes": list(self.notes),
        }


# --- the four enforced rules ------------------------------------------------


def assert_recorded_zoom_default(expected: float = RECORDED_PANEL_ZOOM_DEFAULT) -> None:
    """Fail unless ``braidio.video.Panel``'s zoom default is still ``expected``.

    The one failure that is invisible afterwards. 178 Two Silences panels carry
    a zoom nothing recorded — it was this default, read off the library at
    extraction time. 1.18 against 1.14 is near-invisible on one panel and
    diverges over ten minutes.

    >>> assert_recorded_zoom_default()
    >>> assert_recorded_zoom_default(1.14)
    Traceback (most recent call last):
        ...
    braidio.importing._writer.ImportError_: braidio.video.Panel.zoom is 1.18...
    """
    import dataclasses

    from braidio.video import Panel

    actual = next(f for f in dataclasses.fields(Panel) if f.name == "zoom").default
    if abs(float(actual) - float(expected)) > 1e-9:
        raise ImportError_(
            f"braidio.video.Panel.zoom is {actual!r}, not the {expected!r} the "
            "extraction read off it. Panels whose zoom was never recorded in "
            "data took this default, so the manifest's zoom is now wrong and "
            "nothing downstream would notice. Re-extract against the current "
            "library, or pass the default that was in force."
        )


def normalized_licenses(stills: Iterable[StillRecord]) -> dict[str, str]:
    """``{still key: canonical code}``, raising on anything unrecognised.

    The gate, not the value: what gets written into the still body is the
    *recorded* spelling, because "CC BY-SA 4.0" is what a credit should read
    and "by-sa" is not. An unrecognised code survives ``normalize_license``
    unchanged and would therefore silently fail a downstream allowlist with no
    error at all — which is why an unknown fails here instead.
    """
    try:
        from illustration.licensing import normalize_license
    except ImportError as exc:  # pragma: no cover - environment-dependent
        raise ImportError_(
            "importing a production needs `illustration` for licence "
            "normalization (pip install 'braidio[importing]'). It is the SSOT "
            "for the four provider dialects; a second copy of that table here "
            "is how a licence gate silently starts dropping images."
        ) from exc

    known = {"by", "by-sa", "by-nc", "by-nd", "by-nc-sa", "by-nc-nd", "cc0", "pdm"}
    codes: dict[str, str] = {}
    unknown: list[str] = []
    for still in stills:
        raw = (still.license or "").strip()
        if not raw:
            continue
        code = normalize_license(raw)
        codes[still.key] = code
        if code not in known:
            unknown.append(f"{still.key}: {raw!r} -> {code!r}")
    if unknown:
        raise ImportError_(
            "licence codes illustration.licensing.normalize_license does not "
            "recognise:\n  " + "\n  ".join(unknown) + "\nAll 15 spellings across "
            "the three finished productions resolve cleanly, so this is a "
            "genuinely new code rather than a gap in the table. Add it to "
            "illustration's LICENSE_ALIASES (a deliberate decision, never a "
            "convenience) before importing."
        )
    return codes


def _check_card_weights(cut: CutRecord) -> None:
    """Refuse a context card too light to survive ``video_cut.finish``."""
    light = [
        f"{label.kind}@{label.start:.1f}s (weight {label.weight})"
        for label in cut.labels
        if label.kind in ("context", "note") and label.weight < 2
    ]
    if light:
        raise ImportError_(
            f"cut {cut.label!r}: context cards need weight >= 2, got "
            + ", ".join(light)
            + ". video_cut.finish resolves overlays at PLAN time and a "
            "weight-1 card over a labelled still is a collision, so the cut "
            "would be refused before a frame is rendered."
        )


# --- graph plumbing ---------------------------------------------------------


def _mint(production: str, *parts: Any) -> uuid.UUID:
    """A stable annotation id for ``production`` and a key. See idempotency."""
    return uuid.uuid5(IMPORT_NAMESPACE, "/".join([production, *map(str, parts)]))


def _provenance(derived_from: Iterable[uuid.UUID] = ()):
    from lacing import Provenance, RationalTime

    return Provenance(
        was_generated_by="braidio:import_production",
        was_attributed_to="agent:braidio",
        was_derived_from=list(derived_from),
        generated_at_time=RationalTime.now(),
        activity="import",
    )


def _identity(ann) -> str:
    """Everything about ``ann`` a re-import would be rewriting, as one string.

    Deliberately excludes ``provenance.generated_at_time`` — that moves on
    every run by definition, and comparing it would make every re-import a
    rewrite, which stales every rendered cut downstream for no reason.
    """
    return json.dumps(
        {
            "tier": ann.tier,
            "body": ann.body,
            "schema": ann.body_schema_uri,
            "reference": ann.reference.model_dump(mode="json"),
            "parents": sorted(str(p) for p in ann.provenance.was_derived_from),
        },
        sort_keys=True,
        default=str,
    )


def _upsert(project, ann, index: dict) -> bool:
    """Write ``ann`` unless an identical node already sits under its id.

    Returns True when the graph changed. Replacement is remove-then-add: the
    store enforces id uniqueness, and a removal takes the annotation's
    verifying traces with it (nw#36) so no inert sidecar is left behind.
    """
    existing = index.get(ann.id)
    if existing is not None:
        if _identity(existing) == _identity(ann):
            return False
        project.graph.remove_annotation(ann.id)
    project.graph.add_annotation(ann)
    index[ann.id] = ann
    return True


def _node_ref(tier: str, ann_id: uuid.UUID):
    """A **deterministic** :class:`lacing.NodeRef` for a non-media node.

    braidio's own ``transforms._common.node_ref`` mints a fresh uuid into the
    ``scene_path`` on every call, which is right for a Transform (each run is a
    new node) and wrong for an import: the reference would differ on every run,
    so :func:`_identity` would never compare equal and a re-import would
    rewrite every still, episode and cut — moving ``generated_at_time`` and
    staling rendered cuts for no reason at all. Keying the path on the node's
    own (already deterministic) id makes a no-op re-import a genuine no-op.
    """
    from lacing import NodeRef, TimeInterval

    return NodeRef(
        scene_path=f"{tier}/{ann_id}",
        interval=TimeInterval.from_seconds(0.0, 1.0, rate=1000),
    )


def _media_ref(asset_id: str, start: float, end: float):
    from lacing import MediaRef, RationalTime, TimeInterval

    rate = 1000
    return MediaRef(
        asset_id=str(asset_id),
        interval=TimeInterval(
            RationalTime(int(round(start * rate)), rate),
            RationalTime(int(round(end * rate)), rate),
        ),
    )


def _artifact_for(path: Path, *, kind: str, mime: str | None = None, duration_s=None):
    from lacing import Artifact

    return Artifact.from_path(
        path,
        kind=kind,
        was_generated_by="braidio:import_production",
        was_attributed_to="agent:braidio",
        duration_s=duration_s,
        mime=mime,
    )


def _safe_name(key: str) -> str:
    """``'acoustic-guitar#1'`` -> ``'acoustic-guitar_1'``.

    >>> _safe_name("acoustic-guitar#1")
    'acoustic-guitar_1'
    >>> _safe_name("central-park-decay#3")
    'central-park-decay_3'
    """
    return _UNSAFE_IN_FILENAME.sub("_", key).strip("_")


def _rect_from_ltrb(box) -> Optional[dict[str, float]]:
    """A fractional ``(left, top, right, bottom)`` crop as a ``RectV1`` mapping.

    The one geometry conversion in this importer, and it is load-bearing. Both
    productions that crop record LTRB (``l, t, r, b = CROPS[slot]``; Hamilton's
    "a fractional (left, top, right, bottom) box"), while ``RectV1`` — and
    ``braidio.transforms._video_cut._crop_still``, which applies it — is
    ``(x, y, w, h)``. Passing the tuple through unchanged mis-frames every
    cropped still, and ``RectV1``'s unit-square check catches only the one crop
    whose left+right happens to exceed 1: nine of the ten here would be
    silently wrong.

    >>> _rect_from_ltrb((0.0, 0.0, 1.0, 0.88))
    {'x': 0.0, 'y': 0.0, 'w': 1.0, 'h': 0.88}
    >>> _rect_from_ltrb((0.05, 0.33, 0.96, 0.95))['w']
    0.91
    >>> _rect_from_ltrb(None) is None
    True
    >>> _rect_from_ltrb((0.9, 0.0, 0.1, 1.0))
    Traceback (most recent call last):
        ...
    braidio.importing._writer.ImportError_: crop (0.9, 0.0, 0.1, 1.0) is not...
    """
    if box is None:
        return None
    left, top, right, bottom = (float(v) for v in box)
    if not (0.0 <= left < right <= 1.0 and 0.0 <= top < bottom <= 1.0):
        raise ImportError_(
            f"crop {tuple(box)!r} is not a fractional (left, top, right, "
            "bottom) box inside the unit square. The manifest records LTRB; "
            "if this is really (x, y, w, h) the extractor and the importer "
            "have drifted, and a wrong crop is invisible after the render."
        )
    return {
        "x": round(left, 6),
        "y": round(top, 6),
        "w": round(right - left, 6),
        "h": round(bottom - top, 6),
    }


def _beat_id(raw: Optional[str]) -> Optional[str]:
    """``'beat:12'`` -> ``'0012'``; anything else passes through unchanged.

    The extraction recorded the *timeline member index* a panel sat under.
    braidio spells that identity zero-padded (``BEAT_ID_WIDTH``), and
    ``picks_from_panels`` keys a re-plan's pick map on it — so leaving
    ``'beat:12'`` in place would make a later re-plan silently ignore every
    pick and fall back to cycling the pool, i.e. a different set of pictures
    with nothing raised. Converting is the assumption that timeline member
    index == script position, which holds for a script nothing filtered.

    >>> _beat_id("beat:12"), _beat_id("beat:0"), _beat_id(None), _beat_id("0007")
    ('0012', '0000', None, '0007')
    """
    if raw is None:
        return None
    text = str(raw)
    if text.startswith("beat:") and text[5:].isdigit():
        return f"{int(text[5:]):04d}"
    return text


# --- the verb ---------------------------------------------------------------


def import_production(
    manifest: ProductionManifest,
    project_root,
    *,
    source_root=None,
    copy_media: bool = True,
    dry_run: bool = False,
) -> ImportReport:
    """Write ``manifest`` into a braidio project at ``project_root``.

    Args:
        manifest: the normalized production (see ``load_manifest``).
        project_root: where the project lives. Created if absent; an existing
            project is updated in place, which is what makes a re-run one
            project rather than two.
        source_root: the folder ``manifest.source_dir`` is relative to. The
            manifest never stores an absolute path (one committed production
            manifest did, in a shared repo — only basenames come forward), so
            the caller supplies the root.
        copy_media: copy the stills and the episode audio into the project, so
            it is self-contained and a fork can hardlink it. The shipped cut
            mp4s are always referenced in place: they are the evidence a
            re-render is compared against, not an input to one.
        dry_run: validate everything — files present, licences known, card
            weights sufficient, zoom default unmoved — and write nothing.

    Returns:
        an :class:`ImportReport`.
    """
    import nw  # noqa: F401  (import registers the tiers/transforms)

    from braidio.bodies._render_nodes import EPISODE_RENDER_V1, RENDER_PROFILE_V1
    from braidio.bodies._video import (
        LABEL_TRACK_V1,
        STILL_V1,
        VIDEO_CUT_V1,
        VIDEO_PANEL_V1,
        LabelTrackBodyV1,
        StillBodyV1,
        VideoCutBodyV1,
        VideoPanelBodyV1,
    )
    from braidio.bodies._render_nodes import EpisodeRenderBodyV1, RenderProfileBodyV1
    from braidio.project import Project
    from braidio.rights import PUBLISHABLE_CLIP_RIGHTS, Profile
    from braidio.transforms._common import (
        TIER_EPISODE_RENDER,
        TIER_LABEL_TRACK,
        TIER_RENDER_PROFILE,
        TIER_STILL,
        TIER_VIDEO_CUT,
        TIER_VIDEO_PANEL,
        file_url,
    )
    from lacing import Annotation

    # --- rule 2: the library default the extraction depended on -------------
    assert_recorded_zoom_default()

    source_root = Path(source_root or ".").expanduser().resolve()
    src = source_root / manifest.source_dir
    if not src.is_dir():
        raise ImportError_(
            f"source folder {src} does not exist. The manifest records "
            f"source_dir={manifest.source_dir!r}; pass source_root= the folder "
            "it is relative to."
        )

    report = ImportReport(
        production=manifest.production,
        project_root=Path(project_root).expanduser().resolve(),
        title=manifest.title,
        rights_position=manifest.rights.position,
        gaps=list(manifest.gaps),
    )
    report.notes.append(MOVE_IMPORT_NOTE)

    # --- rule 3: licences, and rule 4: card weights -------------------------
    report.license_codes = normalized_licenses(manifest.stills)
    for cut in manifest.cuts:
        _check_card_weights(cut)

    # Never promote what the source did not.
    if manifest.rights.position in _NON_PUBLIC_POSITIONS:
        public = [
            c.label for c in manifest.cuts if c.profile == Profile.PUBLISHED.value
        ]
        if public:
            raise ImportError_(
                f"{manifest.production}: rights position is "
                f"{manifest.rights.position!r} but cuts {public} declare the "
                "'published' profile. The importer never promotes a cut."
            )

    # --- resolve every file before writing anything -------------------------
    still_paths = {s.key: src / s.path for s in manifest.stills}
    missing = sorted(k for k, p in still_paths.items() if not p.is_file())
    if missing:
        raise ImportError_(
            f"{len(missing)} still files are not on disk: {missing[:8]}"
            + ("" if len(missing) <= 8 else f" (+{len(missing) - 8} more)")
        )
    used_keys = {p.still_key for cut in manifest.cuts for p in cut.panels}
    unknown_keys = sorted(used_keys - manifest.still_keys)
    if unknown_keys:
        raise ImportError_(
            f"panels name stills the manifest does not hold: {unknown_keys}"
        )

    audio_paths = {}
    for cut in manifest.cuts:
        audio_paths[cut.audio.path] = src / cut.audio.path
    audio_paths.setdefault(
        manifest.episode_audio.path, src / manifest.episode_audio.path
    )
    missing_audio = sorted(p for p, f in audio_paths.items() if not f.is_file())
    if missing_audio:
        raise ImportError_(f"episode audio not on disk: {missing_audio}")

    report.untitled_stills = sorted(s.key for s in manifest.stills if not s.title)
    report.bare_attributions = sorted(
        s.key
        for s in manifest.stills
        if s.attribution
        and s.license
        and s.license.lower().replace(" ", "")
        not in s.attribution.lower().replace(" ", "")
        and "creativecommons" not in s.attribution.lower()
        and "public domain" not in s.attribution.lower()
    )

    if dry_run:
        report.notes.append("dry run: validated, nothing written")
        return report

    # --- the project --------------------------------------------------------
    root = report.project_root
    if (root / "project.json").exists():
        project = Project(root)
    else:
        project = Project.init(root, title=manifest.title, force=True)
    project.update_spec(title=manifest.title, notes=_project_notes(manifest, report))

    index = {a.id: a for a in nw.iter_all_annotations(project.root)}
    profile = _common_profile(manifest)

    # --- the rights position, as structured graph data ----------------------
    _upsert(
        project,
        Annotation(
            id=_mint(manifest.production, "render-profile"),
            tier=TIER_RENDER_PROFILE,
            reference=_node_ref(
                TIER_RENDER_PROFILE, _mint(manifest.production, "render-profile")
            ),
            body=RenderProfileBodyV1(
                profile=profile,
                publishable_clip_rights=tuple(sorted(PUBLISHABLE_CLIP_RIGHTS)),
            ).model_dump(mode="json"),
            body_schema_uri=RENDER_PROFILE_V1,
            provenance=_provenance(),
        ),
        index,
    )

    # --- the stills ---------------------------------------------------------
    still_ids: dict[str, uuid.UUID] = {}
    for still in manifest.stills:
        dest = still_paths[still.key]
        if copy_media:
            dest = _copy_into(
                still_paths[still.key],
                root / "data" / "stills",
                _safe_name(still.key) + still_paths[still.key].suffix,
                report,
            )
        artifact = _artifact_for(dest, kind="image")
        ann_id = _mint(manifest.production, "still", still.key)
        still_ids[still.key] = ann_id
        body = StillBodyV1(
            key=still.key,
            artifact_id=artifact.asset_id,
            url=file_url(dest),
            width=still.width,
            height=still.height,
            title=still.title,
            license=still.license,
            license_url=still.license_url,
            attribution=still.attribution,
            source_page_url=still.source_page_url,
            author=still.author,
            author_url=still.author_url,
            cacheable=still.cacheable,
            labelled=still.labelled,
            subject=still.subject,
            about=still.about,
            crop=_rect_from_ltrb(still.crop),
            note=still.note,
        )
        written = _upsert(
            project,
            Annotation(
                id=ann_id,
                tier=TIER_STILL,
                reference=_node_ref(TIER_STILL, ann_id),
                body=body.model_dump(mode="json"),
                body_schema_uri=STILL_V1,
                provenance=_provenance(),
            ),
            index,
        )
        if written:
            report.stills_written += 1
        else:
            report.stills_unchanged += 1

    # --- the episode audio: one node per distinct mix -----------------------
    episode_ids: dict[str, uuid.UUID] = {}
    episode_assets: dict[str, str] = {}
    durations = {manifest.episode_audio.path: manifest.episode_audio.duration_s}
    for cut in manifest.cuts:
        durations[cut.audio.path] = cut.audio.duration_s
    for rel, srcfile in audio_paths.items():
        dest = srcfile
        if copy_media:
            dest = _copy_into(
                srcfile, root / "data" / "episodes", Path(rel).name, report
            )
        artifact = _artifact_for(
            dest, kind="audio", mime="audio/mpeg", duration_s=durations.get(rel)
        )
        ann_id = _mint(manifest.production, "episode", rel)
        episode_ids[rel] = ann_id
        episode_assets[rel] = artifact.asset_id
        _upsert(
            project,
            Annotation(
                id=ann_id,
                tier=TIER_EPISODE_RENDER,
                reference=_node_ref(TIER_EPISODE_RENDER, ann_id),
                body=EpisodeRenderBodyV1(
                    profile=profile,
                    ordered_member_ids=(),
                    artifact_id=artifact.asset_id,
                    url=file_url(dest),
                    duration_s=float(durations.get(rel) or 0.0),
                    timeline=None,
                ).model_dump(mode="json"),
                body_schema_uri=EPISODE_RENDER_V1,
                provenance=_provenance(),
            ),
            index,
        )
        report.episodes += 1

    # --- per cut: panels, cards, the cut records ----------------------------
    for cut in manifest.cuts:
        episode_id = episode_ids[cut.audio.path]
        audio_asset = episode_assets[cut.audio.path]
        track_id = str(_mint(manifest.production, "track", cut.label))

        panel_ids: list[uuid.UUID] = []
        for panel in sorted(cut.panels, key=lambda p: p.order):
            beat = _beat_id(panel.beat_id)
            if beat != panel.beat_id:
                report.beat_ids_renumbered += 1
            pid = _mint(manifest.production, "panel", cut.label, panel.order)
            panel_ids.append(pid)
            _upsert(
                project,
                Annotation(
                    id=pid,
                    tier=TIER_VIDEO_PANEL,
                    reference=_media_ref(audio_asset, panel.start, panel.end),
                    body=VideoPanelBodyV1(
                        still_id=str(still_ids[panel.still_key]),
                        # rule 1 — reality, not the never-realised intent
                        move=IMPORTED_MOVE,
                        zoom=panel.zoom,
                        focus=panel.focus,
                        path=None,
                        # kept as provenance of the source ordinal; nothing
                        # reads it, because nothing is 'auto'
                        seed=panel.seed,
                        beat_id=beat,
                        order=panel.order,
                        track_id=track_id,
                    ).model_dump(mode="json"),
                    body_schema_uri=VIDEO_PANEL_V1,
                    provenance=_provenance([episode_id]),
                ),
                index,
            )
        report.panels_by_cut[cut.label] = len(panel_ids)

        label_ids: list[uuid.UUID] = []
        for i, label in enumerate(sorted(cut.labels, key=lambda x: x.start)):
            lid = _mint(manifest.production, "label", cut.label, i)
            label_ids.append(lid)
            _upsert(
                project,
                Annotation(
                    id=lid,
                    tier=TIER_LABEL_TRACK,
                    reference=_media_ref(audio_asset, label.start, label.end),
                    body=LabelTrackBodyV1(
                        kind=label.kind,
                        lines=label.lines,
                        headline=label.headline,
                        weight=label.weight,
                        slot=label.slot,
                    ).model_dump(mode="json"),
                    body_schema_uri=LABEL_TRACK_V1,
                    provenance=_provenance([episode_id]),
                ),
                index,
            )
        report.labels_by_cut[cut.label] = len(label_ids)

        still_parents = sorted({still_ids[p.still_key] for p in cut.panels}, key=str)
        settings = _cut_settings(manifest, cut)

        motion_id = None
        if cut.motion_artifact:
            motion_file = src / cut.motion_artifact
            if motion_file.is_file():
                motion_id = _mint(manifest.production, "cut", cut.label, "motion")
                motion_art = _artifact_for(
                    motion_file,
                    kind="video",
                    mime="video/mp4",
                    duration_s=cut.duration_s,
                )
                _upsert(
                    project,
                    Annotation(
                        id=motion_id,
                        tier=TIER_VIDEO_CUT,
                        reference=_node_ref(TIER_VIDEO_CUT, motion_id),
                        body=VideoCutBodyV1(
                            label=cut.label,
                            stage="motion",
                            profile=cut.profile,
                            audio_artifact_id=audio_asset,
                            panel_ids=tuple(str(p) for p in panel_ids),
                            # None: braidio did not render this, so there is no
                            # key that describes its pixels, and a cache lookup
                            # must never answer with it.
                            cache_key=None,
                            artifact_id=motion_art.asset_id,
                            url=file_url(motion_file),
                            duration_s=cut.duration_s,
                            width=cut.width,
                            height=cut.height,
                            fps=cut.fps,
                            settings=settings,
                        ).model_dump(mode="json"),
                        body_schema_uri=VIDEO_CUT_V1,
                        provenance=_provenance(
                            [*panel_ids, *still_parents, episode_id]
                        ),
                    ),
                    index,
                )
                report.cuts_written.append(f"{cut.label} (motion)")

        delivered_id = _mint(manifest.production, "cut", cut.label, "delivered")
        delivered_file = src / cut.artifact
        captions_id = None
        if cut.captions and (src / cut.captions).is_file():
            captions_id = _artifact_for(
                src / cut.captions, kind="text", mime="application/x-subrip"
            ).asset_id
        delivered_art = (
            _artifact_for(
                delivered_file,
                kind="video",
                mime="video/mp4",
                duration_s=cut.duration_s,
            )
            if delivered_file.is_file()
            else None
        )
        parents = [
            *([motion_id] if motion_id else []),
            *label_ids,
            *panel_ids,
            *still_parents,
            episode_id,
        ]
        _upsert(
            project,
            Annotation(
                id=delivered_id,
                tier=TIER_VIDEO_CUT,
                reference=_node_ref(TIER_VIDEO_CUT, delivered_id),
                body=VideoCutBodyV1(
                    label=cut.label,
                    stage="delivered",
                    profile=cut.profile,
                    audio_artifact_id=audio_asset,
                    panel_ids=tuple(str(p) for p in panel_ids),
                    cache_key=None,
                    artifact_id=delivered_art.asset_id if delivered_art else None,
                    url=file_url(delivered_file) if delivered_file.is_file() else None,
                    duration_s=cut.duration_s,
                    width=cut.width,
                    height=cut.height,
                    fps=cut.fps,
                    captions_artifact_id=captions_id,
                    settings=settings,
                    published=cut.published,
                ).model_dump(mode="json"),
                body_schema_uri=VIDEO_CUT_V1,
                provenance=_provenance(parents),
            ),
            index,
        )
        report.cuts_written.append(f"{cut.label} (delivered)")
        if cut.published and cut.published.get("url"):
            report.published_links[cut.label] = str(cut.published["url"])

    return report


def _common_profile(manifest: ProductionManifest) -> str:
    """The profile every cut agrees on (the episode's rights projection)."""
    profiles = {c.profile for c in manifest.cuts} or {"personal"}
    if len(profiles) > 1:
        raise ImportError_(
            f"{manifest.production}: cuts declare more than one profile "
            f"({sorted(profiles)}); an episode has one rights projection."
        )
    return next(iter(profiles))


def _cut_settings(manifest: ProductionManifest, cut: CutRecord) -> dict[str, Any]:
    """The cut's recorded settings, plus what a surface needs beside it.

    ``size`` and ``fps`` are what ``video_cut.render`` reads, so they are
    normalized here rather than left to whatever the source happened to spell.
    ``rights`` rides along because plan §10 asks for the position to be shown
    *next to the cut*, and ``import`` records that these panels' motion is a
    recovered fact rather than an authored choice.
    """
    settings = dict(cut.settings)
    if cut.width and cut.height:
        settings["size"] = [int(cut.width), int(cut.height)]
    settings.setdefault("size", list(settings.get("size") or ()))
    if cut.fps:
        settings["fps"] = int(cut.fps)
    settings["rights"] = {
        "position": manifest.rights.position,
        "why": manifest.rights.why,
        "measured": manifest.rights.measured,
    }
    settings["import"] = {
        "source": manifest.source_dir,
        "move_note": MOVE_IMPORT_NOTE,
        "audio": cut.audio.model_dump(mode="json", exclude_none=True),
    }
    return settings


def _project_notes(manifest: ProductionManifest, report: ImportReport) -> str:
    """The project-level rights position and import caveats, as readable text."""
    lines = [
        f"{manifest.title} — imported from {manifest.source_dir}.",
        "",
        f"RIGHTS: {manifest.rights.position}.",
        manifest.rights.why,
    ]
    if manifest.rights.measured:
        lines += ["", f"Measured: {manifest.rights.measured}"]
    lines += ["", "IMPORT NOTE:", MOVE_IMPORT_NOTE]
    if manifest.gaps:
        lines += ["", "WHAT THE ARCHAEOLOGY COULD NOT SETTLE:"]
        lines += [f"- {g}" for g in manifest.gaps]
    return "\n".join(lines)


def _copy_into(src: Path, folder: Path, name: str, report: ImportReport) -> Path:
    """Copy ``src`` to ``folder/name`` unless identical bytes are already there."""
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / name
    if dest.exists() and dest.stat().st_size == src.stat().st_size:
        return dest
    shutil.copyfile(src, dest)
    report.media_copied += 1
    return dest
