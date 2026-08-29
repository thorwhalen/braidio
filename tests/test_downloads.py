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
