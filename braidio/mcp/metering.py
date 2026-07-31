"""Usage metering + access control for the braidio MCP server.

The server runs with a **shared** ElevenLabs key, so the usage ledger is the only
record of who spent what. Metering is a FastMCP **middleware**, not per-tool
decorators — a decorator you forget on a paid tool means untracked spend; a
middleware wraps *every* call (this is what py2mcp's ``middleware=`` hook,
i2mint/py2mcp#7, exists for). It runs after OAuth, so the caller's email is known.

Two concerns:

- **Access** — an in-code allowlist (defense-in-depth over the platform's
  ``resource_allowlist``): a caller whose email isn't allowed is rejected before
  any tool runs.
- **Usage** — one append-only ledger entry per call: who / when / tool, and — for
  costed tools that surface it in their result — ``cost_usd`` and
  ``cache_hit_savings_usd``. The ledger is a ``MutableMapping`` injected by the
  connector (a ``dol`` file store under ``~/.local/share/braidio/usage/`` locally;
  swappable for S3/DB later without touching this code).
"""

from __future__ import annotations

import os
import time
from collections.abc import MutableMapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from fastmcp.exceptions import ToolError
from fastmcp.server.middleware import Middleware

#: Env fallback for the caller email when there is no OAuth context (stdio/dev).
LOCAL_USER_ENV_VAR = "BRAIDIO_MCP_LOCAL_USER"


def caller_email(*, default: Optional[str] = None) -> str:
    """The authenticated caller's email (token ``sub``), lowercased.

    Falls back — when there is no request/auth context (local stdio, tests) — to
    ``default`` → ``$BRAIDIO_MCP_LOCAL_USER`` → ``"local@braidio"``.
    """
    try:
        from fastmcp.server.dependencies import get_access_token

        token = get_access_token()
    except Exception:  # noqa: BLE001 — no active request/token context
        token = None
    if token is not None:
        sub = (getattr(token, "claims", None) or {}).get("sub")
        if sub:
            return str(sub).lower()
    return (default or os.environ.get(LOCAL_USER_ENV_VAR) or "local@braidio").lower()


@dataclass(frozen=True)
class UsageLedger:
    """Append-only usage/cost ledger over an injected ``MutableMapping``.

    One JSON entry per call, keyed ``{email}/{YYYY-MM}/{ts_ns}-{tool}.json`` — a
    layout that answers "what did X spend this month" with a cheap subtree scan.
    The store is DI'd (a ``dol`` file store in prod, a plain ``dict`` in tests) so
    the ledger can grow up to blob storage without changing callers.
    """

    store: MutableMapping

    def record(self, entry: dict) -> str:
        key = f"{entry['email']}/{entry['month']}/{entry['id']}.json"
        self.store[key] = entry
        return key


class MeteringMiddleware(Middleware):
    """FastMCP middleware: authorize the caller, then meter every tool call.

    ``allowed`` is an email allow-set (``None`` = allow any authenticated caller);
    ``default_email`` overrides the no-auth fallback for local dev.
    """

    def __init__(
        self,
        ledger: UsageLedger,
        *,
        allowed: Optional[set[str]] = None,
        default_email: Optional[str] = None,
    ):
        self.ledger = ledger
        self.allowed = {e.lower() for e in allowed} if allowed is not None else None
        self.default_email = default_email

    async def on_call_tool(self, context, call_next):
        email = caller_email(default=self.default_email)
        if self.allowed is not None and email not in self.allowed:
            raise ToolError(f"{email!r} is not authorized to use this braidio server")

        tool = context.message.name
        t0 = time.time_ns()
        now = datetime.now(timezone.utc)
        entry = {
            "id": f"{t0}-{tool}",
            "email": email,
            "month": now.strftime("%Y-%m"),
            "ts": now.isoformat(),
            "tool": tool,
            "status": "started",
        }
        try:
            result = await call_next(context)
            out = getattr(result, "structured_content", None)
            if isinstance(out, dict):
                entry["cost_usd"] = out.get("cost_usd")
                entry["cache_hit_savings_usd"] = out.get("cache_hit_savings_usd")
                entry["characters"] = out.get("characters")
                entry["artifact_ref"] = out.get("url") or out.get("ref")
            entry["status"] = "done"
            entry["elapsed_s"] = (time.time_ns() - t0) / 1e9
            return result
        except Exception as exc:  # noqa: BLE001 — record the failure, then re-raise
            entry["status"] = "error"
            entry["error"] = repr(exc)
            entry["elapsed_s"] = (time.time_ns() - t0) / 1e9
            raise
        finally:
            # Never fail a tool because metering couldn't write.
            try:
                self.ledger.record(entry)
            except Exception:  # noqa: BLE001
                pass
