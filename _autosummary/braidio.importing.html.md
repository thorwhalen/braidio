# braidio.importing

Bring a finished commentary production into a braidio project graph.

Three commentary videos were made before the picture track was data: \*Actually
Romantic\*, *Two Silences* and Hamilton’s *Burn*. Each recorded its pictures a
different way — hand-authored absolute seconds in a python module, a derived
`<stem>-panels.json`, and, for the hardest, no driver at all. This package
turns them into real projects: stills with their rights and their editorial
labels, the episode audio, the panel track for each cut, the editorial cards,
and the cut records with their `published` links.

Two entry points, and the split is the point:

- `load_manifest()` reads a \*\*normalized
  manifest\*\* — the shared target every production is extracted into, so each
  production keeps exactly one entry point (its extractor) and the importer
  has exactly one input shape.
- `import_production()` writes one into a
  project, **idempotently**: run it twice and you have one project with one
  track per cut, not two.
  ```pycon
  >>> from braidio.importing import assert_recorded_zoom_default
  >>> assert_recorded_zoom_default()   # the library default the data leans on
  ```

The CLI door is `python -m braidio.importing`:

```default
python -m braidio.importing MANIFEST.json ~/projects/two-silences \
    --source-root ~/src --dry-run
```

Read `braidio/importing/_writer.py`’s docstring before changing anything:
it carries the four rules this importer enforces rather than documents, each
of which was a measured defect in one of the three productions — most sharply
that \*\*every imported panel is `push_in``**, because the source's push/drift
alternation was a no-op and writing ``auto` today would invent a drift the
films never had (thorwhalen/braidio#72).

### Functions

| [`load_manifest`](#braidio.importing.load_manifest)(path)                           | Read and validate a manifest JSON file.                               |
|------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------|
| [`import_production`](#braidio.importing.import_production)(manifest, project_root, \*) | Write `manifest` into a braidio project at `project_root`.            |
| [`assert_recorded_zoom_default`](#braidio.importing.assert_recorded_zoom_default)([expected])      | Fail unless `braidio.video.Panel`'s zoom default is still `expected`. |
| [`normalized_licenses`](#braidio.importing.normalized_licenses)(stills)                   | `{still key: canonical code}`, raising on anything unrecognised.      |
| [`assert_local_backend`](#braidio.importing.assert_local_backend)([env])                   | Refuse to register into a filesystem the host will not read.          |
| [`catalog_dir`](#braidio.importing.catalog_dir)(project_root)                     | Where the rows live.                                                  |
| [`blobs_dir`](#braidio.importing.blobs_dir)(project_root)                       | Where the content-addressed bytes live.                               |
| [`registered_ids`](#braidio.importing.registered_ids)(project_root)                  | Every artifact id this project's catalog currently answers for.       |

### Classes

| [`ProductionManifest`](#braidio.importing.ProductionManifest)(\*\*data)                | A finished production, normalized — the importer's only input shape.    |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`RightsPosition`](#braidio.importing.RightsPosition)(\*\*data)                    | A production's rights finding, argued rather than assumed (plan §10).   |
| [`StillRecord`](#braidio.importing.StillRecord)(\*\*data)                       | One image with its rights and its editorial label — the still/v1 input. |
| [`PanelRecord`](#braidio.importing.PanelRecord)(\*\*data)                       | A still over a span of one cut's episode audio.                         |
| [`LabelRecord`](#braidio.importing.LabelRecord)(\*\*data)                       | A timed editorial card that is not per-still (title, context, tag).     |
| [`CutRecord`](#braidio.importing.CutRecord)(\*\*data)                         | One finished rendering, with the panels and cards it was made from.     |
| [`ImportReport`](#braidio.importing.ImportReport)(production, project_root, ...) | What one import did, and what it could not settle.                      |
| [`BeatRecord`](#braidio.importing.BeatRecord)(\*\*data)                        | One member of a rendered episode — the unit a panel is cut against.     |
| [`TakeRecord`](#braidio.importing.TakeRecord)(\*\*data)                        | The audio a listener actually hears for one beat — the recording.       |
| [`CatalogReport`](#braidio.importing.CatalogReport)([rows_written, ...])          | What registering a project's media did, and what it could not hold.     |

### Exceptions

| [`ImportError_`](#braidio.importing.ImportError_)           | Raised when a manifest cannot be imported faithfully.             |
|-------------------------------------------------------------------------|-------------------------------------------------------------------|
| [`CrossDeviceCatalog`](#braidio.importing.CrossDeviceCatalog)     | The project's blob store is not on the source media's filesystem. |
| [`CatalogBackendMismatch`](#braidio.importing.CatalogBackendMismatch) | The host is configured to read its artifacts from somewhere else. |

### *class* braidio.importing.BeatRecord(\*\*data)

Bases: `BaseModel`

One member of a rendered episode — the unit a panel is cut against.

This is the *render’s own* beat, read off the persisted timeline
(`TimelineBreakdown.to_dict()`), not the authored script’s. The two
agree in order but not necessarily in count: a rights profile can drop a
beat before it is rendered, and it is the rendered sequence the panels and
cards were timed against.

`text` is the **full** narration, recovered from the authored script.
The timeline’s own `label` is a 48-character snippet, which is enough to
*match* a script beat to a rendered one and not enough to edit. A beat
whose script did not survive carries `text=None` and is still
addressable and playable — just not re-synthesizable without retyping it,
which is the honest state rather than a guess.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *exception* braidio.importing.CatalogBackendMismatch

Bases: [`RuntimeError`](https://docs.python.org/3/builtins/exceptions.html#RuntimeError)

The host is configured to read its artifacts from somewhere else.

### *class* braidio.importing.CatalogReport(rows_written=0, rows_unchanged=0, blobs_linked=0, blobs_present=0, blobs_copied=0, bytes_copied=0, cross_device=False, unregistered=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What registering a project’s media did, and what it could not hold.

#### unregistered *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[tuple](https://docs.python.org/3/builtins/stdtypes.html#tuple)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]]*

`(path, reason)` for a file the catalog cannot hold — today only a
kind outside `CATALOG_KINDS`. Reported, never silently dropped:
an unregistered artifact is one a caller will ask for and not get.

### *exception* braidio.importing.CrossDeviceCatalog

Bases: [`OSError`](https://docs.python.org/3/builtins/exceptions.html#OSError)

The project’s blob store is not on the source media’s filesystem.

### *class* braidio.importing.CutRecord(\*\*data)

Bases: `BaseModel`

One finished rendering, with the panels and cards it was made from.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *exception* braidio.importing.ImportError_

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

Raised when a manifest cannot be imported faithfully.

### *class* braidio.importing.ImportReport(production, project_root, title, rights_position, stills_written=0, stills_unchanged=0, episodes=0, panels_by_cut=<factory>, labels_by_cut=<factory>, cuts_written=<factory>, published_links=<factory>, untitled_stills=<factory>, bare_attributions=<factory>, license_codes=<factory>, beat_ids_renumbered=0, media_copied=0, bytes_copied=0, beats_by_cut=<factory>, takes_by_cut=<factory>, beats_without_text=<factory>, takes_missing=<factory>, segments_without_source=<factory>, catalog=<factory>, gaps=<factory>, notes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one import did, and what it could not settle.

Returned rather than logged, so a CLI, a test and a future MCP tool all
read the same answer.

#### bare_attributions *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

rendering it verbatim
would fail the licence condition. `credit_line` composes instead.

* **Type:**
  Stills whose `attribution` names no licence

#### beats_by_cut *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [int](https://docs.python.org/3/builtins/functions.html#int)]*

narration / clip / break.

* **Type:**
  Members written per cut, by tier-ish role

#### beats_without_text *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`"<cut>/<index>"` for every narration beat whose authored text did
not survive. Imported with an EMPTY text, never the snippet — so the
count is the only place the loss is visible. See the module docstring.

#### media_copied *: [int](https://docs.python.org/3/builtins/functions.html#int)* *= 0*

Media files copied into the project, and the bytes that cost. The
project owns its bytes rather than linking to a shared source tree —
see `_place_into()` for why the link is the wrong trade here.

#### segments_without_source *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

`"<cut>/<index>"` for every clip whose span in the SOURCE recording
was never persisted. Written with `source_span_recorded=False` rather
than an invented `(0.0, duration)`, which would be a false claim
about where third-party material was cut from.

#### takes_by_cut *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [int](https://docs.python.org/3/builtins/functions.html#int)]*

Playable narration takes written per cut.

#### takes_missing *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Takes named by the manifest whose audio file is not on disk.

#### to_dict()

A JSON-able summary (what the CLI’s `--json` prints).

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`Any`](https://docs.python.org/3/library/typing.html#typing.Any)]

#### untitled_stills *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

Stills with no `title` — they credit WITHOUT one, silently, so the
count is surfaced rather than left to be discovered in a credit roll.

### *class* braidio.importing.LabelRecord(\*\*data)

Bases: `BaseModel`

A timed editorial card that is not per-still (title, context, tag).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* braidio.importing.PanelRecord(\*\*data)

Bases: `BaseModel`

A still over a span of one cut’s episode audio.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* braidio.importing.ProductionManifest(\*\*data)

Bases: `BaseModel`

A finished production, normalized — the importer’s only input shape.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* braidio.importing.RightsPosition(\*\*data)

Bases: `BaseModel`

A production’s rights finding, argued rather than assumed (plan §10).

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* braidio.importing.StillRecord(\*\*data)

Bases: `BaseModel`

One image with its rights and its editorial label — the still/v1 input.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *class* braidio.importing.TakeRecord(\*\*data)

Bases: `BaseModel`

The audio a listener actually hears for one beat — the recording.

A *take* is the replaceable unit. `source` is why the field exists at
all: an imported take is `"tts"` (a machine said it), and the only other
value is `"upload"` (a person recorded it). Without the distinction a
replacement is indistinguishable from the thing it replaced, and “put the
robot back” is not a question anything can answer.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### braidio.importing.assert_local_backend(env=None)

Refuse to register into a filesystem the host will not read.

This is the one failure this module could not survive quietly. Everything
else here fails loudly — a missing blob raises, an unlinkable destination
raises, an unholdable kind is reported. But writing a perfectly correct
`catalog/` and `blobs/` next to a project whose host resolves artifacts
out of S3 produces an import that reports complete success and a project
where **every id still 404s** — which is precisely the defect this module
exists to remove, reintroduced one layer up.

Raising is right rather than harsh: the caller who genuinely wants the
graph without the catalog has `register_artifacts=False`, and that is an
explicit choice the report then records.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> assert_local_backend({})
>>> assert_local_backend({"REELEE_ARTIFACT_BACKEND": "fs"})
>>> assert_local_backend({"REELEE_ARTIFACT_BACKEND": "aws"})
Traceback (most recent call last):
    ...
braidio.importing._catalog.CatalogBackendMismatch: ...
```

### braidio.importing.assert_recorded_zoom_default(expected=1.18)

Fail unless `braidio.video.Panel`’s zoom default is still `expected`.

The one failure that is invisible afterwards. 178 Two Silences panels carry
a zoom nothing recorded — it was this default, read off the library at
extraction time. 1.18 against 1.14 is near-invisible on one panel and
diverges over ten minutes.

* **Return type:**
  [`None`](https://docs.python.org/3/builtins/constants.html#None)

```pycon
>>> assert_recorded_zoom_default()
>>> assert_recorded_zoom_default(1.14)
Traceback (most recent call last):
    ...
braidio.importing._writer.ImportError_: braidio.video.Panel.zoom is 1.18...
```

### braidio.importing.blobs_dir(project_root)

Where the content-addressed bytes live.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### braidio.importing.catalog_dir(project_root)

Where the rows live.

* **Return type:**
  [`Path`](https://docs.python.org/3/library/pathlib.html#pathlib.Path)

### braidio.importing.import_production(manifest, project_root, , source_root=None, copy_media=True, dry_run=False, register_artifacts=True, materialize_cuts='delivered', allow_cross_device_copy=False)

Write `manifest` into a braidio project at `project_root`.

**All or nothing — when the path did not already exist.** That qualifier
is the whole of the guarantee, and it is deliberately not stronger. A
refusal that fires after the first node is written (an unlinkable blob is
the live case) would otherwise leave a CLI printing “import refused” over
a directory holding a `project.json`, a graph with one annotation and
some media — the refusal saying nothing happened and the tree saying
otherwise. So a project **this call created** is removed entirely.

What is NOT promised, because promising it would mean deleting directories
we did not create:

- `mkdir -p` the path first — which is how people prepare one — and the
  rollback does not fire, so a refusal can leave exactly that half-written
  state. Measured.
- A failed **re-import leaves an existing project partially updated**, not
  as it was found: annotations written before the failure keep their new
  values. A reader who retries expecting a clean slate is wrong. The price
  of never deleting somebody’s project is that a failed run can leave it
  half-changed; re-running the import is how it converges.
- Empty parent directories this call created are left behind. Removing
  directories because we also made them is the first step back down the
  road that produced the bug this guard exists for.

* **Parameters:**
  * **manifest** ([`ProductionManifest`](#braidio.importing.ProductionManifest)) – the normalized production (see `load_manifest`).
  * **project_root** – where the project lives. Created if absent; an existing
    project is updated in place, which is what makes a re-run one
    project rather than two.
  * **source_root** – the folder `manifest.source_dir` is relative to. The
    manifest never stores an absolute path (one committed production
    manifest did, in a shared repo — only basenames come forward), so
    the caller supplies the root.
  * **copy_media** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – bring the stills, the episode audio and the narration
    takes into the project, so it is self-contained and survives being
    moved to a server. See `_place_into()` for why this is a copy
    and the blob store’s link is not.
  * **dry_run** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – validate everything — files present, licences known, card
    weights sufficient, zoom default unmoved, beat kinds coherent —
    and write nothing.
  * **register_artifacts** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – register every artifact in the project’s delivery
    catalog, so `GET /api/artifacts/{id}/bytes` answers instead of
    404ing. On by default: an unregistered artifact is a file the
    graph names and no surface can hand over.
  * **materialize_cuts** ([`str`](https://docs.python.org/3/builtins/stdtypes.html#str)) – which rendered cuts come into the project —
    `"delivered"` (default; every cut’s delivered mp4), `"all"`
    (also the text-free motion passes), or `"none"` (reference them
    where they are, which means no surface can serve them; reported).
  * **allow_cross_device_copy** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – permit a real byte copy when the project’s
    blob store is not on the media’s filesystem. Off by default,
    because the copy is silent, is the whole production again, and is
    rarely what the caller meant.
* **Return type:**
  [`ImportReport`](#braidio.importing.ImportReport)
* **Returns:**
  an [`ImportReport`](#braidio.importing.ImportReport).
* **Raises:**
  * [**ImportError**](https://docs.python.org/3/builtins/exceptions.html#ImportError) – the manifest cannot be imported faithfully.
  * [**CatalogBackendMismatch**](#braidio.importing.CatalogBackendMismatch) – the host reads artifacts from an object store.
  * [**CrossDeviceCatalog**](#braidio.importing.CrossDeviceCatalog) – blobs cannot be linked and no copy was authorized.

### braidio.importing.load_manifest(path)

Read and validate a manifest JSON file.

* **Return type:**
  [`ProductionManifest`](#braidio.importing.ProductionManifest)

```pycon
>>> import json, tempfile, pathlib
>>> doc = dict(
...     production="demo", title="Demo", source_dir="demo",
...     rights=dict(position="private", why="test"),
...     episode_audio=dict(path="ep.mp3", duration_s=1.0),
...     stills=[dict(key="a", path="a.jpg", labelled=False)],
...     cuts=[],
... )
>>> with tempfile.TemporaryDirectory() as d:
...     p = pathlib.Path(d, "m.json"); _ = p.write_text(json.dumps(doc))
...     m = load_manifest(p)
>>> m.production, len(m.stills), m.rights.position
('demo', 1, 'private')
```

### braidio.importing.normalized_licenses(stills)

`{still key: canonical code}`, raising on anything unrecognised.

The gate, not the value: what gets written into the still body is the
*recorded* spelling, because “CC BY-SA 4.0” is what a credit should read
and “by-sa” is not. An unrecognised code survives `normalize_license`
unchanged and would therefore silently fail a downstream allowlist with no
error at all — which is why an unknown fails here instead.

* **Return type:**
  [`dict`](https://docs.python.org/3/builtins/stdtypes.html#dict)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str), [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]

### braidio.importing.registered_ids(project_root)

Every artifact id this project’s catalog currently answers for.

* **Return type:**
  [`frozenset`](https://docs.python.org/3/builtins/stdtypes.html#frozenset)[[`str`](https://docs.python.org/3/builtins/stdtypes.html#str)]
