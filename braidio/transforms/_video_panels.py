"""``video_panels.plan`` — an episode + its stills → the panel track.

A **free, batch** Transform (commentary-studio plan §5): one ``episode-render``
plus the project's ``still`` nodes in, one ``video-panel/v1`` annotation per
span out. Spans come from :func:`braidio.video.plan_spans` over the episode's
**persisted** timeline (reconstructed for rows that predate it, see
:func:`braidio.transforms.episode_timeline`), so the cuts land where the
narration changes subject and survive a reopen. Each panel is pinned to its
span through a :class:`lacing.MediaRef` on the episode's audio, which is what
makes "which panel covers *t*?" an interval query rather than a scan.

Assignment takes an explicit **pick map** — ``params["picks"]``, ``{beat_id:
[still_key, ...]}``, the shape the finished productions already used — and
falls back to cycling the pool without a back-to-back repeat (the
:func:`braidio.video.assign_stills` rule) for any beat it does not name. A key
the pool does not hold raises at plan time: a silent fallback would ship a
picture nobody chose.

**The seed is minted from the beat, not the ordinal.** ``mint_seed(beat_id,
k)`` hashes the beat's id and the panel's index *within that beat*, so a
panel's camera move survives a reorder, a re-weave and a still swap — "keep
this move, change this picture" is the first thing the owner asked for, and
``i % 4`` could not express it.

**A panel derives from the episode, not from its still.** ``still_id`` is an
authored pointer — the same shape as ``audio-clip.source_node_id`` — and the
panel's *value* never reads the still, so a provenance edge to it would make
every label edit on a still stale the panel (and, through it, every cut)
with nothing to re-derive. The **cuts** derive from the stills: a still's
label edit stales the cuts, and the motion pass answers from its cache while
the text pass re-runs — which is the split earning itself. Swapping the
picture is a patch to ``still_id`` (the panel's own digest moves); replacing
the bytes is a new still with a new artifact id, then that patch.

**One track per episode.** ``execute`` returns the panels already derived
from this episode when there are any (the planner is idempotent per episode —
panels are what the user edits *after* planning, and a re-plan must not
double the track or overwrite an edit); ``force=True`` writes a fresh track
beside the old one. After a re-weave the new episode has no track yet, so the
planner plans anew; carry choices forward with :func:`picks_from_panels`.
"""

from __future__ import annotations

import hashlib
import uuid

from falaw import Plan
from lacing import Annotation, MediaRef, RationalTime, TimeInterval
from nw import BaseTransform, TransformInputs, TransformResult, register_transform
from nw.transforms._provenance import derive_provenance

from braidio.bodies._render_nodes import EPISODE_RENDER_V1
from braidio.bodies._video import (
    DEFAULT_MOVE,
    DEFAULT_ZOOM,
    STILL_V1,
    VIDEO_PANEL_V1,
    VideoPanelBodyV1,
)
from braidio.transforms._common import (
    TIER_EPISODE_RENDER,
    TIER_STILL,
    TIER_VIDEO_PANEL,
    graph_index,
    resolve_parents,
)
from braidio.transforms._episode import episode_timeline
from braidio.video import MAX_PANEL_S, MIN_PANEL_S, plan_spans

NAME = "video_panels.plan"

#: Rate of the panel intervals on the episode audio (milliseconds).
_RATE = 1000
#: Seeds are 31-bit so they survive every JSON reader and burns' int index.
_SEED_BITS = 31


def span_interval(start_s: float, end_s: float) -> TimeInterval:
    """A span's interval on the episode audio, quantized to whole milliseconds.

    lacing's time is rational and refuses a lossy float; a span edge from
    ``plan_spans`` is a float (a beat divided in three lands on 22.88…), so it
    is rounded to the tick here, once, and consecutive spans stay gapless
    because they round the same shared edge the same way.

    >>> iv = span_interval(0.0, 22.8866)
    >>> (iv.start.value, iv.end.value, iv.end.rate)
    (0, 22887, 1000)
    """
    return TimeInterval(
        RationalTime(int(round(start_s * _RATE)), _RATE),
        RationalTime(int(round(end_s * _RATE)), _RATE),
    )


def mint_seed(beat_id: str | None, k: int) -> int:
    """A panel's motion seed: a stable hash of its beat and its index in it.

    >>> mint_seed("0003", 0) == mint_seed("0003", 0)
    True
    >>> mint_seed("0003", 0) != mint_seed("0003", 1)
    True
    """
    digest = hashlib.sha256(f"{beat_id or ''}/{k}".encode()).digest()
    return int.from_bytes(digest[:4], "big") & ((1 << _SEED_BITS) - 1)


def picks_from_panels(panels, index: dict) -> dict[str, list[str]]:
    """``{beat_id: [still_key, ...]}`` recovered from an existing track.

    The pick map to hand the planner after a re-weave, so the new track keeps
    the pictures the old one chose per beat.
    """
    picks: dict[str, list[str]] = {}
    for panel in sorted(panels, key=lambda p: int(p.body.get("order", 0))):
        beat_id = panel.body.get("beat_id")
        still = index.get(uuid.UUID(str(panel.body["still_id"])))
        if beat_id is None or still is None:
            continue
        picks.setdefault(str(beat_id), []).append(str(still.body["key"]))
    return picks


def panels_for_episode(project, episode_id) -> list[Annotation]:
    """The panel track derived from ``episode_id``, in ``order``."""
    import nw

    hits = [
        a
        for a in nw.annotations_at_tier(project.root, TIER_VIDEO_PANEL)
        if episode_id in a.provenance.was_derived_from
    ]
    return sorted(hits, key=lambda a: int(a.body.get("order", 0)))


