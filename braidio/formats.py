"""Ready-made **format templates** — high-quality presets under standard names.

braidio parametrizes *any* commentary style (a :class:`~braidio.script.Script` of
``Narration`` / ``Dialogue`` / ``SegmentBeat`` beats, cast via
:class:`~braidio.conversation.ConversationCast`, tuned by
:class:`~braidio.weave_config.WeaveConfig` and :class:`~braidio.delivery.Delivery`).
This module ships the *ready-made* end of that: a small set of named
:class:`Format` presets that bundle good defaults for the recurring, industry-named
ways people comment on an artifact — so ``render_format(DEEP_DIVE, script, …)``
just works, and advanced users still compose the primitives directly.

The taxonomy + recipes are in
``misc/docs/research/commentary-formats-and-styles.md``. The organizing rule:
**the talk is the spine; narration bridges and source clips are optional
"illustration" layers** attached to it.

What a :class:`Format` actually drives at render time **today**: the dialogue
**cast** (role→voice), the **narration voice + delivery**, the **clip
weave/duck + loudness** (:class:`WeaveConfig`). Per-clip placement renders too —
set it on each ``SegmentBeat(placement=…)``; ``Format.clip_placement`` is the
recommended *default* for the format. A **music bed** renders when you pass a
``bed_asset`` to :func:`render_format` — the format's ``music_bed`` *intensity*
picks the gain. Fields tagged *(authoring)* — ``roles``, ``scripting`` — are
conventions for whoever writes (or generates) the ``Script``; scene stings remain
**roadmap** on the render side (braidio#1). Preset ids mirror the standard names
so a UI can label them ("Deep Dive", "Song Exploder-style").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from braidio.conversation import CHRIS, JESSICA, LAURA, WILL, ConversationCast
from braidio.delivery import Delivery, V2_NARRATOR, V2_PRESENTER
from braidio.rights import Profile
from braidio.tts import DEFAULT_VOICE_ID
from braidio.weave_config import WeaveConfig

# --- extra role voices (from the curated premade pools, distinct timbres) -----
GEORGE = DEFAULT_VOICE_ID            # warm, captivating storyteller (M) — narrator
MATILDA = "XrExE9yKIg1WjnnlVkGX"     # professional (F) — neutral moderator
SARAH = "EXAVITQu4vr4xnSDxMaL"       # mature, reassuring (F)
CHARLIE = "IKne3meq5aSn9XLyUdCD"     # deep, energetic (M, Australian)
ERIC = "cjVigY5qzO86Huf0OWal"        # smooth, trustworthy (M)
BILL = "pqHfZKP75CvOlQylNhV4"        # wise, mature (M)


@dataclass(frozen=True)
class Format:
    """A named commentary-format preset: a bundle of high-quality defaults.

    Rendered fields drive :func:`render_format` → :func:`braidio.render.render_production`.
    Authoring fields document how to write a ``Script`` for this format (and, for
    ``clip_placement`` / ``music_bed``, flag render features still on the roadmap).
    """

    id: str  # preset id (mirrors the standard name), e.g. "deep_dive"
    name: str  # standard / industry name for UI labels, e.g. 'Two-Host Conversation ("Deep Dive")'
    summary: str
    aka: tuple[str, ...] = ()  # alternate names / exemplar shows

    # --- rendered defaults --------------------------------------------------
    cast: ConversationCast | None = None  # Dialogue roles→voices; None = no dialogue spine
    narration_voice: str | None = None  # default voice for Narration beats
    narration_delivery: Delivery = V2_PRESENTER  # delivery for Narration beats
    weave: WeaveConfig = field(default_factory=WeaveConfig)

    # --- authoring guidance (documented; render support varies) -------------
    roles: Mapping[str, str] = field(default_factory=dict)  # role → semantic (narrator/host/guest/…)
    clip_placement: str = "before"  # recommended default SegmentBeat.placement (renders; before|under|after)
    music_bed: str = "light"  # continuous | light | sparse | none (authoring / roadmap)
    scripting: str = ""  # how to author a Script for this format (authoring)

    def render(
        self,
        script,
        *,
        source,
        out_path: str | Path | None = None,
        profile: Profile = Profile.PERSONAL,
        **overrides,
    ) -> Path:
        """Render ``script`` with this format's defaults (see :func:`render_format`)."""
        return render_format(
            self, script, source=source, out_path=out_path, profile=profile, **overrides
        )


