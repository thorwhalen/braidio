"""braidio MCP server — the tool surface + metering for a remote Claude.ai connector.

Optional subpackage (extra ``braidio[mcp]``: ``fastmcp`` + ``py2mcp``; the ledger
store is dependency-injected). ``import braidio`` never imports this. The connector
references the tools by name via :data:`TOOL_REFS`; :func:`build_server` assembles
them with the :class:`~braidio.mcp.metering.MeteringMiddleware` for local (stdio)
testing or as the served app.

The costed tools (:data:`COSTED_TOOLS`) are the only ones that spend ElevenLabs
money; every call is metered by the middleware (using py2mcp's ``middleware=`` hook,
i2mint/py2mcp#7).
"""

from braidio.mcp.metering import MeteringMiddleware, UsageLedger, caller_email
from braidio.mcp.workspace import Workspace, data_root

#: Free, stateless tools (no ElevenLabs spend): catalog + planning/read + project mgmt.
FREE_TOOLS = [
    "list_formats",
    "list_presets",
    "list_deliveries",
    "list_voice_pools",
    "describe_genre",
    "estimate_cost",
    "plan_production",
    "find_forbidden_quotes",
    "content_violations",
    "audit_platitudes",
    "clean_text",
    "build_timeline",
    "narration_segments",
    "assign_voices",
    "find_segment",
    "create_project",
    "list_projects",
    "project_status",
]

#: Tools that spend ElevenLabs money — gated + metered.
COSTED_TOOLS = [
    "narrate",
    "render_dialogue",
    "render_multivoice",
    "compose_narration",
    "render_production",
    "render_format",
    "weave_project",
]

TOOL_NAMES = FREE_TOOLS + COSTED_TOOLS

#: ``'module:function'`` refs (py2mcp form) — what the connector's ConnectorSpec lists.
TOOL_REFS = [f"braidio.mcp.tools:{name}" for name in TOOL_NAMES]


def build_server(
    *,
    ledger: "MutableMapping | None" = None,  # noqa: F821 - forward type only
    allowed: "set[str] | None" = None,
    name: str = "braidio",
    default_email: str | None = None,
):
    """Build a FastMCP server exposing braidio's tools with usage metering.

    ``ledger`` is the usage store (a ``MutableMapping``); defaults to an in-memory
    ``dict`` for dev/tests — the connector injects a durable ``dol`` store under
    ``~/.local/share/braidio/usage/``. ``allowed`` is an email allow-set (``None``
    = any authenticated caller). Auth (OAuth) is added by the connector via
    ``py2mcp``'s ``auth=`` on the HTTP path; here we wire only the middleware.
    """
    from py2mcp import mk_mcp_from_refs

    store = {} if ledger is None else ledger
    middleware = MeteringMiddleware(
        UsageLedger(store), allowed=allowed, default_email=default_email
    )
    return mk_mcp_from_refs(TOOL_REFS, name=name, middleware=[middleware])


__all__ = [
    "FREE_TOOLS",
    "COSTED_TOOLS",
    "TOOL_NAMES",
    "TOOL_REFS",
    "build_server",
    "MeteringMiddleware",
    "UsageLedger",
    "caller_email",
    "Workspace",
    "data_root",
]
