"""Make an imported project's media *retrievable* — the delivery catalog.

An imported still, recording or film is recorded in the graph by its
content-addressed id. That id is what a body carries and what a surface asks
for, and until something registers it in the host's artifact catalog, asking
for it answers **404**. The bytes are on disk, the graph knows their hash, and
no door opens: a project that looks complete in every census and delivers
nothing. That is the same defect as thorwhalen/reelee#439, one layer down —
there it is a producer with no registered resolver, here it is bytes with no
registered row.

Two writes make an id resolvable, and the order between them is the whole
correctness argument:

1. the **blob** lands at ``blobs/<sha256>`` — the filename *is* the digest;
2. the **row** lands at ``catalog/<id>.json``.

The row is written **second, and only once the blob is there**, because the
host's route looks the row up first: a row with no blob behind it is not a 404,
it is a 500 from inside a stream that has already promised a 200.

Three decisions that are the point rather than detail:

- **The id IS the content hash.** The host mints opaque ids (``art-image-…``)
  for things it ingests itself; an imported artifact cannot use one, because
  the graph already recorded ``artifact_id=<sha256>`` in every body that names
  it. Registering under any other id yields a catalog that is populated and a
  project that still 404s on every id it actually holds. A 64-character hex
  digest is a valid single path component, which is what makes this legal.
- **Blobs are HARDLINKED, never copied.** The media is already inside the
  project; a copy would double a 300 MB production on the server's disk for no
  benefit. The link is safe rather than merely cheap *because* the filename is
  the digest: a shared inode can only ever be rewritten with identical bytes,
  and genuinely different bytes get a different name. A cross-device
  destination **refuses** (:class:`CrossDeviceCatalog`) instead of quietly
  copying gigabytes — the same bargain, and the same errno allow-list, as
  ``reelee.fork.fork_project``.
- **A row's ``url`` is never a ``file://`` path.** It is the host's own
  ``/api/artifacts/<id>/bytes`` route. This is not tidiness: a row registered
  by hand with a ``file://`` URL reached an ``<img src>`` and put the owner's
  home directory into the page's DOM. A local path in a served record is a
  disclosure, and it is also just wrong — the consumer is not on this machine.

**On writing another package's record shape.** The directory layout is
lacing's (``ArtifactStore.from_directory`` — a ``catalog/`` of JSON documents
beside a ``blobs/`` of content-addressed files), but the record *shape* in it
belongs to the host that reads it, and the host validates with
``extra="forbid"``. braidio cannot import it: the dependency runs the other way
(the host imports braidio's genre), so this module carries the shape as a
declared **wire contract** — :class:`CatalogRow` — rather than a guess.
``tests/test_importing.py`` validates a row braidio writes through the host's
own model whenever the host is importable, which is the only check that can
actually catch drift; the field list here is what CI pins when it is not.
"""

from __future__ import annotations

import errno
import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional

#: Where the host keeps its artifact store inside a project. lacing's layout,
#: the host's directory name.
DELIVERY_CATALOG_SUBPATH: tuple[str, ...] = (".reelee", "artifacts")
_CATALOG_DIRNAME = "catalog"
_BLOBS_DIRNAME = "blobs"

#: Content categories the host's catalog can hold. Deliberately NOT extended:
#: a row whose ``kind`` the host's ``Literal`` does not name fails validation
#: at read time, which turns one unservable file into a broken catalog.
#: braidio's ``text`` artifacts (an .srt sidecar) have no home here and are
#: reported unregistered rather than coerced into ``json``.
CATALOG_KINDS: frozenset[str] = frozenset({"image", "video", "audio", "json"})

#: The route the host serves a registered artifact from. A row's ``url`` is
#: this and never a local path — see the module docstring.
BYTES_ROUTE = "/api/artifacts/{artifact_id}/bytes"

#: ``os.link`` failures that mean "this filesystem cannot make the link",
#: as opposed to a real error. EXDEV is a different device; EMLINK is the link
#: ceiling; EPERM is a filesystem that refuses links outright. Everything else
#: propagates. Same allow-list as ``reelee.fork._link_or_copy``.
_LINKABLE_REFUSALS = (errno.EXDEV, errno.EMLINK, errno.EPERM)


class CrossDeviceCatalog(OSError):
    """The project's blob store is not on the source media's filesystem."""


