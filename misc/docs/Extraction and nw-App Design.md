# braidio — extraction & nw-app design

How braidio is built: a **pure functional core** (ships now) plus an optional
**nw-app layer** (graph bodies + transforms + provenance). Extracted from the
[Hamilton lyrics-podcast](https://github.com/thorwhalen/Hamilton) (Hamilton
issues #18/#28/#19), which is braidio's first consumer.

## The core insight

braidio is **two layers in one package**:

- **Functional core** — pure Python over files + numbers, doing the actual audio
  work. Deps: `mixing`, `elevenlabs`, `ffmpeg` on PATH. **Zero** `nw`/`lacing`
  dependency. This is what Hamilton consumes today.
- **nw-app layer** (optional) — `bodies/` (lacing schemas), `transforms/` (nw
  Transforms), `project.py` (`nw.Project` subclass). Its `execute()` phases
  *call into the core* to gain provenance, freshness, and partial re-render.
  Imported only when `nw` is available — `import braidio` never requires it.

## Module layout

```
braidio/
  __init__.py            facade: re-export core; guarded import of nw layer
  # ── functional core ──
  script.py              Script, Narration, SegmentBeat, Beat, narration_segments
  sources.py             SegmentSource(Protocol), ResolvedSegment, TimedLine, TimedLineSegmentSource
  tts.py                 narrate, resolve_voice_id, DEFAULT_*, VOICE_ENV_VAR=BRAIDIO_TTS_VOICE
  delivery.py            Delivery, DELIVERIES (baseline/v2-tuned/v2-aggressive/v3-*)
  multivoice.py          Voice, POOL_4/POOL_MANY, split_segments, group_turns, assign_voices, render_multivoice
  compose.py             compose_narration(segments, config)
  weave.py               TimelineItem, extract_padded, weave_timeline, layout_starts, duration_s
  weave_config.py        WeaveConfig, PRESETS
  rights.py              Profile, RightsPolicy, plan_production, find_verbatim_text, content_violations
  render.py              render_production(script, *, source, config, ...) -> Path
  # ── nw-app layer (optional; deps: nw, lacing, falaw) ──
  kinds.py               WeaveKind ("commentary_weave")
  project.py             Project(nw.Project)
  bodies/                weave-config / source-media / commentary / segment-ref /
                         voice-assignment / narration-render / segment-extraction / episode-render
  transforms/            commentary→voice-assignment, commentary→narration (TTS),
                         segment-ref→extraction, weave→episode (batch N→1)
```

## How braidio is an nw app

**Mechanism = import-time registry population + `Project` subclassing.** No entry
points, no manifest (nw has none). On `import braidio.project`:

1. `bodies/__init__.py` imports each body module; each calls
   `lacing.schema.register_body_schema(URI, Model)` at module scope.
2. `transforms/__init__.py` imports each transform; each is decorated
   `@register_transform("<name>")` into nw's transform registry.
3. `class Project(nw.Project)` overrides `init()` to seed the singleton
   `weave-config/v1` node (the production-kind marker, like reelee's
   `output-intent/v1`).

**Defers to the substrate (reimplements none of it):** folder/graph/freshness
(`nw.Project`, `nw.stale_after`), provenance edges
(`nw.transforms._provenance.derive_provenance`), plan/execute + cost
(`nw.Transform` + `falaw`), content-addressed artifacts + cache
(`lacing.Artifact` + falaw), audio DSP/TTS (`mixing`), video (`reelee`).
Explicitly **does not** use `nw.workflow`/`nw.renderers.Strategy` (both are
shot/mp4-hardcoded); braidio lives on the Transform + body-schema + provenance
seams, exactly as reelee does. Generalizing nw's shot-specific render-provenance
is tracked in [nw#9](https://github.com/thorwhalen/nw/issues/9).

## Key abstractions (to introduce)

- **`SegmentSource` protocol** — `resolve(reference) -> ResolvedSegment | None`
  (`asset_path`, `start_s`, `end_s`). Makes lyrics/audiobook/news/SFX resolution
  pluggable. `TimedLineSegmentSource` is a generic token-F1 matcher over timed
  lines; Hamilton's lyric alignment becomes a `LyricsSegmentSource` adapter.
- **Generalized composition** — `Script`/`Narration`/`SegmentBeat` replace
  song-specific `EpisodeScript`/`Clip`; `song_position` disappears (all source
  addressing lives in the `SegmentSource`).
- **Pluggable rights** — `RightsPolicy(forbidden_texts, publishable_clip_rights)`
  injects the forbidden-content provider; braidio owns the profile filter +
  verbatim scanner, the consumer supplies *what* is forbidden.
- **Generalized render** — `render_production(script, *, source, config, ...)`;
  the Hamilton `song_audio + timing + cut_quote` path collapses to
  `source.resolve(ref)` → `extract_padded(...)`.

## Video-readiness (doors kept open, not by patch)

The woven timeline is **data, not media** (`episode-render/v1` annotations);
`SegmentSource` addresses any time-indexed asset; `WeaveConfig` extends
additively for visual knobs; braidio stays off nw's shot/mp4 seam; reelee is the
proven video sibling registering into the *same* nw registries. A `"visual"`
`TimelineItem.kind` and a `VideoClipSource` drop in with no change to `Script`,
`SegmentSource`, `WeaveConfig`, `RightsPolicy`, or the graph vocabulary.

## Migration status

Green-gate: Hamilton's full suite + braidio's suite.

- ✅ **Steps 1–3 (done, merged):** scaffold braidio; move the zero-coupling core
  (`weave`, `weave_config`, `delivery`, `compose`, `tts`, `multivoice`).
  Hamilton's modules are now deprecated shims re-exporting braidio; 49 Hamilton
  tests + 18 braidio tests green.
- ⏳ **Steps 4–7 (staged):** `sources.py` (generalize align), `script.py`
  (generalize EpisodeScript), rights mechanism, `render_production`.
- ⏳ **Step 8:** split the graph vocabulary (generic bodies → braidio, Genius
  bodies stay in Hamilton), keeping URIs identical.
- ⏳ **Step 10:** the nw-app layer (bodies/transforms/project), landing
  alongside/after nw#9.

## Open decisions (see Hamilton #28)

- **D1** nw-layer packaging: in-package guarded import (recommended) vs a
  separate `braidio_nw`.
- **D2** one `bodies/` package for authoring + render nodes (recommended) vs a
  `bodies/render/` split.
- **D3** voice resolution via env var (recommended: constant + param override).
- **D4** ElevenLabs coupling: keep presets now, abstract a `VoiceEngine` only
  when a second provider appears (defer).
- **D5** confirm `Profile` enum values (`personal|published`) before the rights
  move to avoid a serialization break.
