"""The braidio MCP tool surface — flat, JSON-in/JSON-out functions.

Each function here becomes one MCP tool (referenced by the connector as
``braidio.mcp.tools:<name>``); its signature + docstring *is* the tool schema, so
keep both clean. Three groups:

- **catalog / planning / read** — free, stateless (no ElevenLabs, no spend);
- **project workspace** — per-user projects (create/list/status), free;
- **[COSTED]** renders — the only tools that spend ElevenLabs money. Each writes
  its output into the caller's :class:`~braidio.mcp.workspace.Workspace` and returns
  ``cost_usd`` (an estimate; see :mod:`braidio.cost` + braidio#8) so the metering
  middleware records real dollars.

Values are coerced to JSON via :func:`~braidio.mcp._helpers.to_json`. Costed tools'
intermediate/work files stay inside the workspace (never the server CWD).
"""

from __future__ import annotations

import braidio  # attr access (braidio.narrate, ...) so tests can monkeypatch
from fastmcp.exceptions import ToolError

from braidio.mcp._helpers import script_from_json, source_from_json, to_json
from braidio.mcp.metering import current_email
from braidio.mcp.workspace import Workspace
from braidio.tts import DEFAULT_MODEL_ID, DIALOGUE_MODEL_ID


def _workspace() -> Workspace:
    """The calling user's workspace, keyed by the identity the middleware resolved."""
    return Workspace.for_email(current_email())


def _require_nw(tool: str) -> None:
    if not braidio.HAS_NW:
        raise ToolError(f"{tool} needs braidio's nw layer, which is not installed here")


def _reject_dialogue(scr, tool: str) -> None:
    """The nw graph pipeline can't ingest Dialogue beats yet — fail BEFORE mutating."""
    from braidio import Dialogue

    if any(isinstance(b, Dialogue) for b in scr.beats):
        raise ToolError(
            f"{tool}: Dialogue beats aren't supported by the graph pipeline yet — "
            "use render_production for dialogue"
        )


# --- assistance -------------------------------------------------------------


def help() -> dict:
    """What braidio can do and how to use it.

    Call this when a user asks what this connector/assistant can do, or to recall the
    document -> script -> audio workflow and the free-vs-costed tool split.
    """
    from braidio.mcp._guide import capabilities

    return capabilities()


# --- catalog / registries (free) --------------------------------------------


def list_formats() -> dict:
    """List braidio's ready-made production formats, keyed by format id."""
    return {"formats": {k: to_json(v) for k, v in braidio.FORMATS.items()}}


def list_presets() -> dict:
    """List WeaveConfig presets (bundles of editing knobs), keyed by name."""
    return {"presets": {k: v.to_dict() for k, v in braidio.PRESETS.items()}}


def list_deliveries() -> dict:
    """List delivery presets (TTS model + voice-settings tunings), keyed by name."""
    return {"deliveries": {k: to_json(v) for k, v in braidio.DELIVERIES.items()}}


def list_voice_pools() -> dict:
    """List named voice pools for multi-voice casting, keyed by pool label."""
    return {
        "pools": {
            k: [to_json(voice) for voice in pool] for k, pool in braidio.POOLS.items()
        }
    }


def describe_genre() -> dict:
    """Describe the ``commentary_weave`` genre (its transforms, schemas, status)."""
    if not braidio.HAS_NW:
        return {"available": False, "reason": "nw layer not installed"}
    return {"available": True, "genre": to_json(braidio.COMMENTARY_WEAVE)}


# --- planning / read / safety (free) ----------------------------------------


def estimate_cost(script: dict) -> dict:
    """Estimate the ElevenLabs cost of a production BEFORE paying for synthesis.

    ``script`` is a JSON script envelope (see :func:`weave_project` for the shape).
    Segment extraction / weaving is free; only narration + dialogue text is billed.
    Returns exact character counts and an honest dollar estimate.
    """
    roll = braidio.estimate_cost(script_from_json(script))
    out = to_json(roll)
    out["summary"] = roll.summary
    return out


def plan_production(script: dict, profile: str = "personal") -> dict:
    """Filter a script into the beats renderable under a rights ``profile``.

    ``profile`` is ``"personal"`` (play everything) or ``"published"`` (drop /
    substitute non-publishable clips). Returns the planned beats + what was
    dropped/substituted — a dry run, nothing is rendered.
    """
    from braidio import Profile

    plan = braidio.plan_production(script_from_json(script), Profile(profile))
    return to_json(plan)


