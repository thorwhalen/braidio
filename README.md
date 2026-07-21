# braidio

**Weave narration with extracted media segments into audiovisual productions.**

`braidio` braids two kinds of strand into one production: **authored narration**
(text-to-speech — a single voice or a cycled pool of voices) and **extracted
segments of source media** (song clips addressed by lyrics, audiobook passages,
news clips, sound effects). The result is a **network of linked artifacts** that
renders to an audiovisual object — audio today, with visual support to follow.

> Status: early. `braidio` is being extracted from the
> [Hamilton lyrics-podcast](https://github.com/thorwhalen/Hamilton) (its first
> application) into a reusable engine. APIs will move quickly.

## What it does

Given a **composition** (ordered narration beats interleaved with segment
references) and a **`WeaveConfig`** (every editing knob), braidio:

1. **casts voices** — one narrator, or a pool cycled across turns;
2. **synthesizes narration** — TTS with delivery presets, turn grouping, slight
   speed variation;
3. **extracts segments** — padded, faded cuts of a resolved `[start, end]` from
   a source asset (the *resolution* — quote → interval — is a pluggable
   `SegmentSource`);
4. **weaves** — places narration and segments on a timeline where clips tuck
   under the speech (speech stays dominant), with ducking, crossfades, and a
   loudness master;
5. renders the result — and records the **choices** as provenance, so a change
   re-renders only the affected parts.

## What it deliberately does *not* do

braidio is a thin orchestration layer. It **delegates**:

| Concern | Owner |
|---|---|
| Content acquisition (Genius, audiobooks, news…) | the consuming app, via `SegmentSource` adapters |
| Linked-artifact graph / content-addressed media | [`lacing`](https://github.com/thorwhalen/lacing) |
| Project workflow, provenance, plan/execute, partial re-render | [`nw`](https://github.com/thorwhalen/nw) |
| Video render + visual support | [`reelee`](https://github.com/thorwhalen/reelee) |
| Raw audio DSP + TTS (crop, concat, duck, loudnorm, synth) | [`mixing`](https://github.com/thorwhalen/mixing) / `falaw` |

braidio orchestrates these; it never reimplements the DSP or the graph.

## Ecosystem

`braidio` is a **production kind** on top of `nw` — a reusable definition of
"commentary that weaves narration with extracted media" — the way a music video
is another production kind. It sits on `lacing` (graph) + `nw` (workflow /
provenance) + `mixing`/`falaw` (audio/TTS), and will use `reelee` for video.

## Install

```bash
pip install braidio   # (once published)
```

## License

MIT