def _beat_ids(episode: Annotation, index: dict) -> list[str | None]:
    """The ``beat_id`` behind each timeline beat, in member order."""
    out: list[str | None] = []
    for sid in episode.body.get("ordered_member_ids", ()):
        member = index.get(uuid.UUID(sid))
        if member is None:
            out.append(None)
            continue
        own = member.body.get("beat_id")
        if own is None:
            own = next(
                (
                    p.body.get("beat_id")
                    for p in resolve_parents(member, index)
                    if p.body.get("beat_id") is not None
                ),
                None,
            )
        out.append(None if own is None else str(own))
    return out


def _choose_stills(spans, beat_ids, stills, picks: dict) -> list[Annotation]:
    """One still per span: the pick map where it names the beat, else the pool."""
    by_key = {str(s.body["key"]): s for s in stills}
    unknown = sorted({k for keys in picks.values() for k in keys if k not in by_key})
    if unknown:
        raise ValueError(
            f"{NAME}: picks name still keys the project does not hold: "
            f"{unknown}. Known keys: {sorted(by_key)}"
        )
    chosen: list[Annotation] = []
    within_beat: dict[str | None, int] = {}
    pool_cursor = 0
    for span in spans:
        beat_id = beat_ids[span.beat_index] if span.beat_index < len(beat_ids) else None
        k = within_beat.get(beat_id, 0)
        within_beat[beat_id] = k + 1
        keys = picks.get(beat_id) if beat_id is not None else None
        if keys:
            chosen.append(by_key[keys[min(k, len(keys) - 1)]])
            continue
        still = stills[pool_cursor % len(stills)]
        # no back-to-back repeat when the pool allows it
        if chosen and still.id == chosen[-1].id and len(stills) > 1:
            pool_cursor += 1
            still = stills[pool_cursor % len(stills)]
        pool_cursor += 1
        chosen.append(still)
    return chosen


@register_transform(NAME)
class VideoPanelsPlan(BaseTransform):
    """``episode-render`` (+ the project's stills) → one ``video-panel/v1`` per span."""

    name = NAME
    input_kinds = (EPISODE_RENDER_V1, STILL_V1)
    output_kind = VIDEO_PANEL_V1
    is_batch = True

    def plan(
        self, project, inputs: TransformInputs, *, params=None
    ) -> tuple[Plan, tuple[Annotation, ...]]:
        import nw

        params = dict(params or {})
        episode = inputs.primary[0]
        if episode.tier != TIER_EPISODE_RENDER:
            raise ValueError(
                f"{NAME}: the first primary input must be an episode-render"
            )
        audio_id = episode.body.get("artifact_id")
        if not audio_id:
            raise ValueError(
                f"{NAME}: episode {episode.id} has no rendered audio yet — weave first"
            )
        stills = [a for a in inputs.primary[1:] if a.tier == TIER_STILL] or list(
            nw.annotations_at_tier(project.root, TIER_STILL)
        )
        if not stills:
            raise ValueError(f"{NAME}: the project holds no stills to plan panels from")
        stills = sorted(stills, key=lambda s: str(s.body.get("key", "")))

        index = graph_index(project)
        timeline = episode_timeline(project, episode)
        spans = plan_spans(
            timeline,
            min_panel_s=float(params.get("min_panel_s", MIN_PANEL_S)),
            max_panel_s=float(params.get("max_panel_s", MAX_PANEL_S)),
        )
        beat_ids = _beat_ids(episode, index)
        chosen = _choose_stills(
            spans, beat_ids, stills, dict(params.get("picks") or {})
        )
        move = str(params.get("move", DEFAULT_MOVE))
        zoom = float(params.get("zoom", DEFAULT_ZOOM))

        skeletons = []
        within_beat: dict[str | None, int] = {}
        for order, (span, still) in enumerate(zip(spans, chosen)):
            beat_id = (
                beat_ids[span.beat_index] if span.beat_index < len(beat_ids) else None
            )
            k = within_beat.get(beat_id, 0)
            within_beat[beat_id] = k + 1
            full = TransformInputs(primary=(episode,))
            skeletons.append(
                Annotation(
                    id=uuid.uuid4(),
                    tier=TIER_VIDEO_PANEL,
                    reference=MediaRef(
                        asset_id=str(audio_id),
                        interval=span_interval(span.start, span.end),
                    ),
                    body=VideoPanelBodyV1(
                        still_id=str(still.id),
                        move=move,
                        zoom=zoom,
                        seed=mint_seed(beat_id, k),
                        beat_id=beat_id,
                        order=order,
                    ).model_dump(mode="json"),
                    body_schema_uri=VIDEO_PANEL_V1,
                    provenance=derive_provenance(
                        self, full, attributed_to="agent:braidio"
                    ),
                )
            )
        return Plan(calls=()), tuple(skeletons)

    def execute(
        self,
        project,
        plan: Plan,
        skeleton: tuple[Annotation, ...],
        *,
        use_cache: bool = True,
        force: bool = False,
    ) -> TransformResult:
        if not skeleton:
            return TransformResult(annotations=(), artifacts=(), cost_usd_actual=0.0)
        episode_id = skeleton[0].provenance.was_derived_from[0]
        if use_cache and not force:
            existing = panels_for_episode(project, episode_id)
            if existing:
                return TransformResult(
                    annotations=tuple(existing), artifacts=(), cost_usd_actual=0.0
                )
        for skel in skeleton:
            project.graph.add_annotation(skel)
        return TransformResult(
            annotations=tuple(skeleton), artifacts=(), cost_usd_actual=0.0
        )