def render_format(
    fmt: Format,
    script,
    *,
    source,
    out_path: str | Path | None = None,
    profile: Profile = Profile.PERSONAL,
    bed_asset: str | None = None,
    **overrides,
) -> Path:
    """Render ``script`` under ``fmt``'s defaults; ``overrides`` win over them.

    Wires the format's ``cast`` / ``narration_voice`` / ``narration_delivery`` /
    ``weave`` into :func:`braidio.render.render_production`. Any beat may still
    override voice/settings per-beat (e.g. a graver book-narrator inside an
    otherwise lively presenter piece — pass ``V2_NARRATOR.voice_settings`` on that
    ``Narration`` beat).

    ``bed_asset`` (a path to an app-supplied instrumental) adds a music bed at the
    gain implied by ``fmt.music_bed`` (skipped when the format's intensity is
    ``"none"``); pass ``music_bed=MusicBed(...)`` in ``overrides`` for full control.
    """
    from braidio.music import bed_for_intensity
    from braidio.render import render_production

    kwargs = dict(
        source=source,
        config=fmt.weave,
        profile=profile,
        delivery=fmt.narration_delivery,
        out_path=out_path,
    )
    if fmt.cast is not None:
        kwargs["cast"] = fmt.cast
    if fmt.narration_voice is not None:
        kwargs["voice_id"] = fmt.narration_voice
    if bed_asset is not None:
        bed = bed_for_intensity(bed_asset, fmt.music_bed)
        if bed is not None:
            kwargs["music_bed"] = bed
    kwargs.update(overrides)
    return render_production(script, **kwargs)


# =============================================================================
# Presets — the ready-made, standard-named format templates.
# =============================================================================

SOLO_EXPLAINER = Format(
    id="solo_explainer",
    name="Solo-Presenter Explainer",
    aka=("video essay", "audio-essay", "close reading", "Dissect", "audio guide"),
    summary="One presenter advances a thesis over exhibits; narration is the spine.",
    cast=None,  # no dialogue — a single voice throughout
    narration_voice=GEORGE,
    narration_delivery=V2_PRESENTER,
    weave=WeaveConfig(voices=(GEORGE,), pool_label="single", min_turn=1, max_turn=3),
    roles={"presenter": "narrator=host=expert, collapsed into one authoritative voice"},
    clip_placement="before",  # set up every exhibit before it plays
    music_bed="continuous",
    scripting=(
        "Intro (hook + thesis) → body as repeated (claim → clip → analysis) → "
        "conclusion. Per-exhibit micro-shape: hook → describe → meaning → memorable "
        "detail → prompt (~60–90s). Scripted, dense; every exhibit is set up first. "
        "Serialize by emitting one Script per sub-topic with an end-of-episode hook."
    ),
)

DEEP_DIVE = Format(
    id="deep_dive",
    name='Two-Host Conversation ("Deep Dive")',
    aka=("co-hosted chat", "two-host teaching dialogue", "Switched on Pop", "NotebookLM Deep Dive"),
    summary="Two complementary hosts talk it through; one teaches, one probes.",
    cast=ConversationCast(roles={"host_a": JESSICA, "host_b": CHRIS}, settings={"stability": 0.45}),
    narration_voice=GEORGE,  # for optional bridges between segments
    narration_delivery=V2_NARRATOR,
    weave=WeaveConfig(),
    roles={"host_a": "explainer / driver", "host_b": "prober / curious surrogate"},
    clip_placement="after",  # hosts cue, then play/react (the cue is the bridge)
    music_bed="light",
    scripting=(
        "Cold banter → frame the artifact → segment-by-segment walkthrough where one "
        "host teaches the other (roles may trade) → recap → sign-off. Prove each claim "
        "with a clip or a described demonstration. For the DEBATE sub-preset, give the "
        "two hosts opposing stances (raise disagreement) for tension without a third voice."
    ),
)

INTERVIEW = Format(
    id="interview",
    name="Interview (Host + Guest)",
    aka=("host + subject", "Q&A"),
    summary="Host questions a guest to elicit their first-person account.",
    cast=ConversationCast(roles={"host": JESSICA, "guest": CHRIS}, settings={"stability": 0.45}),
    narration_voice=GEORGE,  # optional chapter bridges only
    narration_delivery=V2_NARRATOR,
    weave=WeaveConfig(),
    roles={"host": "curious interviewer", "guest": "first-person authority (the center)"},
    clip_placement="before",
    music_bed="light",
    scripting=(
        "Host question → guest answer (Q-then-A). Host or guest sets up each exhibit "
        "before it plays. Narration bridges only between chapters. See SONG_EXPLODER "
        "for the host-removed variant."
    ),
)

