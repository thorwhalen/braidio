"""The CLI door onto :func:`braidio.importing.import_production`.

``python -m braidio.importing MANIFEST PROJECT_ROOT [options]``

Argument parsing is deliberately **not** a seam: argparse from the standard
library, because braidio's core declares two dependencies and an importer is
not the reason to add a third. The verb is the function; this is a door onto
it, and everything it prints comes from the returned
:class:`~braidio.importing.ImportReport`.

``--dry-run`` validates without writing — every file present, every licence
recognised, every context card heavy enough to survive ``video_cut.finish``,
and the library zoom default still what the extraction read off it. Run it
first; it is free and it is where a broken manifest should be found.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """The argument parser (exposed so tests can drive it without a subprocess)."""
    p = argparse.ArgumentParser(
        prog="python -m braidio.importing",
        description=(
            "Import a finished commentary production into a braidio project "
            "graph. Idempotent: running it twice gives you one project."
        ),
    )
    p.add_argument("manifest", type=Path, help="Normalized production manifest (JSON).")
    p.add_argument("project_root", type=Path, help="Where the project lives.")
    p.add_argument(
        "--source-root",
        type=Path,
        default=Path("."),
        help=(
            "Folder the manifest's source_dir is relative to. Manifests store "
            "no absolute path, so this is how the bytes are found."
        ),
    )
    p.add_argument(
        "--no-copy-media",
        action="store_true",
        help=(
            "Reference the stills and episode audio where they sit instead of "
            "copying them into the project. The project is then not "
            "self-contained and a fork cannot hardlink it."
        ),
    )
    p.add_argument(
        "--no-register",
        action="store_true",
        help=(
            "Do not register the artifacts in the project's delivery catalog. "
            "Every artifact id then 404s on every surface — the project can "
            "be read and not watched or listened to."
        ),
    )
    p.add_argument(
        "--materialize-cuts",
        choices=("delivered", "all", "none"),
        default="delivered",
        help=(
            "Which rendered cuts come into the project. 'delivered' (default) "
            "brings in every cut's delivered mp4; 'all' adds the text-free "
            "motion passes, which roughly doubles the weight; 'none' leaves "
            "them where they sit, which means no surface can serve them."
        ),
    )
    p.add_argument(
        "--allow-cross-device-copy",
        action="store_true",
        help=(
            "Permit a real byte copy when the project is not on the media's "
            "filesystem. Off by default: the copy is the whole production "
            "again and is rarely what was meant."
        ),
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate everything and write nothing.",
    )
    p.add_argument("--json", action="store_true", help="Print the report as JSON.")
    return p


def _render(report) -> str:
    """The human report — what changed, and what is still unsettled."""
    out = [
        f"{report.title}  [{report.production}]",
        f"  project      {report.project_root}",
        f"  rights       {report.rights_position}",
        f"  stills       {report.stills_written} written, "
        f"{report.stills_unchanged} unchanged",
        f"  episodes     {report.episodes}",
        f"  panels       {report.panels_total} across "
        f"{len(report.panels_by_cut)} cut(s): "
        + ", ".join(f"{k}={v}" for k, v in report.panels_by_cut.items()),
        f"  cards        "
        + ", ".join(f"{k}={v}" for k, v in report.labels_by_cut.items()),
        f"  cuts         " + ", ".join(report.cuts_written),
    ]
    if report.beats_by_cut:
        out.append(
            "  beats        "
            + ", ".join(f"{k}={v}" for k, v in report.beats_by_cut.items())
        )
        out.append(f"  takes        {report.takes_total} playable narration take(s)")
    if report.media_placed:
        out.append(
            f"  media        {report.media_linked} linked, "
            f"{report.media_copied} copied ({report.bytes_copied / 1e6:.0f} MB)"
        )
    cat = report.catalog
    out.append(
        f"  catalog      {cat.rows_written} row(s) written, "
        f"{cat.rows_unchanged} unchanged; {cat.blobs_linked} blob(s) linked, "
        f"{cat.blobs_present} already present, {cat.blobs_copied} copied"
    )
    if cat.unregistered:
        out.append(
            f"  UNRETRIEVABLE {len(cat.unregistered)} artifact(s) no surface can serve:"
        )
        out += [f"    - {Path(p).name}: {why}" for p, why in cat.unregistered[:6]]
    if report.published_links:
        out.append("  published:")
        out += [f"    {k}: {v}" for k, v in report.published_links.items()]
    if report.untitled_stills:
        out.append(
            f"  UNTITLED     {len(report.untitled_stills)} still(s) have no title "
            "and will credit without one, silently: "
            + ", ".join(report.untitled_stills[:6])
        )
    if report.bare_attributions:
        out.append(
            f"  note         {len(report.bare_attributions)} still(s) carry an "
            "attribution naming no licence; credits are composed from the "
            "parts, never that string"
        )
    if report.beats_without_text:
        out.append(
            f"  NO TEXT      {len(report.beats_without_text)} narration beat(s) "
            "imported with an empty text (the script did not survive): "
            + ", ".join(report.beats_without_text[:6])
        )
    if report.segments_without_source:
        out.append(
            f"  NO SPAN      {len(report.segments_without_source)} clip(s) have "
            "no recorded source span; start_s/end_s are not a span"
        )
    if report.takes_missing:
        out.append(
            f"  MISSING      {len(report.takes_missing)} take file(s) named by "
            "the manifest are not on disk: " + ", ".join(report.takes_missing[:6])
        )
    if report.beat_ids_renumbered:
        out.append(
            f"  beat ids     {report.beat_ids_renumbered} renumbered from "
            "'beat:N' to braidio's zero-padded form"
        )
    if report.gaps:
        out.append(f"  GAPS         {len(report.gaps)} carried from the manifest:")
        out += [f"    - {g.splitlines()[0][:150]}" for g in report.gaps]
    return "\n".join(out)


def main(argv=None) -> int:
    """Parse ``argv``, run the import, print the report. Returns an exit code."""
    from braidio.importing import (
        CrossDeviceCatalog,
        ImportError_,
        import_production,
        load_manifest,
    )

    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        report = import_production(
            manifest,
            args.project_root,
            source_root=args.source_root,
            copy_media=not args.no_copy_media,
            dry_run=args.dry_run,
            register_artifacts=not args.no_register,
            materialize_cuts=args.materialize_cuts,
            allow_cross_device_copy=args.allow_cross_device_copy,
        )
    except ImportError_ as exc:
        print(f"import refused: {exc}", file=sys.stderr)
        return 2
    except CrossDeviceCatalog as exc:
        print(f"import refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), indent=2) if args.json else _render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