def find_forbidden_quotes(text: str, forbidden: list[str], min_words: int = 5) -> dict:
    """Find forbidden verbatim quotes (>= ``min_words`` words) in ``text``."""
    return {
        "violations": braidio.find_verbatim_text(text, forbidden, min_words=min_words)
    }


def content_violations(
    script: dict, forbidden: list[str], profile: str = "published", min_words: int = 5
) -> dict:
    """Scan a production's render plan for non-publishable clips + forbidden quotes."""
    from braidio import Profile

    plan = braidio.plan_production(script_from_json(script), Profile(profile))
    return {
        "violations": braidio.content_violations(plan, forbidden, min_words=min_words)
    }


def audit_platitudes(text: str) -> dict:
    """Flag recycled rhetorical tics in commentary + a platitudes-per-1000-words rate."""
    return {
        "findings": [to_json(f) for f in braidio.audit_platitudes(text)],
        "rate_per_1000_words": braidio.platitude_rate(text),
    }


def clean_text(text: str, collapse_whitespace: bool = True) -> dict:
    """Prep text for clean TTS: expand ligatures/soft-hyphens + drop leaked speaker labels."""
    cleaned = braidio.strip_speaker_labels(
        braidio.clean_ocr(text, collapse_whitespace=collapse_whitespace)
    )
    return {"text": cleaned}


def build_timeline(
    kinds: list[str],
    durations: list[float],
    placements: list[str] | None = None,
    labels: list[str] | None = None,
    title: str = "",
) -> dict:
    """Assemble a queryable timeline breakdown of a planned production (no rendering)."""
    tb = braidio.build_timeline(
        kinds=kinds,
        durations=durations,
        placements=placements,
        labels=labels,
        title=title,
    )
    out = tb.to_dict()
    out["totals"] = tb.totals()
    out["shares"] = tb.shares()
    return out


def narration_segments(script: dict) -> dict:
    """Split a script's narration into sentence-level segments."""
    return {"segments": braidio.narration_segments(script_from_json(script))}


def assign_voices(n: int, pool: str = "four", seed: int = 0) -> dict:
    """Deterministically assign ``n`` voices from a named pool (``"four"`` | ``"many"``)."""
    if pool not in braidio.POOLS:
        raise ToolError(f"unknown pool {pool!r}; use one of {sorted(braidio.POOLS)}")
    voices = braidio.assign_voices(n, braidio.POOLS[pool], seed=seed)
    return {"voices": [to_json(v) for v in voices]}


def find_segment(
    lines: list[dict], quote: str, max_span: int = 12, min_score: float = 0.5
) -> dict:
    """Resolve a quote to a ``[start,end]`` window over time-aligned lines (token-F1)."""
    from braidio import TimedLine

    seg = braidio.find_segment(
        [TimedLine(**ln) for ln in lines], quote, max_span=max_span, min_score=min_score
    )
    if seg is None:
        return {"segment": None}
    out = to_json(seg)
    out["duration_s"] = seg.duration_s
    return {"segment": out}


# --- project workspace (free) -----------------------------------------------


def create_project(project_id: str, title: str = "") -> dict:
    """Create a new braidio project in your workspace (holds the graph + renders)."""
    _require_nw("create_project")
    proj = _workspace().create_project(project_id, title=title)
    return {
        "project_id": project_id,
        "title": title or project_id,
        "root": str(proj.root),
    }


def list_projects() -> dict:
    """List your braidio projects (newest first)."""
    return {"projects": _workspace().list_projects()}


def project_status(project_id: str) -> dict:
    """A project's status: its finished episode renders (url + duration), if any."""
    _require_nw("project_status")
    import nw

    proj = _workspace().open_project(project_id)
    episodes = [
        to_json(a.body) for a in nw.annotations_at_tier(proj.root, "episode-renders")
    ]
    return {"project_id": project_id, "episodes": episodes}


