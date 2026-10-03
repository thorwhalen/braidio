# braidio.compose

Config-driven narration composition (#20) — the reusable entrypoint.

Turn a list of narration segments + a `WeaveConfig` into audio. Dispatches
single-voice and multi-voice uniformly (single = a pool of one), reading *every*
knob from the config. This is the seed of the reusable weave engine (#18/#19):
it has no Hamilton-specifics — it takes plain text segments and a config.

Clip weaving (padded extraction + ducking) is composed separately (#21); this
module renders the narration track.

### Functions

| [`compose_narration`](#braidio.compose.compose_narration)(segments, config, \*, out_path)   | Render `segments` under `config` → `out_path`.   |
|------------------------------------------------------------------------------------------------------|--------------------------------------------------|

### braidio.compose.compose_narration(segments, config, , out_path, api_key=None, work_dir='data/tts/compose')

Render `segments` under `config` → `out_path`.

Single-voice and multi-voice go through the same turn-based path (a single
voice is just a one-voice pool). Returns the `(voice, turn_text)`
assignment for reporting / provenance.

`api_key` is an optional per-request ElevenLabs key threaded to
[`braidio.multivoice.render_multivoice()`](braidio.multivoice.md#braidio.multivoice.render_multivoice) (and thence every synthesized
turn); `None` (default) keeps the `$ELEVENLABS_API_KEY` fallback.

Note `config.segmentation_unit` is **not** read here: this function is
handed `segments` already cut, so the unit was chosen upstream (usually
[`braidio.script.narration_segments()`](braidio.script.md#braidio.script.narration_segments)). It is the
[`braidio.render.render_production()`](braidio.render.md#braidio.render.render_production) path that cuts a beat itself, and
there the field is the switch that turns pacing on — see
[`braidio.pacing`](braidio.pacing.md#module-braidio.pacing).

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Voice`](braidio.multivoice.md#braidio.multivoice.Voice), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]]
