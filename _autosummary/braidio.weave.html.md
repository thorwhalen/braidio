# braidio.weave

Weave narration + audio clips on a timeline (#21) — the reusable mix engine.

Two generic, Hamilton-agnostic primitives:

- [`extract_padded()`](#braidio.weave.extract_padded) — extract `[start, end]` from a source asset but
  **padded** by pre/post-roll (so the words are captured cleanly) with in/out
  fades on the padded edges. The padded, faded edges are what we tuck under the
  neighbouring narration.
- [`weave_timeline()`](#braidio.weave.weave_timeline) — place ordered narration/clip parts on a timeline
  where each clip **overlaps its neighbours** by `clip_edge_overlap_s` and its
  faded padded edges duck under the speech, so **speech stays dominant**, then
  mix (`amix` sum) and loudness-normalize.

This is the audio counterpart of a video timeline; it consumes plain file paths

+ numbers, no Genius/lyrics knowledge (that resolution lives in
  `graph/align.py` and the Hamilton adapters). Ducking here is achieved by
  fade-shaped overlap; a dynamic sidechain duck (`duck_db`) is a documented
  refinement (see #21 / the research).

### Functions

| `duration_s`(path)                                                                               |                                                                  |
|--------------------------------------------------------------------------------------------------|------------------------------------------------------------------|
| [`extract_padded`](#braidio.weave.extract_padded)(asset_path, start_s, end_s, ...) | Extract `[start_s-pre_roll, end_s+post_roll]` with in/out fades. |
| [`layout_placed`](#braidio.weave.layout_placed)(kinds, durs, placements, \*, ...) | Start offset (s) of each part, placement-aware.                  |
| [`layout_starts`](#braidio.weave.layout_starts)(kinds, durs, \*, ...)             | Start offset (s) of each part (all sequential).                  |
| [`weave_timeline`](#braidio.weave.weave_timeline)(items, out_path, \*[, ...])      | Place items on a timeline and mix.                               |

### Classes

| [`TimelineItem`](#braidio.weave.TimelineItem)(kind, path[, placement, ...])   | One part on the weave timeline.   |
|-----------------------------------------------------------------------------------------------|-----------------------------------|

### *class* braidio.weave.TimelineItem(kind, path, placement='sequential', duck_db=0.0, spotlight=False)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One part on the weave timeline.

`placement` `"sequential"` (default — narration, and clean `before` /
`after` clips) lays the part in its own slot. `"under"` overlays the part
beneath the *following* sequential part (it does not consume its own slot),
attenuated by `duck_db` — a ducked underlay (a clip talked over, or later a
music bed).

`spotlight` marks the part the music bed drops out for (fade-to-spotlight):
the bed is silent over this part’s span and resumes after it. Inert without
a bed.

### braidio.weave.extract_padded(asset_path, start_s, end_s, out_path, , pre_roll_s=0.4, post_roll_s=0.3, fade_in_s=0.5, fade_out_s=0.8, min_len_s=2.2)

Extract `[start_s-pre_roll, end_s+post_roll]` with in/out fades.

The target words sit in the middle; the padded, faded head/tail are the
parts that overlap (tuck under) neighbouring narration in the weave.

Two guards keep **short** clips from sounding like they just swell in and
out (no steady body):

- the tail is extended so the clip is at least `min_len_s` long, giving the
  fade somewhere to breathe;
- the fades are **adaptive** — capped to a fraction of the clip so they never
  swallow it (a 1.5 s clip gets ~0.3 s fades, not 0.5 s + 0.8 s).

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### braidio.weave.layout_placed(kinds, durs, placements, , clip_edge_overlap_s, narration_crossfade_s)

Start offset (s) of each part, placement-aware. Pure function.

Sequential parts advance a running cursor: a clip (or a part following a clip)
starts `clip_edge_overlap_s` before the cursor so its faded edges tuck under
the neighbour; narration-after-narration overlaps by `narration_crossfade_s`.
An `"under"` part starts *at* the cursor (concurrent with the next
sequential part) and does **not** advance it — so it overlays what follows.
Clamped ≥ 0.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

### braidio.weave.layout_starts(kinds, durs, , clip_edge_overlap_s, narration_crossfade_s)

Start offset (s) of each part (all sequential). Thin wrapper over
[`layout_placed()`](#braidio.weave.layout_placed) — kept for callers that don’t use placement.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`float`](https://docs.python.org/3/builtins/functions.html#float)]

### braidio.weave.weave_timeline(items, out_path, , clip_edge_overlap_s=0.5, narration_crossfade_s=0.12, target_lufs=-16.0, true_peak=-1.0, sample_rate=44100, bed=None)

Place items on a timeline and mix. Clips overlap neighbours by
`clip_edge_overlap_s` (their faded edges tuck under narration); narration
parts butt-join with a small crossfade. Returns `out_path`.

`bed` (a [`MusicBed`](braidio.music.html.md#braidio.music.MusicBed)) lays an instrumental underscore
under the whole production: it’s rendered to cover the timeline, attenuated,
and mixed in posted by `bed.lead_in_s`. Items marked `spotlight` open a
gap in it (the bed is rendered as the regions around them — see
[`braidio.music.bed_regions()`](braidio.music.html.md#braidio.music.bed_regions)); with none marked the bed is the single
whole-span file. Falls back to a plain concat feel when
`clip_edge_overlap_s == 0` and there’s nothing to overlay.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)