# Song Exploder architecture — the sharpest "illustration" model.
SONG_EXPLODER = Format(
    id="interview_host_removed",
    name="Song Exploder-style (host-removed interview)",
    aka=("Song Exploder", "deconstruction", "stems"),
    summary="Guest narrates in first person; every claim illustrated by its isolated stem; full artifact at the tail.",
    cast=None,  # host removed → continuous guest monologue (Narration voiced by the guest)
    narration_voice=CHRIS,  # the maker, first person
    narration_delivery=V2_PRESENTER,
    weave=WeaveConfig(),
    roles={"guest": "the maker, sole voice; host is the invisible editor/curator"},
    clip_placement="before",  # name the element, then play the isolated stem
    music_bed="none",  # the artifact's own segments ARE the score
    scripting=(
        "Interview the maker, strip the host's questions → guest narrates first-person "
        "→ drop the exact isolated stem as each element is named → close with the "
        "complete, un-narrated artifact (the payoff). ~15–20 min."
    ),
)

PANEL = Format(
    id="panel",
    name="Panel / Roundtable",
    aka=("roundtable", "Pop Culture Happy Hour"),
    summary="A moderator routes a group of distinct voices around a shared topic.",
    cast=ConversationCast(
        roles={"moderator": MATILDA, "panelist_1": CHARLIE, "panelist_2": SARAH, "panelist_3": ERIC},
        settings={"stability": 0.45},
    ),
    narration_voice=GEORGE,
    narration_delivery=V2_NARRATOR,
    weave=WeaveConfig(),
    roles={
        "moderator": "neutral routing voice (spine + traffic control)",
        "panelist_1": "distinct viewpoint", "panelist_2": "distinct viewpoint",
        "panelist_3": "distinct viewpoint",
    },
    clip_placement="before",
    music_bed="light",  # segment stings mark each round (signposting is critical with many voices)
    scripting=(
        "Moderator frames topic → round-robin takes ('a trip around the table') → clip "
        "drops as shared reference → moderator synthesizes → next topic → close on a "
        "recurring ritual. Keep voices maximally distinct (accent/gender) for legibility."
    ),
)

DEBATE = Format(
    id="debate",
    name="Debate (Oxford-style)",
    aka=("two opposing takes + moderator",),
    summary="Two advocates argue a stated motion; a neutral moderator enforces phases.",
    cast=ConversationCast(
        roles={"moderator": BILL, "proposition": JESSICA, "opposition": CHRIS},
        settings={"stability": 0.45},
    ),
    narration_voice=BILL,  # structural announcements, voiced by the moderator
    narration_delivery=V2_NARRATOR,
    weave=WeaveConfig(),
    roles={
        "moderator": "neutral; frames + routes, never argues",
        "proposition": "advocate A", "opposition": "advocate B",
    },
    clip_placement="before",  # evidence entered by a side, then argued (clips may be re-used across sides)
    music_bed="sparse",  # phase stings (open / rebuttal / close) keep structure legible
    scripting=(
        "State the motion up front → phased turns: opening remarks → moderated "
        "exchange/rebuttals → cross-examination → closing arguments. The same clip may "
        "be entered and re-interpreted by both sides. Oxford variant: announce a "
        "before/after opinion frame."
    ),
)

DOCUMENTARY_VO = Format(
    id="documentary_vo",
    name='Documentary Voice-Over (expository "Voice of God")',
    aka=("expository documentary", "This American Life", "99% Invisible"),
    summary="An authoritative narrator drives; interviews, clips and actuality illustrate beneath.",
    cast=ConversationCast(roles={"guest": CHRIS, "expert": LAURA}, settings={"stability": 0.45}),
    narration_voice=GEORGE,  # omniscient narrator — the top, driest layer
    narration_delivery=V2_NARRATOR,
    weave=WeaveConfig(min_turn=1, max_turn=3),
    roles={
        "narrator": "omniscient, authoritative — the spine, top layer",
        "guest": "first-person testimony", "expert": "borrowed-credibility interpretation",
    },
    clip_placement="before",  # narration states → clip/interview demonstrates → narration bridges
    music_bed="continuous",  # scored; announce scoring early; stings/swells mark scenes
    scripting=(
        "Ira-Glass engine: anecdote → anecdote → a beat of reflection; run on a theme "
        "in numbered 'acts' with a prologue stating the theme; land a 'turn'. Layer "
        "bottom→top: ambience → bed (ducked) → clips/actuality → testimony → narration "
        "on top. Optional cold open (best tape pulled forward). Narration is always the "
        "top layer; everything below illustrates."
    ),
)


FORMATS: dict[str, Format] = {
    f.id: f
    for f in (
        SOLO_EXPLAINER, DEEP_DIVE, INTERVIEW, SONG_EXPLODER, PANEL, DEBATE, DOCUMENTARY_VO,
    )
}
