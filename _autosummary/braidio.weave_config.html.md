# braidio.weave_config

WeaveConfig — every editing choice for weaving narration + segments (#20).

One frozen config object that exposes **all** the knobs (casting, turns, pacing,
timing, clip weaving, loudness) so a composer picks combinations rather than
inheriting one hardcoded style (the “enable all choices” mandate of #18/#28).

Defaults come from `docs/research/podcast-audio-weaving-editing.md`. This
module is deliberately **Hamilton-agnostic** — no Genius/LRCLIB/episode imports —
so it can move to the reusable weave package unchanged (#19). It references the
generic voice pools/ids only.

The config is designed to serialize cleanly ([`WeaveConfig.to_dict()`](#braidio.weave_config.WeaveConfig.to_dict)) into a
`render-config` provenance node (#26), so a render is reproducible from its
recorded choices.

### Classes

| [`WeaveConfig`](#braidio.weave_config.WeaveConfig)([voices, pool_label, ...])   | All editing choices for a narration+segment weave.   |
|-------------------------------------------------------------------------------------------|------------------------------------------------------|

### *class* braidio.weave_config.WeaveConfig(voices=('JBFqnCBsd6RMkjVDRZzb', ), pool_label='single', voice_seed=7, avoid_immediate_repeat=True, model_id='eleven_multilingual_v2', voice_settings=<factory>, segmentation_unit='beat', min_turn=2, max_turn=4, speed_base=1.0, speed_jitter=0.04, crossfade_s=0.12, gap_turn_s=0.0, overlap_turn_s=0.0, clip_pre_roll_s=0.4, clip_post_roll_s=0.3, clip_fade_in_s=0.5, clip_fade_out_s=0.8, clip_min_len_s=2.2, clip_edge_overlap_s=0.5, duck_db=-15.0, target_lufs=-16.0, true_peak_dbtp=-1.0, sample_rate=44100)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

All editing choices for a narration+segment weave. Frozen + serializable.

#### *property* paces_narration *: [bool](https://docs.python.org/3/builtins/functions.html#bool)*

Whether a render cuts each narration beat into separately-spoken turns.

`False` (the default, `segmentation_unit="beat"`) is one TTS call per
beat — no intra-beat gaps, no per-turn speed, so `gap_turn_s` and
`speed_jitter` do nothing on the [`braidio.render.render_production()`](braidio.render.html.md#braidio.render.render_production)
path. Opt in by setting `segmentation_unit` to a smaller unit.

```pycon
>>> WeaveConfig().paces_narration
False
>>> WeaveConfig(segmentation_unit="sentence").paces_narration
True
```

#### to_dict()

Stable serialization for a `render-config` provenance node (#26).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### with_(\*\*changes)

Return a copy with fields overridden (e.g. `cfg.with_(min_turn=1)`).

* **Return type:**
  [`WeaveConfig`](#braidio.weave_config.WeaveConfig)
