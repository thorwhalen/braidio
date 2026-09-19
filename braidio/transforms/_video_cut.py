"""``video_cut.render`` and ``video_cut.finish`` — panels → the delivered mp4.

Two **local-CPU** Transforms, not one, and that is deliberate (plan §5): the
motion pass is minutes of frame generation, the text pass is seconds, and
editing a label must re-run only the cheap one. The split also enforces
tituli's correctness rule — text composites onto the *finished motion* and is
never burned into a still, because text in a still pans and zooms with the
picture.

- ``video_cut.render`` — the panel track + the stills it points at + the
  episode audio → a ``video-cut/v1`` at ``stage="motion"``: one
  ``burns.ken_burns_film`` pass over the prepared canvases, muxed under the
  episode audio. Its ``cache_key`` covers everything that reaches a pixel —
  the audio, the frame geometry, and per panel the still's *bytes*, its crop,
  its span and its move — and **nothing editorial**: a still's ``subject``,
  ``labelled`` or rights are not in it, so a label edit is a free re-run.
- ``video_cut.finish`` — a motion cut + the label tracks + the stills'
  editorial decisions → a ``video-cut/v1`` at ``stage="delivered"``: tituli
  labels and cards composited in one ffmpeg pass, an SRT sidecar from the
  beats' own text (never ASR), optionally burnt in, and a credits roll
  appended when asked for. Its ``cache_key`` covers the motion cut's bytes and
  everything the text pass reads.

Both follow the ``segment_extraction.ffmpeg`` pattern exactly: a zero-call
``falaw.Plan`` plus a skeleton carrying its own ``cache_key`` through
``nw.transforms.cache_key``, ``fresh_equivalent`` for the idempotent re-run,
``cached_output`` + ``adopt_output`` for the compare-and-skip.

**The camera move is resolved at render time, against the image**, by
``burns.resolve_move`` — a panel stores an *intent* (``move``, ``zoom``,
``focus``, ``seed``), not a path pinned to one image's pixels, so swapping the
still re-frames the move. A stored ``path`` (``BurnsPath.to_dict()``) is the
explicit override for a hand-corrected move. Until burns ships
``resolve_move`` this module carries :func:`resolve_move`, a thin shim that
defers to burns' the moment it exists and otherwise builds the same eight
moves from burns' existing primitives — see the note on it.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

from falaw import Plan
from lacing import Annotation
from nw import BaseTransform, TransformInputs, TransformResult, register_transform
from nw.transforms._provenance import derive_provenance

from braidio.bodies._render_nodes import EPISODE_RENDER_V1
from braidio.bodies._video import (
    LABEL_TRACK_V1,
    MOVES,
    STILL_V1,
    VIDEO_CUT_V1,
    VIDEO_PANEL_V1,
    VideoCutBodyV1,
    credit_line,
)
from braidio.transforms._common import (
    TIER_EPISODE_RENDER,
    TIER_LABEL_TRACK,
    TIER_STILL,
    TIER_VIDEO_CUT,
    TIER_VIDEO_PANEL,
    adopt_output,
    cached_output,
    file_url,
    fresh_equivalent,
    graph_index,
    media_artifact,
    node_ref,
    resolve_parents,
    require_tier,
    safe_duration,
    url_to_path,
)
from braidio.video import DEFAULT_FPS, DEFAULT_SIZE

RENDER_NAME = "video_cut.render"
FINISH_NAME = "video_cut.finish"

#: Where a cut's files land inside the project.
_CUTS_DIR = ("data", "cuts")
#: Default hold of the credits roll, when one is asked for (``credits_s``).
DEFAULT_CREDITS_S = 8.0
#: Default caption wrap (a player's two lines).
DEFAULT_CAPTION_CHARS = 42
#: Default delivery for tituli's reserved zones (the subtitle band + controls).
DEFAULT_DELIVERY = "youtube"
#: The tituli slot each label-track kind lands in when the body names none.
_KIND_SLOTS = {
    "title": "center",
    "context": "top-left",
    "note": "top-left",
    "tag": "bottom-left",
}
#: Weight of a per-still label — lighter than any card (whose default is 2).
_LABEL_WEIGHT = 1


# --- the move ---------------------------------------------------------------


def resolve_move(move, *, image, aspect: float, zoom=1.18, focus=None, seed=0):
    """A ``BurnsPath`` for an authored ``move`` over ``image``.

    **Shim over burns' own.** The signature is burns' (plan §4):
    ``resolve_move(move, *, image, aspect, zoom, focus, seed) -> BurnsPath``,
    where ``move`` is a name from ``MOVES`` **or** an explicit ``BurnsPath`` /
    its ``to_dict()`` payload (the two front doors on one path), ``focus`` is
    a normalized ``(x, y, w, h)`` tuple overriding the saliency frame, and
    ``seed`` chooses what ``"auto"`` becomes and nothing else. When burns
    exports the name this delegates to it unconditionally; until it is on a
    released burns, the fallback below builds the same vocabulary from burns'
    shipped primitives (``content_aware_path_for`` for the pushes,
    ``ken_burns_path`` for the horizontal drifts, hand-built windows for the
    vertical ones and the hold).
    """
    import burns

    if hasattr(burns, "resolve_move"):
        return burns.resolve_move(
            move, image=image, aspect=aspect, zoom=zoom, focus=focus, seed=seed
        )
    return _fallback_resolve_move(
        move, image=image, aspect=aspect, zoom=zoom, focus=focus, seed=seed
    )


def _fallback_resolve_move(move, *, image, aspect, zoom, focus, seed):
    from burns import BurnsPath, Rect, content_aware_path, ken_burns_path
    from burns.content import content_aware_path_for, salient_box
    from PIL import Image

    if isinstance(move, BurnsPath):
        return move
    if isinstance(move, dict):
        return BurnsPath.from_dict(move)
    if move not in MOVES:
        raise ValueError(f"resolve_move: {move!r} is not one of {MOVES}")
    box = None
    if focus is not None:
        x, y, w, h = (float(v) for v in focus)
        box = (x, y, x + w, y + h)
    if move == "hold":
        full = Rect(0.0, 0.0, 1.0, 1.0)
        return BurnsPath.from_start_end(full, full, output_aspect=aspect)
    if move in ("push_in", "pull_out", "auto"):
        mode = {"push_in": "in", "pull_out": "out", "auto": "auto"}[move]
        if box is None:
            return content_aware_path_for(
                str(image), index=int(seed), output_aspect=aspect, zoom=zoom, mode=mode
            )
        with Image.open(image) as img:
            iw, ih = img.size
        return content_aware_path(
            iw,
            ih,
            subject=box,
            index=int(seed),
            output_aspect=aspect,
            zoom=zoom,
            mode=mode,
        )
    if move in ("drift_left", "drift_right"):
        # ken_burns_path drifts right on odd indices, left on even.
        index = 1 if move == "drift_right" else 2
        return ken_burns_path(index, style="drift", output_aspect=aspect)
    # vertical drift: a constant-zoom window sliding up or down through the image
    subject = box if box is not None else salient_box(str(image))
    cx = (subject[0] + subject[2]) / 2.0
    z = max(1.05, float(zoom))
    w, h = 1.0 / z, 1.0 / z
    travel = min(0.5 * (1.0 - h), 0.08)
    ys = (
        (0.5 - travel, 0.5 + travel)
        if move == "drift_down"
        else (0.5 + travel, 0.5 - travel)
    )
    x = min(max(cx - w / 2.0, 0.0), 1.0 - w)
    start = Rect(x, min(max(ys[0] - h / 2.0, 0.0), 1.0 - h), w, h)
    end = Rect(x, min(max(ys[1] - h / 2.0, 0.0), 1.0 - h), w, h)
    return BurnsPath.from_start_end(start, end, output_aspect=aspect)


def path_for_panel(panel_body: dict, *, image, aspect: float):
    """The ``BurnsPath`` a panel body asks for over ``image``.

    One code path, two front doors: a stored ``path`` (a hand-corrected
    move) is handed to :func:`resolve_move` as the move itself and returned
    as authored; otherwise the named ``move`` resolves against the image with
    the panel's ``zoom`` / ``focus`` / ``seed``. A stored path that names no
    ``output_aspect`` takes the cut's, so a path authored before the delivery
    size was chosen still fills the frame.
    """
    stored = panel_body.get("path")
    if stored:
        move = dict(stored)
        if move.get("output_aspect") is None:
            move["output_aspect"] = aspect
    else:
        move = str(panel_body.get("move", "auto"))
    focus = panel_body.get("focus")
    return resolve_move(
        move,
        image=image,
        aspect=aspect,
        zoom=float(panel_body.get("zoom", 1.18)),
        focus=None
        if focus is None
        else (focus["x"], focus["y"], focus["w"], focus["h"]),
        seed=int(panel_body.get("seed", 0)),
    )


# --- shared resolution ------------------------------------------------------


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, default=str)


def _interval_s(ann: Annotation) -> tuple[float, float]:
    iv = ann.reference.interval
    return iv.start.to_seconds(), iv.end.to_seconds()


def _ordered_panels(panels) -> list[Annotation]:
    return sorted(panels, key=lambda p: int(p.body.get("order", 0)))


def _panels_from_ids(ids, index: dict) -> list[Annotation]:
    out = []
    for sid in ids:
        panel = index.get(uuid.UUID(str(sid)))
        if panel is None or panel.tier != TIER_VIDEO_PANEL:
            raise ValueError(f"video cut: panel {sid} is not in the graph")
        out.append(panel)
    return _ordered_panels(out)


def _still_of(panel: Annotation, index: dict) -> Annotation:
    still = index.get(uuid.UUID(str(panel.body["still_id"])))
    if still is None or still.tier != TIER_STILL:
        raise ValueError(
            f"video cut: panel {panel.id} points at still {panel.body['still_id']}, "
            "which is not a still in the graph"
        )
    return still


def _episode_of(panels, index: dict) -> Annotation:
    episodes = {
        p.id: p
        for panel in panels
        for p in resolve_parents(panel, index)
        if p.tier == TIER_EPISODE_RENDER
    }
    if len(episodes) != 1:
        raise ValueError(
            f"video cut: the panels derive from {len(episodes)} episodes; a cut is "
            "made against exactly one"
        )
    return next(iter(episodes.values()))


def _local_path(ann: Annotation, what: str) -> Path:
    url = ann.body.get("url")
    if not url:
        raise ValueError(f"video cut: {what} {ann.id} has no url — nothing to read")
    path = url_to_path(url)
    if not path.exists():
        raise FileNotFoundError(f"video cut: {what} {ann.id}: {path} is missing")
    return path


def _cuts_dir(project) -> Path:
    return project.root.joinpath(*_CUTS_DIR)


def _probe_geometry(video: Path) -> tuple[int | None, int | None, int | None]:
    """``(width, height, fps)`` of the first video stream, or ``None``s."""
    if shutil.which("ffprobe") is None:
        return None, None, None
    try:
        out = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate",
                "-of",
                "csv=p=0",
                str(video),
            ],
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        w, h, rate = out.split(",")[:3]
        num, _, den = rate.partition("/")
        fps = round(float(num) / float(den or 1))
        return int(w), int(h), int(fps)
    except Exception:  # noqa: BLE001 — geometry is advisory
        return None, None, None


def _complete(skel: Annotation, artifact, out_path: Path, **extra) -> Annotation:
    width, height, fps = _probe_geometry(out_path)
    return skel.model_copy(
        update={
            "body": {
                **skel.body,
                "artifact_id": artifact.asset_id,
                "url": file_url(out_path),
                "duration_s": artifact.duration_s or 0.0,
                "width": width or skel.body.get("width"),
                "height": height or skel.body.get("height"),
                "fps": fps or skel.body.get("fps"),
                **extra,
            }
        }
    )


def _reuse(project, skel: Annotation):
    """The idempotent / compare-and-skip half every render Transform shares."""
    existing = fresh_equivalent(project, skel)
    if existing is None:
        hit = cached_output(project, TIER_VIDEO_CUT, skel.body["cache_key"])
        if hit is not None:
            existing = adopt_output(skel, hit)
            project.graph.add_annotation(existing)
    if existing is None:
        return None
    return TransformResult(annotations=(existing,), artifacts=(), cost_usd_actual=0.0)


# --- video_cut.render -------------------------------------------------------


def _crop_still(src: Path, crop: dict | None, workdir: Path) -> Path:
    """``src`` cropped to ``crop`` (a RectV1 dump), cached by content + crop."""
    if not crop:
        return src
    from PIL import Image

    tag = hashlib.sha256(f"{src.resolve()}|{_json(crop)}".encode()).hexdigest()[:16]
    dst = workdir / f"crop_{tag}.jpg"
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    with Image.open(src) as img:
        img = img.convert("RGB")
        w, h = img.size
        box = (
            round(crop["x"] * w),
            round(crop["y"] * h),
            round((crop["x"] + crop["w"]) * w),
            round((crop["y"] + crop["h"]) * h),
        )
        img.crop(box).save(dst, quality=96)
    return dst


@register_transform(RENDER_NAME)
class VideoCutRender(BaseTransform):
    """Panels (+ their stills + the episode audio) → ``video-cut/v1`` (motion)."""

    name = RENDER_NAME
    input_kinds = (VIDEO_PANEL_V1, STILL_V1, EPISODE_RENDER_V1)
    output_kind = VIDEO_CUT_V1
    is_batch = True

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        from nw.transforms import cache_key as transform_cache_key

        params = dict(params or {})
        panels = _ordered_panels(
            [a for a in inputs.primary if a.tier == TIER_VIDEO_PANEL]
        )
        if not panels:
            raise ValueError(f"{RENDER_NAME}: needs at least one video-panel")
        index = graph_index(project)
        episode = _episode_of(panels, index)
        audio_id = episode.body.get("artifact_id")
        if not audio_id:
            raise ValueError(
                f"{RENDER_NAME}: episode {episode.id} has no rendered audio"
            )
        stills = [_still_of(p, index) for p in panels]

        size = tuple(int(v) for v in params.get("size", DEFAULT_SIZE))
        fps = int(params.get("fps", DEFAULT_FPS))
        parts = [str(audio_id), _json(size), str(fps)]
        for panel, still in zip(panels, stills):
            start, end = _interval_s(panel)
            parts += [
                str(still.body["artifact_id"]),
                _json(still.body.get("crop")),
                f"{start:.3f}",
                f"{end:.3f}",
                str(panel.body.get("move")),
                str(panel.body.get("zoom")),
                _json(panel.body.get("focus")),
                _json(panel.body.get("path")),
                str(panel.body.get("seed")),
            ]
        cache_key = transform_cache_key(self, "video-cut-motion", *parts)

        unique_stills = list({s.id: s for s in stills}.values())
        full = TransformInputs(
            primary=tuple(panels),
            context={STILL_V1: tuple(unique_stills), EPISODE_RENDER_V1: (episode,)},
        )
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_VIDEO_CUT,
            reference=node_ref(TIER_VIDEO_CUT),
            body=VideoCutBodyV1(
                label=str(params.get("label", "motion")),
                stage="motion",
                profile=str(episode.body.get("profile", "personal")),
                audio_artifact_id=str(audio_id),
                panel_ids=tuple(str(p.id) for p in panels),
                cache_key=cache_key,
                settings={"size": list(size), "fps": fps},
            ).model_dump(mode="json"),
            body_schema_uri=VIDEO_CUT_V1,
            provenance=derive_provenance(self, full, attributed_to="agent:braidio"),
        )
        return Plan(calls=()), (skeleton,)

    def execute(
        self,
        project,
        plan: Plan,
        skeleton: tuple[Annotation, ...],
        *,
        use_cache: bool = True,
        force: bool = False,
    ) -> TransformResult:
        import braidio.video as video  # runtime attr access: tests patch render_video

        skel = skeleton[0]
        if use_cache and not force:
            reused = _reuse(project, skel)
            if reused is not None:
                return reused

        index = graph_index(project)
        panels = _panels_from_ids(skel.body["panel_ids"], index)
        episode = require_tier(resolve_parents(skel, index), TIER_EPISODE_RENDER)
        audio_path = _local_path(episode, "episode")
        size = tuple(skel.body["settings"]["size"])
        fps = int(skel.body["settings"]["fps"])
        aspect = size[0] / size[1]

        workdir = _cuts_dir(project) / "_frames"
        video_panels = []
        bodies_by_still: dict[str, dict] = {}
        for panel in panels:
            still = _still_of(panel, index)
            src = _crop_still(
                _local_path(still, "still"), still.body.get("crop"), workdir
            )
            start, end = _interval_s(panel)
            video_panels.append(
                video.Panel(start, end, str(src), zoom=float(panel.body["zoom"]))
            )
            bodies_by_still[str(src)] = panel.body

        def path_for(canvas, i, panel):
            return path_for_panel(panels[i].body, image=canvas, aspect=aspect)

        out_path = _cuts_dir(project) / f"{skel.id}_motion.mp4"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        video.render_video(
            video_panels,
            audio_path=audio_path,
            out_path=out_path,
            size=size,
            fps=fps,
            workdir=workdir,
            path_for=path_for,
        )
        artifact = media_artifact(
            out_path,
            kind="video",
            transform_name=self.name,
            derived_from=skel.provenance.was_derived_from,
            duration_s=safe_duration(out_path),
            mime="video/mp4",
        )
        completed = _complete(skel, artifact, out_path)
        project.graph.add_annotation(completed)
        return TransformResult(
            annotations=(completed,),
            artifacts=(artifact,),
            cost_usd_actual=0.0,
            cache_hit_savings_usd=0.0,
        )


# --- video_cut.finish -------------------------------------------------------


def _finish_settings(motion: Annotation, params: dict) -> dict:
    return {
        **dict(motion.body.get("settings") or {}),
        "delivery": str(params.get("delivery", DEFAULT_DELIVERY)),
        "captions": bool(params.get("captions", True)),
        "burn_captions": bool(params.get("burn_captions", False)),
        "caption_chars": int(params.get("caption_chars", DEFAULT_CAPTION_CHARS)),
        "credits_s": float(params.get("credits_s", 0.0)),
        "credits_heading": str(params.get("credits_heading", "Images")),
    }


def _captions_srt(project, episode: Annotation, *, max_chars: int) -> str:
    from braidio.captions import captions_for
    from braidio.transforms._episode import episode_script, episode_timeline

    return captions_for(
        episode_script(project, episode),
        episode_timeline(project, episode),
        max_chars=max_chars,
    )


def _card_payload(body: dict) -> tuple[dict, str]:
    """``(tituli payload, slot)`` for a label-track body."""
    kind = str(body["kind"])
    lines = [str(l) for l in body.get("lines", ())]
    headline = body.get("headline") or (lines[0] if lines else "")
    rest = lines if body.get("headline") else lines[1:]
    if kind == "title":
        payload = {"kind": "title", "text": headline, "subtitle": " ".join(rest)}
    elif kind == "tag":
        payload = {"kind": "lower_third", "text": headline, "role": " ".join(rest)}
    else:
        payload = {"kind": "note", "text": headline, "lines": rest}
    return payload, str(body.get("slot") or _KIND_SLOTS[kind])


def _overlays(panels, stills_by_id: dict, label_tracks):
    """The resolved tituli overlays for a finish: cards, then per-still labels."""
    from tituli import UNLABELLED, Label, Span, TimedOverlay, resolve, schedule_labels

    cards = []
    for track in label_tracks:
        start, end = _interval_s(track)
        payload, slot = _card_payload(track.body)
        cards.append(
            TimedOverlay(
                None,
                start,
                end,
                slot=slot,
                weight=int(track.body.get("weight", 2)),
                payload=payload,
            )
        )
    spans = []
    for panel in panels:
        start, end = _interval_s(panel)
        spans.append(Span(start, end, key=str(panel.body["still_id"])))

    def label_for(span):
        body = stills_by_id[span.key].body
        if not body["labelled"]:
            return UNLABELLED
        return Label(str(body["subject"]), _short_attribution(body), key=body["key"])

    labels = schedule_labels(
        spans, label_for, suppressed_by=cards, weight=_LABEL_WEIGHT
    )
    return resolve([*cards, *labels])


def _short_attribution(body: dict) -> str:
    parts = [body.get("author"), body.get("license")]
    return " · ".join(str(p).strip() for p in parts if p and str(p).strip())


def _credit_lines(panels, stills_by_id: dict) -> list[str]:
    """One credit per still, in order of first use — raising on a missing licence."""
    seen: list[str] = []
    for panel in panels:
        key = str(panel.body["still_id"])
        if key not in seen:
            seen.append(key)
    return [credit_line(stills_by_id[k].body) for k in seen]


def _append_credits(
    film: Path,
    lines: list[str],
    dst: Path,
    *,
    size,
    fps: int,
    hold_s: float,
    heading: str,
) -> Path:
    """``film`` with a tituli credits roll appended, the audio padded to match."""
    from tituli import Credits, credits_cards, credits_frame, render
    from tituli.video import ffmpeg_path, frames_to_video

    frame = credits_frame(size)
    cards = credits_cards(Credits.from_lines(lines, heading=heading), frame=frame)
    per_card = max(1, round(hold_s / len(cards) * fps))

    def frames():
        for card in cards:
            img = render(card, frame).convert("RGB")
            for _ in range(per_card):
                yield img

    roll = dst.with_name(dst.stem + "_credits.mp4")
    frames_to_video(frames(), roll, size=size, fps=fps)
    pad = per_card * len(cards) / fps
    subprocess.run(
        [
            ffmpeg_path(),
            "-y",
            "-loglevel",
            "error",
            "-i",
            str(film),
            "-i",
            str(roll),
            "-filter_complex",
            f"[0:a]apad=pad_dur={pad:.3f}[a];[0:v][1:v]concat=n=2:v=1:a=0[v]",
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-shortest",
            str(dst),
        ],
        check=True,
        capture_output=True,
    )
    roll.unlink(missing_ok=True)
    return dst


@register_transform(FINISH_NAME)
class VideoCutFinish(BaseTransform):
    """A motion cut (+ label tracks, panels, stills) → ``video-cut/v1`` (delivered)."""

    name = FINISH_NAME
    input_kinds = (VIDEO_CUT_V1, LABEL_TRACK_V1, VIDEO_PANEL_V1, STILL_V1)
    output_kind = VIDEO_CUT_V1

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        import nw
        from nw.transforms import cache_key as transform_cache_key

        params = dict(params or {})
        motion = inputs.primary[0]
        if motion.tier != TIER_VIDEO_CUT or motion.body.get("stage") != "motion":
            raise ValueError(
                f"{FINISH_NAME}: the first primary input must be a motion cut"
            )
        if not motion.body.get("artifact_id"):
            raise ValueError(
                f"{FINISH_NAME}: motion cut {motion.id} is not rendered yet"
            )
        explicit_tracks = [a for a in inputs.primary[1:] if a.tier == TIER_LABEL_TRACK]
        tracks = explicit_tracks or list(
            nw.annotations_at_tier(project.root, TIER_LABEL_TRACK)
        )
        tracks = sorted(tracks, key=_interval_s)

        index = graph_index(project)
        panels = _panels_from_ids(motion.body["panel_ids"], index)
        stills = {str(p.body["still_id"]): _still_of(p, index) for p in panels}
        episode = require_tier(resolve_parents(motion, index), TIER_EPISODE_RENDER)
        settings = _finish_settings(motion, params)

        parts = [str(motion.body["artifact_id"]), _json(settings)]
        for track in tracks:
            parts += [_json(track.body), _json(_interval_s(track))]
        for panel in panels:
            still = stills[str(panel.body["still_id"])]
            parts += [
                _json(_interval_s(panel)),
                still.body["key"],
                str(still.body["labelled"]),
                str(still.body.get("subject")),
                _short_attribution(still.body),
            ]
        if settings["captions"]:
            parts.append(
                _captions_srt(project, episode, max_chars=settings["caption_chars"])
            )
        if settings["credits_s"] > 0:
            # raises now, at plan time, if a still has no licence to credit
            parts += _credit_lines(panels, stills)
        cache_key = transform_cache_key(self, "video-cut-finish", *parts)

        full = TransformInputs(
            primary=(motion, *tracks),
            context={
                VIDEO_PANEL_V1: tuple(panels),
                STILL_V1: tuple(stills.values()),
            },
        )
        skeleton = Annotation(
            id=uuid.uuid4(),
            tier=TIER_VIDEO_CUT,
            reference=node_ref(TIER_VIDEO_CUT),
            body=VideoCutBodyV1(
                label=str(params.get("label", motion.body.get("label", "cut"))),
                stage="delivered",
                profile=str(motion.body["profile"]),
                audio_artifact_id=str(motion.body["audio_artifact_id"]),
                panel_ids=tuple(motion.body.get("panel_ids", ())),
                cache_key=cache_key,
                settings=settings,
            ).model_dump(mode="json"),
            body_schema_uri=VIDEO_CUT_V1,
            provenance=derive_provenance(self, full, attributed_to="agent:braidio"),
        )
        return Plan(calls=()), (skeleton,)

    def execute(
        self,
        project,
        plan: Plan,
        skeleton: tuple[Annotation, ...],
        *,
        use_cache: bool = True,
        force: bool = False,
    ) -> TransformResult:
        skel = skeleton[0]
        if use_cache and not force:
            reused = _reuse(project, skel)
            if reused is not None:
                return reused

        index = graph_index(project)
        parents = resolve_parents(skel, index)
        motion = next(
            p
            for p in parents
            if p.tier == TIER_VIDEO_CUT and p.body.get("stage") == "motion"
        )
        tracks = sorted(
            (p for p in parents if p.tier == TIER_LABEL_TRACK), key=_interval_s
        )
        panels = _panels_from_ids(skel.body["panel_ids"], index)
        stills = {str(p.body["still_id"]): _still_of(p, index) for p in panels}
        episode = require_tier(resolve_parents(motion, index), TIER_EPISODE_RENDER)
        settings = dict(skel.body["settings"])
        size = tuple(settings["size"])
        fps = int(settings["fps"])

        cuts = _cuts_dir(project)
        cuts.mkdir(parents=True, exist_ok=True)
        current = _local_path(motion, "motion cut")
        stages: list[Path] = []
        extra: dict = {}

        overlays = _overlays(panels, stills, tracks)
        if overlays:
            from tituli.video import overlay

            staged = cuts / f"{skel.id}_labels.mp4"
            overlay(
                current,
                overlays,
                staged,
                size=size,
                delivery=settings["delivery"],
                workdir=cuts / "_overlays",
            )
            current = staged
            stages.append(staged)

        if settings["captions"]:
            srt = _captions_srt(project, episode, max_chars=settings["caption_chars"])
            srt_path = cuts / f"{skel.id}.srt"
            srt_path.write_text(srt, encoding="utf-8")
            captions = media_artifact(
                srt_path,
                kind="text",
                transform_name=self.name,
                derived_from=skel.provenance.was_derived_from,
                mime="application/x-subrip",
            )
            extra["captions_artifact_id"] = captions.asset_id
            if settings["burn_captions"]:
                from mixing.video import write_subtitles_in_video

                staged = cuts / f"{skel.id}_captioned.mp4"
                write_subtitles_in_video(str(current), str(srt_path), str(staged))
                current = staged
                stages.append(staged)

        if settings["credits_s"] > 0:
            staged = cuts / f"{skel.id}_credited.mp4"
            _append_credits(
                current,
                _credit_lines(panels, stills),
                staged,
                size=size,
                fps=fps,
                hold_s=settings["credits_s"],
                heading=settings["credits_heading"],
            )
            current = staged
            stages.append(staged)

        out_path = cuts / f"{skel.id}.mp4"
        if current == _local_path(motion, "motion cut"):
            shutil.copyfile(
                current, out_path
            )  # nothing to composite: the motion IS the cut
        else:
            shutil.move(str(current), out_path)
        for stage in stages:
            if stage.exists() and stage != out_path:
                stage.unlink()

        artifact = media_artifact(
            out_path,
            kind="video",
            transform_name=self.name,
            derived_from=skel.provenance.was_derived_from,
            duration_s=safe_duration(out_path),
            mime="video/mp4",
        )
        completed = _complete(skel, artifact, out_path, **extra)
        project.graph.add_annotation(completed)
        return TransformResult(
            annotations=(completed,),
            artifacts=(artifact,),
            cost_usd_actual=0.0,
            cache_hit_savings_usd=0.0,
        )
