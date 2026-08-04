"""Document ingestion for the braidio MCP server: fetch a URI or accept text, then
extract plaintext so an agent can analyze source material into a Script.

Fetching is **SSRF-hardened** because the connector fetches user-supplied URLs
server-side on a shared production box:

- http/https only, on ports {80, 443};
- the host must resolve to a *public* address (``ipaddress.is_global``), with
  IPv4-mapped IPv6 canonicalized — loopback / private / link-local / cloud-metadata
  (``169.254.169.254``) targets are refused;
- **redirects are NOT auto-followed** — every hop's ``Location`` is re-validated, so
  a public URL can't ``302`` to an internal host;
- the whole fetch is bounded by a wall-clock deadline, a redirect cap, and a
  total-bytes cap (chunked read), so a slow-loris or redirect loop can't pin a worker.

Residual: a determined attacker who controls a domain's DNS could race the
validate-vs-connect resolution (the two lookups aren't pinned to one IP). Accepted
here because the connector is restricted to trusted, allowlisted users.

Extraction is content-type aware: HTML is stripped to text, PDF uses ``pypdf``
(page-capped), everything else is decoded as UTF-8.
"""

from __future__ import annotations

import io
import ipaddress
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser

#: Fetch bounds (all hops).
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
TOTAL_TIMEOUT_S = 25.0  # wall-clock budget for the whole fetch
OP_TIMEOUT_S = 10.0  # per-socket-op timeout
ALLOWED_SCHEMES = ("http", "https")
ALLOWED_PORTS = frozenset({80, 443})
PDF_MAX_PAGES = 300

#: Socket read granularity. Bounds how far past ``MAX_BYTES`` a hostile response can
#: push us before the cap is enforced, and how often the deadline is re-checked.
READ_CHUNK_BYTES = 64 * 1024

#: HTTP statuses treated as a redirect worth following. Each hop is re-validated
#: against the SSRF rules above, so a public URL can never redirect us inward.
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})

#: Identifies braidio to the origin server. Kept honest (no browser spoofing) so
#: operators can see, and rate-limit, what is fetching their documents.
USER_AGENT = "braidio-mcp/1.0"


class _TextHTMLParser(HTMLParser):
    """Collect visible text from HTML, skipping <script>/<style>."""

    def __init__(self):
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self._chunks.append(data)

    def text(self) -> str:
        return " ".join(" ".join(self._chunks).split())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Disable urllib's auto-follow — a 3xx raises so we validate the hop ourselves."""

    def redirect_request(self, *args, **kwargs):  # noqa: D401, ARG002
        return None


def _host_is_public(host: str) -> bool:
    """True only if every resolved address for ``host`` is globally routable."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if ip.version == 6 and ip.ipv4_mapped is not None:
            ip = ip.ipv4_mapped  # canonicalize ::ffff:127.0.0.1 etc.
        if not ip.is_global:  # rejects private/loopback/link-local/reserved/…
            return False
    return True


def _validate_target(uri: str) -> None:
    """Reject a URI whose scheme/host/port isn't a public http(s) endpoint."""
    parts = urllib.parse.urlparse(uri)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise ValueError(f"only http/https URIs are supported, got {parts.scheme!r}")
    if not parts.hostname or not _host_is_public(parts.hostname):
        raise ValueError(f"refusing to fetch a non-public host: {parts.hostname!r}")
    port = parts.port or (443 if parts.scheme == "https" else 80)
    if port not in ALLOWED_PORTS:
        raise ValueError(f"port {port} is not allowed (only 80/443)")


def _read_bounded(resp, deadline: float) -> bytes:
    """Read the body in chunks, enforcing the byte cap and the wall-clock deadline."""
    chunks: list[bytes] = []
    total = 0
    while total <= MAX_BYTES:
        if time.monotonic() > deadline:
            raise ValueError("document fetch exceeded its time budget")
        chunk = resp.read(READ_CHUNK_BYTES)
        if not chunk:
            break
        total += len(chunk)
        chunks.append(chunk)
    data = b"".join(chunks)
    if len(data) > MAX_BYTES:
        raise ValueError(f"document exceeds the {MAX_BYTES}-byte limit")
    return data


def fetch_uri(uri: str) -> tuple[bytes, str]:
    """Fetch a public http(s) URI (SSRF-hardened). Returns ``(bytes, content_type)``."""
    deadline = time.monotonic() + TOTAL_TIMEOUT_S
    opener = urllib.request.build_opener(_NoRedirect)
    current = uri
    for _ in range(MAX_REDIRECTS + 1):
        _validate_target(current)  # re-validate scheme/host/port at EVERY hop
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise ValueError("document fetch exceeded its time budget")
        req = urllib.request.Request(current, headers={"User-Agent": USER_AGENT})
        try:
            resp = opener.open(req, timeout=min(OP_TIMEOUT_S, remaining))  # noqa: S310
        except urllib.error.HTTPError as err:
            loc = err.headers.get("Location") if err.headers else None
            if err.code in REDIRECT_STATUS_CODES and loc:
                current = urllib.parse.urljoin(current, loc)
                continue  # the loop re-validates the redirect target
            raise ValueError(f"fetch failed: HTTP {err.code}") from err
        except urllib.error.URLError as err:
            raise ValueError(f"fetch failed: {err.reason}") from err
        with resp:
            ctype = (
                (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
            )
            data = _read_bounded(resp, deadline)
        return data, ctype or "application/octet-stream"
    raise ValueError(f"too many redirects (>{MAX_REDIRECTS})")


def _pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - optional dep
        raise ValueError("PDF ingestion needs pypdf (pip install pypdf)") from exc
    reader = PdfReader(io.BytesIO(data))
    pages = list(reader.pages)[:PDF_MAX_PAGES]  # cap work on an adversarial PDF
    return "\n\n".join((page.extract_text() or "") for page in pages).strip()


def extract_text(data: bytes, content_type: str) -> str:
    """Extract plaintext from ``data`` given its ``content_type``."""
    ct = (content_type or "").lower()
    if "pdf" in ct:
        return _pdf_text(data)
    text = data.decode("utf-8", "replace")
    if "html" in ct or "xml" in ct:
        parser = _TextHTMLParser()
        parser.feed(text)
        return parser.text()
    return text
