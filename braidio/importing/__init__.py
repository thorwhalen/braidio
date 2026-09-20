"""Bring a finished commentary production into a braidio project graph.

Three commentary videos were made before the picture track was data: *Actually
Romantic*, *Two Silences* and Hamilton's *Burn*. Each recorded its pictures a
different way — hand-authored absolute seconds in a python module, a derived
``<stem>-panels.json``, and, for the hardest, no driver at all. This package
turns them into real projects: stills with their rights and their editorial
labels, the episode audio, the panel track for each cut, the editorial cards,
and the cut records with their ``published`` links.

Two entry points, and the split is the point:

- :func:`~braidio.importing._manifest.load_manifest` reads a **normalized
  manifest** — the shared target every production is extracted into, so each
  production keeps exactly one entry point (its extractor) and the importer
  has exactly one input shape.
- :func:`~braidio.importing._writer.import_production` writes one into a
  project, **idempotently**: run it twice and you have one project with one
  track per cut, not two.

    >>> from braidio.importing import assert_recorded_zoom_default
    >>> assert_recorded_zoom_default()   # the library default the data leans on

The CLI door is ``python -m braidio.importing``::

    python -m braidio.importing MANIFEST.json ~/projects/two-silences \\
        --source-root ~/src --dry-run

Read ``braidio/importing/_writer.py``'s docstring before changing anything:
it carries the four rules this importer enforces rather than documents, each
of which was a measured defect in one of the three productions — most sharply
that **every imported panel is ``push_in``**, because the source's push/drift
alternation was a no-op and writing ``auto`` today would invent a drift the
films never had (thorwhalen/braidio#72).
"""

from braidio.importing._manifest import (
    CutRecord,
    LabelRecord,
    PanelRecord,
    BeatRecord,
    ProductionManifest,
    RightsPosition,
    StillRecord,
    TakeRecord,
    load_manifest,
)
from braidio.importing._catalog import (
    BYTES_ROUTE,
    CATALOG_KINDS,
    CatalogReport,
    CrossDeviceCatalog,
    blobs_dir,
    catalog_dir,
    registered_ids,
)
from braidio.importing._writer import (
    IMPORTED_CACHE_KEY_PREFIX,
    IMPORTED_MOVE,
    NARRATION_REPLACEMENT_NOTE,
    IMPORT_NAMESPACE,
    MOVE_IMPORT_NOTE,
    RECORDED_PANEL_ZOOM_DEFAULT,
    ImportError_,
    ImportReport,
    assert_recorded_zoom_default,
    import_production,
    normalized_licenses,
)

__all__ = [
    "load_manifest",
    "import_production",
    "ProductionManifest",
    "RightsPosition",
    "StillRecord",
    "PanelRecord",
    "LabelRecord",
    "CutRecord",
    "ImportReport",
    "ImportError_",
    "assert_recorded_zoom_default",
    "normalized_licenses",
    "IMPORTED_MOVE",
    "IMPORT_NAMESPACE",
    "MOVE_IMPORT_NOTE",
    "RECORDED_PANEL_ZOOM_DEFAULT",
    "IMPORTED_CACHE_KEY_PREFIX",
    "NARRATION_REPLACEMENT_NOTE",
    "BeatRecord",
    "TakeRecord",
    "CatalogReport",
    "CrossDeviceCatalog",
    "CATALOG_KINDS",
    "BYTES_ROUTE",
    "catalog_dir",
    "blobs_dir",
    "registered_ids",
]
