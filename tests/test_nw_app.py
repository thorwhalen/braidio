"""Tests for the nw-app layer: body schemas + render provenance + partial
re-render. Skipped entirely if lacing isn't installed (the core stays usable)."""

from __future__ import annotations

from uuid import uuid4

import pytest

import braidio

pytestmark = pytest.mark.skipif(not braidio.HAS_GRAPH, reason="lacing not available")


def test_domain_and_render_schemas_registered():
    from lacing.schema import is_registered
    from braidio.bodies import SCHEMA_URIS

    assert len(SCHEMA_URIS) == 11  # 5 domain + 6 render
    for uri in SCHEMA_URIS:
        assert is_registered(uri), uri


def test_domain_bodies_validate():
    from lacing.schema import validate
    from braidio.bodies import COMMENTARY_V1, AUDIO_CLIP_V1, EPISODE_RENDER_V1

    validate({"text": "hi", "facet": "historical", "source_ids": (), "generated_by": "human:t"}, COMMENTARY_V1)
    validate({"source_node_id": "x", "label": "l", "rights": "owned-local"}, AUDIO_CLIP_V1)
    validate({"profile": "personal", "ordered_member_ids": ("a",)}, EPISODE_RENDER_V1)


def test_record_render_writes_provenance_graph():
    from lacing import MemoryStore

    store = MemoryStore()
    b1, b2 = uuid4(), uuid4()
    ids = braidio.record_render(
        store,
        weave_config={"voices": ["x"], "min_turn": 2},
        beats=[
            {"kind": "narration", "source_id": b1, "cache_key": "k1", "duration_s": 3.0},
            {"kind": "segment", "source_id": b2, "cache_key": "k2", "start_s": 1.0, "end_s": 4.0},
        ],
        profile="personal",
    )
    # config + voice-assignment + narration-render + segment-extraction + episode-render
    assert sum(1 for _ in store.all()) == 5
    assert len(ids["members"]) == 2


def test_partial_rerender_scope():
    from lacing import MemoryStore

    store = MemoryStore()
    b1, b2 = uuid4(), uuid4()
    ids = braidio.record_render(
        store,
        weave_config={"seed": 7},
        beats=[
            {"kind": "narration", "source_id": b1, "cache_key": "k1"},
            {"kind": "segment", "source_id": b2, "cache_key": "k2"},
        ],
    )
    # changing narration beat b1 → its voice-assignment + narration-render + episode
    stale_b1 = braidio.stale_after(store, b1)
    assert ids["episode"] in stale_b1
    assert ids["members"][1] not in stale_b1  # the unrelated segment stays fresh
    # changing the segment source b2 → its extraction + episode, NOT the narration
    stale_b2 = braidio.stale_after(store, b2)
    assert ids["members"][1] in stale_b2 and ids["members"][0] not in stale_b2
    # changing the config → everything derived from it (narration, segment, voice, episode)
    stale_cfg = braidio.stale_after(store, ids["config"])
    assert ids["members"][0] in stale_cfg and ids["members"][1] in stale_cfg
    assert ids["episode"] in stale_cfg


def test_import_braidio_core_does_not_require_graph():
    # HAS_GRAPH may be True here, but the core API must be importable regardless.
    for name in ("Script", "WeaveConfig", "render_production", "weave_timeline"):
        assert hasattr(braidio, name)
