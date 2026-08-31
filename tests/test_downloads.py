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


# ---------------------------------------------------------------------------
# list_projects — braidio's half of nw.delivery.ProjectLister (reelee#333)
# ---------------------------------------------------------------------------


def test_a_project_with_no_episode_yet_is_findable_at_zero(tmp_path, monkeypatch):
    """The reelee#333 acceptance case for braidio: a production someone is
    mid-way through must list as "no episode yet", not vanish."""
    import json

    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    from braidio.downloads import list_projects
    from braidio.mcp.workspace import Workspace

    ws = Workspace.for_email(OWNER)
    wip = ws.projects_dir / "wip"
    wip.mkdir(parents=True)
    (wip / "project.json").write_text(json.dumps({"title": "Work In Progress"}))

    rows = list_projects(OWNER)
    assert [r.project_id for r in rows] == ["wip"]
    assert rows[0].title == "Work In Progress"
    assert rows[0].genre == GENRE
    assert rows[0].deliverable_count == 0
    assert rows[0].modified_at is not None


def test_episodes_are_counted_and_flat_renders_are_not(tmp_path, monkeypatch):
    """Episodes are the project-scoped population; the flat per-caller
    renders belong to no project and are the Lister's to show."""
    _episode(tmp_path, monkeypatch)          # braidio_test_02 gets 1 episode
    _render(tmp_path, monkeypatch, name="Flat One")  # belongs to no project
    from braidio.downloads import list_projects

    rows = list_projects(OWNER)
    assert [r.project_id for r in rows] == ["braidio_test_02"]
    assert rows[0].deliverable_count == 1


def test_listing_is_blind_to_other_callers_and_never_mints_dirs(
    tmp_path, monkeypatch
):
    _episode(tmp_path, monkeypatch, email=OTHER)
    from braidio.downloads import list_projects
    from braidio.mcp.workspace import Workspace

    assert list_projects(OWNER) == []
    assert not Workspace.for_email(OWNER).projects_dir.exists()


# ---------------------------------------------------------------------------
# organise — braidio's half of nw.delivery.Organiser (ADR asset-surfaces §3.3/§4)
# ---------------------------------------------------------------------------


def test_an_accepted_title_mirrors_into_ref_and_resolves(tmp_path, monkeypatch):
    """braidio's ref IS its title — the label follows the rename, the
    identity (stem, file, outstanding tokens) does not."""
    from braidio.downloads import organise

    path = _render(tmp_path, monkeypatch, name="Why the Sky Looks Blue")
    got = organise(
        OWNER, "", "Why the Sky Looks Blue",
        title="Sky Final", tags=["keeper"], note="the good one",
    )
    assert got.artifact_id == "Why the Sky Looks Blue"  # identity untouched
    assert got.ref == "Sky Final"  # the mirror rule
    assert got.title == "Sky Final"
    assert got.meta["tags"] == ["keeper"]
    assert got.meta["note"] == "the good one"
    assert path.exists()  # the file did not move
    # Accepted-title-resolves, and the old spellings keep working too.
    assert resolve(OWNER, "", "Sky Final").artifact_id == "Why the Sky Looks Blue"
    assert resolve(OWNER, "", "sky final").artifact_id == "Why the Sky Looks Blue"
    assert resolve(OWNER, "", "Why the Sky Looks Blue").artifact_id == (
        "Why the Sky Looks Blue"
    )


def test_an_episode_can_finally_be_named(tmp_path, monkeypatch):
    """The uuid-keyed population gains a speakable name — the eight-rows-
    called-cut-1-to-8 gap (ADR §4), closed for braidio's episodes."""
    from braidio.downloads import organise

    _episode(tmp_path, monkeypatch)
    got = organise(OWNER, "braidio_test_02", EPISODE_ID, title="Sky Episode One")
    assert got.artifact_id == EPISODE_ID
    assert got.ref == "Sky Episode One"
    assert resolve(OWNER, "", "Sky Episode One").artifact_id == EPISODE_ID
    # The episode file itself never moved (its location is load-bearing).
    assert got.path.name == f"{EPISODE_ID}.mp3"


def test_collisions_are_refused_across_the_whole_resolvable_set(
    tmp_path, monkeypatch
):
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="First")
    _render(tmp_path, monkeypatch, name="Second")
    _episode(tmp_path, monkeypatch)
    # Colliding with another flat render's STEM.
    with pytest.raises(ValueError, match="already held"):
        organise(OWNER, "", "First", title="Second")
    # Colliding with an EPISODE id.
    with pytest.raises(ValueError, match="already held"):
        organise(OWNER, "", "First", title=EPISODE_ID)
    # Colliding with an already-ASSIGNED title, case-folded.
    organise(OWNER, "", "First", title="The Slow Open")
    with pytest.raises(ValueError, match="already held"):
        organise(OWNER, "", "Second", title="the slow open")
    # Re-assigning the same title to the SAME target is not a collision.
    assert organise(OWNER, "", "First", title="The Slow Open").ref == "The Slow Open"


