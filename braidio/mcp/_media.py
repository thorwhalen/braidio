"""Credentialed audio retrieval for the braidio MCP server.

``download_audio`` pulls the audio behind a *page* link (YouTube, SoundCloud, …)
through yt-dlp. On a shared host that is not a neutral operation:

- **Credentials.** YouTube bot-gates datacenter IPs ("Sign in to confirm you're
  not a bot"), so yt-dlp needs a signed-in session. The material is provisioned as
  *files on the server* — never in code, never in the repo: a Netscape cookie jar
  named by :data:`COOKIES_FILE_ENV_VAR`, or simply dropped at
  ``<data root>/credentials/youtube-cookies.txt``, where it is picked up with no
  configuration at all. :data:`EXTRACTOR_ARGS_ENV_VAR` is the no-secret knob
  (yt-dlp's ``extractor_args``, e.g. a different player client) — worth trying
  first precisely because it carries nothing to leak or expire.
- **Legibility.** yt-dlp reports a bot gate, an age gate, a private video and a
  deleted video as one undifferentiated string, and ``yt_dlp.cookies.load_cookies``
  *silently ignores* an unreadable cookie file — so a mis-provisioned server fails
  exactly like a bot-gated one. :meth:`SourceCredentials.check` and
  :func:`classify_download_error` split those cases into errors that each name
  their own fix in one line.

Every error here subclasses ``ToolError``: FastMCP forwards ``FastMCPError``
messages to the caller verbatim and masks everything else, so only these reach the
agent with their fix intact.

Cookies expire. The refresh procedure is ``misc/docs/youtube_ingest_credentials.md``.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastmcp.exceptions import ToolError

from braidio.mcp.workspace import DATA_HOME_ENV_VAR, data_root

#: Path to a Netscape-format cookie jar handed to yt-dlp (its ``--cookies``).
COOKIES_FILE_ENV_VAR = "BRAIDIO_YTDLP_COOKIES_FILE"

#: Browser to read cookies from (``--cookies-from-browser``): ``"safari"`` or
#: ``"chrome:Profile 1"``. A developer-machine convenience — a headless server has
#: no browser to read, which is why the cookie *file* is the deployed path.
COOKIES_FROM_BROWSER_ENV_VAR = "BRAIDIO_YTDLP_COOKIES_FROM_BROWSER"

#: yt-dlp ``extractor_args`` as JSON, e.g.
#: ``'{"youtube": {"player_client": ["tv", "web_safari"]}}'``. No secret material,
#: so it is the first thing to try against a bot gate.
EXTRACTOR_ARGS_ENV_VAR = "BRAIDIO_YTDLP_EXTRACTOR_ARGS"

#: Zero-config cookie location, under the data root (never the deploy tree, so a
#: redeploy's ``rsync --delete`` cannot erase it — the rule the workspace follows).
CREDENTIALS_DIRNAME = "credentials"
COOKIES_FILENAME = "youtube-cookies.txt"


class MediaSourceError(ToolError):
    """braidio could not retrieve audio from a source link."""


class SourceAuthRequired(MediaSourceError):
    """The source demands a signed-in session and this server has none."""


class SourceCredentialsRejected(SourceAuthRequired):
    """This server HAS credentials for the source and they did not work.

    Almost always expiry. Distinct from :class:`SourceAuthRequired` (nothing was
    provisioned) and from :class:`SourceUnavailable` (no credential would help).
    """


class SourceUnavailable(MediaSourceError):
    """The source is private, removed, or blocked here — not an auth problem."""


#: Fragments meaning "the credential itself is bad", whatever is configured.
CREDENTIAL_MARKERS = (
    "failed to load cookies",  # yt_dlp.cookies.CookieLoadError
    "cookies are no longer valid",  # yt-dlp's rotated-cookies report
)

#: Fragments meaning "the source is gone/blocked" — no credential fixes these.
UNAVAILABLE_MARKERS = (
    "private video",
    "video unavailable",
    "video is unavailable",
    "video is not available",
    "not made this video available in your country",
    "not available from your location",
    "has been removed",
    "has been terminated",
    "video does not exist",
)

#: Fragments meaning "authenticate". ``use --cookies`` is yt-dlp's OWN login hint
#: (``InfoExtractor._login_hint``) and matches all three of its phrasings, so it
#: survives YouTube rewording its reasons; the rest pin reasons seen in the wild.
AUTH_MARKERS = (
    "use --cookies",
    "sign in to confirm",  # "…you're not a bot" / "…your age"
    "not a bot",  # apostrophe-agnostic form of the bot gate
    "confirm your age",  # yt-dlp's own AGE_GATE_REASONS
    "age-restricted",
    "age_verification_required",
    "login details are needed",
    "only available for registered users",
    "requiring a captcha challenge",
    "members-only",
)

#: One line, cause + fix (issue #23's second acceptance criterion).
_REFRESH_FIX = (
    "this server's stored credentials for the source were rejected — they have most "
    "likely expired; re-export the cookies from a signed-in browser and replace the "
    "cookie file (procedure: misc/docs/youtube_ingest_credentials.md)."
)


def _browser_spec(value: str) -> tuple[str, ...]:
    """yt-dlp's ``cookiesfrombrowser`` tuple from ``"chrome"`` / ``"chrome:Profile 1"``.

    >>> _browser_spec("chrome:Profile 1")
    ('chrome', 'Profile 1')
    >>> _browser_spec("safari")
    ('safari',)
    """
    browser, _, profile = value.partition(":")
    return (browser.strip(), profile.strip()) if profile.strip() else (browser.strip(),)


def _extractor_args(raw: str) -> dict:
    """yt-dlp ``extractor_args`` parsed from JSON (keyed by extractor name)."""
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise SourceCredentialsRejected(
            f"${EXTRACTOR_ARGS_ENV_VAR} is not valid JSON — expected an object like "
            '\'{"youtube": {"player_client": ["tv"]}}\''
        ) from exc
    if not isinstance(parsed, dict):
        raise SourceCredentialsRejected(
            f"${EXTRACTOR_ARGS_ENV_VAR} must be a JSON object keyed by extractor name"
        )
    return parsed


def _cookie_file(env: Mapping[str, str]) -> Path | None:
    """The jar to use: the configured one, else the conventional one if it exists.

    A configured path is returned even when absent — reporting that is
    :meth:`SourceCredentials.check`'s job, and saying so beats yt-dlp's silence.
    """
    configured = (env.get(COOKIES_FILE_ENV_VAR) or "").strip()
    if configured:
        return Path(configured).expanduser()
    conventional = data_root() / CREDENTIALS_DIRNAME / COOKIES_FILENAME
    return conventional if conventional.exists() else None


def _jar_is_expired(path: Path, *, now: float | None = None) -> bool:
    """True when every *dated* cookie in a Netscape jar is in the past.

    Session cookies (expiry ``0``) carry no date and are ignored, so a jar of only
    session cookies is never called expired. ``#HttpOnly_`` lines are real cookies
    with a comment-looking prefix, so they count; anything unparseable is treated
    as fine. This is a legibility check, not a validator — it must never block a
    jar yt-dlp would happily use.
    """
    now = time.time() if now is None else now
    expiries: list[float] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for raw_line in fh:
                line = raw_line.strip()
                if line.startswith("#HttpOnly_"):
                    line = line[len("#HttpOnly_") :]
                elif not line or line.startswith("#"):
                    continue
                fields = line.split("\t")
                if len(fields) < 5:
                    continue
                try:
                    expiry = float(fields[4])
                except ValueError:
                    continue
                if expiry > 0:
                    expiries.append(expiry)
    except OSError:
        return False
    return bool(expiries) and max(expiries) < now


@dataclass(frozen=True)
class SourceCredentials:
    """Whatever credential material this deployment gave yt-dlp (possibly none).

    ``opts`` is merged into yt-dlp's option dict. ``configured`` is what lets a bot
    gate read as *expiry* rather than *never provisioned*. ``cookie_file`` is kept
    so :meth:`check` can fail before the network.
    """

    opts: Mapping[str, Any] = field(default_factory=dict)
    cookie_file: Path | None = None

    @property
    def configured(self) -> bool:
        """Whether this server has anything at all to authenticate with."""
        return bool(self.opts)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "SourceCredentials":
        """Read the deployment's credential configuration (call time, not import time)."""
        env = os.environ if env is None else env
        opts: dict[str, Any] = {}
        cookie_file = _cookie_file(env)
        if cookie_file is not None:
            opts["cookiefile"] = str(cookie_file)
        browser = (env.get(COOKIES_FROM_BROWSER_ENV_VAR) or "").strip()
        if browser:
            opts["cookiesfrombrowser"] = _browser_spec(browser)
        raw = (env.get(EXTRACTOR_ARGS_ENV_VAR) or "").strip()
        if raw:
            opts["extractor_args"] = _extractor_args(raw)
        return cls(opts=opts, cookie_file=cookie_file)

    def check(self) -> None:
        """Fail *before* the network when the configured cookie jar cannot work.

        ``yt_dlp.cookies.load_cookies`` skips an unreadable jar without a word, so
        without this a mis-provisioned server is indistinguishable from a bot-gated
        one — the mystery this module exists to remove.
        """
        if self.cookie_file is None:
            return
        if not os.access(self.cookie_file, os.R_OK):
            raise SourceCredentialsRejected(
                f"the cookie file this server is configured to use (${COOKIES_FILE_ENV_VAR}, "
                f"else the credentials dir under ${DATA_HOME_ENV_VAR}) is missing or "
                "unreadable — re-provision it; yt-dlp would otherwise ignore it "
                "silently and fail as if no credentials existed."
            )
        if _jar_is_expired(self.cookie_file):
            raise SourceCredentialsRejected(
                "this server's YouTube cookies have expired — re-export them from a "
                "signed-in browser and replace the cookie file (procedure: "
                "misc/docs/youtube_ingest_credentials.md)."
            )


