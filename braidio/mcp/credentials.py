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


#: The provider name the key is redacted under (``<redacted:elevenlabs>``) —
#: the same name braidio's transforms read it by from nw's ``secrets=`` seam.
_PROVIDER = "elevenlabs"


def redact_caller_key(text: str) -> str:
    """``text`` with the in-flight caller key, if any, replaced by a marker.

    For free text the server persists or returns that it did not author — a
    provider's error message. ElevenLabs quotes the key back on a 401, and the
    usage ledger records the failure of every costed call, so without this the
    key lands on disk exactly when the provider rejects it. Delegates to
    :func:`nw.secrets.redact` when nw is installed (the ``mcp`` extra has it)
    and does the same exact-substring replacement itself when it is not, so
    the metering layer never needs the nw layer.
    """
    key = caller_elevenlabs_key()
    if not key or not text:
        return text
    try:
        from nw.secrets import redact
    except ImportError:  # the mcp surface without the nw layer
        return text.replace(key, f"<redacted:{_PROVIDER}>")
    return redact(text, {_PROVIDER: key})


def scrub_caller_key(error: BaseException) -> BaseException:
    """The exception to re-raise so its rendering never carries the caller key.

    The client-facing counterpart of :func:`redact_caller_key`: fastmcp turns
    the raised exception's text into the tool error the model sees, and that
    lands in the host transcript. Same object back when it was already clean;
    otherwise the same type rebuilt from the clean text, or a ``RuntimeError``
    naming the original type when the type will not construct that way.
    """
    key = caller_elevenlabs_key()
    if not key:
        return error
    try:
        from nw.secrets import redact_exception
    except ImportError:
        rendered = str(error)
        clean = redact_caller_key(rendered)
        if clean == rendered:
            return error
        try:
            return type(error)(clean)
        except Exception:  # noqa: BLE001 — any construction failure takes the fallback
            return RuntimeError(f"{type(error).__name__}: {clean}")
    return redact_exception(error, {_PROVIDER: key})


__all__ = [
    "ELEVENLABS_KEY_HEADER",
    "caller_elevenlabs_key",
    "redact_caller_key",
    "scrub_caller_key",
]
