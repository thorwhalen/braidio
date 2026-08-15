# YouTube ingest credentials

YouTube bot-gates shared and datacenter IPs, so `download_audio` on a deployed
connector gets *"Sign in to confirm you're not a bot"* for links that work fine
from a laptop. braidio ships no credentials; an operator provisions them.

This is the refresh procedure braidio's error messages point at.

## Try the free knob first

`BRAIDIO_YTDLP_EXTRACTOR_ARGS` takes yt-dlp's `extractor_args` as JSON:

```
BRAIDIO_YTDLP_EXTRACTOR_ARGS='{"youtube": {"player_client": ["tv", "web_safari"]}}'
```

No secret, nothing to expire, safe to rotate — worth trying before you take on a
credential you have to keep alive.

While you're there: **keep `yt-dlp` current in the connector's venv.** Bot-gate
workarounds ship in yt-dlp releases, and a stale copy is a common cause of a gate
that everyone else has already routed around.

## Cookies

1. In a **private/incognito** window, sign into a **throwaway** YouTube account.
   A leaked jar is full account access — do not use a personal account.
2. Export cookies for `youtube.com` in **Netscape** format. (yt-dlp's wiki
   documents this under *Extractors → Exporting YouTube cookies*.)
3. Close that window **without signing out.** Signing out rotates the session and
   invalidates the export immediately.
4. Put the file at `<data root>/credentials/youtube-cookies.txt`, where the data
   root is `$BRAIDIO_DATA_HOME` (default `~/.local/share/braidio`). **No other
   configuration is needed** — braidio discovers that path. Use
   `BRAIDIO_YTDLP_COOKIES_FILE` only if you want it somewhere else.
5. `chmod 600`, owned by the service user. **Never commit it.** The data root is
   deliberately outside the deploy tree, so a redeploy can neither erase nor
   publish it.
6. Restart the connector.

## When it expires

You get a `SourceCredentialsRejected` — one line naming expiry and this file, not
a raw yt-dlp string. Redo steps 1–6.

braidio also checks the jar *before* the network, because
`yt_dlp.cookies.load_cookies` silently ignores an unreadable file: without that
check, a mis-provisioned server fails exactly like a bot-gated one. So a missing
or unreadable jar, and a jar whose every dated cookie is in the past, are both
reported as credential problems rather than as gates.

A genuinely private, removed, or geo-blocked video raises `SourceUnavailable`
instead. No cookie refresh helps that one — the distinction is the point.

## Developer machines

`BRAIDIO_YTDLP_COOKIES_FROM_BROWSER=safari` (or `chrome:Profile 1`) reads the
browser's own jar directly. Convenient locally, useless on a headless server —
which is why the cookie *file* is the deployed path.

## Env vars

| Var | Meaning |
|---|---|
| `BRAIDIO_YTDLP_EXTRACTOR_ARGS` | yt-dlp `extractor_args` as a JSON object keyed by extractor name. No secret material. |
| `BRAIDIO_YTDLP_COOKIES_FILE` | Path to a Netscape cookie jar. Overrides the conventional location. |
| `BRAIDIO_YTDLP_COOKIES_FROM_BROWSER` | `browser` or `browser:profile`. Local development only. |
| `BRAIDIO_DATA_HOME` | The data root; `credentials/youtube-cookies.txt` under it is discovered with no configuration. |
