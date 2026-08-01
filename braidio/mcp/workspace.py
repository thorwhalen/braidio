"""Per-user project + render workspace for the braidio MCP server.

A remote MCP connector is stateless and multi-user: it carries no ambient project
and each caller must be isolated. This module maps a caller's email to a private
area under the braidio data root and owns the filesystem layout — so tools take a
``project_id`` (never a path) and cannot reach another user's data.

Layout (default root ``~/.local/share/braidio``; override via ``BRAIDIO_DATA_HOME``):

- ``{root}/projects/{email}/{project_id}/`` — an nw project folder (graph + files)
- ``{root}/renders/{email}/{name}.mp3`` — one-shot (non-project) renders

Per the app-data-lifecycle rule this lives in the user-data dir, **never** inside
the app/deploy tree (a deploy's ``rsync --delete`` would erase it).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

#: Env var overriding the braidio data root (where per-user projects/renders live).
DATA_HOME_ENV_VAR = "BRAIDIO_DATA_HOME"


def data_root() -> Path:
    """The braidio data root: ``$BRAIDIO_DATA_HOME`` or ``~/.local/share/braidio``."""
    override = os.environ.get(DATA_HOME_ENV_VAR)
    return Path(override) if override else Path.home() / ".local" / "share" / "braidio"


def _safe_component(value: str, *, label: str) -> str:
    """A single, traversal-safe path component (no ``/``, ``\\``, ``..``, or empties)."""
    v = (value or "").strip()
    if not v or v in (".", "..") or "/" in v or "\\" in v or "\x00" in v:
        raise ValueError(f"invalid {label}: {value!r}")
    return v


@dataclass(frozen=True)
class Workspace:
    """A single caller's private area, addressed by ``email``.

    ``email`` and every ``project_id`` are validated as single path components, so
    a caller can never escape their own subtree.
    """

    email: str
    root: Path

    @classmethod
    def for_email(cls, email: str, *, root: Path | None = None) -> "Workspace":
        return cls(email=email, root=root or data_root())

    @property
    def projects_dir(self) -> Path:
        return self.root / "projects" / _safe_component(self.email, label="email")

    @property
    def renders_dir(self) -> Path:
        return self.root / "renders" / _safe_component(self.email, label="email")

    def project_root(self, project_id: str) -> Path:
        pid = _safe_component(project_id, label="project_id")
        return self.projects_dir / pid

    def create_project(self, project_id: str, *, title: str = "", force: bool = False):
        """Create (and return) a new :class:`braidio.Project` under this user."""
        from braidio import Project

        root = self.project_root(project_id)
        root.parent.mkdir(parents=True, exist_ok=True)
        return Project.init(root, title=title or project_id, force=force)

    def open_project(self, project_id: str):
        """Open an existing :class:`braidio.Project` (raises if it doesn't exist)."""
        from braidio import Project

        root = self.project_root(project_id)
        if not (root / "project.json").exists():
            raise FileNotFoundError(f"no project {project_id!r} for {self.email}")
        return Project(root)

    def list_projects(self) -> list[dict]:
        """List this user's projects: ``[{project_id, title}]`` (newest-modified first)."""
        pdir = self.projects_dir
        if not pdir.exists():
            return []
        rows = []
        for child in pdir.iterdir():
            spec = child / "project.json"
            if not (child.is_dir() and spec.exists()):
                continue
            try:
                title = json.loads(spec.read_text()).get("title", child.name)
            except (OSError, ValueError):
                title = child.name
            rows.append(
                {
                    "project_id": child.name,
                    "title": title,
                    "mtime": spec.stat().st_mtime,
                }
            )
        rows.sort(key=lambda r: r["mtime"], reverse=True)
        for r in rows:
            r.pop("mtime")
        return rows

    def render_path(self, name: str, *, suffix: str = ".mp3") -> Path:
        """A path for a one-shot (non-project) render, inside this user's renders dir."""
        stem = _safe_component(name, label="render name")
        self.renders_dir.mkdir(parents=True, exist_ok=True)
        return self.renders_dir / f"{stem}{suffix}"

    # -- assets (braidio#10) --------------------------------------------------
    # Media/source blobs a caller uploads, stored through a dol content store so
    # the local backend can later swap to s3dol with no tool-code change. Assets
    # are **per-user** (not per-project): content-addressing dedupes identical
    # media across a user's productions, and one-shot renders (render_production /
    # render_format — no project) share the same store as the project graph.
    # Content (bytes) is content-addressed under ``assets/{email}/``; a JSON
    # sidecar under ``assets_meta/{email}/`` holds each blob's name/mime/size (the
    # content-metadata bifurcation — the CAS store only knows hashes).

    @property
    def assets_dir(self) -> Path:
        return self.root / "assets" / _safe_component(self.email, label="email")

    def content_store(self):
        """The user's content-addressed asset store (``dol`` — local now, S3 later).

        The backend is a local :class:`dol.Files`; swapping it for an ``s3dol`` store
        (or injecting one) needs no change to the tools that consume this.
        """
        from dol import Files, with_content_addressing

        self.assets_dir.mkdir(parents=True, exist_ok=True)
        return with_content_addressing(Files(str(self.assets_dir)))

    def asset_meta(self):
        """The user's asset metadata sidecar (``{hash: {name, mimeType, size, ...}}``)."""
        from dol import JsonFiles

        d = self.root / "assets_meta" / _safe_component(self.email, label="email")
        d.mkdir(parents=True, exist_ok=True)
        return JsonFiles(str(d))

    def asset_path(self, asset_id: str) -> str:
        """Resolve a stored asset (a :class:`dol.ContentRef` ``item_id``/hash) to its
        server-local file path — so weave/render can read the media."""
        key = _safe_component(asset_id, label="asset_id")
        if key not in self.content_store():
            raise FileNotFoundError(f"no asset {asset_id!r} for {self.email}")
        return str(self.assets_dir / key)
