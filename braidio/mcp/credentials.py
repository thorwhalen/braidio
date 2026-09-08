"""The caller's bring-your-own ElevenLabs key for the in-flight tool call.

The credential counterpart of :func:`braidio.mcp.metering.current_email`: the
key is resolved **from the request**, never from a tool argument (tool
arguments are model-visible and land in the usage ledger), and read by the
costed tools through one function so the one-shot and graph paths cannot
diverge (thorwhalen/braidio#58).

The carrier is the ``X-Elevenlabs-Key`` request header — reelee's BYO model
(``reelee.key_policy``), so a client that already sends it to reelee sends
the same thing here. Absent means "bill the server's key": every costed tool
then passes ``api_key=None`` and ``mixing`` resolves ``ELEVENLABS_API_KEY``
from the environment, exactly as before the seam existed. The key is held in
memory for the call — it goes to ``narrate`` / ``render_dialogue`` /
``weave_project(api_key=)`` and to nothing that persists.

Under a host that does not forward the header (stdio dev, a connector whose
edge strips it) this resolves to ``None`` and the fallback applies; the
platform-side work to supply a per-user key is tracked on the issue.
"""

from __future__ import annotations

#: The request header carrying the caller's ElevenLabs key (case-insensitive
#: on the wire; fastmcp hands headers back lower-cased).
ELEVENLABS_KEY_HEADER = "x-elevenlabs-key"


def caller_elevenlabs_key() -> str | None:
    """The BYO ElevenLabs key on the current request, or ``None`` (server key).

    Never raises: with no HTTP request in flight (stdio) there are no headers
    and the answer is ``None``.
    """
    from fastmcp.server.dependencies import get_http_headers

    headers = get_http_headers(include={ELEVENLABS_KEY_HEADER})
    for name, value in headers.items():
        if name.lower() == ELEVENLABS_KEY_HEADER:
            return value.strip() or None
    return None


__all__ = ["ELEVENLABS_KEY_HEADER", "caller_elevenlabs_key"]
