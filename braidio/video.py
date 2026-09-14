"""Turn a rendered production into a Ken Burns film over still images.

braidio's delegation table sends *video render* to ``reelee`` -- and still does
for anything with generated footage, characters or shots. This module is the one
case reelee cannot serve: reelee imports braidio, so braidio cannot import
reelee. What it needs instead is a leaf dependency, and pan/zoom over stills is
exactly that: :mod:`burns` owns the motion, this module owns *where the cuts go*,
which is braidio-specific knowledge because only braidio knows where a beat ends.

**Optional layer.** Nothing here is imported by ``braidio/__init__`` eagerly and
no function-level dependency is imported at module scope, so ``import
braidio.video`` succeeds with nothing extra installed. :data:`HAS_VIDEO` reports
whether the render path's dependencies (``braidio[video]`` -> ``burns``,
``pillow``) are actually present; :func:`plan_spans` and :func:`assign_stills`
are pure and work regardless.

The seams, and what each defaults to:

===================== ====================================== =========================
Seam                  v1 default                             Replaced by
===================== ====================================== =========================
where stills come     caller supplies paths; braidio fetches  any image source in the
from                  nothing (same rule as ``SegmentSource``) consuming app
camera motion         ``burns.content_aware_path_for``        any ``path_for=``
                      (saliency-framed, so a push does not    callable returning a
                      drift off a face)                       ``BurnsPath``
still -> frame        blurred-fill composite, nothing         any ``prepare=``
                      cropped away                            callable
===================== ====================================== =========================

Deliberately *not* seams: sentence splitting, the credits-card layout, the
panel-length bounds. They are written directly, with constants at module top.

Why the blurred fill: a pool of found stills mixes portrait and landscape, and
cover-cropping a tall image into a wide frame throws most of it away. Compositing
onto a blurred, darkened enlargement of the image itself keeps the whole picture
and never shows dead black bars.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Sequence

__all__ = [
    "HAS_VIDEO",
    "Panel",
    "Span",
    "assign_stills",
    "credits_card",
    "missing_dependencies",
    "plan_spans",
    "prepare_still",
    "render_video",
]

#: Default frame. 16:9 at 1080p is what every consumer player and upload wants.
DEFAULT_SIZE = (1920, 1080)
DEFAULT_FPS = 30

#: A still holds the screen this long. Under the floor it reads as a flicker;
#: over the ceiling a static photograph starts to feel stalled even while moving.
MIN_PANEL_S = 5.0
MAX_PANEL_S = 9.0

#: Blurred-fill background: blur hard and darken, so it reads as depth rather
#: than as a second picture competing with the foreground.
_BG_BLUR_PX = 42
_BG_BRIGHTNESS = 0.45

#: Alternating camera moves, so consecutive panels never travel the same way.
_STYLES = ("push", "drift")


def missing_dependencies() -> list[str]:
    """Which ``braidio[video]`` dependencies are absent (empty when ready)."""
    missing = []
    for mod, dist in (("burns", "burns"), ("PIL", "pillow")):
        try:
            __import__(mod)
        except ImportError:
            missing.append(dist)
    return missing


HAS_VIDEO = not missing_dependencies()


def _require() -> None:
    missing = missing_dependencies()
    if missing:
        raise ImportError(
            "braidio.video needs " + ", ".join(missing) + " — install braidio[video]"
        )


def _split_count(length: float, min_panel_s: float, max_panel_s: float) -> int:
    """How many panels a stretch of ``length`` should become.

    Ceiling division, so no panel exceeds ``max_panel_s`` -- ``round`` would let a
    20s beat become two 10s panels, over a 9s ceiling. But the ceiling yields to
    the floor: if splitting would make every part shorter than ``min_panel_s``, one
    slightly-too-long panel beats a row of flickers.

    Examples:
        >>> _split_count(20.0, 5.0, 9.0)   # 3 x 6.67, all under the ceiling
        3
        >>> _split_count(9.5, 5.0, 9.0)    # 2 x 4.75 would breach the floor
        1
        >>> _split_count(4.0, 5.0, 9.0)
        1
    """
    import math

    if length <= max_panel_s:
        return 1
    parts = math.ceil(length / max_panel_s)
    while parts > 1 and length / parts < min_panel_s:
        parts -= 1
    return parts


@dataclass(frozen=True)
class Span:
    """A stretch of screen time, before any image is chosen for it.

    ``beat_index`` / ``kind`` / ``label`` carry the beat this came from, so a
    caller assigning pictures can see what is being said over each span.
    """

    start: float
    end: float
    beat_index: int
    kind: str = ""
    label: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class Panel:
    """A :class:`Span` with a still and its camera move."""

    start: float
    end: float
    still: str
    style: str = "push"
    zoom: float = 1.18
    label: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start


def plan_spans(
    timeline,
    *,
    min_panel_s: float = MIN_PANEL_S,
    max_panel_s: float = MAX_PANEL_S,
) -> list[Span]:
    """Cut ``timeline`` into contiguous spans of roughly one still each.

    Cuts land on **beat boundaries** wherever a beat is already a comfortable
    length, because that is where the narration actually changes subject. A beat
    longer than ``max_panel_s`` is divided into equal parts (so a 30-second
    passage becomes four panels rather than one stalled photograph); a beat
    shorter than ``min_panel_s`` is merged forward into the next one rather than
    producing a flicker.

    The result is gapless and ordered: ``spans[i].end == spans[i + 1].start``.

    Args:
        timeline: a :class:`~braidio.timeline.TimelineBreakdown`.
        min_panel_s: below this, a beat is merged into the following span.
        max_panel_s: above this, a beat is split into equal parts.

    Returns:
        Spans covering the whole production, in playback order.

    Examples:
        >>> from braidio.timeline import build_timeline
        >>> tl = build_timeline(kinds=["narration"], durations=[20.0])
        >>> [round(s.duration, 2) for s in plan_spans(tl)]
        [6.67, 6.67, 6.67]

        A short beat does not become its own panel:

        >>> tl = build_timeline(kinds=["narration", "narration"], durations=[2.0, 8.0])
        >>> len(plan_spans(tl))
        1
    """
    beats = sorted(timeline.beats, key=lambda b: b.start)
    if not beats:
        return []

    # The weave crossfades beats, so spans would overlap if taken verbatim. Walk a
    # single cursor instead: each span runs from wherever the last one ended.
    spans: list[Span] = []
    cursor = beats[0].start
    pending: list = []

    for i, beat in enumerate(beats):
        pending.append(beat)
        is_last = i == len(beats) - 1
        end = beats[i + 1].start if not is_last else beat.start + beat.duration
        length = end - cursor
        if length < min_panel_s and not is_last:
            continue  # too short to stand alone — carry it into the next beat

        head = pending[0]
        parts = _split_count(length, min_panel_s, max_panel_s)
        step = length / parts
        for p in range(parts):
            spans.append(
                Span(
                    start=cursor + p * step,
                    end=cursor + (p + 1) * step,
                    beat_index=head.index,
                    kind=head.kind,
                    label=head.label,
                )
            )
        cursor = end
        pending = []

    return spans


def assign_stills(
    spans: Iterable[Span],
    stills: Sequence[str],
    *,
    zoom: float = 1.18,
) -> list[Panel]:
    """Attach stills to ``spans``, cycling so none repeats back-to-back.

    This is the *mechanical* default. Which picture belongs over which sentence is
    an authoring decision — it needs to know what is being said — so a caller that
    cares builds :class:`Panel` objects directly and uses each span's ``label``
    and ``beat_index`` to choose. This function is what you want when the stills
    are interchangeable texture.

    Examples:
        >>> spans = [Span(0, 5, 0), Span(5, 10, 1), Span(10, 15, 2)]
        >>> [p.still for p in assign_stills(spans, ["a.jpg", "b.jpg"])]
        ['a.jpg', 'b.jpg', 'a.jpg']
        >>> [p.style for p in assign_stills(spans, ["a.jpg", "b.jpg"])]
        ['push', 'drift', 'push']
    """
    if not stills:
        raise ValueError("assign_stills needs at least one still")
    out = []
    for i, span in enumerate(spans):
        out.append(
            Panel(
                start=span.start,
                end=span.end,
                still=str(stills[i % len(stills)]),
                style=_STYLES[i % len(_STYLES)],
                zoom=zoom,
                label=span.label,
            )
        )
    return out


def prepare_still(src, dst, *, size: tuple[int, int] = DEFAULT_SIZE) -> Path:
    """Composite ``src`` onto a blurred fill of itself at exactly ``size``.

    Nothing is cropped away and no dead black bar appears, whatever the source
    aspect. Idempotent: an existing ``dst`` is returned untouched, so re-running a
    build does not redo the work.
    """
    _require()
    from PIL import Image, ImageEnhance, ImageFilter

    dst = Path(dst)
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)

    width, height = size
    img = Image.open(src).convert("RGB")

    cover = max(width / img.width, height / img.height)
    bg = img.resize(
        (round(img.width * cover), round(img.height * cover)), Image.LANCZOS
    )
    left, top = (bg.width - width) // 2, (bg.height - height) // 2
    bg = bg.crop((left, top, left + width, top + height))
    bg = bg.filter(ImageFilter.GaussianBlur(_BG_BLUR_PX))
    bg = ImageEnhance.Brightness(bg).enhance(_BG_BRIGHTNESS)

    contain = min(width / img.width, height / img.height)
    fg = img.resize(
        (round(img.width * contain), round(img.height * contain)), Image.LANCZOS
    )
    bg.paste(fg, ((width - fg.width) // 2, (height - fg.height) // 2))
    bg.save(dst, quality=94)
    return dst


def credits_card(
    lines: Sequence[str],
    dst,
    *,
    heading: str = "Credits",
    footer: str = "",
    size: tuple[int, int] = DEFAULT_SIZE,
) -> Path:
    """Render an end card listing ``lines``.

    Reusing a photograph under CC BY / CC BY-SA is conditional on crediting it, so
    for a film built from found images this card is part of the licence
    compliance, not decoration. Generate ``lines`` from whatever manifest recorded
    the fetches, so the card cannot drift from what was actually used.
    """
    _require()
    from PIL import Image, ImageDraw, ImageFont

    def font(px: int):
        for candidate in (
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
        ):
            if Path(candidate).exists():
                return ImageFont.truetype(candidate, px)
        return ImageFont.load_default()

    width, height = size
    card = Image.new("RGB", (width, height), (12, 12, 14))
    draw = ImageDraw.Draw(card)
    draw.text((100, 62), heading, fill=(238, 238, 243), font=font(34))
    y = 140
    for line in lines:
        draw.text((100, y), line, fill=(186, 186, 198), font=font(21))
        y += 31
    if footer:
        draw.text((100, height - 78), footer, fill=(120, 120, 132), font=font(21))
    dst = Path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    card.save(dst, quality=94)
    return dst


def render_video(
    panels: Sequence[Panel],
    *,
    audio_path,
    out_path,
    size: tuple[int, int] = DEFAULT_SIZE,
    fps: int = DEFAULT_FPS,
    workdir=None,
    prepare: Callable[..., Path] | None = None,
    path_for: Callable[..., object] | None = None,
    **write_kwargs,
) -> Path:
    """Render ``panels`` as one Ken Burns film and mux ``audio_path`` under it.

    One ``burns.ken_burns_film`` pass rather than per-panel renders plus a concat:
    that avoids a re-encode seam at every cut and a frozen frame at every panel
    tail.

    Args:
        panels: the stills and their screen time, in order.
        audio_path: the finished mix. Its length should match the panels; pad it
            first if the film ends on a credits card.
        out_path: mp4 to write.
        size, fps: frame geometry and rate.
        workdir: where prepared canvases are cached (default: next to ``out_path``).
        prepare: still -> frame-sized image. Default :func:`prepare_still`.
        path_for: ``(image_path, index, panel) -> BurnsPath``. Default is
            ``burns.content_aware_path_for``, which frames on the image's salient
            region so a slow push stays on the subject.
        **write_kwargs: forwarded to ``burns.ken_burns_film``.

    Returns:
        The written mp4 path.
    """
    _require()
    from burns import content_aware_path_for, ken_burns_film

    if not panels:
        raise ValueError("render_video needs at least one panel")

    out_path = Path(out_path)
    workdir = Path(workdir) if workdir else out_path.parent / "_frames"
    prepare = prepare or prepare_still

    def default_path_for(image, index, panel):
        return content_aware_path_for(
            str(image),
            index=index,
            output_aspect=size[0] / size[1],
            zoom=panel.zoom,
            mode="in" if panel.style == "push" else "auto",
        )

    path_for = path_for or default_path_for

    triples = []
    for i, panel in enumerate(panels):
        canvas = prepare(
            panel.still, workdir / f"{i:03d}_{Path(panel.still).stem}.jpg", size=size
        )
        triples.append((str(canvas), path_for(canvas, i, panel), panel.duration))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    return ken_burns_film(
        triples,
        saveas=str(out_path),
        fps=fps,
        audio_path=str(audio_path),
        **write_kwargs,
    )


def with_credits(
    panels: Sequence[Panel], card: str | Path, *, duration_s: float
) -> list[Panel]:
    """Append a credits card to ``panels``, held for ``duration_s``.

    The audio must be padded to match — see the skill for the one-line ``ffmpeg``
    ``apad`` that does it.
    """
    last_end = panels[-1].end if panels else 0.0
    return [
        *panels,
        Panel(last_end, last_end + duration_s, str(card), style="drift", zoom=1.04),
    ]
