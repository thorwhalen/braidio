# braidio — agent & contributor guide

`braidio` weaves **commentary** with **extracted source clips** into one rendered
audio production. Seven format presets ship today — `solo_explainer`,
`deep_dive`, `interview`, `interview_host_removed`, `panel`, `debate`,
`documentary_vo` (`braidio.formats.FORMATS` is the registry; there is no `duo`
preset — the two-host shape is `deep_dive`).
The talk is the spine; narration bridges and source clips are the
illustration layers. It is a thin **orchestration** layer: it owns the
composition model, the format templates, the rights projection and the cost
model, and delegates DSP/TTS to `mixing`, the graph to `lacing`, and the
workflow/provenance to `nw`.

## Read this first: braidio is live infrastructure

This is not an experiment. Three things depend on the code in this repo, so a
careless signature change has real blast radius:

| Consumer | What it uses | Failure mode if you break it |
|---|---|---|
| **PyPI** (`braidio`, published by CI on merge) | the whole public API | anyone installing the release |
| **`reelee`** — `reelee/transforms/panel_to_voiceover.py` | `braidio.narrate`, `braidio.render_dialogue`, `braidio.ConversationCast` (declared `braidio>=0.0.2`) | storyboard voiceover stops rendering |
| **Two deployed MCP connectors** | `braidio.mcp.TOOL_REFS` (own connector) and `braidio.mcp.register_tools(..., prefix="braidio_")` (aggregated into the unified AV connector) | a live tool surface breaks for real users mid-conversation |

Practical consequences:

- **`narrate`, `render_dialogue`, `ConversationCast` are a contract.** Adding a
  keyword-only arg with a default is fine; renaming, reordering, or changing a
  return type is a coordinated change with `reelee`.
- **The MCP tool signatures + docstrings *are* the wire schema.** A tool's
  parameters and its whole docstring are what the model sees, and the
  description is what tool search indexes.
  `tests/test_wire_descriptions.py` caps every wire description at
  `MAX_WIRE_DESCRIPTION_CHARS` (500) — long, jargon-dense descriptions measurably
  embed *away* from short user queries, which is how a tool once became
  unfindable on a live connector. Keep the wire to purpose + key constraint,
  in the user's vocabulary; put detail in `help` / `_guide.py` / docs.
- **`braidio.mcp.FREE_TOOLS` / `COSTED_TOOLS` are the money boundary.** A new
  tool that spends ElevenLabs credits MUST be listed in `COSTED_TOOLS`, not
  `FREE_TOOLS` — the deployed connector passes `metered_tools=set(COSTED_TOOLS)`
  to its metering middleware, so a costed tool in the wrong list is spend that
  no cap applies to. Count the surface with `len(braidio.mcp.TOOL_NAMES)` rather
  than quoting a number.

### How a change actually reaches production (the deploy coupling)

Merging to `main` here does **not** update the live connectors. The connector
app lives in the platform repo (`tw_platform`, app `braidio_mcp`); its venv
installs `braidio[mcp]` as an **unversioned git pin**, and the aggregated tools
ride along in the sibling `reelee_mcp` app the same way. The sequence is:

1. Merge to braidio `main` (CI bumps the version and publishes to PyPI).
2. Run a platform deploy. Its per-connector refresh step reads the app's
   `deploy/connector-requirements.txt`, compares each git requirement's
   installed commit against the remote, reinstalls the ones that moved with
   `--force-reinstall --no-deps`, and restarts the systemd unit only if
   something actually changed.
3. Confirm the connector reports the new commit.

Why the ceremony: **`pip install --upgrade` is a silent no-op on an unversioned
git pin.** pip sees the requirement already satisfied, upgrades the
*dependencies*, and reports success — which is exactly how a connector once
served days-old code while every deploy stayed green. If you change something
the connector depends on, say so in the PR so the deploy is not skipped.

## Architecture — the layering

Each layer only knows the ones beneath it. Keep it that way.

| Layer | Modules | Depends on |
|---|---|---|
| **1. Functional core** | `script` (Narration/SegmentBeat/Dialogue/Script), `rights` (Profile + plan_production), `sources` (SegmentSource, TimedLine), `tts`, `cost`, `delivery`, `multivoice`, `weave_config`, `music`, `compose`, `weave`, `render`, `timeline`, `textprep`, `style`, `kinds` | `mixing`, `elevenlabs`, `ffmpeg` on PATH — nothing else |
| **2. Format templates** | `formats` (`Format`, `render_format`, `FORMATS`) | layer 1 only. Templates are *good defaults over the primitives*, never new mechanism |
| **3. Graph vocabulary** | `bodies/` — lacing body schemas + tiers, registered as an import side effect | `lacing` (extra `graph`) |
| **4. nw pipeline** | `transforms/` (voice-assignment → narration-render → segment-extraction → episode), `provenance`, `project`, `genre` | layers 1–3 + `nw` (extra `nw-app`) |
| **5. MCP tool surface** | `mcp/` — `tools.py` (the tools), `_guide.py` (the front door), `metering.py`, `workspace.py`, `_docs.py`, `_helpers.py` | everything above + `fastmcp`/`py2mcp` (extra `mcp`) |

