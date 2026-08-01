"""Tests for the braidio MCP server (``braidio.mcp``).

Skipped entirely if the ``mcp`` extra (fastmcp + py2mcp) isn't installed. Exercises
the JSON helpers, the per-user workspace (isolation + traversal safety), the
fail-closed identity/allowlist model, and the served tools end-to-end via an
in-memory FastMCP client — including that costed tools record real cost in the
usage ledger and the error path is recorded. ElevenLabs/ffmpeg work is stubbed.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

import braidio

pytest.importorskip("fastmcp")
pytest.importorskip("py2mcp")

import braidio.mcp as bmcp  # noqa: E402
from braidio.mcp import metering  # noqa: E402
from braidio.mcp._helpers import (
    script_from_json,
    source_from_json,
    to_json,
)  # noqa: E402
from braidio.mcp.workspace import Workspace  # noqa: E402
from fastmcp import Client  # noqa: E402

_NW = pytest.mark.skipif(not braidio.HAS_NW, reason="nw layer not installed")

OWNER = "owner@example.com"


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.delenv("BRAIDIO_TTS_USD_PER_1K_CHARS", raising=False)


def _local_server(**kw):
    """A server in explicit local-dev mode (identity = OWNER, no OAuth)."""
    kw.setdefault("local_user", OWNER)
    return bmcp.build_server(**kw)


def _call(server, tool, args):
    async def go():
        async with Client(server) as c:
            return await c.call_tool(tool, args)

    return asyncio.run(go())


def _mock_token(monkeypatch, email):
    import fastmcp.server.dependencies as deps

    tok = type("Tok", (), {"claims": {"email": email}})()
    monkeypatch.setattr(deps, "get_access_token", lambda: tok)


# --- serialization ----------------------------------------------------------


def test_to_json_coerces_path_enum_dataclass():
    from braidio import Profile, Voice

    assert to_json(Path("/a/b")) == str(Path("/a/b"))  # Path -> str (platform-agnostic)
    assert to_json(Profile.PUBLISHED) == "published"
    assert to_json(Voice(id="v", name="V", gender="f")) == {
        "id": "v",
        "name": "V",
        "gender": "f",
        "accent": "",
        "note": "",
    }


def test_to_json_pydantic_and_str_fallback():
    from pydantic import BaseModel

    class M(BaseModel):
        a: int
        b: str

    assert to_json(M(a=1, b="x")) == {"a": 1, "b": "x"}

    class Weird:
        def __repr__(self):
            return "WEIRD"

    assert to_json(Weird()) == "WEIRD"  # last-resort str()


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
    assert script.beats[2].turns == (("A", "x"), ("B", "y"))


def test_script_from_json_rejects_unknown_beat_type():
    with pytest.raises(ValueError):
        script_from_json({"title": "t", "id_slug": "01", "beats": [{"type": "song"}]})


def test_source_from_json_none_and_built():
    assert source_from_json(None) is None
    src = source_from_json(
        {
            "lines": [{"index": 0, "start_s": 0.0, "end_s": 1.0, "text": "la"}],
            "asset_path": "/tmp/song.mp3",
            "song_end_s": 12.0,
        }
    )
    assert type(src).__name__ == "TimedLineSegmentSource"
    assert src.resolve("la") is not None  # a working source over the timed line


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
    with pytest.raises(ValueError):
        ws.render_path(bad)


@_NW
def test_workspace_open_missing_and_list(tmp_path):
    ws = Workspace.for_email("u@x.com", root=tmp_path)
    assert ws.list_projects() == []
    with pytest.raises(FileNotFoundError):
        ws.open_project("nope")
    ws.create_project("p1", title="One")
    assert ws.list_projects() == [{"project_id": "p1", "title": "One"}]
    assert ws.open_project("p1").root == ws.project_root("p1")


# --- identity / access (fail-closed) ----------------------------------------


def test_token_email_prefers_email_claim_lowercased(monkeypatch):
    _mock_token(monkeypatch, "USER@Example.COM")
    assert metering.token_email() == "user@example.com"


def test_current_email_raises_outside_call():
    with pytest.raises(Exception):
        metering.current_email()


def test_served_uses_token_identity(monkeypatch):
    _mock_token(monkeypatch, "user@example.com")
    ledger = {}
    server = bmcp.build_server(
        ledger=ledger, allowed={"user@example.com"}
    )  # no local_user
    _call(server, "list_formats", {})
    assert next(iter(ledger.values()))["email"] == "user@example.com"


def test_fail_closed_without_token_or_local_user():
    server = bmcp.build_server(
        ledger={}, allowed={"a@b.com"}
    )  # no local_user, no token
    with pytest.raises(Exception) as ei:
        _call(server, "list_formats", {})
    assert "authentication required" in str(ei.value)


def test_deny_by_default_when_no_allowlist(monkeypatch):
    _mock_token(monkeypatch, "user@example.com")
    server = bmcp.build_server(ledger={})  # served, allowed=None, allow_any off
    with pytest.raises(Exception) as ei:
        _call(server, "list_formats", {})
    assert "allowlist" in str(ei.value)


def test_allowlist_rejects_unauthorized_caller():
    server = _local_server(ledger={}, allowed={"someone@else.com"})  # OWNER not in set
    with pytest.raises(Exception) as ei:
        _call(server, "list_formats", {})
    assert "not authorized" in str(ei.value)


# --- served tools -----------------------------------------------------------


def test_all_tools_registered():
    server = _local_server(ledger={})

    async def names():
        async with Client(server) as c:
            return {t.name for t in await c.list_tools()}

    assert asyncio.run(names()) == set(bmcp.TOOL_NAMES)
    assert len(bmcp.COSTED_TOOLS) == 7


def test_estimate_cost_tool():
    server = _local_server(ledger={})
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
    server = _local_server(ledger=ledger)
    _call(server, "list_formats", {})
    entry = next(iter(ledger.values()))
    assert entry["tool"] == "list_formats"
    assert entry["status"] == "done"
    assert entry["email"] == OWNER
    assert entry.get("cost_usd") is None  # free op


def _stub_writes(monkeypatch, fn_name):
    def _stub(*a, **kw):
        out = kw.get("out_path") or (a[1] if len(a) > 1 else None)
        if out:
            p = Path(out)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"AUDIO")
            return p
        return None

    monkeypatch.setattr(braidio, fn_name, _stub)


def test_narrate_records_real_cost(monkeypatch):
    _stub_writes(monkeypatch, "narrate")
    ledger = {}
    server = _local_server(ledger=ledger)
    r = _call(server, "narrate", {"text": "x" * 2000})
    assert r.structured_content["cost_usd"] == pytest.approx(0.60)
    assert r.structured_content["cost_basis"] == "estimate"
    entry = [e for e in ledger.values() if e["tool"] == "narrate"][0]
    assert entry["cost_usd"] == pytest.approx(0.60)  # spend reached the ledger


def test_render_dialogue_records_cost(monkeypatch):
    _stub_writes(monkeypatch, "render_dialogue")
    ledger = {}
    server = _local_server(ledger=ledger)
    r = _call(
        server, "render_dialogue", {"turns": [["A", "x" * 500], ["B", "y" * 500]]}
    )
    assert r.structured_content["cost_usd"] == pytest.approx(0.30)
    assert [e for e in ledger.values() if e["tool"] == "render_dialogue"][0][
        "cost_usd"
    ] > 0


def test_render_production_costs_the_plan_and_stays_in_workspace(monkeypatch, tmp_path):
    calls = {}

    def _stub(scr, *, out_path, **kw):
        calls.update(kw)
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(b"EP")
        return Path(out_path)

    monkeypatch.setattr(braidio, "render_production", _stub)
    ledger = {}
    server = _local_server(ledger=ledger)
    r = _call(
        server,
        "render_production",
        {
            "script": {
                "title": "t",
                "id_slug": "01",
                "beats": [{"type": "narration", "text": "a" * 1000}],
            }
        },
    )
    assert r.structured_content["cost_usd"] == pytest.approx(0.30)
    assert r.structured_content["cost_basis"] == "estimate"
    # intermediates go into the workspace, not the CWD
    assert str(tmp_path) in calls["tts_dir"] and str(tmp_path) in calls["clips_dir"]


def test_render_production_requires_source_for_segments():
    server = _local_server(ledger={})
    with pytest.raises(Exception) as ei:
        _call(
            server,
            "render_production",
            {
                "script": {
                    "title": "t",
                    "id_slug": "01",
                    "beats": [{"type": "segment", "reference": "clip"}],
                }
            },
        )
    assert "no `source`" in str(ei.value)


def test_metering_records_error_status(monkeypatch):
    def _boom(*a, **kw):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(braidio, "narrate", _boom)
    ledger = {}
    server = _local_server(ledger=ledger)
    with pytest.raises(Exception):
        _call(server, "narrate", {"text": "hi"})
    entry = [e for e in ledger.values() if e["tool"] == "narrate"][0]
    assert entry["status"] == "error"
    assert "kaboom" in entry["error"]


def test_ledger_refuses_when_unwritable(monkeypatch):
    class _Broken(dict):
        def __setitem__(self, k, v):
            raise OSError("disk full")

    server = _local_server(ledger=_Broken())
    with pytest.raises(Exception) as ei:
        _call(server, "list_formats", {})
    assert "ledger unavailable" in str(ei.value)


def test_unknown_pool_and_format_raise():
    server = _local_server(ledger={})
    with pytest.raises(Exception):
        _call(server, "assign_voices", {"n": 2, "pool": "nope"})


@_NW
def test_create_and_list_projects():
    server = _local_server(ledger={})
    _call(server, "create_project", {"project_id": "demo", "title": "Demo"})
    r = _call(server, "list_projects", {})
    assert r.structured_content["projects"] == [{"project_id": "demo", "title": "Demo"}]


@_NW
def test_weave_project_records_cost(monkeypatch):
    server = _local_server(ledger={})
    _call(server, "create_project", {"project_id": "demo", "title": "Demo"})

    episode = type("Ann", (), {"body": {"url": "file:///x.mp3", "duration_s": 1.0}})()
    monkeypatch.setattr(
        braidio, "weave_project", lambda proj, scr, source=None: episode
    )
    ledger = {}
    server2 = _local_server(ledger=ledger)
    r = _call(
        server2,
        "weave_project",
        {
            "project_id": "demo",
            "script": {
                "title": "t",
                "id_slug": "01",
                "beats": [{"type": "narration", "text": "n" * 1000}],
            },
        },
    )
    assert r.structured_content["cost_usd"] == pytest.approx(0.30)
    assert r.structured_content["url"] == "file:///x.mp3"


# --- assistance + document ingestion ----------------------------------------


def test_help_tool_served():
    server = _local_server(ledger={})
    r = _call(server, "help", {})
    assert "what_is_braidio" in r.structured_content
    assert "render_COSTED" in r.structured_content["tools"]
    assert any("ingest_document" in step for step in r.structured_content["workflow"])


def test_docs_extract_text_html_and_plain():
    from braidio.mcp import _docs

    html = b"<html><body><p>Hi <b>there</b></p><script>x=1</script></body></html>"
    assert _docs.extract_text(html, "text/html") == "Hi there"
    assert _docs.extract_text(b"plain body", "text/plain") == "plain body"


@pytest.mark.parametrize(
    "bad_uri",
    [
        "ftp://example.com/x",
        "file:///etc/passwd",
        "http://localhost/x",
        "http://127.0.0.1/x",
        "http://192.168.0.1/x",
        "http://169.254.169.254/latest/meta-data",  # cloud metadata SSRF
    ],
)
def test_docs_fetch_ssrf_guard(bad_uri):
    from braidio.mcp import _docs

    with pytest.raises(ValueError):
        _docs.fetch_uri(bad_uri)  # rejected before any network call


@_NW
def test_ingest_document_requires_project_then_stores_text():
    server = _local_server(ledger={})
    with pytest.raises(Exception) as ei:
        _call(server, "ingest_document", {"project_id": "p1", "text": "hello"})
    assert "create_project" in str(ei.value)

    _call(server, "create_project", {"project_id": "p1", "title": "P1"})
    r = _call(server, "ingest_document", {"project_id": "p1", "text": "A " * 100})
    assert r.structured_content["characters"] == 200
    assert r.structured_content["source"] == "inline"
    assert r.structured_content["text"].startswith("A ")


@_NW
def test_save_script_links_narration_beats():
    server = _local_server(ledger={})
    _call(server, "create_project", {"project_id": "p2", "title": "P2"})
    r = _call(
        server,
        "save_script",
        {
            "project_id": "p2",
            "script": {
                "title": "t",
                "id_slug": "01",
                "beats": [{"type": "narration", "text": "hello"}],
            },
        },
    )
    beats = r.structured_content["beats"]
    assert len(beats) == 1 and beats[0]["kind"] == "narration"


# --- assets (braidio#10) ----------------------------------------------------
# Assets are per-USER (no project needed), so one-shot renders share them too.


def test_upload_asset_dedups_lists_and_gets():
    import base64

    from dol import content_hash

    server = _local_server(ledger={})  # no create_project — assets are project-less
    payload = b"FAKE-AUDIO-BYTES"
    b64 = base64.b64encode(payload).decode()
    meta = _call(
        server, "upload_asset", {"data_b64": b64, "name": "song.mp3"}
    ).structured_content
    assert meta["itemId"] == content_hash(payload)  # content-addressed
    assert meta["hash"] == meta["itemId"] and meta["size"] == len(payload)
    assert meta["mimeType"].startswith("audio/") and meta["name"] == "song.mp3"

    # identical bytes dedupe to one stored asset
    again = _call(server, "upload_asset", {"data_b64": b64}).structured_content
    assert again["itemId"] == meta["itemId"]
    listed = _call(server, "list_assets", {}).structured_content["assets"]
    assert len(listed) == 1 and listed[0]["itemId"] == meta["itemId"]
    got = _call(server, "get_asset", {"asset_id": meta["itemId"]}).structured_content
    assert got["itemId"] == meta["itemId"]


def test_upload_asset_requires_uri_or_data():
    server = _local_server(ledger={})
    with pytest.raises(Exception) as ei:  # neither uri nor data_b64
        _call(server, "upload_asset", {})
    assert "uri" in str(ei.value) or "data_b64" in str(ei.value)


def test_asset_reference_resolves_to_local_path():
    import base64
    from pathlib import Path as P

    server = _local_server(ledger={})
    item_id = _call(
        server, "upload_asset", {"data_b64": base64.b64encode(b"MEDIA").decode()}
    ).structured_content["itemId"]

    ws = Workspace.for_email(OWNER)  # the resolver weave/render use for `source.asset_id`
    path = ws.asset_path(item_id)
    assert P(path).exists() and P(path).read_bytes() == b"MEDIA"
    with pytest.raises(FileNotFoundError):
        ws.asset_path("deadbeefdeadbeef")


def test_oneshot_render_resolves_asset_id(monkeypatch):
    # A project-LESS render_production resolves source.asset_id to the uploaded file.
    import base64
    from pathlib import Path as P

    captured = {}

    def _stub(scr, *, out_path, **kw):
        captured.update(kw)
        P(out_path).parent.mkdir(parents=True, exist_ok=True)
        P(out_path).write_bytes(b"EP")
        return P(out_path)

    monkeypatch.setattr(braidio, "render_production", _stub)
    server = _local_server(ledger={})
    item_id = _call(
        server, "upload_asset", {"data_b64": base64.b64encode(b"SONG").decode()}
    ).structured_content["itemId"]
    _call(
        server,
        "render_production",
        {
            "script": {
                "title": "t",
                "id_slug": "01",
                "beats": [{"type": "segment", "reference": "line-0"}],
            },
            "source": {
                "lines": [{"index": 0, "start_s": 0, "end_s": 1, "text": "hi"}],
                "asset_id": item_id,
            },
        },
    )
    src = captured["source"]  # the TimedLineSegmentSource braidio.render_production got
    assert str(src._asset) == Workspace.for_email(OWNER).asset_path(item_id)
    assert P(src._asset).read_bytes() == b"SONG"


def test_docs_rejects_disallowed_port(monkeypatch):
    from braidio.mcp import _docs

    monkeypatch.setattr(_docs, "_host_is_public", lambda h: True)
    with pytest.raises(ValueError, match="port"):
        _docs._validate_target("http://example.com:8080/x")
    _docs._validate_target("https://example.com/x")  # 443 default is fine


def test_docs_redirect_to_private_is_rejected(monkeypatch):
    # The CRITICAL fix: a public URL that 302s to an internal host must be refused,
    # and the internal target must never be fetched.
    import urllib.error
    import urllib.request as ureq

    from braidio.mcp import _docs

    monkeypatch.setattr(_docs, "_host_is_public", lambda h: h != "127.0.0.1")
    hops = []

    def fake_open(self, req, data=None, timeout=None):
        hops.append(req.full_url)
        raise urllib.error.HTTPError(
            req.full_url, 302, "redir", {"Location": "http://127.0.0.1/secret"}, None
        )

    monkeypatch.setattr(ureq.OpenerDirector, "open", fake_open)
    with pytest.raises(ValueError):
        _docs.fetch_uri("http://public.example/start")
    assert hops == ["http://public.example/start"]  # never fetched the private target


@_NW
def test_save_script_rejects_dialogue_before_mutating():
    server = _local_server(ledger={})
    _call(server, "create_project", {"project_id": "pd", "title": "PD"})
    with pytest.raises(Exception) as ei:
        _call(
            server,
            "save_script",
            {
                "project_id": "pd",
                "script": {
                    "title": "t",
                    "id_slug": "01",
                    "beats": [{"type": "dialogue", "turns": [["A", "hi"]]}],
                },
            },
        )
    assert "Dialogue" in str(ei.value)
