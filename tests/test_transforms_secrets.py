"""The graph path threads a caller's ElevenLabs key to synthesis — and nowhere else.

thorwhalen/braidio#58: ``weave_project(api_key=)`` reaches ``narrate`` /
``render_dialogue`` with that key through nw's ``execute(secrets=)`` seam;
without one both are called with ``api_key=None`` (the documented
environment fallback). The key is never persisted: these tests grep every
file the project wrote for a sentinel. Synthesis is monkeypatched — no
ElevenLabs, no ffmpeg, no spend.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import braidio

pytestmark = pytest.mark.skipif(
    not braidio.HAS_NW, reason="nw (and lacing) not available"
)

SENTINEL = "sk-SENTINEL-7b2e0a4c-must-never-persist"
TURNS = (("A", "The thing that gets me is the bass."), ("B", "Say more?"))


def _write(out_path, tag: bytes) -> Path:
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(tag)
    return p


@pytest.fixture
def boundary(monkeypatch):
    """Stub every audio boundary; record the ``api_key`` each synthesis got."""
    rec = {"narrate": [], "dialogue": []}

    def _narrate(text, out, *, api_key=None, return_cache_status=False, **kw):
        rec["narrate"].append(api_key)
        p = _write(out, b"TTS")
        return (p, False) if return_cache_status else p

    def _render_dialogue(
        turns, cast, *, api_key=None, out_path, return_cache_status=False, **kw
    ):
        rec["dialogue"].append(api_key)
        p = _write(out_path, b"DIALOGUE")
        return (p, False) if return_cache_status else p

    monkeypatch.setattr(braidio, "narrate", _narrate)
    monkeypatch.setattr(braidio, "render_dialogue", _render_dialogue)
    monkeypatch.setattr(
        braidio, "weave_timeline", lambda items, out, **kw: _write(out, b"EPISODE")
    )
    monkeypatch.setattr(braidio, "duration_s", lambda path: 2.0)
    return rec


@pytest.fixture
def project(tmp_path):
    return braidio.Project.init(tmp_path / "proj", title="secrets weave")


def _script():
    return braidio.Script(
        title="Keys",
        id_slug="keys",
        beats=[
            braidio.Narration(text="Opening line."),
            braidio.Dialogue(TURNS, label="the bass"),
        ],
    )


def _grep_tree(root: Path) -> list[str]:
    needle = SENTINEL.encode()
    return [
        str(p.relative_to(root))
        for p in root.rglob("*")
        if p.is_file() and needle in p.read_bytes()
    ]


def test_weave_project_threads_the_caller_key_to_both_synthesis_boundaries(
    project, boundary, tmp_path
):
    episode = braidio.weave_project(project, _script(), api_key=SENTINEL)

    assert boundary["narrate"] == [SENTINEL]
    assert boundary["dialogue"] == [SENTINEL]
    assert episode.body["url"]
    # Never persisted: not a node body, not provenance, not a cache key, not
    # the episode — nothing under the project root carries it.
    assert _grep_tree(tmp_path) == []


def test_weave_project_without_a_key_falls_back_to_the_environment(project, boundary):
    braidio.weave_project(project, _script())
    assert boundary["narrate"] == [None]
    assert boundary["dialogue"] == [None]


def test_the_key_is_not_an_input_so_it_changes_no_cache_key(project, boundary):
    """The same script under a different key is the same render: a cache hit,
    not a re-bill — the seam must not make a key part of the render identity."""
    import nw

    from braidio.transforms._common import TIER_DIALOGUE_RENDER, TIER_NARRATION_RENDER

    braidio.weave_project(project, _script(), api_key=SENTINEL)
    braidio.weave_project(project, _script(), api_key="sk-another-key")

    assert boundary["narrate"] == [SENTINEL]  # second run: cache hit, no call
    assert boundary["dialogue"] == [SENTINEL]
    for tier in (TIER_NARRATION_RENDER, TIER_DIALOGUE_RENDER):
        keys = {a.body["cache_key"] for a in nw.annotations_at_tier(project.root, tier)}
        assert len(keys) == 1


def test_the_free_transforms_are_never_offered_a_secret(project, boundary):
    """Only the two paid transforms declare ``secrets``; the driver must not
    hand it to the others (a TypeError here would be that mistake)."""
    from braidio.transforms import _episode, _segment, _voice
    import inspect

    for mod in (_voice, _segment, _episode):
        cls = next(
            v
            for v in vars(mod).values()
            if inspect.isclass(v) and getattr(v, "name", "") == mod.NAME
        )
        assert "secrets" not in inspect.signature(cls.execute).parameters
    braidio.weave_project(project, _script(), api_key=SENTINEL)  # does not raise
