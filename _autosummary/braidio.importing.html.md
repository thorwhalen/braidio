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

### Classes

| [`ProductionManifest`](#braidio.importing.ProductionManifest)(\*\*data)                | A finished production, normalized — the importer's only input shape.    |
|----------------------------------------------------------------------------------------------|-------------------------------------------------------------------------|
| [`RightsPosition`](#braidio.importing.RightsPosition)(\*\*data)                    | A production's rights finding, argued rather than assumed (plan §10).   |
| [`StillRecord`](#braidio.importing.StillRecord)(\*\*data)                       | One image with its rights and its editorial label — the still/v1 input. |
| [`PanelRecord`](#braidio.importing.PanelRecord)(\*\*data)                       | A still over a span of one cut's episode audio.                         |
| [`LabelRecord`](#braidio.importing.LabelRecord)(\*\*data)                       | A timed editorial card that is not per-still (title, context, tag).     |
| [`CutRecord`](#braidio.importing.CutRecord)(\*\*data)                         | One finished rendering, with the panels and cards it was made from.     |
| [`ImportReport`](#braidio.importing.ImportReport)(production, project_root, ...) | What one import did, and what it could not settle.                      |

### Exceptions

| [`ImportError_`](#braidio.importing.ImportError_)   | Raised when a manifest cannot be imported faithfully.   |
|-----------------------------------------------------------------|---------------------------------------------------------|

### *class* braidio.importing.CutRecord(\*\*data)

Bases: `BaseModel`

One finished rendering, with the panels and cards it was made from.

#### model_config *: [ClassVar](https://docs.python.org/3/library/typing.html#typing.ClassVar)[ConfigDict]* *= {'extra': 'forbid', 'frozen': True}*

Configuration for the model, should be a dictionary conforming to [`ConfigDict`][pydantic.config.ConfigDict].

### *exception* braidio.importing.ImportError_

Bases: [`Exception`](https://docs.python.org/3/builtins/exceptions.html#Exception)

Raised when a manifest cannot be imported faithfully.

### *class* braidio.importing.ImportReport(production, project_root, title, rights_position, stills_written=0, stills_unchanged=0, episodes=0, panels_by_cut=<factory>, labels_by_cut=<factory>, cuts_written=<factory>, published_links=<factory>, untitled_stills=<factory>, bare_attributions=<factory>, license_codes=<factory>, beat_ids_renumbered=0, media_copied=0, gaps=<factory>, notes=<factory>)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

What one import did, and what it could not settle.

Returned rather than logged, so a CLI, a test and a future MCP tool all
read the same answer.

#### bare_attributions *: [list](https://docs.python.org/3/builtins/stdtypes.html#list)[[str](https://docs.python.org/3/builtins/stdtypes.html#str)]*

rendering it verbatim
would fail the licence condition. `credit_line` composes instead.

* **Type:**
  Stills whose `attribution` names no licence

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

### braidio.importing.import_production(manifest, project_root, , source_root=None, copy_media=True, dry_run=False)

Write `manifest` into a braidio project at `project_root`.

* **Parameters:**
  * **manifest** ([`ProductionManifest`](#braidio.importing.ProductionManifest)) – the normalized production (see `load_manifest`).
  * **project_root** – where the project lives. Created if absent; an existing
    project is updated in place, which is what makes a re-run one
    project rather than two.
  * **source_root** – the folder `manifest.source_dir` is relative to. The
    manifest never stores an absolute path (one committed production
    manifest did, in a shared repo — only basenames come forward), so
    the caller supplies the root.
  * **copy_media** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – copy the stills and the episode audio into the project, so
    it is self-contained and a fork can hardlink it. The shipped cut
    mp4s are always referenced in place: they are the evidence a
    re-render is compared against, not an input to one.
  * **dry_run** ([`bool`](https://docs.python.org/3/builtins/functions.html#bool)) – validate everything — files present, licences known, card
    weights sufficient, zoom default unmoved — and write nothing.
* **Return type:**
  [`ImportReport`](#braidio.importing.ImportReport)
* **Returns:**
  an [`ImportReport`](#braidio.importing.ImportReport).

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
