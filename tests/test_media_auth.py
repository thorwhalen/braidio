"""Credential passthrough + yt-dlp error classification (braidio#23).

Every test here is offline: yt-dlp failures are faked as plain exceptions carrying
the strings yt-dlp actually produces, and cookie jars are tmp files. Nothing
imports yt_dlp or touches the network.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("fastmcp")

from fastmcp.exceptions import ToolError  # noqa: E402

from braidio.mcp import _media  # noqa: E402

NO_CREDS = _media.SourceCredentials()
WITH_CREDS = _media.SourceCredentials(opts={"cookiefile": "/dev/null"})

# Real yt-dlp/YouTube message shapes. Note that yt-dlp appends its own
# "Use --cookies…" login hint to ANY playability reason containing "sign in" —
# which is why PRIVATE below carries it too, and why the unavailable check must
# run before the auth check.
BOT_GATE = (
    "ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm you're not a bot. "
    "Use --cookies-from-browser or --cookies for the authentication. See "
    "https://github.com/yt-dlp/yt-dlp/wiki/FAQ for how to manually pass cookies"
)
AGE_GATE = (
    "ERROR: [youtube] abc: Sign in to confirm your age. This video may be "
    "inappropriate for some users. Use --cookies-from-browser or --cookies for "
    "the authentication."
)
PRIVATE = (
    "ERROR: [youtube] abc: Private video. Sign in if you've been granted access "
    "to this video. Use --cookies-from-browser or --cookies for the authentication."
)
REMOVED = (
    "ERROR: [youtube] abc: Video unavailable. This video has been removed by the "
    "uploader"
)
UNAVAILABLE = "ERROR: [youtube] abc: This video is unavailable"
GEO = (
    "ERROR: [youtube] abc: The uploader has not made this video available in your "
    "country"
)
LOGIN_REQUIRED = (
    "ERROR: [youtube:tab] Login details are needed to download this content. "
    "Use --cookies-from-browser or --cookies for the authentication."
)


def _classify(message, *, credentials=NO_CREDS, extra_text=""):
    return _media.classify_download_error(
        Exception(message), credentials=credentials, extra_text=extra_text
    )


def _jar(tmp_path, expiry, *, httponly=False):
    p = tmp_path / "cookies.txt"
    prefix = "#HttpOnly_" if httponly else ""
    p.write_text(
        "# Netscape HTTP Cookie File\n"
        f"{prefix}.youtube.com\tTRUE\t/\tTRUE\t{int(expiry)}\tLOGIN_INFO\tvalue\n"
    )
    return p


# -- classification ----------------------------------------------------------


def test_bot_gate_without_credentials_names_cause_and_fix():
    err = _classify(BOT_GATE)
    assert isinstance(err, _media.SourceAuthRequired)
    assert not isinstance(err, _media.SourceCredentialsRejected)
    assert _media.COOKIES_FILE_ENV_VAR in str(err)
    assert "\n" not in str(err)  # one line: cause + fix


def test_bot_gate_with_credentials_reads_as_expiry():
    err = _classify(BOT_GATE, credentials=WITH_CREDS)
    assert isinstance(err, _media.SourceCredentialsRejected)
    assert "expired" in str(err) and "re-export" in str(err)


def test_age_gate_is_an_auth_error():
    assert isinstance(_classify(AGE_GATE), _media.SourceAuthRequired)


def test_private_video_is_unavailable_not_auth():
    # THE ORDERING PIN. This string carries yt-dlp's "Use --cookies…" hint, so it
    # matches the auth markers too — it only classifies correctly because the
    # unavailable check runs first. Reorder those checks and this is what fails.
    err = _classify(PRIVATE)
    assert isinstance(err, _media.SourceUnavailable)
    assert not isinstance(err, _media.SourceAuthRequired)


def test_removed_video_is_unavailable():
    assert isinstance(_classify(REMOVED), _media.SourceUnavailable)


def test_bare_unavailable_string_is_unavailable():
    # "This video is unavailable" — the separate "video is unavailable" marker;
    # the "video unavailable" marker does not match this wording.
    assert isinstance(_classify(UNAVAILABLE), _media.SourceUnavailable)


def test_geo_block_is_unavailable():
    assert isinstance(_classify(GEO), _media.SourceUnavailable)


def test_ytdlp_login_hint_alone_is_an_auth_error():
    # yt-dlp's OWN wording rather than YouTube's, so it survives YouTube
    # rewording its reason strings.
    assert isinstance(_classify(LOGIN_REQUIRED), _media.SourceAuthRequired)


def test_cookie_load_failure_reads_as_credential_problem():
    assert isinstance(
        _classify("failed to load cookies"), _media.SourceCredentialsRejected
    )


def test_rotated_cookie_warning_classifies_via_extra_text():
    # yt-dlp reports rotated cookies as a WARNING, never in the exception, so the
    # extra_text channel is how that ever becomes observed rather than inferred.
    err = _classify(
        BOT_GATE,
        extra_text="WARNING: The provided YouTube account cookies are no longer valid.",
    )
    assert isinstance(err, _media.SourceCredentialsRejected)


def test_unrelated_failure_is_not_classified():
    assert _classify("HTTP Error 500: Internal Server Error") is None


def test_as_tool_error_falls_back_generically():
    err = _media.as_tool_error(
        Exception("boom"), fallback="audio download failed", credentials=NO_CREDS
    )
    assert type(err) is ToolError
    assert str(err).startswith("audio download failed:")


def test_all_errors_are_tool_errors():
    # fastmcp forwards FastMCPError messages verbatim and masks everything else,
    # so only a ToolError subclass reaches the agent with its fix intact.
    for cls in (
        _media.MediaSourceError,
        _media.SourceAuthRequired,
        _media.SourceCredentialsRejected,
        _media.SourceUnavailable,
    ):
        assert issubclass(cls, ToolError)


# -- credential discovery ----------------------------------------------------


def test_no_credentials_by_default(tmp_path, monkeypatch):
    for var in (
        _media.COOKIES_FILE_ENV_VAR,
        _media.COOKIES_FROM_BROWSER_ENV_VAR,
        _media.EXTRACTOR_ARGS_ENV_VAR,
    ):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    creds = _media.SourceCredentials.from_env()
    assert creds.opts == {}
    assert creds.configured is False
    assert creds.cookie_file is None


def test_conventional_cookie_path_is_discovered_with_no_config(tmp_path, monkeypatch):
    monkeypatch.delenv(_media.COOKIES_FILE_ENV_VAR, raising=False)
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    jar = tmp_path / _media.CREDENTIALS_DIRNAME / _media.COOKIES_FILENAME
    jar.parent.mkdir(parents=True)
    jar.write_text("# Netscape HTTP Cookie File\n")

    creds = _media.SourceCredentials.from_env()
    assert creds.opts["cookiefile"] == str(jar)
    assert creds.configured is True


def test_env_var_overrides_the_conventional_path(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    conventional = tmp_path / _media.CREDENTIALS_DIRNAME / _media.COOKIES_FILENAME
    conventional.parent.mkdir(parents=True)
    conventional.write_text("# Netscape HTTP Cookie File\n")
    chosen = _jar(tmp_path, time.time() + 86400)
    monkeypatch.setenv(_media.COOKIES_FILE_ENV_VAR, str(chosen))

    assert _media.SourceCredentials.from_env().opts["cookiefile"] == str(chosen)


def test_cookies_from_browser_is_coerced_to_a_tuple():
    assert _media._browser_spec("safari") == ("safari",)
    assert _media._browser_spec("chrome:Profile 1") == ("chrome", "Profile 1")


def test_extractor_args_env_is_parsed_as_json(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.delenv(_media.COOKIES_FILE_ENV_VAR, raising=False)
    monkeypatch.setenv(
        _media.EXTRACTOR_ARGS_ENV_VAR, '{"youtube": {"player_client": ["tv"]}}'
    )
    creds = _media.SourceCredentials.from_env()
    assert creds.opts["extractor_args"] == {"youtube": {"player_client": ["tv"]}}

    for bad in ("[]", "{not json"):
        monkeypatch.setenv(_media.EXTRACTOR_ARGS_ENV_VAR, bad)
        with pytest.raises(_media.SourceCredentialsRejected) as excinfo:
            _media.SourceCredentials.from_env()
        assert _media.EXTRACTOR_ARGS_ENV_VAR in str(excinfo.value)


# -- pre-network checks ------------------------------------------------------


def test_missing_cookie_file_names_the_env_var_not_the_path(tmp_path, monkeypatch):
    bogus = tmp_path / "nowhere" / "cookies.txt"
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.setenv(_media.COOKIES_FILE_ENV_VAR, str(bogus))

    with pytest.raises(_media.SourceCredentialsRejected) as excinfo:
        _media.SourceCredentials.from_env().check()
    message = str(excinfo.value)
    assert _media.COOKIES_FILE_ENV_VAR in message
    # A remote caller must not learn this server's filesystem layout.
    assert str(bogus) not in message


def test_expired_jar_is_detected_before_the_network(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.setenv(_media.COOKIES_FILE_ENV_VAR, str(_jar(tmp_path, time.time() - 3600)))

    with pytest.raises(_media.SourceCredentialsRejected, match="expired"):
        _media.SourceCredentials.from_env().check()


def test_fresh_jar_passes_check(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIDIO_DATA_HOME", str(tmp_path))
    monkeypatch.setenv(
        _media.COOKIES_FILE_ENV_VAR, str(_jar(tmp_path, time.time() + 86400))
    )
    assert _media.SourceCredentials.from_env().check() is None


def test_session_only_jar_is_not_called_expired(tmp_path):
    # Expiry 0 means "session cookie" — no date, so nothing to call stale. The
    # check must never block a jar yt-dlp would happily use.
    assert _media._jar_is_expired(_jar(tmp_path, 0)) is False


def test_httponly_prefixed_cookies_are_counted(tmp_path):
    # `#HttpOnly_` lines are real cookies wearing a comment-looking prefix.
    assert _media._jar_is_expired(_jar(tmp_path, time.time() + 86400, httponly=True)) is False
    assert _media._jar_is_expired(_jar(tmp_path, time.time() - 3600, httponly=True)) is True