Two invariants worth stating explicitly:

- **`import braidio` never requires the optional layers.** `braidio/__init__.py`
  imports `bodies`/`provenance` and `project`/`transforms`/`genre` behind
  `try/except ImportError`, reporting `HAS_GRAPH` / `HAS_NW`. Never move an
  optional-dep import to the top of a core module.
- **`braidio.genre` must stay fastmcp-free.** It imports
  `braidio.mcp.workspace` *lazily* inside the project factory; a top-level
  import would pull `fastmcp` through `braidio.mcp` and flip `HAS_NW` off. There
  is a comment saying so in `genre.py` — do not "clean it up".

Renders take one path or the other: the **no-graph fast path**
(`render_production` / `render_format` — one call, one file) and the **graph
path** (`save_script` → `weave_project`, provenance + partial re-render). The
transforms delegate to the same core primitives; do not fork the DSP.

## `mixing` owns the audio DSP — do not wrap it in a blindfold

Everything braidio does to actual samples goes through `mixing` (or a direct
`ffmpeg` subprocess): `mixing.text_to_speech` under `braidio.tts.narrate`,
`mixing.concatenate_audio` in `render`/`conversation`/`multivoice`,
`mixing._cache` for the TTS and dialogue caches. braidio never reimplements the
DSP, and it does not own `mixing`'s bugs — but it must not hide them either.

**Rule: no broad `except` around a `mixing` (or ffmpeg) call.** A
`except Exception: pass` there turns a real DSP failure into a silent, wrong
production — a track that renders "successfully" with a missing beat. The
current code obeys this: every broad catch in the package is on a non-DSP
boundary (metering context lookup, URL fetch, yt-dlp extractor errors, an
advisory duration probe) and each carries a `# noqa: BLE001` with the reason.
Match that pattern: catch the *specific* exception, or let it propagate.

The one deliberate exception is `render._end_tail`, which catches
`(subprocess.CalledProcessError, ValueError, KeyError)` because the end-fade is
cosmetic — note that it is narrow and commented, not a bare `Exception`.

Delegation contract (from the README, and it holds):

| Concern | Owner |
|---|---|
| Raw audio DSP + TTS (crop, concat, duck, loudnorm, synth) | `mixing` / `falaw` |
| Linked-artifact graph / content-addressed media | `lacing` |
| Project workflow, provenance, partial re-render | `nw` |
| Video render + visual support | `reelee` |
| Content acquisition (lyrics, audiobooks, news…) | the consuming app, via a `SegmentSource` |

## Money: ElevenLabs is the only spend

Everything else — extraction, weaving, loudness, mastering — is local ffmpeg and
free. ElevenLabs bills **per character of submitted text** (including `eleven_v3`
`[audio tags]`), which is why `braidio.cost.billable_chars` is just `len(text)`
behind a named function.

- `estimate_cost(script)` is free and must be offered before any paid render.
- Characters are always exact. **Dollars are a rate estimate**, resolved
  most-specific-first: `MODEL_USD_PER_1K_CHARS` (currently empty, by design —
  only confirmed per-model rates go there) → the env override →
  `DEFAULT_USD_PER_1K_CHARS`.
- **Unpriced mode is honest, not free.** Setting the rate env var to `none`,
  `unpriced`, `unknown`, or empty — or to anything non-numeric, negative, or
  non-finite — makes `usd_per_1k_chars()` return `None`, so costs report `None`
  (*unpriced*) with the character counts still exact. Never let an unknown rate
  become `0.0` for non-empty text; empty text is genuinely `0.0`.

| Env var | Meaning |
|---|---|
| `BRAIDIO_TTS_USD_PER_1K_CHARS` (`cost.RATE_ENV_VAR`) | USD per 1000 chars. Unset → conservative default; `none` → unpriced |
| `BRAIDIO_TTS_VOICE` (`tts.VOICE_ENV_VAR`) | default ElevenLabs voice id for narration |
| `BRAIDIO_DIALOGUE_CACHE_DIR` (`tts.DIALOGUE_CACHE_ENV_KEY`) | on-disk cache dir for Text-to-Dialogue takes |
| `BRAIDIO_DATA_HOME` (`mcp.workspace.DATA_HOME_ENV_VAR`) | data root for per-user projects/renders/assets (default `~/.local/share/braidio`) |
| `BRAIDIO_AUDIO_MAX_BYTES`, `BRAIDIO_AUDIO_MAX_DURATION_S` | bounds on `download_audio` server-side fetches |
| `ELEVENLABS_API_KEY` / `ELEVEN_API_KEY` | resolved by `mixing` / the elevenlabs client when no `api_key=` is threaded |

