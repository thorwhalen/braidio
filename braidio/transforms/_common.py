"""Shared helpers for braidio's ``nw.Transform`` pipeline.

The transforms in this package turn braidio's authoring graph (narrative
beats, audio clips, a weave-config snapshot) into render-provenance nodes
(voice-assignment, narration-render, segment-extraction, episode-render),
writing each **through** ``project.graph`` so ``nw.stale_after`` traverses
them. This is the whole point of riding nw: one freshness engine over the
project graph — *not* braidio's parallel standalone ``record_render`` store
(which stays as the no-nw fast path in :mod:`braidio.provenance`).

Tier-name constants mirror :mod:`braidio.bodies._tiers`; body schemas live in
:mod:`braidio.bodies`.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from lacing import Annotation, Artifact, NodeRef, TimeInterval

# Tier names (must match braidio.bodies._tiers).
TIER_WEAVE_CONFIG = "weave-configs"
TIER_SOURCE_MEDIA = "source-media"
TIER_NARRATIVE_BEAT = "narrative-beats"
TIER_AUDIO_CLIP = "audio-clips"
TIER_VOICE_ASSIGNMENT = "voice-assignments"
TIER_NARRATION_RENDER = "narration-renders"
TIER_SEGMENT_EXTRACTION = "segment-extractions"
TIER_EPISODE_RENDER = "episode-renders"

#: Rate for the (incidental) NodeRef intervals on non-media nodes.
_RATE = 1000


def node_ref(tier: str) -> NodeRef:
    """A fresh zero-length :class:`NodeRef` for a node in ``tier``.

    Render/authoring nodes that don't point at a media interval still need a
    ``reference``; a NodeRef keyed by a fresh id is the neutral choice.
    """
    return NodeRef(
        scene_path=f"{tier}/{uuid.uuid4()}",
        interval=TimeInterval.from_seconds(0.0, 1.0, rate=_RATE),
    )


def file_url(path: str | Path) -> str:
    """The ``file://`` URL for a local path (what render bodies store)."""
    return Path(path).resolve().as_uri()


def url_to_path(url: str) -> Path:
    """Local path from a ``file://`` URL (inverse of :func:`file_url`)."""
    parsed = urlparse(url)
    if parsed.scheme and parsed.scheme != "file":
        raise ValueError(f"expected a file:// URL, got {url!r}")
    return Path(url2pathname(parsed.path))


def graph_index(project) -> dict:
    """``{annotation.id: annotation}`` across the whole project graph.

    ``Transform.execute`` receives no ``inputs`` — it re-resolves what it
    needs from the graph, keyed by the ids recorded in the skeleton's
    ``provenance.was_derived_from``.
    """
    import nw

    return {a.id: a for a in nw.iter_all_annotations(project.root)}


def singleton(project, tier: str) -> Annotation:
    """The one annotation at ``tier`` (raises if there isn't exactly one)."""
    import nw

    anns = nw.annotations_at_tier(project.root, tier)
    if len(anns) != 1:
        raise ValueError(
            f"expected exactly one {tier!r} node in the project graph, "
            f"found {len(anns)}"
        )
    return anns[0]


def child_at_tier(project, tier: str, parent_id) -> Annotation:
    """The most recent ``tier`` annotation derived from ``parent_id``."""
    import nw

    hits = [
        a
        for a in nw.annotations_at_tier(project.root, tier)
        if parent_id in a.provenance.was_derived_from
    ]
    if not hits:
        raise ValueError(f"no {tier!r} node derived from {parent_id}")
    return hits[-1]


def resolve_parents(skeleton: Annotation, index: dict) -> list:
    """The annotations ``skeleton`` was derived from, resolved via ``index``."""
    return [index[pid] for pid in skeleton.provenance.was_derived_from if pid in index]


def require_tier(anns, tier: str) -> Annotation:
    """The first annotation in ``anns`` at ``tier`` (raise if none)."""
    for a in anns:
        if a.tier == tier:
            return a
    raise ValueError(
        f"expected a {tier!r} node among derived-from nodes {[a.tier for a in anns]}"
    )


def cached_output(project, tier: str, cache_key: str):
    """An existing completed ``tier`` node with matching ``cache_key`` (or None).

    Non-fal renders (ElevenLabs TTS, ffmpeg extraction) aren't covered by
    falaw's content-addressed cache, so each carries an explicit ``cache_key``
    and compares-and-skips here before doing billable/expensive work.
    """
    import nw

    for ann in nw.annotations_at_tier(project.root, tier):
        body = ann.body or {}
        if body.get("cache_key") == cache_key and body.get("artifact_id"):
            return ann
    return None


def audio_artifact(
    path: str | Path,
    *,
    transform_name: str,
    derived_from,
    duration_s: float | None = None,
    cost_usd: float | None = None,
) -> Artifact:
    """A content-addressed ``lacing.Artifact`` for a produced audio file.

    ``cost_usd`` is the cost to produce this file (``None`` = unpriced, never a
    fake ``0.0``); for TTS it is a rate ESTIMATE from
    :func:`braidio.cost.tts_cost_usd` (see that module + thorwhalen/braidio#8).
    """
    return Artifact.from_path(
        Path(path),
        kind="audio",
        was_generated_by=f"transform:{transform_name}",
        was_attributed_to="agent:braidio",
        was_derived_from=tuple(str(x) for x in derived_from),
        duration_s=duration_s,
        cost_usd=cost_usd,
    )


def safe_duration(path: str | Path) -> float:
    """Best-effort audio duration in seconds; ``0.0`` if it can't be probed."""
    import braidio

    try:
        return float(braidio.duration_s(path))
    except Exception:  # noqa: BLE001 — duration is advisory; never fail a render on it
        return 0.0
