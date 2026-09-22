# braidio.video

Turn a rendered production into a Ken Burns film over still images.

braidio’s delegation table sends *video render* to `reelee` – and still does
for anything with generated footage, characters or shots. This module is the one
case reelee cannot serve: reelee imports braidio, so braidio cannot import
reelee. What it needs instead is a leaf dependency, and pan/zoom over stills is
exactly that: `burns` owns the motion, this module owns *where the cuts go*,
which is braidio-specific knowledge because only braidio knows where a beat ends.

**Optional layer.** Nothing here is imported by `braidio/__init__` eagerly and
no function-level dependency is imported at module scope, so `import
braidio.video` succeeds with nothing extra installed. `HAS_VIDEO` reports
whether the render path’s dependencies (`braidio[video]` -> `burns`,
`pillow`) are actually present; [`plan_spans()`](#braidio.video.plan_spans) and [`assign_stills()`](#braidio.video.assign_stills)
are pure and work regardless.

The seams, and what each defaults to:

Deliberately *not* seams: sentence splitting, the credits-card layout, the
panel-length bounds. They are written directly, with constants at module top.

Why the blurred fill: a pool of found stills mixes portrait and landscape, and
cover-cropping a tall image into a wide frame throws most of it away. Compositing
onto a blurred, darkened enlargement of the image itself keeps the whole picture
and never shows dead black bars.

### Functions

| [`assign_stills`](#braidio.video.assign_stills)(spans, stills, \*[, zoom])       | Attach stills to `spans`, cycling so none repeats back-to-back.      |
|-------------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`credits_card`](#braidio.video.credits_card)(lines, dst, \*[, heading, ...])   | Render an end card listing `lines`, **fitted** so none is lost.      |
| [`missing_dependencies`](#braidio.video.missing_dependencies)()                         | Which `braidio[video]` dependencies are absent (empty when ready).   |
| [`plan_spans`](#braidio.video.plan_spans)(timeline, \*[, min_panel_s, ...])   | Cut `timeline` into contiguous spans of roughly one still each.      |
| [`prepare_still`](#braidio.video.prepare_still)(src, dst, \*[, size])            | Composite `src` onto a blurred fill of itself at exactly `size`.     |
| [`render_video`](#braidio.video.render_video)(panels, \*, audio_path, out_path) | Render `panels` as one Ken Burns film and mux `audio_path` under it. |

### Classes

| [`Panel`](#braidio.video.Panel)(start, end, still[, style, zoom, label])   | A [`Span`](#braidio.video.Span) with a still and its camera move.   |
|---------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------|
| [`Span`](#braidio.video.Span)(start, end, beat_index[, kind, label])      | A stretch of screen time, before any image is chosen for it.                                |

### *class* braidio.video.Panel(start, end, still, style='push', zoom=1.18, label='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A [`Span`](#braidio.video.Span) with a still and its camera move.

### *class* braidio.video.Span(start, end, beat_index, kind='', label='')

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

A stretch of screen time, before any image is chosen for it.

`beat_index` / `kind` / `label` carry the beat this came from, so a
caller assigning pictures can see what is being said over each span.

### braidio.video.assign_stills(spans, stills, , zoom=1.18)

Attach stills to `spans`, cycling so none repeats back-to-back.

This is the *mechanical* default. Which picture belongs over which sentence is
an authoring decision — it needs to know what is being said — so a caller that
cares builds [`Panel`](#braidio.video.Panel) objects directly and uses each span’s `label`
and `beat_index` to choose. This function is what you want when the stills
are interchangeable texture.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Panel`](#braidio.video.Panel)]

### Examples

```pycon
>>> spans = [Span(0, 5, 0), Span(5, 10, 1), Span(10, 15, 2)]
>>> [p.still for p in assign_stills(spans, ["a.jpg", "b.jpg"])]
['a.jpg', 'b.jpg', 'a.jpg']
>>> [p.style for p in assign_stills(spans, ["a.jpg", "b.jpg"])]
['push', 'drift', 'push']
```

### braidio.video.credits_card(lines, dst, , heading='Credits', footer='', size=(1920, 1080))

Render an end card listing `lines`, **fitted** so none is lost.

Reusing a photograph under CC BY / CC BY-SA is conditional on crediting it, so
for a film built from found images this card is part of the licence
compliance, not decoration. Generate `lines` from whatever manifest recorded
the fetches, so the card cannot drift from what was actually used.

Because it is compliance, it must not *silently* drop an attribution — and a
fixed 31px leading did exactly that past roughly thirty lines: the tail ran
off the bottom of the frame and the footer drew over whatever was left. A
forty-three-image film credited twenty-eight of them and looked fine.

So the type is fitted to the content instead. Leading shrinks first, then the
list goes to two columns, and only if it still will not fit does this raise —
which is the right failure, because a caller who cannot see the problem cannot
fix it. Pass a bigger `size` or split across two cards.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### braidio.video.missing_dependencies()

Which `braidio[video]` dependencies are absent (empty when ready).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### braidio.video.plan_spans(timeline, , min_panel_s=5.0, max_panel_s=9.0)

Cut `timeline` into contiguous spans of roughly one still each.

Cuts land on **beat boundaries** wherever a beat is already a comfortable
length, because that is where the narration actually changes subject. A beat
longer than `max_panel_s` is divided into equal parts (so a 30-second
passage becomes four panels rather than one stalled photograph); a beat
shorter than `min_panel_s` is merged forward into the next one rather than
producing a flicker.

The result is gapless and ordered: `spans[i].end == spans[i + 1].start`.

* **Parameters:**
  * **timeline** – a [`TimelineBreakdown`](braidio.timeline.md#braidio.timeline.TimelineBreakdown).
  * **min_panel_s** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – below this, a beat is merged into the following span.
  * **max_panel_s** ([`float`](https://docs.python.org/3/builtins/functions.html#float)) – above this, a beat is split into equal parts.
* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Span`](#braidio.video.Span)]
* **Returns:**
  Spans covering the whole production, in playback order.

### Examples

```pycon
>>> from braidio.timeline import build_timeline
>>> tl = build_timeline(kinds=["narration"], durations=[20.0])
>>> [round(s.duration, 2) for s in plan_spans(tl)]
[6.67, 6.67, 6.67]
```

A short beat does not become its own panel:

```pycon
>>> tl = build_timeline(kinds=["narration", "narration"], durations=[2.0, 8.0])
>>> len(plan_spans(tl))
1
```

### braidio.video.prepare_still(src, dst, , size=(1920, 1080))

Composite `src` onto a blurred fill of itself at exactly `size`.

Nothing is cropped away and no dead black bar appears, whatever the source
aspect. Idempotent: an existing `dst` is returned untouched, so re-running a
build does not redo the work.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### braidio.video.render_video(panels, , audio_path, out_path, size=(1920, 1080), fps=30, workdir=None, prepare=None, path_for=None, \*\*write_kwargs)

Render `panels` as one Ken Burns film and mux `audio_path` under it.

One `burns.ken_burns_film` pass rather than per-panel renders plus a concat:
that avoids a re-encode seam at every cut and a frozen frame at every panel
tail.

* **Parameters:**
  * **panels** ([`Sequence`](https://docs.python.org/3/library/typing.html#typing.Sequence)[[`Panel`](#braidio.video.Panel)]) – the stills and their screen time, in order.
  * **audio_path** – the finished mix. Its length should match the panels; pad it
    first if the film ends on a credits card.
  * **out_path** – mp4 to write.
  * **size** ([`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`int`](https://docs.python.org/3/builtins/functions.html#int), [`int`](https://docs.python.org/3/builtins/functions.html#int)]) – frame geometry and rate.
  * **fps** ([`int`](https://docs.python.org/3/builtins/functions.html#int)) – frame geometry and rate.
  * **workdir** – where prepared canvases are cached (default: next to `out_path`).
  * **prepare** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)]]) – still -> frame-sized image. Default [`prepare_still()`](#braidio.video.prepare_still).
  * **path_for** ([`Optional`](https://docs.python.org/3/library/typing.html#typing.Optional)[[`Callable`](https://docs.python.org/3/library/typing.html#typing.Callable)[[`...`](https://docs.python.org/3/builtins/constants.html#Ellipsis), [`object`](https://docs.python.org/3/builtins/functions.html#object)]]) – `(image_path, index, panel) -> BurnsPath`. Default is
    `burns.content_aware_path_for`, which frames on the image’s salient
    region so a slow push stays on the subject.
  * **\*\*write_kwargs** – forwarded to `burns.ken_burns_film`.
* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
* **Returns:**
  The written mp4 path.