@dataclass
class CatalogReport:
    """What registering a project's media did, and what it could not hold."""

    rows_written: int = 0
    rows_unchanged: int = 0
    blobs_linked: int = 0
    blobs_present: int = 0
    blobs_copied: int = 0
    bytes_copied: int = 0
    cross_device: bool = False
    #: ``(path, reason)`` for a file the catalog cannot hold — today only a
    #: kind outside :data:`CATALOG_KINDS`. Reported, never silently dropped:
    #: an unregistered artifact is one a caller will ask for and not get.
    unregistered: list[tuple[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "rows_written": self.rows_written,
            "rows_unchanged": self.rows_unchanged,
            "blobs_linked": self.blobs_linked,
            "blobs_present": self.blobs_present,
            "blobs_copied": self.blobs_copied,
            "bytes_copied": self.bytes_copied,
            "cross_device": self.cross_device,
            "unregistered": [list(u) for u in self.unregistered],
        }


class CatalogRow:
    """The host's artifact record, as JSON — a wire contract, not a model.

    Deliberately not a pydantic model: this is *the host's* schema and braidio
    has no business owning a second authority for it. It is a dict-builder with
    every field spelled out, so a failure to load on the host's side shows up
    as a diff against this list rather than as an absence.
    """

    #: Every key the host's record declares, in its own order. The host
    #: validates ``extra="forbid"``, so an omission and an addition are both
    #: fatal — which is why this is an exhaustive list rather than a subset.
    FIELDS: tuple[str, ...] = (
        "id",
        "kind",
        "url",
        "width",
        "height",
        "duration_seconds",
        "cost_usd",
        "provenance",
        "content_hash",
    )
    PROVENANCE_FIELDS: tuple[str, ...] = (
        "source",
        "model",
        "request_id",
        "prompt",
        "generated_at",
        "triggered_by",
        "filename",
    )

    @staticmethod
    def build(
        artifact_id: str,
        *,
        kind: str,
        generated_at: str,
        width: Optional[int] = None,
        height: Optional[int] = None,
        duration_s: Optional[float] = None,
        filename: str = "",
        note: str = "",
    ) -> dict:
        """One record, ready to serialize.

        >>> row = CatalogRow.build("ab" * 32, kind="image",
        ...     generated_at="2026-09-20T00:00:00Z", width=800, height=600)
        >>> row["id"] == row["content_hash"] == "ab" * 32
        True
        >>> row["url"]
        '/api/artifacts/abababababababababababababababababababababababababababababababab/bytes'
        >>> sorted(row) == sorted(CatalogRow.FIELDS)
        True
        """
        return {
            "id": artifact_id,
            "kind": kind,
            # NEVER a file:// path. See the module docstring.
            "url": BYTES_ROUTE.format(artifact_id=artifact_id),
            "width": width,
            "height": height,
            "duration_seconds": duration_s,
            "cost_usd": None,
            "provenance": {
                # "manual" is the host's value for "a person put these bytes
                # here", which is exactly what an import is. The alternatives
                # name generation vendors and would be a false claim.
                "source": "manual",
                "model": None,
                "request_id": None,
                "prompt": note or None,
                "generated_at": generated_at,
                "triggered_by": None,
                "filename": filename or None,
            },
            "content_hash": artifact_id,
        }


def catalog_root(project_root) -> Path:
    """``<project>/.reelee/artifacts`` — creates nothing.

    >>> catalog_root("/tmp/p").as_posix()
    '/tmp/p/.reelee/artifacts'
    """
    return Path(project_root).joinpath(*DELIVERY_CATALOG_SUBPATH)


def catalog_dir(project_root) -> Path:
    """Where the rows live."""
    return catalog_root(project_root) / _CATALOG_DIRNAME


def blobs_dir(project_root) -> Path:
    """Where the content-addressed bytes live."""
    return catalog_root(project_root) / _BLOBS_DIRNAME


def hash_file(path, *, chunk_size: int = 1 << 20) -> str:
    """SHA-256 of a file's bytes, chunked — the same digest lacing computes.

    Kept here rather than imported from lacing so this module can be reasoned
    about (and tested) without the graph layer; the two are pinned equal by
    ``tests/test_importing.py``.

    >>> import tempfile, pathlib
    >>> with tempfile.TemporaryDirectory() as d:
    ...     p = pathlib.Path(d, "x"); _ = p.write_bytes(b"abc")
    ...     hash_file(p)
    'ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad'
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def _link_or_copy(src: Path, dst: Path, *, allow_copy: bool) -> tuple[bool, int]:
    """Hardlink ``src`` to ``dst``; ``(linked, bytes_written)``.

    Only the three "this filesystem cannot link" errnos are eligible for the
    copy fallback, and only when the caller asked for it. Every other
    ``OSError`` is a real failure and propagates.
    """
    try:
        os.link(src, dst)
        return True, 0
    except OSError as exc:
        if exc.errno not in _LINKABLE_REFUSALS:
            raise
        if not allow_copy:
            raise CrossDeviceCatalog(
                exc.errno,
                f"cannot hardlink {src.name} into {dst.parent}: the project's "
                "blob store is not on the same filesystem as the media. The "
                "catalog shares bytes by inode, so this would silently copy "
                "the whole production a second time. Put the project on the "
                "media's filesystem, or pass allow_cross_device_copy=True to "
                "pay for the copy deliberately.",
            ) from exc
        import shutil

        shutil.copy2(src, dst)
        return False, dst.stat().st_size


def register_artifact(
    project_root,
    path,
    *,
    artifact_id: str,
    kind: str,
    generated_at: str,
    report: CatalogReport,
    width: Optional[int] = None,
    height: Optional[int] = None,
    duration_s: Optional[float] = None,
    note: str = "",
    allow_cross_device_copy: bool = False,
) -> bool:
    """Make ``artifact_id`` retrievable from ``project_root``. True if it now is.

    ``artifact_id`` must be the content hash of ``path``'s bytes — it is what
    the graph already recorded, and registering under anything else produces a
    catalog that answers nothing the project actually asks for. The caller
    passes it rather than this function recomputing it, so the two can be
    compared: a mismatch means the file on disk is not the file the graph
    describes, which is a real defect and is raised, not repaired.
    """
    src = Path(path)
    if kind not in CATALOG_KINDS:
        report.unregistered.append(
            (str(src), f"kind {kind!r} is not one the catalog can hold")
        )
        return False

    blobs = blobs_dir(project_root)
    blobs.mkdir(parents=True, exist_ok=True)
    rows = catalog_dir(project_root)
    rows.mkdir(parents=True, exist_ok=True)

    blob = blobs / artifact_id
    if blob.exists():
        # Content-addressed: the name IS the digest, so anything already
        # under it is byte-identical by construction.
        report.blobs_present += 1
    else:
        linked, written = _link_or_copy(src, blob, allow_copy=allow_cross_device_copy)
        if linked:
            report.blobs_linked += 1
        else:
            report.blobs_copied += 1
            report.bytes_copied += written
            report.cross_device = True

    # The row LAST, and only now the blob is there: the host's route reads the
    # row first, so a row without bytes behind it is a 500 rather than a 404.
    row_path = rows / f"{artifact_id}.json"
    row = CatalogRow.build(
        artifact_id,
        kind=kind,
        generated_at=generated_at,
        width=width,
        height=height,
        duration_s=duration_s,
        filename=src.name,
        note=note,
    )
    if row_path.exists():
        try:
            existing = json.loads(row_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            existing = None
        # `generated_at` is when this artifact was FIRST registered, so a
        # re-import must not move it — and comparing it would make every
        # re-import rewrite every row, which is the catalog's version of the
        # timestamp churn the graph's `_upsert` exists to avoid.
        if existing is not None and _same_but_for_stamp(existing, row):
            report.rows_unchanged += 1
            return True
    row_path.write_text(json.dumps(row, indent=2), encoding="utf-8")
    report.rows_written += 1
    return True


def _same_but_for_stamp(a: dict, b: dict) -> bool:
    """Two rows equal, ignoring when they were registered.

    >>> row = CatalogRow.build("ab" * 32, kind="image", generated_at="2026-01-01T00:00:00Z")
    >>> later = CatalogRow.build("ab" * 32, kind="image", generated_at="2027-06-06T12:00:00Z")
    >>> _same_but_for_stamp(row, later)
    True
    >>> _same_but_for_stamp(row, CatalogRow.build("cd" * 32, kind="image",
    ...     generated_at="2026-01-01T00:00:00Z"))
    False
    """

    def _strip(row: dict) -> dict:
        out = dict(row)
        prov = dict(out.get("provenance") or {})
        prov.pop("generated_at", None)
        out["provenance"] = prov
        return out

    return _strip(a) == _strip(b)


def registered_ids(project_root) -> frozenset[str]:
    """Every artifact id this project's catalog currently answers for."""
    rows = catalog_dir(project_root)
    if not rows.is_dir():
        return frozenset()
    return frozenset(p.stem for p in rows.glob("*.json"))


def iter_rows(project_root) -> Iterable[dict]:
    """Every catalog row, parsed. For tests and diagnostics."""
    for p in sorted(catalog_dir(project_root).glob("*.json")):
        yield json.loads(p.read_text(encoding="utf-8"))