def ingest_document(
    project_id: str,
    uri: str | None = None,
    text: str | None = None,
    name: str | None = None,
    max_chars: int = 40000,
) -> dict:
    """Ingest source material into a project so you can analyze it into a Script.

    Provide EITHER ``uri`` (a public http/https URL — PDF, HTML, or plain text) OR
    ``text`` (pasted content). The document is fetched (SSRF-guarded: public hosts
    only, size/time bounded), its plaintext extracted and stored in the project, and
    the text returned (up to ``max_chars``) for you to read and turn into narration /
    segment beats. Free — no synthesis.
    """
    from braidio.mcp import _docs

    ws = _workspace()
    root = ws.project_root(project_id)
    if not (root / "project.json").exists():
        raise ToolError(f"no project {project_id!r} — call create_project first")
    try:
        if uri:
            data, ctype = _docs.fetch_uri(uri)
            src = uri
        elif text is not None:
            data, ctype, src = text.encode("utf-8"), "text/plain", "inline"
        else:
            raise ToolError("provide either `uri` or `text`")
        full = _docs.extract_text(data, ctype)
    except ValueError as exc:
        raise ToolError(str(exc)) from exc

    from hashlib import sha256

    docs_dir = root / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    doc_id = sha256(data).hexdigest()[:16]
    (docs_dir / f"{doc_id}.txt").write_text(full, encoding="utf-8")
    return {
        "doc_id": doc_id,
        "name": name or src,
        "source": src,
        "content_type": ctype,
        "characters": len(full),
        "truncated": len(full) > max_chars,
        "text": full[:max_chars],
    }


def save_script(project_id: str, script: dict, source: dict | None = None) -> dict:
    """Link a Script's beats into a project's graph (free authoring; render later).

    Writes the narration + segment beats (with their source-media links) into the
    project graph, so you can review (project_status) and render with weave_project
    when ready. Narration + Segment beats only (Dialogue is not yet in the graph
    pipeline). Free — no synthesis.
    """
    _require_nw("save_script")
    scr = script_from_json(script)
    _reject_dialogue(scr, "save_script")
    src = _resolve_source(source)
    _check_source(scr, src)
    proj = _workspace().open_project(project_id)
    ingested = braidio.transforms.ingest_script(proj, scr, source=src)
    return {
        "project_id": project_id,
        "beats": [{"kind": k, "id": str(a.id)} for k, a in ingested.ordered],
    }


# --- assets (braidio#10, free) ----------------------------------------------


def upload_asset(
    uri: str | None = None,
    data_b64: str | None = None,
    name: str | None = None,
) -> dict:
    """Upload media/source into your asset library; returns a ContentRef.

    Provide EITHER ``uri`` (a public http/https URL — audio/video/etc., fetched
    server-side, SSRF-guarded and size-bounded) OR ``data_b64`` (base64 bytes, for
    small inline uploads). The blob is stored **content-addressed** (identical bytes
    dedupe to one copy) in your per-user library, and you get back an ``item_id`` you
    can reference from a segment source as ``source.asset_id`` in ANY render that takes
    a source — ``render_production`` / ``render_format`` (one-shot) or ``save_script`` /
    ``weave_project`` (project graph). Free — no synthesis.
    """
    import base64

    from braidio.mcp import _docs

    if uri:
        try:
            data, ctype = _docs.fetch_uri(uri)
        except ValueError as exc:
            raise ToolError(str(exc)) from exc
        src = uri
    elif data_b64:
        try:
            data = base64.b64decode(data_b64, validate=True)
        except (ValueError, TypeError) as exc:
            raise ToolError(f"invalid data_b64: {exc}") from exc
        ctype, src = None, "inline"
    else:
        raise ToolError("provide either `uri` or `data_b64`")

    ws = _workspace()
    ref = ws.content_store().add(data, mime_type=ctype, name=name or (uri or None))
    meta = {**ref.to_json(), "name": name or src, "source": src}
    ws.asset_meta()[ref.item_id] = meta
    return meta


def list_assets() -> dict:
    """List the media/source assets in your library (ContentRefs + names). Free."""
    meta = _workspace().asset_meta()
    return {"assets": [meta[k] for k in meta]}


def get_asset(asset_id: str) -> dict:
    """Details for one uploaded asset (its ContentRef + name, and a URL if the store
    can mint one — e.g. an S3 backend; a local store returns none). Free."""
    from dol import content_url

    ws = _workspace()
    meta = ws.asset_meta()
    if asset_id not in meta:
        raise ToolError(f"no asset {asset_id!r} in your library")
    out = dict(meta[asset_id])
    url = content_url(ws.content_store(), asset_id)
    if url:
        out["url"] = url
    return out


def _resolve_source(source: dict | None):
    """Build a segment source, resolving a ``source.asset_id`` (an uploaded
    :class:`dol.ContentRef`) to its server-local ``asset_path`` for weave/render."""
    if source and source.get("asset_id") and not source.get("asset_path"):
        source = {**source, "asset_path": _workspace().asset_path(source["asset_id"])}
    return source_from_json(source)


