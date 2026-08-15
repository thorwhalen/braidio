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

from braidio.mcp._guide import INSTRUCTIONS
from braidio.mcp._media import (
    MediaSourceError,
    SourceAuthRequired,
    SourceCredentialsRejected,
    SourceUnavailable,
)
from braidio.mcp.metering import (
    MeteringMiddleware,
    UsageLedger,
    current_email,
    token_email,
)
from braidio.mcp.workspace import Workspace, data_root

#: Free, stateless tools (no ElevenLabs spend): assistance + catalog + planning/read
#: + source ingestion + project management.
FREE_TOOLS = [
    "help",
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
    "ingest_document",
    "save_script",
    "upload_asset",
    "list_assets",
    "get_asset",
    "download_audio",
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
    local_user: str | None = None,
    allow_any_authenticated: bool = False,
    name: str = "braidio",
):
    """Build a FastMCP server exposing braidio's tools with usage metering.

    ``ledger`` is the usage store (a ``MutableMapping``); defaults to an ephemeral
    in-memory ``dict`` — fine for stdio/dev/tests, but a **served** connector MUST
    inject a durable store (a ``dol`` file store under ``~/.local/share/braidio/usage/``).
    Access is **fail-closed**: a served server needs ``allowed`` (an email allow-set)
    or ``allow_any_authenticated=True``; ``local_user`` enables local/stdio dev with an
    explicit identity (no OAuth). Auth (OAuth) is added by the connector via py2mcp's
    ``auth=`` on the HTTP path; here we wire only the metering + allowlist middleware.
    """
    from py2mcp import mk_mcp_from_refs

    store = {} if ledger is None else ledger
    middleware = MeteringMiddleware(
        UsageLedger(store),
        allowed=allowed,
        local_user=local_user,
        allow_any_authenticated=allow_any_authenticated,
    )
    return mk_mcp_from_refs(
        TOOL_REFS, name=name, instructions=INSTRUCTIONS, middleware=[middleware]
    )


def register_tools(server, *, prefix="", include=None, exclude=None):
    """Register braidio's MCP tools onto an EXISTING FastMCP ``server`` — the
    aggregation seam for a host connector (the unified reelee connector, braidio#18).

    Lets a host expose braidio's tool surface alongside its own. ``prefix`` namespaces
    the tool names (e.g. ``"braidio_"``) to avoid collisions with the host's tools;
    ``include`` / ``exclude`` (sets of bare tool names) select the subset. Mirrors
    ``falaw.bridges.mcp.register_tools``. Returns the registered (prefixed) names.

    The host must install braidio's metering/identity separately (or aggregate under its
    own metering middleware) — this only wires the tool functions. braidio's tools resolve
    the caller via :func:`current_email`, which works under any host middleware.
    """
    from py2mcp.util import import_object

    names = list(include) if include is not None else list(TOOL_NAMES)
    skip = set(exclude or ())
    registered = []
    for name in names:
        if name in skip:
            continue
        fn = import_object(f"braidio.mcp.tools:{name}")
        server.tool(
            fn, name=f"{prefix}{name}", description=(fn.__doc__ or "").strip() or None
        )
        registered.append(f"{prefix}{name}")
    return registered


__all__ = [
    "FREE_TOOLS",
    "COSTED_TOOLS",
    "TOOL_NAMES",
    "TOOL_REFS",
    "INSTRUCTIONS",
    "build_server",
    "register_tools",
    "MeteringMiddleware",
    "UsageLedger",
    "current_email",
    "token_email",
    "MediaSourceError",
    "SourceAuthRequired",
    "SourceCredentialsRejected",
    "SourceUnavailable",
    "Workspace",
    "data_root",
]
