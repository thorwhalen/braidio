"""braidio.downloads — the resolver half of render retrieval (braidio#10 item 1).

The defect these guard against is not a crash: every braidio render tool
*succeeded*, charged correctly, and returned a `file://` path on the connector's
own disk that no remote caller could read. It hid for months because on a local
stdio server that path IS openable by the human sitting there — it only becomes
visible the moment there is a remote caller, which is also the moment it costs
money.

So the contract under test is: resolve() is the ONLY authority mapping
(email, artifact_id) -> file, it refuses everything that is not the caller's
with KeyError (no existence leaks, no traversal), and the render tools hand out
claims rather than paths a remote caller cannot use.
"""

from __future__ import annotations

import pytest

nw = pytest.importorskip("nw")

from nw.delivery import Deliverable  # noqa: E402

from braidio.downloads import GENRE, claim, list_deliverables, resolve  # noqa: E402

OWNER = "owner@example.com"
OTHER = "someone-else@example.com"


def _render(tmp_path, monkeypatch, *, email=OWNER, name="Why the Sky Looks Blue",
            ext=".mp3", data=b"ID3-audio-bytes"):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    from braidio.mcp.workspace import Workspace

    ws = Workspace.for_email(email)
    ws.renders_dir.mkdir(parents=True, exist_ok=True)
    path = ws.renders_dir / f"{name}{ext}"
    path.write_bytes(data)
    return path


def test_resolve_returns_the_shared_deliverable_not_a_path(tmp_path, monkeypatch):
    """The host reads .path/.content_type/.filename off the return value.

    Typing this seam `-> Path` while a genre returned its own dataclass is what
    made every muvid download a 500 for its whole life (thorwhalen/reelee#322).
    braidio builds to the shared type from the start.
    """
    _render(tmp_path, monkeypatch)
    got = resolve(OWNER, "", "Why the Sky Looks Blue")
    assert isinstance(got, Deliverable)
    assert got.path.read_bytes() == b"ID3-audio-bytes"
    assert got.content_type == "audio/mpeg"
    assert got.filename == "Why the Sky Looks Blue.mp3"
    assert got.kind == "audio"
    assert got.genre == GENRE


def test_the_reference_is_the_title_because_braidio_already_has_one(
    tmp_path, monkeypatch
):
    """muvid invents `cut 4` because its ids are uuids. braidio must not:
    replacing a real title with `episode 3` is a worse reference, not a better
    one. `Deliverable.ref` means "the label a human should say"."""
    _render(tmp_path, monkeypatch)
    got = resolve(OWNER, "", "Why the Sky Looks Blue")
    assert got.ref == "Why the Sky Looks Blue"
    assert got.label == "Why the Sky Looks Blue"


def test_the_extension_is_optional_because_a_human_will_omit_it(
    tmp_path, monkeypatch
):
    _render(tmp_path, monkeypatch)
    with_ext = resolve(OWNER, "", "Why the Sky Looks Blue.mp3")
    without = resolve(OWNER, "", "Why the Sky Looks Blue")
    assert with_ext.path == without.path


@pytest.mark.parametrize("ext,ctype", [(".mp3", "audio/mpeg"), (".wav", "audio/wav"),
                                       (".m4a", "audio/mp4"), (".mp4", "video/mp4")])
def test_every_extension_a_render_may_carry_is_servable(
    tmp_path, monkeypatch, ext, ctype
):
    """A format render lands in the same directory; listing something we cannot
    serve would be a worse bug than not listing it."""
    _render(tmp_path, monkeypatch, name="Ep", ext=ext)
    assert resolve(OWNER, "", "Ep").content_type == ctype


def test_resolve_refuses_another_callers_render(tmp_path, monkeypatch):
    _render(tmp_path, monkeypatch, email=OWNER)
    with pytest.raises(KeyError):
        resolve(OTHER, "", "Why the Sky Looks Blue")


def test_resolve_refuses_traversal_shaped_ids(tmp_path, monkeypatch):
    """The renders dir is flat and email-scoped; nothing may address outside it."""
    _render(tmp_path, monkeypatch)
    # Something worth stealing, one level up from the caller's renders dir.
    (tmp_path / "renders" / "secret.mp3").write_bytes(b"not yours")
    for bad in ("../secret", "../secret.mp3", "a/b", "", ".", "..", "\x00x"):
        with pytest.raises(KeyError):
            resolve(OWNER, "", bad)


def test_resolve_refuses_a_missing_render_without_saying_whose_it_is(
    tmp_path, monkeypatch
):
    _render(tmp_path, monkeypatch, email=OTHER, name="Private Episode")
    with pytest.raises(KeyError) as exc:
        resolve(OWNER, "", "Private Episode")
    # "no such render" and "not yours" must be indistinguishable — saying which
    # would confirm the existence of another tenant's work.
    assert OTHER not in str(exc.value)