# --- [COSTED] renders (spend ElevenLabs money) ------------------------------


def _work_dir(ws: Workspace, name: str) -> str:
    """A per-render scratch dir inside the workspace (keeps intermediates off CWD)."""
    return str(ws.renders_dir / "_work" / name)


def _check_source(scr, source) -> None:
    """Fail early if a script needs segment media but no ``source`` was given.

    A segment source references a **server-accessible** ``asset_path``; a remote
    caller can only weave clips whose media already lives on the server (retrieval /
    upload of media is a connector concern — thorwhalen/braidio#10).
    """
    from braidio import SegmentBeat

    if source is None and any(isinstance(b, SegmentBeat) for b in scr.beats):
        raise ToolError(
            "this script has segment beats but no `source`; provide a source (timed "
            "lines + a server-accessible asset_path) or use a narration-only script"
        )


def _render_cost(scr, profile: str) -> dict:
    """Estimate the spend of the beats that WILL render under ``profile``.

    Costs :func:`braidio.plan_production`'s output (the SSOT for the rights
    projection), so under ``"published"`` dropped clips cost nothing and synthesized
    substitutes are billed — unlike costing the raw script. The figure is a rate
    estimate (``cost_basis="estimate"``; see :mod:`braidio.cost` + braidio#8).
    """
    from braidio import Profile

    plan = braidio.plan_production(scr, Profile(profile))
    chars = 0
    priced: list[float] = []
    unpriced = False
    for b in plan.beats:
        if b.kind == "narration":
            text, model = b.content, DEFAULT_MODEL_ID
        elif b.kind == "dialogue":
            text, model = "".join(t for _r, t in (b.turns or ())), DIALOGUE_MODEL_ID
        else:
            continue  # clip = free (local ffmpeg)
        chars += braidio.billable_chars(text)
        cost = braidio.tts_cost_usd(text, model_id=model)
        if cost is None and text:
            unpriced = True
        elif cost is not None:
            priced.append(cost)
    usd = round(sum(priced), 6) if priced else (None if unpriced else 0.0)
    return {
        "cost_usd": usd,
        "characters": chars,
        "unpriced": unpriced,
        "cost_basis": "estimate",
    }


def _delivery(name: str):
    """Resolve a delivery/register preset name to its :class:`braidio.Delivery`."""
    if name not in braidio.DELIVERIES:
        raise ToolError(
            f"unknown delivery {name!r}; use one of {sorted(braidio.DELIVERIES)} "
            "(list_deliveries describes them)"
        )
    return braidio.DELIVERIES[name]


def narrate(
    text: str,
    voice_id: str | None = None,
    delivery: str = "narration",
    name: str = "narration",
) -> dict:
    """[COSTED] Synthesize one text to speech (single voice) → an mp3 in your workspace.

    ``delivery`` picks the speaking register / voice preset: ``"narration"`` (default —
    reading a script) or ``"conversational"`` (sounds like talking, not reading), among
    others from ``list_deliveries``. It sets the model + voice settings.
    """
    d = _delivery(delivery)
    ws = _workspace()
    out = ws.render_path(name)
    braidio.narrate(
        text,
        out,
        voice_id=voice_id,
        model_id=d.model_id,
        voice_settings=d.voice_settings,
    )
    return {
        "url": out.as_uri(),
        "path": str(out),
        "cost_usd": braidio.tts_cost_usd(text, model_id=d.model_id),
        "characters": braidio.billable_chars(text),
        "cost_basis": "estimate",
    }


def render_dialogue(turns: list[list[str]], name: str = "dialogue") -> dict:
    """[COSTED] Render a multi-speaker exchange (``[[role, text], ...]``) → one mp3 (eleven_v3)."""
    pairs = [(r, t) for r, t in turns]
    ws = _workspace()
    out = ws.render_path(name)
    braidio.render_dialogue(pairs, out_path=out)
    text = "".join(t for _r, t in pairs)
    return {
        "url": out.as_uri(),
        "path": str(out),
        "cost_usd": braidio.tts_cost_usd(text, model_id="eleven_v3"),
        "characters": braidio.billable_chars(text),
        "cost_basis": "estimate",
    }


