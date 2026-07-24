# braidio

**Weave *commentary* — solo, duo, panel, debate, interview, documentary — with
source clips into a production.**

`braidio` braids the strands of a piece that talks *about* something (a song, a
book, a film, an event) into one rendered production. The **talk is the spine** —
a single presenter, two hosts, a panel, a narrator — and **source clips and
narration bridges are the "illustration" layers** woven onto it. Audio today,
with visual support to follow (it braids A/V — *braid-io*, and it sounds like
*radio*).

Two things braidio gives you:

1. **Ready-made format templates** under the standard, industry names people
   already recognize — *Deep Dive*, *Song Exploder-style*, *Panel*, *Debate*,
   *Documentary VO* — each a high-quality bundle of defaults you can render in one
   call.
2. **Full parametrization** underneath, so any style is expressible: a `Script`
   of beats, cast via a `ConversationCast`, tuned by `WeaveConfig` + `Delivery`,
   with per-beat voice/delivery overrides.

> Status: early. `braidio` is extracted from the
> [Hamilton lyrics-podcast](https://github.com/thorwhalen/Hamilton) (its first
> application) into a reusable engine. APIs will move quickly.

## The model

A production is a **`Script`** — an ordered list of **beats**:

| Beat | What it is |
|---|---|
| `Narration(text, voice?, voice_settings?, …)` | one voice reading — a narrator **or** a solo presenter. `voice` / `voice_settings` override per beat, so one timeline can carry a lively **presenter** *and* a graver **book-narrator**. |
| `Dialogue(turns=[(role, text)])` | a multi-speaker exchange, synthesized in **one pass** (so it sounds like people *talking to each other*, not alternating monologues). A `ConversationCast` maps roles → voices. |
| `SegmentBeat(reference)` | a span of source media to cut and weave in (resolved by a pluggable `SegmentSource` — quote → `[start, end]`). |

`WeaveConfig` holds every editing knob (casting, turns, pacing, clip pre/post-roll,
duck, crossfades, loudness). `Delivery` presets bundle the TTS model + voice
settings (e.g. `V2_PRESENTER` lively vs `V2_NARRATOR` grave). The renderer
loudness-normalizes every part, tucks clips under the speech (speech stays
dominant), and masters the result.

## Ready-made formats

Pick a standard format and render it — the template supplies the cast, voices,
delivery and mix defaults:

```python
from braidio import DEEP_DIVE, render_format

render_format(DEEP_DIVE, script, source=my_source, out_path="episode.mp3")
```

| Preset id | Standard name | Shape |
|---|---|---|
| `solo_explainer` | Solo-Presenter Explainer (video/audio essay, close reading) | one presenter + exhibits |
| `deep_dive` | Two-Host Conversation (*"Deep Dive"*, Switched on Pop, NotebookLM) | two hosts; one teaches, one probes |
| `interview` | Interview (host + guest) | Q→A, guest is the center |
| `interview_host_removed` | *Song Exploder*-style (host removed) | guest monologue; each claim illustrated by its isolated stem; full artifact at the tail |
| `panel` | Panel / Roundtable (Pop Culture Happy Hour) | moderator routes distinct voices |
| `debate` | Debate (Oxford-style) | proposition / opposition / moderator, phased |
| `documentary_vo` | Documentary Voice-Over (*"Voice of God"*, This American Life) | narrator on top; interviews + clips + actuality beneath |

**Narration bridges** and **source clips** are optional *illustration layers*
usable with any format. The taxonomy, weaving grammar, exemplar recipes and the
full template specs are in
[`misc/docs/research/commentary-formats-and-styles.md`](misc/docs/research/commentary-formats-and-styles.md).

*Render support note:* the cast, per-role voices, narration deliveries, loudness
master, and **per-clip placement** — `SegmentBeat(placement="before" | "under" |
"after")`, where `under` lays the clip concurrently beneath the talk, ducked —
are applied today. Music beds and scene stings are documented as authoring
conventions and remain on the render-side roadmap (braidio#1).

## Parametrize anything

The templates are just good defaults over the primitives — compose directly for
full control:

```python
from braidio import Script, Dialogue, Narration, SegmentBeat, WeaveConfig
from braidio.conversation import ConversationCast, JESSICA, CHRIS
from braidio import V2_NARRATOR, render_production

script = Script(title="…", id_slug="01", beats=[
    Dialogue((("A", "First thing that gets me…"), ("B", "right — but isn't that…"))),
    SegmentBeat("the lyric being discussed", label="hook"),
    Narration("Here's how the book tells it —",
               voice_settings=V2_NARRATOR.voice_settings),  # graver, per-beat
])
render_production(script, source=my_source,
                  cast=ConversationCast(roles={"A": JESSICA, "B": CHRIS}),
                  config=WeaveConfig(), out_path="out.mp3")
```

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
"commentary that weaves talk with extracted media" — the way a music video is
another production kind. It sits on `lacing` (graph) + `nw` (workflow /
provenance) + `mixing`/`falaw` (audio/TTS), and will use `reelee` for video. The
optional nw-app layer (`braidio.HAS_GRAPH` / `HAS_NW`) records render choices as
provenance so a change re-renders only the affected parts.

## Install

```bash
pip install braidio   # (once published)
```

## License

MIT
