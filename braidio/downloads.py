"""Resolve a caller's rendered audio to its file — braidio's half of delivery.

Every braidio render tool returns ``out.as_uri()``: a ``file://`` path on the
connector's own filesystem, meaningless to a remote caller. A user paid $0.1233
and $0.0252 for two episodes that rendered correctly, passed every check, and
could not be retrieved by any tool on any surface. The defect hid for months
because on a local stdio server a ``file://`` path IS openable by the human
sitting at that machine — it only becomes visible the moment there is a remote
caller, which is also the moment it costs money.

This is the module braidio#10 called *"the actual deliverable of a costed
render"* and which that issue was closed without. Ownership follows the seam
agreed in reelee#252 §1 and already serving muvid:

- **braidio owns resolution** (this module): claim → file, authorised by the
  same per-email workspace scoping every tool uses. It never touches token,
  URL or page code.
- **The host owns transport**: one connector-owned route turning claims into
  signed, expiring URLs and a watch page.

Why braidio's references are names, not numbers
-----------------------------------------------
muvid names a render ``b02fc05417ea`` — a uuid slice nobody can say — so it
assigns ordinals (``cut 4``) and :mod:`nw.delivery` ships the parser for them.
braidio has the opposite problem and needs the opposite answer: its renders are
already titled by the person who made them (*"Why the Sky Looks Blue"*), and
layering ``episode 3`` on top of a real title would replace a good reference
with a worse one. So braidio's ``ref`` IS the title.

That is not an inconsistency in the seam — it is the seam working. A genre
supplies whatever reference is natural for it; ``Deliverable.ref`` means "the
label a human should say", and only the genre knows what that is.

One flat directory, deliberately
--------------------------------
Every render site — ``render_production``, ``render_format``,
``weave_project``, ``narrate``, ``render_dialogue``, ``compose_narration`` —
writes through ``Workspace.render_path``, and the project weaves pass
``episodes_dir=ws.renders_dir`` too. So a caller's audio is one flat set keyed
by title, and ``project_id`` does not narrow it. It is accepted and ignored
rather than removed, because the seam's signature is shared with genres for
which it IS meaningful, and a resolver that silently ignores an argument is
better than one that refuses a well-formed claim.
"""

from __future__ import annotations

from pathlib import Path

from nw.delivery import Deliverable

#: The genre identifier the connector's resolver registry keys on.
GENRE = "braidio"

#: Extensions a render may legitimately carry, with their content types. braidio
#: produces audio; ``.mp4`` is here because an audiovisual format render lands in
#: the same directory and would otherwise be listed but unservable.
_CONTENT_TYPES = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
    ".mp4": "video/mp4",
}

__all__ = ["GENRE", "claim", "resolve", "list_deliverables"]


def claim(project_id: str, artifact_id: str) -> dict:
    """The claim dict a tool returns — what the connector turns into a signed URL."""
    return {"genre": GENRE, "project_id": project_id, "artifact_id": artifact_id}


def _workspace(email: str):
    from braidio.mcp.workspace import Workspace

    return Workspace.for_email(email)


def _deliverable(path: Path, email: str, project_id: str = "") -> Deliverable:
    stat = path.stat()
    return Deliverable(
        path=path,
        content_type=_CONTENT_TYPES[path.suffix.lower()],
        # The title IS the filename here, so it needs no rewriting to be
        # recognisable in a Downloads folder.
        filename=path.name,
        artifact_id=path.stem,
        project_id=project_id,
        genre=GENRE,
        ref=path.stem,
        title=path.stem,
        size_bytes=stat.st_size,
        created_at=stat.st_mtime,
    )


def resolve(email: str, project_id: str, artifact_id: str) -> Deliverable:
    """The caller's rendered audio as a servable file — braidio's download authority.

    ``artifact_id`` is the render's title, with or without its extension.
    ``project_id`` is accepted and ignored (see the module docstring).

    Raises ``KeyError`` for anything that does not resolve to a render of *this*
    caller — including titles shaped like an attack and other users' work. (No
    ``PermissionError`` branch: the renders directory is scoped by email, so
    "someone else's episode" and "no such episode" are indistinguishable here,
    and saying which would leak existence.)
    """
    from braidio.mcp.workspace import _safe_component

    name = (artifact_id or "").strip()
    try:
        # The same rule the workspace applies when it CREATES a render, so we
        # never refuse something it happily wrote.
        _safe_component(name, label="artifact_id")
    except ValueError as e:
        raise KeyError(str(e)) from None

    renders = _workspace(email).renders_dir
    stem = Path(name).stem if Path(name).suffix.lower() in _CONTENT_TYPES else name
    for ext in _CONTENT_TYPES:
        candidate = renders / f"{stem}{ext}"
        # resolve() the parent to defeat a symlink planted inside the dir; the
        # component check above already refuses `..` and separators.
        if candidate.is_file() and candidate.resolve().parent == renders.resolve():
            return _deliverable(candidate, email, project_id)
    raise KeyError(f"no render named {name!r}")


def list_deliverables(email: str, project_id: str = None) -> "list[Deliverable]":
    """Every render this caller can be handed, newest first.

    Without this a reference is undiscoverable — a user could only name a render
    they still remembered from an earlier conversation, which is exactly the
    state that left a paid episode unreachable. ``project_id`` is accepted and
    ignored: braidio's renders are one flat per-caller set.
    """
    renders = _workspace(email).renders_dir
    if not renders.is_dir():
        return []
    out = []
    for child in sorted(renders.iterdir()):
        if child.is_file() and child.suffix.lower() in _CONTENT_TYPES:
            try:
                out.append(_deliverable(child, email))
            except OSError:
                continue
    out.sort(key=lambda d: d.created_at or 0, reverse=True)
    return out