def classify_download_error(
    exc: BaseException, *, credentials: SourceCredentials, extra_text: str = ""
) -> MediaSourceError | None:
    """The actionable braidio error for a yt-dlp failure, or ``None`` if unknown.

    ``extra_text`` carries anything yt-dlp said outside the exception (it reports
    rotated cookies as a *warning*, never in the error).

    The check order is load-bearing: yt-dlp appends its "Use --cookies…" login hint
    to a **private video** error too (any playability reason containing "sign in"),
    so the unavailable match must be taken before the auth match — otherwise every
    private video would read as a bot gate, and issue #23's third acceptance
    criterion would be unmet.
    """
    text = f"{exc}\n{extra_text}".lower()
    if any(m in text for m in CREDENTIAL_MARKERS):
        return SourceCredentialsRejected(_REFRESH_FIX)
    if any(m in text for m in UNAVAILABLE_MARKERS):
        return SourceUnavailable(
            "this link is not retrievable — the source is private, removed, or blocked "
            "in this server's region; no sign-in changes that. Use a different link, "
            "or upload the file with upload_asset."
        )
    if any(m in text for m in AUTH_MARKERS):
        if credentials.configured:
            return SourceCredentialsRejected(_REFRESH_FIX)
        return SourceAuthRequired(
            "this source requires a signed-in session and this server has no "
            f"credentials for it — provision a cookie file (${COOKIES_FILE_ENV_VAR}, "
            "or drop it at <data root>/credentials/youtube-cookies.txt) exported from "
            "a signed-in browser."
        )
    return None


def as_tool_error(
    exc: BaseException, *, fallback: str, credentials: SourceCredentials
) -> ToolError:
    """:func:`classify_download_error` with a generic ``ToolError`` fallback."""
    return classify_download_error(exc, credentials=credentials) or ToolError(
        f"{fallback}: {exc}"
    )
