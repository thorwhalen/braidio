# Commentary Formats and Styles: A Synthesis for braidio

*A synthesis of three research reports — a **format taxonomy**, a **production-weaving grammar**, and a field guide to **audio exemplars** — into one implementation-ready reference. It ends with **proposed braidio format templates**: each a concrete, developer-ready recipe expressed in braidio's own model (beat kinds, roles, `ConversationCast`, and `WeaveConfig` presets).*

---

## Executive summary

When someone talks *about* an artifact — a song, album, film, book, artwork, or historical event — the result almost always falls into one of a small number of recurring, named formats. These formats differ along two axes: **how many voices speak and in what relation** (solo → paired → group → produced/scripted), and **what epistemic stance** they take toward the artifact (explain, judge, inquire, experience, dramatize/document).

Three findings drive braidio's design:

1. **The talk is the spine; everything else illustrates it.** Across documentary theory and podcast craft, the durable rule is that *people talking* carries the argument, and narration, source clips, music, and SFX are illustration events *attached* to points on the talk track [7][W-6][W-7]. braidio already encodes this: a `Script` of `Narration` / `Dialogue` / `SegmentBeat` beats is the spine, and `WeaveConfig` governs how illustrations attach.

2. **A handful of "gold-standard" recipes recur.** *Song Exploder* (deconstruction), *Switched on Pop* (two-host teaching dialogue), *Dissect* (serialized solo close-reading), *This American Life* (documentary-narrative), *Pop Culture Happy Hour* (panel), and *NotebookLM Deep Dive* (two-AI-host) are repeatedly cited as templates worth copying [E-1][E-4][E-7][E-17][E-13][E-9].

3. **Every format is expressible as a 4-tuple in braidio.** A format template = (which **beat kinds + roles**) × (a **cast/voice assignment**) × (a **`WeaveConfig` preset**) × (**structural/scripting conventions**). That 4-tuple is exactly what a developer needs to turn each format into a preset.

The proposed templates, by standard name: **Solo-Presenter Explainer** (video essay / audio-essay), **Two-Host Conversation / "Deep Dive"**, **Interview** (host + guest, incl. the *Song Exploder* "host-removed" variant), **Panel / Roundtable**, **Debate**, and **Documentary-VO** — with **Narration bridges** and **Source clips** available as optional *illustration layers* on any of them.

---

## Format taxonomy

Organized by voice-count. "Elements woven" lists which of {commentary/dialogue, narration/VO, source clips, music bed, SFX/actuality} the format characteristically braids.

