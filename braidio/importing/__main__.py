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
    if report.media_copied:
        out.append(f"  copied       {report.media_copied} media file(s)")
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
    from braidio.importing import ImportError_, import_production, load_manifest

    args = build_parser().parse_args(argv)
    try:
        manifest = load_manifest(args.manifest)
        report = import_production(
            manifest,
            args.project_root,
            source_root=args.source_root,
            copy_media=not args.no_copy_media,
            dry_run=args.dry_run,
        )
    except ImportError_ as exc:
        print(f"import refused: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(report.to_dict(), indent=2) if args.json else _render(report))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
