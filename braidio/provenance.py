"""Record render choices as linked artifacts → trace + partial re-render.

A render is a *projection* of the graph, so the render **choices** belong in the
graph too. :func:`record_render` writes the render-provenance nodes
(weave-config, voice-assignment, narration-render, segment-extraction,
episode-render) with ``was_derived_from`` edges to their inputs.
:func:`stale_after` then returns exactly the nodes downstream of a change — the
partial-re-render frontier (a memoized build DAG for audio; mirrors nw's
``stale_after``). See the design doc + nw's render-provenance rationale.

Requires ``lacing``; imported lazily by ``braidio/__init__`` only when present.
"""

from __future__ import annotations

from uuid import UUID, uuid4

from lacing import Annotation, NodeRef, Provenance, RationalTime, TimeInterval

from braidio.bodies import register_tiers
from braidio.bodies._render_nodes import (
    EPISODE_RENDER_V1,
    NARRATION_RENDER_V1,
    SEGMENT_EXTRACTION_V1,
    VOICE_ASSIGNMENT_V1,
    WEAVE_CONFIG_V1,
)

_RATE = 1000


def _node(store, tier: str, uri: str, body: dict, *, derived_from=()) -> UUID:
    """Add a render node to ``store`` with provenance; return its id."""
    aid = uuid4()
    store.add(
        Annotation(
            id=aid,
            tier=tier,
            reference=NodeRef(
                scene_path=f"{tier}/{aid}",
                interval=TimeInterval.from_seconds(0.0, 1.0, rate=_RATE),
            ),
            body=body,
            body_schema_uri=uri,
            provenance=Provenance(
                was_generated_by="braidio:render",
                was_attributed_to="braidio",
                was_derived_from=list(derived_from),
                generated_at_time=RationalTime.now(rate=_RATE),
                activity="derive",
            ),
        )
    )
    return aid


def record_render(store, *, weave_config: dict, beats: list[dict], profile: str = "personal") -> dict:
    """Write the provenance graph for one render into ``store``.

    ``beats`` is an ordered list of dicts, each either::

        {"kind": "narration", "source_id": <UUID of the beat/commentary node>,
         "cache_key": str, "voice_id": str, "pool_label": str, "seed": int,
         "duration_s": float, "artifact_id": str | None}
        {"kind": "segment", "source_id": <UUID of the source-media/clip node>,
         "cache_key": str, "start_s": float, "end_s": float, "artifact_id": str | None}

    Returns ``{"config": UUID, "members": [UUID,…], "episode": UUID}``.
    """
    register_tiers(store)  # idempotent
    cfg = _node(store, "weave-configs", WEAVE_CONFIG_V1, {"config": weave_config})
    members: list[UUID] = []
    for b in beats:
        src = b["source_id"]
        if b["kind"] == "narration":
            va = _node(
                store, "voice-assignments", VOICE_ASSIGNMENT_V1,
                {"voice_id": b.get("voice_id", ""), "pool_label": b.get("pool_label", "single"),
                 "seed": int(b.get("seed", 0))},
                derived_from=[src, cfg],  # depends on the beat AND the config (pool/seed)
            )
            nid = _node(
                store, "narration-renders", NARRATION_RENDER_V1,
                {"cache_key": b["cache_key"], "artifact_id": b.get("artifact_id"),
                 "duration_s": float(b.get("duration_s", 0.0))},
                derived_from=[src, va, cfg],
            )
            members.append(nid)
        else:  # segment
            sid = _node(
                store, "segment-extractions", SEGMENT_EXTRACTION_V1,
                {"cache_key": b["cache_key"], "start_s": float(b.get("start_s", 0.0)),
                 "end_s": float(b.get("end_s", 1.0)), "artifact_id": b.get("artifact_id")},
                derived_from=[src, cfg],
            )
            members.append(sid)
    episode = _node(
        store, "episode-renders", EPISODE_RENDER_V1,
        {"profile": profile, "ordered_member_ids": tuple(str(m) for m in members),
         "artifact_id": None, "duration_s": 0.0},
        derived_from=[*members, cfg],
    )
    return {"config": cfg, "members": members, "episode": episode}


def descendants_of(store, changed_id: UUID) -> set[UUID]:
    """Every annotation transitively derived from ``changed_id`` (via
    ``provenance.was_derived_from``). Excludes ``changed_id`` itself."""
    children: dict[UUID, list[UUID]] = {}
    for a in store.all():
        for parent in a.provenance.was_derived_from:
            children.setdefault(parent, []).append(a.id)
    out: set[UUID] = set()
    stack = [changed_id]
    while stack:
        cur = stack.pop()
        for child in children.get(cur, []):
            if child not in out:
                out.add(child)
                stack.append(child)
    return out


# The partial-re-render frontier of a change (mirrors nw.stale_after semantics).
stale_after = descendants_of