| Standard name | Definition | Roles / voices | Elements woven | When to use |
|---|---|---|---|---|
| **Solo explainer / video essay** | One author advances a thesis over montaged clips and stills [T-1][T-2] | 1: author-VO (narrator = host = expert, collapsed) | narration (spine) + source clips + near-continuous music bed | Argument-driven online criticism of a single work |
| **Explainer (journalism)** | Boils a complex topic down for a general audience — the *how/why* [T-4][T-5] | 1: institutional/impersonal voice | narration + optional clips | Backgrounding an event/policy for readers lacking context |
| **Review / critique** | First-person evaluation (review = consumer-facing; critique = expert analysis) [T-47][T-48] | 1: critic | narration + short exhibit clips | Point-of-release verdict, or lasting canon-forming analysis |
| **Reaction** | Real-time spontaneous impressions while experiencing the artifact [T-10][T-11] | 1 (or few): reactor | source clip *under/before* + reactive talk | First-listen/first-watch authenticity engagement |
| **Lecture / close reading** | Structured one-directional exposition; multiple passes over one text [T-30][T-32] | 1: expert | narration + quoted passages as clips | Teaching a single artifact deeply |
| **Documentary "Voice of God"** | Authoritative disembodied narrator states info; evidence illustrates [T-15][T-16] | 1: omniscient narrator | narration (top layer) + interviews + clips + actuality + music | Authoritative documentation of a work/person/event |
| **Co-hosted chat show** | Two recurring hosts discuss in casual free-flowing dialogue [T-43][T-44] | 2: co-hosts (chemistry) | dialogue (spine) + light theme/stings + clips | Ongoing culture commentary; personalities as draw |
| **"Deep dive" (2 AI hosts)** | Two synthetic hosts unpack an uploaded source in natural back-and-forth [T-7][T-9] | 2: AI voices (explainer + prober) | dialogue + summarized source | On-demand audio explainer from arbitrary source material |
| **Commentary track** | A synced second audio layer talked over the work in real time [T-12][T-13] | 1–2: creators | dialogue *under* full-length source | Home-video/reissue supplements; author annotating own work |
| **Host + guest interview** | Host questions an invited subject to elicit their account [T-17][T-18] | 2: interviewer + interviewee (center) | dialogue (Q&A) + clips + optional narration bridges | First-hand accounts, making-of, expert perspective |
| **Debate** | Two sides argue a stated motion, refereed by a moderator [T-45][T-46] | 3: proposition, opposition, moderator | dialogue (structured phases) + clips as evidence + phase stings | Contested evaluations/interpretations |
| **Panel / roundtable** | Moderated group; panel = distinct viewpoints, roundtable = equal free flow [T-33][T-35] | 3–8: moderator + experts | dialogue + shared-reference clips + segment stings | Aggregating multiple expert perspectives |
| **Socratic seminar** | Text-based group inquiry via open-ended questions, not debate [T-28][T-29] | facilitator + participants | dialogue (question-led) + shared text clips | Collective interpretation, no verdict |
| **Docent tour / gallery talk** | A guide leads a group through artifacts in situ, adapting [T-20][T-21] | 1 guide + group | narration + object references | Museum/heritage objects for a co-present audience |
| **Master class** | Expert coaches one proficient practitioner while others observe [T-39][T-40] | master + student(s) | dialogue + live demonstration clips | Technique-transfer on a performance/piece |
| **Oral history** | Recorded first-person testimony, interviewer + narrator, archived [T-17][T-19] | interviewer + narrator | dialogue (narrator-shaped) + archival | Documenting events through those who lived them |
| **Documentary (produced)** | Crafted nonfiction weaving narration, interviews, archival, actuality [T-15][T-16] | narrator + cast | all layers | Definitive long-form documentation |
| **Narrative / serial podcast** | Original nonfiction story across sequential episodes [T-24][T-25] | narrator-guide | narration + tape + sound design + music | Investigative/historical arcs with returning audience |
| **Audio drama / dramatization** | Purely acoustic dramatized re-enactment [T-41][T-42] | cast (actors) | dialogue-as-characters + music + SFX | Staging a work/event for the ear |
| **Liner notes / annotated edition** | Explanatory writing bound *with* the work [T-26][T-27] | 1 author / annotator | text (print) | Albums/reissues; study editions |
| **Listening party** | Synchronized collective play-through with real-time communal comment [T-37][T-38] | many participants (equal) | full source + distributed comments | Anniversary/celebration with a fanbase |

---

## How each format weaves its elements

The unifying model (from the weaving report): **treat the talk track as the timeline's primary axis; attach clips/narration/music/SFX as illustration events anchored to points on the talk, each with a placement relation and a ducking rule** [7][W-6].

**Roles, kept distinct** (this matters because braidio assigns a voice per role):
- **Narrator** — omniscient, scripted, never uncertain; owns transitions and thesis.
- **Host** — present-tense, reactive; drives the conversation and *cues* the clips.
- **Guest / subject** — first-person authority on their own experience.
- **Expert** — third-party authority who validates/interprets (borrowed credibility).
- **Moderator** — neutral traffic-control; frames and routes, does not argue.

**The three canonical clip placements** (rotate for rhythm) [W-9][W-1]:
1. **Set-up → clip** (talk *before* the exhibit). Default, clearest for comprehension. "Listen to how the bass enters here…" then the clip plays clean.
2. **Clip → payoff** (talk *after*). Play cold, then react. Used for the **cold open** and reveal/"gotcha" moments.
3. **Clip *under* talk** (bed placement). Source runs at reduced level while the host talks over it — real-time analysis; requires ducking.

**Narration framing** [W-5][W-6]: narration alternates with tape in call-and-response (narrator states → clip demonstrates → narrator bridges). Set-ups tee up, never spoil. The narrator owns transitions; **clips never chain directly without a talk bridge** — that is what separates a documentary from a mixtape.

**Ducking / bed conventions (the most parameterizable part)** [W-1][W-2][W-10]:
- Bed **10–15 dB below voice**, with gentle dips on names/numbers/quotes.
- Optional frequency-carve: cut music **250–2500 Hz by −3 to −6 dB** to clear the speech formant band.
- Fade-in **~1.5 s**; "**post**" the bed *after* speech onset so its entrance feels motivated.
- **Fade-out to spotlight**: cut music out immediately before the single most important line/clip.
- Beds must be **instrumental** (vocals compete with speech). **Announce scoring early** (first 30–60 s).

**Loudness / final-mix targets** [W-8]: integrated **−16 LUFS stereo / −19 mono**; true-peak **−1 dBTP**; dialogue compression **2:1–4:1**; beds **−26 to −31 LUFS** under speech; clean exhibit clips may swing up to spine level.

