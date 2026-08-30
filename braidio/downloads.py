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

Two locations, one caller-facing set (braidio#32)
-------------------------------------------------
A caller's audio lives in two places, and resolution spans both:

- **Flat renders** — every standalone render site (``render_production``,
  ``render_format``, ``narrate``, ``render_dialogue``, ``compose_narration``)
  writes through ``Workspace.render_path``: one flat per-caller directory keyed
  by the title the caller gave the render.
- **Project episodes** — the graph pipeline (``weave_project``) writes each
  assembled episode inside its project, at
  ``{project}/data/episodes/{annotation_id}.mp3``. That location is
  load-bearing: the episode annotation's body records that ``url``, and the
  partial-re-render DAG hangs off it. Delivery adapts to the graph's layout,
  never the other way around.

An earlier revision of this module claimed the project weaves wrote into the
flat directory too. They never did, and the one episode a paying caller
produced through the *documented* project-attached path was exactly the one no
tool could return (braidio#32). The lesson is the module's own founding lesson
one directory over: a resolver that covers only the layout its author
remembered is a resolver with an unreachable population.

``project_id`` still does not narrow anything: it is accepted and ignored.
Callers guess it — the connector requires *some* project_id for braidio but
never validates which, and nothing ties the value in a claim to where the
file actually lives — so treating it as a filter would refuse resolvable
claims over a field that carries no information. Episodes are found by
scanning the caller's own projects, which is bounded and email-scoped.
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


def _episode_deliverable(path: Path, project_id: str, project_title: str) -> Deliverable:
    """A project episode as a Deliverable — id-keyed, so it reads differently.

    The stem is an annotation uuid nobody can say, so ``ref`` stays ``None``
    (``label`` falls back to the id) rather than pretending the uuid is a
    reference, and the human-facing fields borrow the project's title so a
    listing row and a Downloads-folder filename both say whose episode it is.
    """
    stat = path.stat()
    return Deliverable(
        path=path,
        content_type=_CONTENT_TYPES[path.suffix.lower()],
        filename=f"{project_id}-episode-{path.stem[:8]}{path.suffix}",
        artifact_id=path.stem,
        project_id=project_id,
        genre=GENRE,
        ref=None,
        title=f"{project_title} — episode",
        size_bytes=stat.st_size,
        created_at=stat.st_mtime,
        meta={"kind": "episode"},
    )


def _episode_dirs(email: str):
    """``(project_id, title, episodes_dir)`` for each of the caller's projects.

    Bounded: ``list_projects`` only yields directories under the caller's own
    email-scoped tree that carry a ``project.json``. Two hardenings on top:

    - A project whose *resolved* episodes dir escapes the caller's projects
      tree (a symlinked project root or a symlinked ``data/episodes``) is
      skipped — the per-file parent check alone follows the symlinked
      component first and so would happily serve another tenant's directory.
      Nothing reachable creates such a symlink today; this is the check that
      keeps that sentence from having to stay true forever.
    - A directory name that fails the component rule is skipped rather than
      raised: it cannot hold an episode our tools wrote (``create_project``
      applies the same rule), and one out-of-band directory must not turn
      every braidio lookup into a 500.

    Note the ``project.json`` filter's flip side: an episode whose project has
    lost its ``project.json`` is invisible here — acceptable, because
    ``weave_project`` cannot have written it without one (``open_project``
    requires it), so the state only arises from out-of-band damage.
    """
    ws = _workspace(email)
    projects_root = ws.projects_dir.resolve()
    for row in ws.list_projects():
        pid = row["project_id"]
        try:
            episodes = ws.project_root(pid) / "data" / "episodes"
            if not episodes.resolve().is_relative_to(projects_root):
                continue
        except (ValueError, OSError):
            continue
        yield pid, row.get("title", pid), episodes


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

    # Not a flat render — try it as a project episode id (braidio#32). Every
    # project of the caller's is checked, not just ``project_id``: callers
    # guess that argument (nothing validates it against where the file lives),
    # so trusting it would refuse a claim for an episode that exists.
    for pid, title, episodes in _episode_dirs(email):
        for ext in _CONTENT_TYPES:
            candidate = episodes / f"{stem}{ext}"
            if candidate.is_file() and candidate.resolve().parent == episodes.resolve():
                return _episode_deliverable(candidate, pid, title)

    raise KeyError(f"no render named {name!r}")


def list_deliverables(email: str, project_id: str = None) -> "list[Deliverable]":
    """Everything this caller can be handed — flat renders AND project episodes,
    newest first.

    Without this a reference is undiscoverable — a user could only name a render
    they still remembered from an earlier conversation, which is exactly the
    state that left a paid episode unreachable (braidio#32: the episode existed,
    resolved by nothing, and appeared in no listing). ``project_id`` is accepted
    and ignored (see the module docstring).
    """
    out = []
    renders = _workspace(email).renders_dir
    if renders.is_dir():
        for child in sorted(renders.iterdir()):
            if child.is_file() and child.suffix.lower() in _CONTENT_TYPES:
                try:
                    out.append(_deliverable(child, email))
                except OSError:
                    continue
    for pid, title, episodes in _episode_dirs(email):
        if not episodes.is_dir():
            continue
        for child in sorted(episodes.iterdir()):
            if child.is_file() and child.suffix.lower() in _CONTENT_TYPES:
                try:
                    out.append(_episode_deliverable(child, pid, title))
                except OSError:
                    continue
    out.sort(key=lambda d: d.created_at or 0, reverse=True)
    return out
