"""braidio as an nw app: a :class:`nw.Project` for commentary-weave productions.

Subclassing ``nw.Project`` inherits the whole folder facade + lacing graph +
freshness (``stale_after``) machinery; braidio adds its production kind and its
domain/render body-schema vocabulary (registered on import of
:mod:`braidio.bodies`). This module requires ``nw``; it is imported lazily by
``braidio/__init__`` only when ``nw`` is available.

The costed ``plan``/``execute`` Transform pipeline (each transform delegating to
braidio's functional core for the actual audio, and recording provenance via
:mod:`braidio.provenance`) is the next increment — see the design doc and
nw#9 (generalizing nw's shot/mp4 render seam).
"""

from __future__ import annotations

from pathlib import Path

import nw

from braidio import bodies as _bodies  # noqa: F401  (import registers schemas)
from braidio.kinds import WeaveKind


class Project(nw.Project):
    """An nw project for a braidio commentary-weave production."""

    KIND: WeaveKind = WeaveKind.COMMENTARY_WEAVE


def create_project_at(
    projects_dir: "str | Path", project_id: str, *, title: str = "", force: bool = False
) -> Project:
    """Create a braidio project at ``projects_dir/<project_id>`` — the *host-placed* create.

    The counterpart to :meth:`braidio.mcp.workspace.Workspace.create_project`, which
    places a project in braidio's own per-caller workspace. This one takes the
    directory from its caller, because a host that will **serve** the project
    (reelee, over HTTP) has to put it where its own resolver and lister look — under
    braidio's data home it would be a sibling of nothing the host can address. See
    nw's ``projects_dir`` placement contract (thorwhalen/nw#84).

    Deliberately here and not in ``braidio.mcp.workspace``: importing that module
    runs ``braidio/mcp/__init__.py`` and pulls **fastmcp**, and the host-placed path
    has no reason to require the MCP extra. ``project_id`` is validated as a single
    traversal-safe component, so the result is always a direct child of
    ``projects_dir`` — which is the property the host's lister depends on, and which
    nw verifies after the fact.

    >>> import tempfile
    >>> with tempfile.TemporaryDirectory() as d:
    ...     p = create_project_at(d, "ep_01", title="Episode 1")
    ...     p.root.name
    'ep_01'
    """
    from braidio._paths import safe_component

    root = Path(projects_dir) / safe_component(project_id, label="project_id")
    root.parent.mkdir(parents=True, exist_ok=True)
    return Project.init(root, title=title or project_id, force=force)