**Music as structure** [W-3][W-5]: because audio has no visual white space, music signals scene/chapter change — a **sting** for a section change, a **bed swell** for an act break, **theme at open and close** for closure.

**Universal documentary layering order** (bottom→top in the mix): ambience/room tone → music bed (ducked) → source clips/actuality → interview/testimony → **narration on top** (driest, most present). Everything below narration is "illustration."

---

## Audio exemplars & recipes

| Exemplar | Format archetype | Core trick | Recipe |
|---|---|---|---|
| **Song Exploder** ★ | Deconstruction / "stems" | Remove the interviewer; illustrate every claim with the isolated element it names; full artifact at the tail | Interview the maker → strip the host's questions → the guest narrates in first person → drop the exact isolated stem as each element is described → close with the complete, un-narrated song [E-1][E-2][E-3] |
| **Switched on Pop** ★ | Two-host teaching dialogue | One host teaches the song to the other (roles trade); prove each point with a clip or a live demonstration | Pair a theorist (musicologist) with a maker (producer) → heavily researched outline performed as spontaneous talk → clip-plus-demonstration keeps every claim audible [E-4][E-6] |
| **Dissect** ★ | Serialized solo audio-essay | Serialize + end-of-episode cliffhangers; Great-Courses rigor | One album/season, one song/episode → write (don't improvise) → braid biography with line/chord close-reading → hook at each episode end [E-7][E-8] |
| **This American Life / 99pi / Radiolab** ★ | Documentary-narrative | Anecdote → reflection, in numbered "acts"; sound does emotional work | State a theme → move through acts → alternate momentum-tape with a beat of reflection → score it → land a "turn" [E-17][E-18][E-15] |
| **Pop Culture Happy Hour** | Panel / roundtable | Rotating guest chair + fixed segments; disagreement drives interest | 3–4 informed voices + one topical guest → host runs segments ("trip around the table", ratings) → close on a recurring ritual [E-13][E-14] |
| **NotebookLM Deep Dive** | Two-AI-host | Automate the two-host chat; "Debate" preset stages disagreement | Two voices, one explains / one probes → summarize → connect → quote → optionally stage a Debate → keep it short. *Format template, not a craft quality bar* [E-9][E-11][E-12] |
| **Museum audio-guide track** | Companion / commentary | Tight per-stop micro-recipe; write for the ear | Hook → describe → meaning → one memorable detail → prompt to look/listen again; **60–90 s** per stop; put the payload word last [E-20][E-21] |
| **DVD director's commentary** | Companion (synchronous) | Synchrony — analysis and artifact experienced simultaneously | Maker(s) talk in real time *over* the full-length work, loosely keyed to what is playing now [E-19] |

The **single most transferable pattern** for automated artifact commentary is the **Song Exploder architecture**: a talk transcript as the spine, and the artifact's own segments as timestamped illustrations set up by the talk — then optional narration bridges, an instrumental bed (ducked), and scene-marking music [W-S-E].

---

## Proposed braidio format templates

**How to read these.** braidio's model: a production is a `Script` of ordered beats —
- `Narration(text, voice?, voice_settings?, lead_gap_s)` — a single voice reading (narrator OR solo presenter);
- `Dialogue(turns=[(role, text)])` — multi-speaker one-pass; a `ConversationCast` maps roles → voices;
- `SegmentBeat(reference)` — a resolved source clip.

`WeaveConfig` holds all editing knobs (turns, pacing, speaker overlap, clip pre/post-roll + ducking + fades, loudness). `ConversationCast` = role → voice + model/settings.

Each template below gives: a **standard NAME**, the **braidio expression** (beat kinds + roles; cast/voice plan; a `WeaveConfig` preset sketch; scripting conventions), and **defaults**. `WeaveConfig` field names are illustrative — map them to braidio's actual config surface.

> **Shared defaults** (unless a template overrides): loudness `−16 LUFS` / true-peak `−1 dBTP`; dialogue compression `2:1–4:1`; clip default placement `BEFORE` (set-up first); bed `−12 dB` under voice, fade-in `1500 ms`, posted after speech onset; music enters in first `30–60 s`; scene changes marked by a sting. Every clip is preceded by a spine cue; clips never chain without a talk bridge.

---

### 1. Solo-Presenter Explainer
*(a.k.a. video essay, audio-essay, solo close-reading; exemplars: Dissect, museum audio-guide)*

- **Beat kinds + roles:** `Narration` beats only, single role `presenter` (narrator = host = expert collapsed), interleaved with `SegmentBeat` exhibits. No `Dialogue`.
- **Cast / voice plan:** `ConversationCast{ presenter: <authoritative, warm voice> }`. One voice for the whole piece.
- **`WeaveConfig` preset — `solo_explainer`:**
  - `default_clip_placement = BEFORE` (comprehension-first); allow `AFTER` for a cold-open hook and punchlines.
  - `music_bed = continuous`, `duck_db = -12`, `freq_carve = [250, 2500, -4]`, `fade_out_before_key_exhibit = true` (spotlight).
  - `narration.lead_gap_s = 0.4`; `pacing = dense` (scripted, not improvised).
- **Scripting conventions:** intro (hook + thesis) → body as repeated (claim → clip → analysis) → conclusion. Per-exhibit micro-structure (audio-guide recipe): hook → describe → meaning → memorable detail → prompt; ~60–90 s per unit. Every exhibit is set up before it plays.
- **Defaults:** length open-ended; one album/topic per production; serialize by emitting one `Script` per sub-topic with an end-of-episode hook if used as a series.

---

### 2. Two-Host Conversation ("Deep Dive")
*(a.k.a. co-hosted chat show, two-host teaching dialogue; exemplars: Switched on Pop, NotebookLM Deep Dive)*

- **Beat kinds + roles:** `Dialogue` beats carry the spine; roles `host_a` (explainer/driver) and `host_b` (prober/curious surrogate). `SegmentBeat` exhibits and optional `Narration` bridges between segments.
- **Cast / voice plan:** `ConversationCast{ host_a: <expert/theorist voice>, host_b: <maker/practical voice> }` — deliberately complementary timbres. For the AI-generated variant, a male/female pair is the established default.
- **`WeaveConfig` preset — `deep_dive`:**
  - `turns = alternating`, `speaker_overlap = small` (natural back-and-forth, brief affirmations).
  - `default_clip_placement = AFTER` or `UNDER` (play then react / talk over) — hosts *cue* each clip, and the cue is the bridge.
  - `music_bed = light` (theme at top/tail, stings between segments, minimal underscore during talk to preserve the "live conversation" feel).
  - `pacing = conversational`.
- **Scripting conventions:** cold banter/greeting → framing of the artifact → segment-by-segment walkthrough where **one host teaches the other** (roles may trade) → recap/ratings → sign-off. Each claim proven with a clip or a described demonstration.
- **Defaults:** 8–30 min; two roles only; no separate narrator. **Debate sub-preset:** raise `disagreement` and give the two roles opposing stances (the NotebookLM "Debate" move) for tension without adding a third voice.

---

### 3. Interview (Host + Guest)
*(a.k.a. host + subject; two sub-modes — host-present, and host-removed / Song Exploder)*

- **Beat kinds + roles:** `Dialogue` with roles `host` (interviewer) and `guest` (subject, the center of attention). `SegmentBeat` exhibits; optional `Narration` bridges between chapters.
- **Cast / voice plan:** `ConversationCast{ host: <curious, receptive voice>, guest: <first-person authority voice> }`.
- **`WeaveConfig` preset — `interview`:**
  - `turns = Q_then_A` (host question → guest answer); `default_clip_placement = BEFORE` (host or guest sets up the exhibit).
  - `music_bed = light`; bridges may use a `Narration` beat between chapters only.
- **Sub-preset `interview_host_removed` (Song Exploder) — the sharpest "illustration" model:**
  - Drop the `host` role from the render: keep only `guest` turns, producing continuous first-person monologue (`Dialogue` with a single role, or a `Narration` beat voiced by the guest).
  - Every `SegmentBeat` is an **isolated stem/segment** of the artifact, `placement = BEFORE` (talk names the exhibit, then it plays), `full_level = true`.
  - Append a final full-length, un-narrated `SegmentBeat` of the complete artifact (the payoff).
  - `music_bed = none` — the artifact's own segments *are* the score.
- **Defaults:** ~15–20 min for the host-removed variant; guest is sole authority; host is invisible editor/curator.

---

### 4. Panel / Roundtable
*(exemplar: Pop Culture Happy Hour)*

- **Beat kinds + roles:** `Dialogue` with roles `moderator` + `panelist_1..N` (N ≈ 2–4 for panel, up to ~6 for roundtable). Shared `SegmentBeat` reference points; minimal `Narration`.
- **Cast / voice plan:** `ConversationCast{ moderator: <neutral routing voice>, panelist_1: …, panelist_2: …, panelist_3: … }` — each panelist a distinct, easily-told-apart voice (signposting is critical with many voices).
- **`WeaveConfig` preset — `panel`:**
  - `turns = round_robin` (moderator routes: "a trip around the table"); `speaker_overlap = small`.
  - `default_clip_placement = BEFORE` (moderator introduces a shared clip, then opens the floor).
  - `music_bed = light`; **segment stings mark each round/segment change** (voice-count makes signposting essential).
  - Optional stereo/positional separation per role to aid legibility.
- **Scripting conventions:** moderator frames topic → round-robin takes → clip drops as shared reference → moderator synthesizes → next topic → close on a recurring ritual.
- **Defaults:** moderator = spine + traffic control (substitutes for scripted VO); fixed segments scaffold otherwise free talk; rotating guest chair keeps it fresh.

---

### 5. Debate
*(Oxford-style; two opposing takes + moderator)*

- **Beat kinds + roles:** `Dialogue` with roles `proposition`, `opposition`, and `moderator` (neutral). `SegmentBeat` clips serve as **evidence** — the same clip may be entered and re-interpreted by both sides (deliberate re-use).
- **Cast / voice plan:** `ConversationCast{ moderator: <neutral>, proposition: <advocate A>, opposition: <advocate B> }`.
- **`WeaveConfig` preset — `debate`:**
  - `turns = phased`: opening remarks → moderated exchange/rebuttals → cross-examination → closing arguments.
  - `default_clip_placement = BEFORE` (evidence entered by a side, then argued); allow clip re-use across roles.
  - `music_bed = sparse`; **phase stings** (open / rebuttal / close) keep the structure legible; narration confined to structural announcements (voiced by `moderator`).
- **Scripting conventions:** clearly stated motion up front; moderator enforces phases and time; adversarial persuasive tone. Oxford variant: announce a "before/after" opinion frame.
- **Defaults:** three roles; moderator never argues; two advocates of borrowed-authority type.

---

### 6. Documentary-VO
*(expository "Voice of God"; exemplars: This American Life, 99% Invisible, Radiolab)*

- **Beat kinds + roles:** the richest weave — `Narration` (role `narrator`, top/driest layer) as the spine, plus `Dialogue` beats for interview/testimony (roles `guest`, `expert`), plus `SegmentBeat` exhibits and actuality. Full illustration stack.
- **Cast / voice plan:** `ConversationCast{ narrator: <omniscient, authoritative>, guest: <first-person>, expert: <borrowed-credibility> }`. Narrator is a single dominant voice.
- **`WeaveConfig` preset — `documentary_vo`:**
  - **Layering order (bottom→top):** ambience → music bed (ducked `−12 dB`) → source clips/actuality → interview/testimony → narration on top.
  - `default_clip_placement = BEFORE`; narration states → clip/interview demonstrates → narration bridges. Interviews cut into short "sound bites" the narration hands off to.
  - `music_bed = continuous, scored`; `announce_scoring_early = true`; `scene_change = bed_swell | sting`; `theme_at_open_and_close = true`.
  - `structure = three_act` (setup → confrontation → resolution) with an optional **cold open** (best 2–4 tape moments pulled forward, `placement = AFTER`).
- **Scripting conventions (Ira Glass engine):** anecdote → anecdote → a brief "moment of reflection"; episodes run on a theme in numbered "acts" with a prologue stating the theme; land a "turn."
- **Sub-preset `documentary_tape_driven`:** minimize `Narration`; ride on actuality/scenes; narration only bridges what the tape can't self-explain. Where actuality is unavailable, use the three-layer interview (plot / visual / meaning passes) so testimony carries the sensory load.
- **Defaults:** long-form; narration is always the top layer; everything below is illustration.

---

### Optional illustration layers (usable with ANY template above)

These are not standalone formats — they are layers braidio can attach to any preset:

- **Narration bridges.** Insert `Narration` beats (role `narrator`) between `Dialogue` segments or before an exhibit to state stakes and hand off. Turns a bare conversation into a guided piece. Placement: always `BEFORE` the thing it introduces; never let it spoil the exhibit.
- **Source clips.** `SegmentBeat` exhibits with a `placement` (BEFORE / UNDER / AFTER) and a `duck` rule. The artifact-facing illustration — the thing the commentary points at. Optional full-length, un-narrated clip at the tail (Song Exploder payoff) works with any template.
- **Music bed & scene stings.** Instrumental underscore (ducked per shared defaults) plus stings/swells to mark structure. Intensity is a per-template knob: `continuous` for solo/documentary, `light` for conversation/interview/panel, `sparse` for debate.

A developer builds a concrete production by picking a template preset, supplying a `ConversationCast`, and optionally toggling the illustration layers — the same `Script` + `WeaveConfig` machinery serves all of them.

---

## Naming

Use standard / industry names, and expose braidio preset ids that mirror them so users recognize what they are choosing:

| braidio preset id | Standard / industry name(s) | Notes |
|---|---|---|
| `solo_explainer` | Solo explainer, video essay, audio-essay, close reading | Dissect / museum-audio-guide lineage |
| `deep_dive` | Two-host conversation, co-hosted chat show, "Deep Dive" | NotebookLM standardized "Deep Dive"; `debate` sub-preset mirrors NotebookLM's "Debate" |
| `interview` / `interview_host_removed` | Host + guest interview; "Song Exploder" (host-removed) | Keep the *Song Exploder* name for the host-removed variant — it is the recognized term |
| `panel` | Panel discussion / roundtable | "trip around the table" segment convention |
| `debate` | Debate (Oxford-style) | Proposition / opposition / moderator |
| `documentary_vo` / `documentary_tape_driven` | Documentary voice-over, expository "Voice of God" | This American Life "acts" structure |

Prefer the established name in UI labels ("Deep Dive", "Song Exploder-style", "Panel"); keep the neutral preset id in code.

---

## REFERENCES

*Sources are grouped by originating report. `T-` = format taxonomy, `W-` = production-weaving grammar, `E-` = audio exemplars. Numbers preserve each report's own citation index.*

### Format taxonomy

[T-1] StudioBinder. *What is a Video Essay? The Art of the Video Analysis (with Examples).* [studiobinder.com](https://www.studiobinder.com/blog/what-is-a-video-essay-examples/)

[T-2] Pace University Library. *The Video Essay — Media Production and Film Studies.* [libguides.pace.edu](https://libguides.pace.edu/c.php?g=1347055&p=9950884)

[T-4] Democracy Journal. *Nine Questions about Explainer Journalism You Were Too Embarrassed to Ask.* [democracyjournal.org](https://democracyjournal.org/arguments/nine-questions-about-explainer-journalism-you-were-too-embarrassed-to-ask/)

[T-5] FIPP. *What is explainer journalism?* [fipp.com](https://www.fipp.com/news/what-is-explainer-journalism/)

[T-7] Google. *NotebookLM now lets you listen to a conversation about your sources.* [blog.google](https://blog.google/technology/ai/notebooklm-audio-overviews/)

[T-9] Willison S. *NotebookLM's automatically generated podcasts are surprisingly effective.* [simonwillison.net](https://simonwillison.net/2024/Sep/29/notebooklm-audio-overview/)

[T-10] Wikipedia. *Reaction video.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Reaction_video)

[T-11] Simplified. *What do you mean by Reaction Video on Social Media?* [simplified.com](https://simplified.com/social-media-glossary/reaction-video)

[T-12] Wikipedia. *Audio commentary.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Audio_commentary)

[T-13] Fanlore. *DVD Commentary.* [fanlore.org](https://fanlore.org/wiki/DVD_Commentary)

[T-15] MasterClass. *Film 101: Understanding Expository Documentary Mode.* [masterclass.com](https://www.masterclass.com/articles/understanding-expository-documentary-mode)

[T-16] Learoyd J. *Bill Nichols: Six Modes of Documentary.* [wordpress.com](https://jameslearoydsfilmstudiesblog.wordpress.com/2020/03/24/bill-nichols-six-modes-of-documentary/)

[T-17] Oral History Association. *Oral History: Defined.* [oralhistory.org](https://oralhistory.org/about/do-oral-history/)

[T-18] Library of Congress. *What is an oral history?* [ask.loc.gov](https://ask.loc.gov/veterans-history/faq/368984)

[T-19] Wikipedia. *Oral history.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Oral_history)

[T-20] Musa Guide. *Docents vs. Audio Guides: Complementary, Not Competing.* [musa.guide](https://www.musa.guide/en/resources/docents-vs-audio-guides)

[T-21] Edge Studio. *In an audio tour, are you a Docent, or a Tour Guide?* [edgestudio.com](https://edgestudio.com/in-an-audio-tour-are-you-a-docent-or-a-tour-guide/)

[T-24] Wikipedia. *Serial (podcast).* [en.wikipedia.org](https://en.wikipedia.org/wiki/Serial_(podcast))

[T-25] Story Ninety-Four. *Serial — Podcast Glossary.* [storyninetyfour.com](https://www.storyninetyfour.com/podcast-glossary/serial)

[T-26] Wikipedia. *Liner notes.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Liner_notes)

[T-27] Merriam-Webster. *Liner notes — Definition & Meaning.* [merriam-webster.com](https://www.merriam-webster.com/dictionary/liner%20notes)

[T-28] ReadWriteThink. *Socratic Seminars — Strategy Guide.* [readwritethink.org](https://www.readwritethink.org/professional-development/strategy-guides/socratic-seminars)

[T-29] TeachThought. *The Definition of a Socratic Seminar.* [teachthought.com](https://www.teachthought.com/critical-thinking-posts/definition-of-socratic-seminar/)

[T-30] Poetry Foundation. *New Criticism (Glossary).* [poetryfoundation.org](https://www.poetryfoundation.org/education/glossary/new-criticism)

[T-32] Fiveable. *Close reading — Literary Theory and Criticism.* [fiveable.me](https://fiveable.me/literary-theory-criticism/unit-1/close-reading/study-guide/tEhMOBTmoZCMzV9w)

[T-33] Wikipedia. *Panel discussion.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Panel_discussion)

[T-35] Contrast. *How to Run an Effective Virtual Roundtable Discussion.* [getcontrast.io](https://blog.getcontrast.io/roundtable-discussion/)

[T-37] Bennett A, et al. *Collective Nostalgia and Community in Tim's Twitter Listening Party during COVID-19.* Popular Music and Society. [tandfonline.com](https://www.tandfonline.com/doi/full/10.1080/19401159.2020.1852772)

[T-38] Southbank Centre. *Tim Burgess on listening parties and loving albums.* [southbankcentre.co.uk](https://www.southbankcentre.co.uk/magazine/tim-burgess-on-listening-parties-loving-albums/)

[T-39] Wikipedia. *Master class.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Master_class)

[T-40] Cambridge Dictionary. *Masterclass.* [dictionary.cambridge.org](https://dictionary.cambridge.org/dictionary/english/masterclass)

[T-41] Wikipedia. *Radio drama.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Radio_drama)

[T-42] Wikipedia. *Dramatization.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Dramatization)

[T-43] Pacific Content. *Double acts. Dynamic duos. Co-hosts.* [pacific-content.com](https://pacific-content.com/double-acts-dynamic-duos-co-hosts/)

[T-44] Castmagic. *Different Podcast Formats Explained: Find Your Fit.* [castmagic.io](https://www.castmagic.io/post/different-podcast-formats)

[T-45] Brainbound. *Oxford-Style Debate: The Ultimate Guide to Persuasion.* [brainbound.blog](https://brainbound.blog/oxford-style-debate-guide)

[T-46] United States Courts. *Oxford Style Debate.* [uscourts.gov](https://www.uscourts.gov/about-federal-courts/educational-resources/about-educational-outreach/activity-resources/oxford-style-debate)

[T-47] University of Vermont Libraries. *Reviews vs Criticism — Film & Television Studies.* [researchguides.uvm.edu](https://researchguides.uvm.edu/c.php?g=953842&p=6881794)

[T-48] Wikipedia. *Arts criticism.* [en.wikipedia.org](https://en.wikipedia.org/wiki/Arts_criticism)

### Production-weaving grammar

[7] / [W-6] C&I Studios. *Documentary Narration Styles: Voice-Over, Interview-Based, Participatory.* [c-istudios.com](https://c-istudios.com/exploring-different-documentary-narration-styles-voice-over-interview-based-and-participatory/)

[W-1] Lower Street / Riverside / Wikipedia (compiled). *Podcast structure, cold opens, pacing, ducking.* [lowerstreet.co](https://lowerstreet.co/how-to/structure-podcast) ; [en.wikipedia.org](https://en.wikipedia.org/wiki/Cold_open)

[W-2] The Podcast Host. *Adding Structure, Clarity & Timing Through Music.* [thepodcasthost.com](https://www.thepodcasthost.com/editing-production/adding-structure-clarity-timing-music-music-podcasting-2/)

[W-3] Rosenthal R, Transom. *Scoring Stories: Part 1.* [transom.org](https://transom.org/2019/scoring-stories-part-1/)

[W-4] NPR Training. *Score! Best practices for using music in audio storytelling.* [npr.org](https://www.npr.org/sections/npr-training/2025/05/31/g-s1-67187/score-best-practices-for-using-music-in-audio-storytelling)

[W-5] Transom / NPR Training. *Tips to Elevate Your Reporting and Storytelling.* [transom.org](https://transom.org/2024/tips-to-elevate-your-reporting-and-storytelling-from-ira-glass/)

[W-7] Liftoff Network / Videomaker. *Bill Nichols' Modes of Documentary.* [liftoff.network](https://liftoff.network/bill-nichols-6-modes-documentary/) ; [videomaker.com](https://www.videomaker.com/article/c06/18423-six-primary-styles-of-documentary-production/)

[W-8] Podnews / Buzzsprout / Critical Listening Lab. *Podcast loudness (LUFS).* [podnews.net](https://podnews.net/article/lufs-lkfs-for-podcasters) ; [criticallisteninglab.com](https://www.criticallisteninglab.com/en/learn/loudness/podcast)

[W-9] StudioBinder / UT Visual Rhetoric. *Video essay structure; A-roll vs B-roll.* [studiobinder.com](https://www.studiobinder.com/blog/what-is-a-video-essay-examples/) ; [utexas.edu](https://sites.dwrl.utexas.edu/visualrhetoric/2016/03/29/using-b-roll-footage-citations/)

[W-10] Bensound / VideoScribe. *Music under narration.* [bensound.com](https://blog.bensound.com/creation-editing/music-audiobook-producers/)

[W-S-E] Song Exploder. *About the Show* / PRX "100 Episodes." [songexploder.net](https://songexploder.net/about) ; [medium.com](https://medium.com/prxofficial/100-episodes-of-song-exploder-cba4cac9d265)

[W-TL] Transom. *The Layered Approach* (Adler) / *Tape-Driven Storytelling* (Mingle). [transom.org](https://transom.org/2025/the-layered-approach/) ; [transom.org](https://transom.org/2021/tape-driven-storytelling/)

### Audio exemplars

[E-1] Song Exploder — About the Show. [songexploder.net](https://songexploder.net/about)

[E-2] Song Exploder. Wikipedia. [en.wikipedia.org](https://en.wikipedia.org/wiki/Song_Exploder)

[E-3] *Song Exploder: An Intro to Podcasting.* Film and Digital Media. [wordpress.com](https://filmanddigitalmedia.wordpress.com/2020/11/01/song-exploder-intro-to-podcasting/)

[E-4] Switched on Pop. Wikipedia. [en.wikipedia.org](https://en.wikipedia.org/wiki/Switched_on_Pop)

[E-6] Sloan N & Harding C — interview. Tink Media. [tinkmedia.co](https://tinkmedia.co/interviews/switched-on-pop)

[E-7] Dissect — A Serialized Music Podcast. [dissectpodcast.com](https://dissectpodcast.com/) ; DiscoverPods. [discoverpods.com](https://discoverpods.com/dissect-podcast/)

[E-8] Cole Cuchna interview. Creator Science. [creatorscience.com](https://podcast.creatorscience.com/cole-cuchna/) ; Billboard. [billboard.com](https://www.billboard.com/pro/dissect-podcast-cole-cuchna-kanye-frank-ocean-spotlight-interview/)

[E-9] *NotebookLM now lets you listen to a conversation about your sources.* Google. [blog.google](https://blog.google/technology/ai/notebooklm-audio-overviews/)

[E-11] *Google NotebookLM's AI podcast hosts can now get into an argument.* TechRadar. [techradar.com](https://www.techradar.com/ai-platforms-assistants/gemini/google-notebooklms-ai-podcast-hosts-can-now-get-into-an-argument-over-your-notes)

[E-12] Generate Audio Overview. NotebookLM Help. [support.google.com](https://support.google.com/notebooklm/answer/16212820?hl=en)

[E-13] Pop Culture Happy Hour. NPR series page. [npr.org](https://www.npr.org/series/pop-culture-happy-hour/129472378/pop-culture-happy-hour/)

[E-14] *NPR: The Best of Pop Culture Happy Hour.* [amazon.com](https://www.amazon.com/Npr-Best-Culture-Happy-Hour/dp/1665154306)

[E-15] 99% Invisible. Wikipedia. [en.wikipedia.org](https://en.wikipedia.org/wiki/99%25_Invisible)

[E-17] *Ira Glass and the structure of storytelling.* American Libraries Magazine. [americanlibrariesmagazine.org](https://americanlibrariesmagazine.org/blogs/the-scoop/ira-glass-and-the-structure-of-storytelling/)

[E-18] *Ira Glass on storytelling lessons from 30 years of This American Life.* Nieman Storyboard. [niemanstoryboard.org](https://niemanstoryboard.org/2025/05/16/ira-glass-storytelling-lessons-30-years-this-american-life/)

[E-19] Audio commentary. Wikipedia. [en.wikipedia.org](https://en.wikipedia.org/wiki/Audio_commentary)

[E-20] *How to Write a Museum Audio Guide Script: Best Practices.* Nubart. [nubart.eu](https://www.nubart.eu/audio-guides/content-production/writing-museum-guide-scripts.html)

[E-21] *Audio Scriptwriting for Museum Audio Guides.* Pathoura. [pathoura.com](https://pathoura.com/museum-audio-scriptwriting-multilingual-audio-guides/)
