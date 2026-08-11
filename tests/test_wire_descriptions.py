"""Wire-description hygiene for braidio's MCP tools (thorwhalen/reelee#282 fix 1).

The whole docstring goes on the wire (``braidio.mcp.register_tools`` sends
``fn.__doc__``), and the wire description is what tool search indexes. The #282
incident measured that long, jargon-dense descriptions embed away from short
user queries — the two tools the assistant found were among the shortest on the
connector, the two it missed among the longest (``braidio_download_audio``, at
987 chars, was one of the misses). The regression guard: every registered
tool's wire description stays under a hard cap, so a docstring that grows a
schema-restating tail cannot silently re-dilute the index.
"""

from py2mcp.util import import_object

import braidio.mcp as bm

#: One-to-a-few indexable sentences. Not a style aspiration — the guard that
#: keeps descriptions retrieval-sized (reelee#282; evidence in the reelee ADR
#: ``docs/adr_connector_tool_surface.md`` §2.4).
MAX_WIRE_DESCRIPTION_CHARS = 500


def _wire_description(name: str) -> str:
    fn = import_object(f"braidio.mcp.tools:{name}")
    return (fn.__doc__ or "").strip()


def test_every_wire_description_is_present_and_indexably_short():
    for name in bm.TOOL_NAMES:
        desc = _wire_description(name)
        assert desc, f"{name} has no docstring — that IS its wire description"
        assert len(desc) <= MAX_WIRE_DESCRIPTION_CHARS, (
            f"{name}'s wire description is {len(desc)} chars "
            f"(cap {MAX_WIRE_DESCRIPTION_CHARS}). Long descriptions embed away "
            "from short user queries (reelee#282); move detail into `help` / "
            "docs, keep the wire to purpose + key constraint."
        )


def test_download_audio_speaks_user_vocabulary():
    """The #282 miss, pinned: a user 'putting a song in a project' must be able
    to find this tool by the words they would actually type."""
    desc = _wire_description("download_audio").lower()
    for word in ("audio", "song", "link", "youtube"):
        assert word in desc, f"download_audio's wire description lost {word!r}"
    assert "right" in desc  # the copyright constraint stays on the wire