def render_multivoice(
    segments: list[str], pool: str = "four", name: str = "multivoice"
) -> dict:
    """[COSTED] Render text segments cycling a pool of voices → one mp3."""
    if pool not in braidio.POOLS:
        raise ToolError(f"unknown pool {pool!r}; use one of {sorted(braidio.POOLS)}")
    ws = _workspace()
    out = ws.render_path(name)
    braidio.render_multivoice(
        segments, braidio.POOLS[pool], out_path=out, work_dir=_work_dir(ws, name)
    )
    text = "".join(segments)
    return {
        "url": out.as_uri(),
        "path": str(out),
        "cost_usd": braidio.tts_cost_usd(text),
        "characters": braidio.billable_chars(text),
        "cost_basis": "estimate",
    }


def compose_narration(
    segments: list[str], preset: str = "single_narrator", name: str = "narration"
) -> dict:
    """[COSTED] Config-driven narration render (a WeaveConfig preset) → one mp3."""
    if preset not in braidio.PRESETS:
        raise ToolError(
            f"unknown preset {preset!r}; use one of {sorted(braidio.PRESETS)}"
        )
    ws = _workspace()
    out = ws.render_path(name)
    braidio.compose_narration(
        segments, braidio.PRESETS[preset], out_path=out, work_dir=_work_dir(ws, name)
    )
    text = "".join(segments)
    return {
        "url": out.as_uri(),
        "path": str(out),
        "cost_usd": braidio.tts_cost_usd(text),
        "characters": braidio.billable_chars(text),
        "cost_basis": "estimate",
    }


def render_production(
    script: dict,
    source: dict | None = None,
    profile: str = "personal",
    delivery: str = "narration",
    name: str | None = None,
) -> dict:
    """[COSTED] Render a whole script → one mixed episode mp3 in your workspace.

    ``script`` is a JSON script envelope; ``source`` (``{lines, asset_path, ...}``)
    is required only if the script has segment beats. ``profile`` = ``"personal"``
    or ``"published"``. ``delivery`` = the narration register (``"narration"`` =
    reading, ``"conversational"`` = talking; see ``list_deliveries``).
    """
    from braidio import Profile

    scr = script_from_json(script)
    src = _resolve_source(source)
    _check_source(scr, src)
    ws = _workspace()
    stem = name or scr.id_slug
    out = ws.render_path(stem)
    braidio.render_production(
        scr,
        source=src,
        profile=Profile(profile),
        delivery=_delivery(delivery),
        out_path=out,
        tts_dir=_work_dir(ws, stem) + "/tts",
        clips_dir=_work_dir(ws, stem) + "/clips",
        episodes_dir=str(ws.renders_dir),
    )
    return {"url": out.as_uri(), "path": str(out), **_render_cost(scr, profile)}


def render_format(
    format_id: str,
    script: dict,
    source: dict | None = None,
    profile: str = "personal",
    name: str | None = None,
) -> dict:
    """[COSTED] Render a script under a ready-made format preset → mp3 in your workspace."""
    from braidio import Profile

    if format_id not in braidio.FORMATS:
        raise ToolError(
            f"unknown format {format_id!r}; use one of {sorted(braidio.FORMATS)}"
        )
    scr = script_from_json(script)
    src = _resolve_source(source)
    _check_source(scr, src)
    ws = _workspace()
    stem = name or scr.id_slug
    out = ws.render_path(stem)
    braidio.render_format(
        braidio.FORMATS[format_id],
        scr,
        source=src,
        profile=Profile(profile),
        out_path=out,
        tts_dir=_work_dir(ws, stem) + "/tts",
        clips_dir=_work_dir(ws, stem) + "/clips",
        episodes_dir=str(ws.renders_dir),
    )
    return {"url": out.as_uri(), "path": str(out), **_render_cost(scr, profile)}


def weave_project(project_id: str, script: dict, source: dict | None = None) -> dict:
    """[COSTED] Ingest a script into your project and run the full commentary_weave pipeline.

    Uses the nw graph, so re-running re-synthesizes only what changed (partial
    re-render) and records provenance. ``script`` must be Narration + Segment beats
    (Dialogue is not yet supported in the graph pipeline).
    """
    _require_nw("weave_project")
    scr = script_from_json(script)
    _reject_dialogue(scr, "weave_project")
    src = _resolve_source(source)
    _check_source(scr, src)
    proj = _workspace().open_project(project_id)
    episode = braidio.weave_project(proj, scr, source=src)
    body = episode.body
    return {
        "episode": to_json(body),
        "url": body.get("url"),
        **_render_cost(scr, "personal"),
    }