def test_clearing_restores_the_stem_identity(tmp_path, monkeypatch):
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="Ep")
    organise(OWNER, "", "Ep", title="Named", tags=["x"], note="y")
    got = organise(OWNER, "", "Ep", title="", tags=[], note="")
    assert got.ref == "Ep" and got.title == "Ep"
    assert "tags" not in got.meta and "note" not in got.meta
    # A fully-cleared sidecar is removed, not left as an empty file.
    from braidio.downloads import _sidecar_path

    assert not _sidecar_path(got.path).exists()
    with pytest.raises(KeyError):
        resolve(OWNER, "", "Named")


def test_sidecars_never_appear_in_listings(tmp_path, monkeypatch):
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="Ep")
    organise(OWNER, "", "Ep", note="noted")
    rows = list_deliverables(OWNER)
    assert [d.artifact_id for d in rows] == ["Ep"]
    assert rows[0].meta["note"] == "noted"


def test_organise_authorizes_like_resolve(tmp_path, monkeypatch):
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="Private")
    with pytest.raises(KeyError):
        organise(OTHER, "", "Private", title="Mine Now")
    with pytest.raises(ValueError, match="nothing to change"):
        organise(OWNER, "", "Private")
    for bad in ("cut 4", "#7", "12"):
        with pytest.raises(ValueError, match="reads as a reference"):
            organise(OWNER, "", "Private", title=bad)


def test_extension_shaped_titles_are_refused(tmp_path, monkeypatch):
    """resolve() strips media suffixes to find files, so 'Intro.mp3' as a
    TITLE would collide with the stem namespace and resolve to the WRONG
    artifact (adversarial-review major)."""
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="Intro")
    _render(tmp_path, monkeypatch, name="Other")
    with pytest.raises(ValueError, match="media extension"):
        organise(OWNER, "", "Other", title="Intro.mp3")
    # And the extension-optional courtesy works for assigned titles too.
    from braidio.downloads import organise as _org

    _org(OWNER, "", "Other", title="Sky Final")
    assert resolve(OWNER, "", "Sky Final.mp3").artifact_id == "Other"


def test_the_title_fallback_is_not_a_symlink_side_door(tmp_path, monkeypatch):
    """The id probes refuse a planted symlink; the assigned-title path must
    too, or the defense has a named back entrance (adversarial-review major)."""
    import json

    _render(tmp_path, monkeypatch, name="Real")
    secret = tmp_path / "secret.mp3"
    secret.write_bytes(b"not yours")
    from braidio.mcp.workspace import Workspace

    renders = Workspace.for_email(OWNER).renders_dir
    (renders / "planted.mp3").unlink(missing_ok=True)
    (renders / "planted.mp3").symlink_to(secret)
    (renders / "planted.organise.json").write_text(json.dumps({"title": "Nice Name"}))
    with pytest.raises(KeyError):
        resolve(OWNER, "", "Nice Name")


def test_a_new_render_cannot_take_over_an_assigned_title(tmp_path, monkeypatch):
    """Stems beat assigned titles at resolution, so the CREATE path must
    refuse minting a render under a name organise already taught the caller
    (adversarial-review major)."""
    from braidio.downloads import organise
    from braidio.mcp.workspace import Workspace

    _render(tmp_path, monkeypatch, name="Ep")
    organise(OWNER, "", "Ep", title="Sky Final")
    ws = Workspace.for_email(OWNER)
    with pytest.raises(ValueError, match="already the assigned title"):
        ws.render_path("Sky Final")
    # Unrelated names still mint fine.
    assert ws.render_path("Something Else").name == "Something Else.mp3"


def test_an_orphaned_sidecar_neither_resolves_nor_blocks_reuse(
    tmp_path, monkeypatch
):
    from braidio.downloads import organise

    path = _render(tmp_path, monkeypatch, name="Gone")
    organise(OWNER, "", "Gone", title="Held Name")
    path.unlink()  # media removed out of band; sidecar orphaned

    with pytest.raises(KeyError):
        resolve(OWNER, "", "Held Name")
    # The orphaned sidecar does not hold the title against a living render.
    _render(tmp_path, monkeypatch, name="Alive")
    assert organise(OWNER, "", "Alive", title="Held Name").ref == "Held Name"


def test_the_receipt_matches_what_the_listing_shows(tmp_path, monkeypatch):
    from braidio.downloads import organise

    _render(tmp_path, monkeypatch, name="Ep")
    got = organise(OWNER, "some_guessed_project", "Ep", title="Named")
    row = next(d for d in list_deliverables(OWNER) if d.artifact_id == "Ep")
    assert got.project_id == row.project_id == ""
    assert got.ref == row.ref == "Named"
    assert got.filename == row.filename == "Named.mp3"