def test_project_id_is_accepted_and_ignored(tmp_path, monkeypatch):
    """Every render site writes to one flat per-caller dir, so project_id does
    not narrow anything. It is ignored rather than refused, because the seam's
    signature is shared with genres for which it IS meaningful."""
    _render(tmp_path, monkeypatch)
    a = resolve(OWNER, "", "Why the Sky Looks Blue")
    b = resolve(OWNER, "some_project", "Why the Sky Looks Blue")
    assert a.path == b.path


def test_listing_is_how_a_reference_becomes_discoverable(tmp_path, monkeypatch):
    """Without it a user can only name a render they still remember — the state
    that left a PAID episode unreachable."""
    _render(tmp_path, monkeypatch, name="First")
    _render(tmp_path, monkeypatch, name="Second")
    _render(tmp_path, monkeypatch, email=OTHER, name="Not Yours")

    refs = {d.ref for d in list_deliverables(OWNER)}
    assert refs == {"First", "Second"}
    assert all(d.genre == GENRE for d in list_deliverables(OWNER))
    # Blind to everyone else's work.
    assert {d.ref for d in list_deliverables(OTHER)} == {"Not Yours"}


def test_listing_is_empty_rather_than_raising_for_a_caller_with_nothing(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    assert list_deliverables("nobody@example.com") == []


def test_listing_skips_non_media_without_dropping_the_rest(tmp_path, monkeypatch):
    path = _render(tmp_path, monkeypatch, name="Real")
    (path.parent / "notes.txt").write_text("scratch")
    (path.parent / "_work").mkdir(exist_ok=True)
    assert {d.ref for d in list_deliverables(OWNER)} == {"Real"}


EPISODE_ID = "9a23da78-0a3e-4acf-a557-48bd6e519038"


def _episode(tmp_path, monkeypatch, *, email=OWNER, project_id="braidio_test_02",
             title="Sky Colours", episode_id=EPISODE_ID, data=b"episode-bytes"):
    """An episode exactly where ``weave_project``'s pipeline writes one:
    ``{project}/data/episodes/{annotation_id}.mp3`` (braidio#32)."""
    import json

    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    from braidio.mcp.workspace import Workspace

    ws = Workspace.for_email(email)
    root = ws.project_root(project_id)
    root.mkdir(parents=True, exist_ok=True)
    (root / "project.json").write_text(json.dumps({"title": title}))
    episodes = root / "data" / "episodes"
    episodes.mkdir(parents=True, exist_ok=True)
    path = episodes / f"{episode_id}.mp3"
    path.write_bytes(data)
    return path


def test_a_weave_project_episode_is_retrievable_by_its_id(tmp_path, monkeypatch):
    """The braidio#32 defect verbatim: the one render made through the path we
    told the caller was CORRECT was the one no tool could return."""
    path = _episode(tmp_path, monkeypatch)
    got = resolve(OWNER, "braidio_test_02", EPISODE_ID)
    assert isinstance(got, Deliverable)
    assert got.path == path
    assert got.content_type == "audio/mpeg"
    assert got.project_id == "braidio_test_02"
    assert got.artifact_id == EPISODE_ID


def test_an_episode_resolves_whatever_project_id_the_claim_carries(
    tmp_path, monkeypatch
):
    """Callers guess project_id — nothing validates it against where the file
    lives — so trusting it would refuse a claim for an episode that exists."""
    _episode(tmp_path, monkeypatch)
    for pid in ("", "some_reelee_project", "braidio_test_02"):
        assert resolve(OWNER, pid, EPISODE_ID).artifact_id == EPISODE_ID


def test_episodes_appear_in_the_listing_beside_flat_renders(tmp_path, monkeypatch):
    """Listing is how a reference becomes discoverable; an episode absent from
    the listing is unreachable by anyone who did not memorise a uuid."""
    _render(tmp_path, monkeypatch, name="Standalone")
    _episode(tmp_path, monkeypatch)
    rows = list_deliverables(OWNER)
    by_id = {d.artifact_id: d for d in rows}
    assert set(by_id) == {"Standalone", EPISODE_ID}
    ep = by_id[EPISODE_ID]
    assert ep.project_id == "braidio_test_02"
    # The stem is a uuid nobody can say: no ref is honest, the label falls back
    # to the id, and the title borrows the project's so the row reads humanly.
    assert ep.ref is None
    assert ep.label == EPISODE_ID
    assert ep.title == "Sky Colours — episode"
    assert ep.filename.startswith("braidio_test_02-episode-")


def test_an_episode_of_another_caller_is_refused_without_naming_them(
    tmp_path, monkeypatch
):
    _episode(tmp_path, monkeypatch, email=OTHER)
    with pytest.raises(KeyError) as exc:
        resolve(OWNER, "braidio_test_02", EPISODE_ID)
    assert OTHER not in str(exc.value)


def test_episode_lookup_refuses_traversal_and_symlinks(tmp_path, monkeypatch):
    _episode(tmp_path, monkeypatch)
    # Something worth stealing, outside every episodes dir.
    secret = tmp_path / "secret.mp3"
    secret.write_bytes(b"not yours")
    for bad in ("../secret", "../../../secret", "a/b"):
        with pytest.raises(KeyError):
            resolve(OWNER, "braidio_test_02", bad)
    # A symlink planted inside the episodes dir must not escape it.
    from braidio.mcp.workspace import Workspace

    episodes = (
        Workspace.for_email(OWNER).project_root("braidio_test_02")
        / "data" / "episodes"
    )
    (episodes / "planted.mp3").symlink_to(secret)
    with pytest.raises(KeyError):
        resolve(OWNER, "braidio_test_02", "planted")


def test_a_symlinked_project_component_cannot_reach_another_tenant(
    tmp_path, monkeypatch
):
    """The per-file parent check follows a symlinked DIRECTORY component first,
    so it alone would serve a victim's episodes through a symlinked project
    root or a symlinked episodes dir. The containment check in _episode_dirs
    is what refuses both."""
    import json

    victim_path = _episode(tmp_path, monkeypatch, email=OTHER, data=b"victim-bytes")
    from braidio.mcp.workspace import Workspace

    ws = Workspace.for_email(OWNER)
    ws.projects_dir.mkdir(parents=True, exist_ok=True)

    # Attack 1: the caller's project root IS a symlink to the victim's project.
    (ws.projects_dir / "stolen").symlink_to(victim_path.parents[2])
    with pytest.raises(KeyError):
        resolve(OWNER, "stolen", EPISODE_ID)
    assert EPISODE_ID not in {d.artifact_id for d in list_deliverables(OWNER)}

    # Attack 2: a real project whose data/episodes is a symlink to the victim's.
    mine = ws.projects_dir / "mine"
    (mine / "data").mkdir(parents=True)
    (mine / "project.json").write_text(json.dumps({"title": "Mine"}))
    (mine / "data" / "episodes").symlink_to(victim_path.parent)
    with pytest.raises(KeyError):
        resolve(OWNER, "mine", EPISODE_ID)
    assert EPISODE_ID not in {d.artifact_id for d in list_deliverables(OWNER)}


def test_one_damaged_project_does_not_take_down_the_listing(tmp_path, monkeypatch):
    """A project.json holding a JSON LIST used to raise AttributeError out of
    the title read, turning every braidio lookup for that caller into a 500 —
    one malformed project must degrade to its directory name, not knock the
    whole genre out of my_renders."""
    _episode(tmp_path, monkeypatch)
    from braidio.mcp.workspace import Workspace

    broken = Workspace.for_email(OWNER).projects_dir / "broken"
    broken.mkdir(parents=True)
    (broken / "project.json").write_text('["not a dict"]')

    rows = list_deliverables(OWNER)
    assert EPISODE_ID in {d.artifact_id for d in rows}
    assert {p["project_id"] for p in Workspace.for_email(OWNER).list_projects()} == {
        "braidio_test_02",
        "broken",
    }


def test_claim_is_the_connectors_registry_shape():
    assert claim("p", "Ep") == {
        "genre": "braidio",
        "project_id": "p",
        "artifact_id": "Ep",
    }


def test_no_render_tool_still_hands_back_a_bare_file_uri():
    """The whole defect in one assertion.

    Six render sites returned `out.as_uri()` — a path on the connector's own
    disk. A remote caller cannot read it, and it was the ONLY thing offered.

    Checked over the AST rather than the source text: prose that *describes*
    the defect (this module, and the docstring of the helper that replaced it)
    is not the defect, and a substring scan cannot tell the two apart. It read
    its own explanation as a violation on the first run.
    """
    import ast
    from pathlib import Path

    src = Path(__file__).resolve().parents[1] / "braidio" / "mcp" / "tools.py"
    tree = ast.parse(src.read_text())
    offenders = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "as_uri"
    ]
    assert not offenders, (
        f"a render tool calls .as_uri() at line(s) {offenders} — that hands the "
        "caller a server-local file:// URI they cannot read. Return a retrieval "
        "claim instead (braidio#10 item 1)."
    )
