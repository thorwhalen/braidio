"""The ``commentary_weave`` project factory places a project where its CALLER asks.

nw's placement contract (thorwhalen/nw#84) exists because a *host* that will
**serve** a guest genre's project has to put it where its own resolver and lister
look. Under braidio's own data home a commentary project is addressable by
braidio's tools and by nothing of the host's — two surfaces showing different
projects under the same name, which is the shape users read as data loss. The
decision is recorded on thorwhalen/reelee#227: one data root; a guest genre's
project is created where the host says, not where the guest app would put it.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_NW, reason="nw not available (commentary_weave unregistered)"
)


def test_nw_reports_the_genre_as_placeable():
    """What a host asks before offering "create one of these here"."""
    import nw

    assert nw.can_place_genre_project("commentary_weave") is True


def test_the_factory_creates_where_the_host_asks(tmp_path, monkeypatch):
    """The point of the whole change: a DIRECT child of the host's directory.

    ``BRAIDIO_DATA_HOME`` is pointed somewhere real and then asserted empty — the
    negative control. A factory that ignored the placement would still create a
    perfectly good project, report success, and leave it here instead.
    """
    braidio_home = tmp_path / "braidio_data_home"
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(braidio_home))
    host_dir = tmp_path / "host" / "projects" / "noel@example.com"
    host_dir.mkdir(parents=True)

    import nw

    info = nw.create_genre_project(
        "commentary_weave",
        "noel@example.com",
        "two_silences",
        title="Two Silences",
        template="solo_explainer",
        projects_dir=host_dir,
    )
    assert info["project_id"] == "two_silences"
    assert info["genre"] == "commentary_weave"
    assert info["params"] == {"format_id": "solo_explainer"}

    made = host_dir / "two_silences"
    assert (made / "project.json").is_file()
    assert not braidio_home.exists()  # nothing landed in braidio's own data home

    # And it is a real braidio project, openable as one.
    proj = braidio.Project(made)
    assert Path(proj.root) == made.resolve()


def test_with_no_placement_it_still_uses_braidios_own_workspace(tmp_path, monkeypatch):
    """The compatibility half: braidio's own connector is unchanged."""
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    import nw

    from braidio.mcp.workspace import Workspace

    info = nw.create_genre_project(
        "commentary_weave", "owner@example.com", "myshow", title="My Show"
    )
    assert info["project_id"] == "myshow"
    assert Workspace.for_email("owner@example.com", root=tmp_path).open_project(
        "myshow"
    )


def test_a_traversing_project_id_cannot_escape_the_placement(tmp_path):
    """The host validates ids, and so does this — a factory trusts no caller.

    nw's outcome check would also catch an escape, but only *after* the project
    was created, and its rollback then deletes a directory outside the placement.
    Refusing up front is the cheaper and safer half.
    """
    from braidio.project import create_project_at

    for bad in ("../escape", "a/b", "", "..", "."):
        with pytest.raises(ValueError):
            create_project_at(tmp_path, bad)


def test_the_host_placed_create_does_not_require_the_mcp_extra():
    """A host serving a commentary project over HTTP must not need ``fastmcp``.

    In a subprocess because ``sys.modules`` is shared with every other test in this
    run, so an in-process assertion would pass or fail on collection order. The
    braidio-workspace path legitimately pulls fastmcp (it runs
    ``braidio/mcp/__init__.py``); the host-placed path takes a different branch on
    purpose, and this is what keeps that true.
    """
    code = (
        "import sys, tempfile\n"
        "from braidio.project import create_project_at\n"
        "with tempfile.TemporaryDirectory() as d:\n"
        "    create_project_at(d, 'ep_01', title='Ep 1')\n"
        "assert 'fastmcp' not in sys.modules, 'host-placed create pulled fastmcp'\n"
        "print('ok')\n"
    )
    out = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).resolve().parent.parent),
    )
    assert out.returncode == 0, out.stderr
    assert "ok" in out.stdout
