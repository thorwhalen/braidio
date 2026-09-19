"""Path-component validation, shared by every place braidio turns a caller's
string into a directory or file name.

Stdlib-only and dependency-free **on purpose**. This rule used to live in
:mod:`braidio.mcp.workspace`, so the two modules that needed it outside the MCP
server (:mod:`braidio.downloads`, and now :mod:`braidio.genre`'s host-placed
create) had to import ``braidio.mcp.workspace`` to get it — which runs
``braidio/mcp/__init__.py`` and pulls **fastmcp** into ``sys.modules``. For
``braidio.genre`` that is not merely wasteful: the genre module is imported by
``braidio/__init__`` whenever nw is present, and the create path a *host* drives
(reelee serving a ``commentary_weave`` project over HTTP) has no reason to
require the MCP extra at all.

One rule, one home, no surface cost.
"""

from __future__ import annotations

__all__ = ["safe_component"]


def safe_component(value: str, *, label: str) -> str:
    """A single, traversal-safe path component.

    Rejects the empty string, ``.``/``..``, either separator, and a NUL — i.e.
    everything that would let a caller-supplied name address something other
    than a direct child of the directory it is joined to.

    >>> safe_component("ep_01", label="project_id")
    'ep_01'
    >>> safe_component("  ep_01  ", label="project_id")
    'ep_01'
    >>> safe_component("../escape", label="project_id")
    Traceback (most recent call last):
        ...
    ValueError: invalid project_id: '../escape'
    """
    v = (value or "").strip()
    if not v or v in (".", "..") or "/" in v or "\\" in v or "\x00" in v:
        raise ValueError(f"invalid {label}: {value!r}")
    return v
