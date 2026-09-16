# braidio.tts

ElevenLabs narration synthesis.

Thin wrapper over `mixing.text_to_speech()` (the ElevenLabs entry point,
with on-disk caching) applying a voice preset: the `eleven_multilingual_v2`
quality model and a locked voice + settings so a whole production sounds like
one narrator.

Voice defaults to “George — Warm, Captivating Storyteller”; override with the
`BRAIDIO_TTS_VOICE` env var (`VOICE_ENV_VAR`) or the `voice_id` arg.

### Functions

| [`narrate`](#braidio.tts.narrate)(text, out_path, \*[, api_key, ...])   | Synthesize `text` to `out_path` (mp3).                                         |
|------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------|
| [`resolve_voice_id`](#braidio.tts.resolve_voice_id)([voice_id])                  | Voice id from arg → `VOICE_ENV_VAR` env → default.                             |
| [`text_to_dialogue`](#braidio.tts.text_to_dialogue)(turns, \*[, model_id, ...])  | Synthesize a multi-speaker exchange in ONE pass (ElevenLabs Text-to-Dialogue). |

### braidio.tts.narrate(text, out_path, , api_key=None, voice_id=None, model_id='eleven_multilingual_v2', voice_settings=None, output_format='mp3_44100_128', refresh=False, return_cache_status=False)

Synthesize `text` to `out_path` (mp3). Returns the path.

Caching is handled by `mixing.text_to_speech` (keyed on text+voice+model);
pass `refresh=True` to regenerate.

`api_key` is an optional per-request ElevenLabs key: when given it wins
over the environment; when `None` (default) resolution falls back to
`$ELEVENLABS_API_KEY` (unchanged behavior). This is what lets a caller
thread a per-user BYO key without touching the process environment.

`return_cache_status`: when `True`, return `(path, was_cached)` where
`was_cached` is `True` iff mixing served the audio from its on-disk cache
(no ElevenLabs call = $0 real spend). Lets the caller attribute real cost
(braidio#8). Default `False` keeps the `Path` return.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path), [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]

### braidio.tts.resolve_voice_id(voice_id=None)

Voice id from arg → `VOICE_ENV_VAR` env → default.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### braidio.tts.text_to_dialogue(turns, , model_id='eleven_v3', output_format='mp3_44100_128', settings=None, seed=None, api_key=None, cache=True, refresh=False, return_cache_status=False)

Synthesize a multi-speaker exchange in ONE pass (ElevenLabs Text-to-Dialogue).

Unlike per-line [`narrate()`](#braidio.tts.narrate), this renders the whole conversation together
so prosody is conditioned across turns — the key to sounding like people
*talking to each other* rather than alternating monologues (see braidio#1 /
`docs/research/conversational-vs-narration-tts.md`). `eleven_v3` only.

**Cached** (like [`narrate()`](#braidio.tts.narrate)/`mixing.text_to_speech`): the result is
keyed on the SHA-256 of every parameter that affects the audio (turns,
voices, model, settings, seed, format). A cache hit returns the *same* bytes
instantly — no API call, deterministic master, and the basis for partial
re-render (change one exchange → only its key changes). `cache=True`
(default) uses `DIALOGUE_CACHE_ENV_KEY` / the default cache dir;
`cache=False` disables it; a path uses that dir. `refresh=True` forces a
re-render (to re-roll a v3 take). Because v3 is nondeterministic, caching a
seedless call freezes one random take — pass a `seed` for reproducibility.

* **Parameters:**
  * **turns** – ordered `(voice_id, text)` pairs (or `{"voice_id", "text"}`).
    Keep each request under ~2000 chars total (API limit).
  * **settings** ([`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict) | [`None`](https://docs.python.org/3/builtins/constants.html#None)) – optional model settings dict (e.g. `{"stability": 0.45}`).
  * **return_cache_status** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – when `True`, return `(audio, was_cached)` where
    `was_cached` is `True` iff the bytes came from the on-disk cache
    (no ElevenLabs call = $0 real spend) — the same attribution
    [`narrate()`](#braidio.tts.narrate) offers (braidio#8). Default `False` keeps the
    `bytes` return.
* **Return type:**
  [`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes) | [`tuple`](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[`bytes`](https://docs.python.org/3/builtins/stdtypes.html#bytes), [`bool`](https://docs.python.org/3/builtins/functions.html#bool)]
* **Returns:**
  raw audio bytes in `output_format`.
