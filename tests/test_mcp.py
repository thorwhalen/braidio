"""Tests for the braidio MCP server (``braidio.mcp``).

Skipped entirely if the ``mcp`` extra (fastmcp + py2mcp) isn't installed. Exercises
the JSON helpers, the per-user workspace (isolation + traversal safety), and the
served tools end-to-end via an in-memory FastMCP client — including that the
metering middleware records real cost for a costed tool and that the allowlist
rejects an unauthorized caller. ElevenLabs synthesis is stubbed (no API calls).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import braidio

pytest.importorskip("fastmcp")
pytest.importorskip("py2mcp")

import braidio.mcp as bmcp  # noqa: E402
from braidio.mcp._helpers import (
    script_from_json,
    source_from_json,
    to_json,
)  # noqa: E402
from braidio.mcp.workspace import Workspace  # noqa: E402
from fastmcp import Client  # noqa: E402

_NW = pytest.mark.skipif(not braidio.HAS_NW, reason="nw layer not installed")


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("BRAIDIO_MCP_LOCAL_USER", "owner@example.com")
    monkeypatch.delenv("BRAIDIO_TTS_USD_PER_1K_CHARS", raising=False)


def _call(server, tool, args):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go())


# --- serialization ----------------------------------------------------------


def test_to_json_coerces_path_enum_dataclass():
    from braidio import Profile, Voice

    assert to_json(Path("/a/b")) == "/a/b"
    assert to_json(Profile.PUBLISHED) == "published"
    assert to_json(Voice(id="v", name="V", gender="f")) == {
        "id": "v",
        "name": "V",
        "gender": "f",
        "accent": "",
        "note": "",
    }


def test_to_json_rejects_bytes():
    with pytest.raises(TypeError):
        to_json(b"audio")


def test_script_from_json_dispatches_beat_types():
    script = script_from_json(
        {
            "title": "t",
            "id_slug": "01",
            "beats": [
                {"type": "narration", "text": "hi"},
                {"type": "segment", "reference": "clip"},
                {"type": "dialogue", "turns": [["A", "x"], ["B", "y"]]},
            ],
        }
    )
    assert [type(b).__name__ for b in script.beats] == [
        "Narration",
        "SegmentBeat",
        "Dialogue",
    ]
    assert script.beats[2].turns == (("A", "x"), ("B", "y"))  # normalized to tuples


def test_script_from_json_rejects_unknown_beat_type():
    with pytest.raises(ValueError):
        script_from_json({"title": "t", "id_slug": "01", "beats": [{"type": "song"}]})


def test_source_from_json_none():
    assert source_from_json(None) is None


# --- workspace --------------------------------------------------------------


def test_workspace_isolates_users(tmp_path):
    a = Workspace.for_email("a@x.com", root=tmp_path)
    b = Workspace.for_email("b@x.com", root=tmp_path)
    assert a.projects_dir != b.projects_dir
    assert a.projects_dir.parent == b.projects_dir.parent


@pytest.mark.parametrize("bad", ["../escape", "a/b", "..", "", "x\x00y"])
def test_workspace_rejects_path_traversal(tmp_path, bad):
    ws = Workspace.for_email("u@x.com", root=tmp_path)
    with pytest.raises(ValueError):
        ws.project_root(bad)


# --- served tools -----------------------------------------------------------


def test_all_tools_registered():
    server = bmcp.build_server(ledger={})

    async def names():
        async with Client(server) as c:
            return {t.name for t in await c.list_tools()}

    assert asyncio.run(names()) == set(bmcp.TOOL_NAMES)
    assert len(bmcp.COSTED_TOOLS) == 7


def test_estimate_cost_tool():
    server = bmcp.build_server(ledger={})
    r = _call(
        server,
        "estimate_cost",
        {
            "script": {
                "title": "t",
                "id_slug": "01",
                "beats": [{"type": "narration", "text": "a" * 1000}],
            }
        },
    )
    assert r.structured_content["characters"] == 1000
    assert r.structured_content["usd"] == pytest.approx(0.30)


def test_free_tool_records_entry_without_cost():
    ledger = {}
    server = bmcp.build_server(ledger=ledger)
    _call(server, "list_formats", {})
    entry = next(iter(ledger.values()))
    assert entry["tool"] == "list_formats"
    assert entry["status"] == "done"
    assert entry.get("cost_usd") is None  # free op, no spend


def test_costed_tool_records_real_cost(monkeypatch):
    def _stub(text, out, **kw):
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"TTS")
        return p

    monkeypatch.setattr(braidio, "narrate", _stub)
    ledger = {}
    server = bmcp.build_server(ledger=ledger)
    r = _call(server, "narrate", {"text": "x" * 2000})
    assert r.structured_content["cost_usd"] == pytest.approx(0.60)
    entry = [e for e in ledger.values() if e["tool"] == "narrate"][0]
    assert entry["cost_usd"] == pytest.approx(0.60)  # the spend reached the ledger


def test_allowlist_rejects_unauthorized_caller():
    server = bmcp.build_server(
        ledger={}, allowed={"someone@else.com"}, default_email="intruder@nope.com"
    )

    async def go():
        async with Client(server) as c:
            with pytest.raises(Exception) as ei:
                await c.call_tool("list_formats", {})
            return str(ei.value)

    assert "not authorized" in asyncio.run(go())


@_NW
def test_create_and_list_projects():
    server = bmcp.build_server(ledger={})
    _call(server, "create_project", {"project_id": "demo", "title": "Demo"})
    r = _call(server, "list_projects", {})
    assert r.structured_content["projects"] == [{"project_id": "demo", "title": "Demo"}]