Cache-vs-live: `narrate(..., return_cache_status=True)` reports whether `mixing`
served the audio from disk, and the `narration_render` transform uses it to
record `cost_usd_actual = 0.0` on a cache hit. The one-shot MCP tools still
report the rate estimate (`cost_basis="estimate"`) — a deliberate over-estimate
for a spend ledger.

### Metering (MCP)

`mcp/metering.py` is fail-closed by construction and the reason it is
*middleware*, not decorators: a decorator you forget on a paid tool is untracked
spend. Identity is resolved once from the verified OAuth token and read by tools
via `current_email()`; a write-ahead ledger entry is recorded *before* the call
and a failed ledger write **refuses** the call. Do not add an ambient identity
fallback, and do not let a tool re-derive the caller's identity.

**Know which middleware is actually running.** `braidio.mcp.MeteringMiddleware`
(via `build_server`) is the local/stdio/dev path. The **deployed** connectors
build their app from `TOOL_REFS` + `INSTRUCTIONS` and wrap them in the
*platform's* shared `enlace_metering` middleware — durable `dol` ledger, an
email allow-set, and a per-principal monthly credit cap over
`set(COSTED_TOOLS)`. So a change to `braidio/mcp/metering.py` does **not** change
production behaviour, while a change to `COSTED_TOOLS`, a tool's signature, or
`INSTRUCTIONS` does. `current_email()` is written to work under either host's
middleware — keep it that way.

## Conventions

- Favour functional style; small focused helpers (`_underscore` for
  module-private, inner functions for single-use). `dataclasses`, mostly
  `frozen=True`, for data. `Script`, `WeaveConfig`, `Delivery`, `Format`,
  `MusicBed` are all frozen — build variants with `WeaveConfig.with_(...)` /
  `dataclasses.replace`, never by mutation.
- Arguments beyond the 2nd–3rd position are **keyword-only**.
- No magic numbers: name them as module constants (`_DEFAULT_LUFS`,
  `BED_GAIN_BY_INTENSITY`, `PUBLISHABLE_CLIP_RIGHTS`, `CLIP_PLACEMENTS`).
- Every module needs a top-level docstring — `ruff` selects `D100` and CI
  collects doctests from the package itself.
- Time is **seconds** (`float`) everywhere.
- Rights are **data, not judgement**: `SegmentBeat.rights` + `Profile` +
  `plan_production` decide what renders; the consumer injects *what* is
  forbidden via `RightsPolicy`. Never hardcode a rights decision in a renderer.
- MCP tools are flat, JSON-in/JSON-out. Return values go through
  `_helpers.to_json`; `bytes` deliberately raise — write audio into the caller's
  workspace and return its path/url.

## Tests = guardrails

Run `pytest -q` for the current count, and `pytest -q --doctest-modules` for the
CI-equivalent pass (`testpaths` lists both `tests` and `braidio`, so
`--doctest-modules` doubles as an import smoke test for every module). CI
installs the `mcp` extra — without it the MCP and nw-gated tests silently skip,
which is worse than red.

The suite is mostly characterization: `test_mcp.py` pins the tool surface and
its error messages, `test_wire_descriptions.py` pins what the model sees,
`test_cost.py` pins the unpriced/priced semantics, `test_transforms.py` pins the
graph pipeline including the `$0`-on-cache-hit attribution. **Do not edit an
assertion to make a refactor pass** — if behaviour must change, change the
assertion deliberately and say why in the commit.

`ffmpeg` must be on PATH for the render tests (declared in
`[tool.wads.ops.ffmpeg]` so CI installs it).

## What never to do

- Never add a costed tool to `FREE_TOOLS`, and never let a paid path skip the
  metering middleware.
- Never wrap a `mixing`/ffmpeg call in a broad `except` — see above.
- Never move an optional-dep import (`lacing`, `nw`, `fastmcp`) to module top
  level in the functional core, and never let `braidio.genre` import
  `braidio.mcp` eagerly.
- Never write user data into the app/deploy tree — per-user projects, renders
  and assets belong under the data root (`BRAIDIO_DATA_HOME`), because a
  deploy's `rsync --delete` would erase anything inside the app dir.
- Never bypass `Workspace`'s path validation: tools take a `project_id`, never a
  path, so one caller can't reach another's data.
- Never ship music/media in the package — a `MusicBed` asset is always supplied
  by the caller.
- Never change `narrate` / `render_dialogue` / `ConversationCast` signatures
  without checking `reelee` first.

Research and style references live in `misc/docs/` (never inside the importable
package): `research/commentary-formats-and-styles.md` is the taxonomy the
`formats` presets encode, and `style/` holds the commentary-voice guide,
anti-platitude checklist, and per-critic voice files.
