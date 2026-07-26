# NotebookLM & Conversational Pacing: Making Text-to-Dialogue Sound Human

*Synthesis of three research passes (NotebookLM reverse-engineering, pacing science, ElevenLabs v3 controls) into an implementation-ready playbook for our Text-to-Dialogue pipeline.*

---

## Executive summary — highest-impact fixes

Our output sounds robotic for three compounding reasons, each with a concrete fix. In priority order:

1. **We synthesize turns line-by-line and concatenate them.** This is the single biggest cause of the "each line sounds isolated" feel. NotebookLM's audio model (SoundStorm lineage) generates the *whole exchange jointly*, non-autoregressively, so voice, room tone, and prosody carry across turn boundaries. **Fix: send the entire 8-turn exchange in ONE `text_to_dialogue.convert` call** (all turns as a `Sequence[DialogueInput]`), not one call per turn. This alone removes the bookend padding silence and gives cross-turn prosodic continuity.

2. **We write disfluencies as text and/or punctuate backchannels as their own sentences.** `"Mm-hm."` hits a period, which every engine renders as a *paragraph-length* stop — exactly the too-long gap around backchannels we hear. NotebookLM deliberately does NOT script "um"/"uh"/"totally" as transcript text; the audio model performs them. **Fix: (a) fuse backchannels lower-cased into the head of the next clause with a comma or em-dash (`"mm-hm so what you're saying is…"`), never as standalone periods; (b) express reactions as v3 audio tags (`[laughs]`, `[chuckles]`, `[sighs]`) rather than spelled-out filler.**

3. **Every syllable and gap regresses to the mean → flat, evenly-paced delivery.** There is no acceleration/deceleration. In v3 there is **no speed knob** — pacing is controlled entirely by audio tags, punctuation, and stability. **Fix: set `stability=0.5` (Natural) or `0.4` for livelier hosts (never `1.0`/Robust, which mutes tags and IS the robotic voice); stage tempo with `[rushed]`/`[slowly]` tags, `...` for weight, em-dashes for flowing pauses, CAPS for stress; pin `seed` while tuning.**

A fourth, engine-agnostic safety net: **post-process with ffmpeg** — `atempo` to compress over-long fillers, `silenceremove`/`silencedetect` to pull inter-turn gaps down toward the ~200 ms human norm.

---

## What NotebookLM does

NotebookLM's "Audio Overview" naturalness comes from a **strict two-stage separation**, and a crucial twist about *where* the disfluencies come from.

**Stage 1 — multi-pass LLM script generation.** Not a single "write me a podcast" prompt. A chain: outline → detailed script → self-critique → revised final, over Gemini's long-context ingestion of the sources [1][2]. A deliberate **narrative-planning step** decides order, tension, examples, and emphasis *before* scripting turns, then assigns questions, reactions, and reframes to each host [3].

**Stage 2 — dialogue-audio synthesis** by a SoundStorm/AudioLM-lineage model (Google has never officially named the production model; this is strongly-implied inference [5][6]).

**The key architectural decision to imitate:** the team found that **scripting "um"s and "ah"s as text produces *worse* results.** Per Raiza Martin (former NotebookLM lead), micro-interjections ("Oh really?", "Totally"), pauses, and "uh…" are **built into the audio model, not written into the transcript** [4]. The LLM writes relatively clean dialogue lines; the audio model performs the hesitation, timing, and backchannels. Steven Johnson's framing: the model *"adds all the banter and the pauses and the likes… you cannot listen to two robots talking to each other"* [1].

**Content techniques that read as human:**
- **Engineered disagreement / information-withholding** — *"if there's just too much agreement between people, that's not fun"* [4]. Asymmetric host/guest roles, setups and payoffs, one host asking the obvious question the other set up [3].
- **Rhythm and cadence over clarity** — optimized for *"as close to just human speech as possible,"* prioritizing naturalness over perfect enunciation [4].

**Tells that expose it (avoid these):** repetitive openers like "Let's dive in," and direct source-referencing like "The document says…" [3].

**The direct architectural fix for our isolated-line problem:** SoundStorm is **non-autoregressive with bidirectional attention over the whole sequence**, giving *"higher consistency in voice and acoustic conditions"* than line-by-line concatenation [6]. Turn markers in the transcript are the control surface for turn-taking. The natural pacing/breaths/tight "mm-hm" timing are **learned from real unscripted voice-actor recordings** with realistic disfluencies — not rule-based — which is why they land at natural moments [5].

---

## The pacing science

**Why current TTS sounds evenly-paced — a statistical failure, not acoustic.** Neural TTS predicts duration/prosody with a regression objective that **collapses toward the mean** of a multimodal distribution: "overly smooth, averaged contours, missing the sharp, localized variations found in natural speech" [1p][2p]. Even pacing is the *duration* symptom — every syllable and gap regresses to its conditional average, ironing the human push-and-pull flat.

Natural speech is **strongly non-uniform in time** along axes TTS averages away:

- **Speech-rate variation within an utterance** — speakers continuously speed up/slow down; function words and given/predictable information are rushed, new/focal content is slowed and lengthened [3p].
- **Final (pre-pausal) lengthening** — the syllable before a boundary is lengthened *proportional to boundary strength*; stronger boundary → longer pre-boundary syllable AND longer following pause [4p]. TTS that inserts a pause at a comma but does NOT lengthen the syllable before it produces the tell-tale "clipped word + dead-air gap."
- **Anacrusis & function-word reduction** — English is stress-timed; unstressed function words (the, of, to, and, a, that, you) reduce to schwa, and phrase-initial unstressed syllables are "pronounced very fast" before the first accent [6p][7p][9p]. Full citation-form duration on every word destroys this.
- **Tight backchannel timing** — modal inter-turn gap is **~200 ms** across all languages [10p][11p]. Backchannels ("mm-hm," "right," "yeah") are **sub-second** units, often **entirely overlapping** the other speaker's turn; simulated offsets center around only **~0.2 s** [12p][13p]. A backchannel surrounded by half-second silences on both sides is acoustically wrong by an order of magnitude.

**The two problems, diagnosed:**

- **(a) Gaps around backchannels too long.** Over-smoothed duration pads every boundary toward the average, AND — the actionable part — **punctuation forces the pause**: a period ≈ `x-strong`/paragraph break, comma ≈ `strong`, no punctuation ≈ `medium` [14p][15p]. `"Mm-hm."` literally instructs a paragraph-length stop.
- **(b) No accel/decel within an utterance.** The regression-to-mean problem [1p][2p]. A single global speed setting can't fix it — the pathology is that *relative* timing is flattened; a uniform global speed just makes the flat contour uniformly faster/slower.

**The levers (engine-agnostic):**
- **Script punctuation to control pauses** (biggest, cheapest win — see table below).
- **Merge backchannels into the following clause** so the backchannel becomes that clause's fast, reduced anacrusis rather than an isolated utterance flanked by silence.
- **Reduce filler duration explicitly** — spell short (`mm-hm`, not `mmmmm-hmmm`).
- **Per-phrase speed variation** — fast on anacrusis/function-word runs, slow on the last content word before each boundary (synthesizes final-lengthening).
- **Synthesize final lengthening, not just a pause** — the robotic signature is *pause without lengthening*; slow the pre-boundary word AND scale the following break to boundary strength, keeping the two correlated.
- **Post-hoc ffmpeg time-stretch** of gaps and fillers.
- **Don't over-use `<break>` tags** — they cause instability; prefer punctuation.

| Written form | Break the engine inserts |
|---|---|
| Period `.` | x-strong (paragraph-ish, longest) |
| Semicolon / colon | strong |
| Comma `,` | strong (single-comma pause) |
| Em-dash `—` / spaced hyphen ` - ` | short, **flowing** pause (best "connect-through") |
| Ellipsis `…` | pause **plus** hesitation/"nervous" prosody — use sparingly |
| **No punctuation** | medium — words run together (use for anacrusis / reduced runs) |

---

## ElevenLabs v3 / Text-to-Dialogue controls to use (exact params)

Verified against installed SDK `elevenlabs==2.45.0` and current docs. **The biggest lever is stability + audio-tag/punctuation staging, NOT a speed knob.**

### Stability — a FLOAT (0.0–1.0), not an enum

Creative/Natural/Robust are the Studio-UI labels for three snap points of the `stability` float [E1][E2][E6]:

| UI label | Float | Effect |
|---|---|---|
| **Creative** | **0.0** | Max emotional range + strongest tag response; may hallucinate, add unscripted sighs, and **"speak too quickly"** |
| **Natural** | **0.5** (default) | Balanced, fully tag-responsive. **Recommended default for dialogue** |
| **Robust** | **1.0** | Most consistent but ≈v2; **suppresses audio-tag responsiveness → the most robotic delivery. AVOID.** |

**Rule:** lowering stability toward 0.4–0.5 reduces robotic delivery. `1.0` IS the robotic voice (mutes tags). Too low (near 0.0) trades robotic for rushed/erratic. **Sweet spot: `0.5`, or `~0.4` for livelier hosts.**

### Speed — the caveat

- **v3 has NO officially supported speed setting.** Docs: *"Speed is not available for the Eleven v3 model"* [E1][E7]. The Text-to-Dialogue `settings` schema documents **only `stability`** [E4][E5].
- `speed` exists for v2/Turbo/Flash via `voice_settings.speed` (REST 0.25–4.0, default 1.0; Agents clamped 0.7–1.2) — **not v3 dialogue** [E7].
- **SDK reality:** `ModelSettingsResponseModel` has `extra="allow"`, so `ModelSettingsResponseModel(stability=0.5, speed=0.9)` serializes and IS sent — but v3 is documented not to honor it. **Leave `speed` OUT; treat any effect as undefined.**

### The convert call (SDK 2.45.0)

```python
from elevenlabs import ElevenLabs
from elevenlabs.types import DialogueInput, ModelSettingsResponseModel

client = ElevenLabs(api_key=...)

audio = client.text_to_dialogue.convert(
    model_id="eleven_v3",
    settings=ModelSettingsResponseModel(
        stability=0.5,  # Natural. Drop to ~0.4 for livelier hosts.
        # Do NOT approach 0.0 (rushed) or 1.0 (robotic).
        # speed=...           # OMIT — unsupported on v3.
    ),
    seed=12345,  # pin for reproducible pacing while tuning scripts
    apply_text_normalization="auto",
    output_format="mp3_44100_128",
    inputs=[  # ALL 8 turns here, ONE call — never per-turn
        DialogueInput(voice_id=BRIAN, text="So — [chuckles] you actually tried it?"),
        DialogueInput(
            voice_id=CASSIDY, text="I did... [slowly] and it was NOT what I expected."
        ),
        # ... remaining turns ...
    ],
)
```

**Constraints:** ≤10 unique `voice_id`s; keep total ≤~2,000 chars per call (chunk longer episodes on natural boundaries); `seed` 0–4294967295 [E4][E5].

### Audio-tag & punctuation controls for pacing (the real speed dial)

v3 reads text structure as delivery instruction [E8]:

- **Tempo tags** (inline `[brackets]`): `[rushed]`, `[slowly]`, `[drawn out]`, `[pause]`, `[hesitant]`. Put `[slowly]` on a punchline, `[rushed]` on an aside.
- **Pauses/breath:** `...` = weight/longer beat; commas = short breath; `[sigh]`, `[exhale]`, `[pause]` insert real pauses; em-dash `—` = clipped/interrupted feel.
- **Emphasis → perceived tempo:** CAPS pushes stress (`OH MY GOD` vs `oh my god`), altering timing.
- **Backchannels/reactions:** `[laughs]`, `[laughs harder]`, `[chuckles]`, `[sighs]`, `[clears throat]`, `[gasps]` — the interjections that make two hosts feel alive.
- **Tag responsiveness is gated by stability:** tags fire reliably at Creative/Natural, weakly/ignored at Robust. High stability + tags = disappointment.
- **Cross-speaker timing:** you don't set inter-turn gaps directly; the model paces from the `DialogueInput` sequence + each turn's punctuation/tags. End a turn on `...` for a trailing handoff; open the next with a backchannel tag (`[chuckles] Right, but—`).
- **v3 dropped SSML `<break>` entirely** — use tags + punctuation. (Where breaks exist in other engines they cause instability if overused; cap ≤3 s.)

### Voice choice — cadence varies by premade voice

- **Fast/energetic conversational:** Natasha (Valley Girl, high energy), Cassidy (F, best podcast cadence, doesn't go robotic late), Brian (M, recommended for podcasts on v3).
- **Warm/measured:** Josh (M), Charlotte (F, British, interview-style).
- **Recommended energetic pair:** **Brian (M) + Cassidy (F)**; swap Cassidy→Natasha for higher energy, or use Josh + Charlotte for a calmer show. Pair measured voices with slightly *lower* stability to avoid drag.

**What we're likely NOT using and should:** the `settings=` object at all (many callers omit it and get blind default 0.5), deliberate `[rushed]`/`[slowly]` tags, `...`/CAPS staging, backchannel tags, and a pinned `seed`.

---

## Scripting rules for backchannels/disfluencies that don't create robotic pauses

Concrete rewrite rules, applied as a **pacing pass** over the LLM's clean script:

1. **Never end a backchannel with a period.** A period = paragraph-length stop.
   - Robotic: `"Mm-hm."` … `"So what you're saying is…"` (two utterances, two pauses)
   - Natural: `"mm-hm so what you're saying is…"` or `"right—so what you're saying is…"`

2. **Fuse the backchannel, lower-cased, comma- or dash-joined, to the head of the next clause** so it becomes that clause's fast, reduced anacrusis — mirroring the corpus fact that backchannels are sub-second units contained *within* surrounding speech.

3. **Prefer audio tags over spelled-out filler** for reactions: `[chuckles]`, `[laughs]`, `[sighs]` instead of writing "haha" / "hmm" / "uh". Let the audio model perform them (the NotebookLM lesson). Reserve spelled filler for cases where you specifically want the word audible, and keep it short (`mm-hm`, `mhm`, `yeah` — not `mmmmm-hmmm`).

4. **Em-dash / spaced hyphen is the reliable "keep-moving" pause** — ElevenLabs reports a dash "provides the most consistent output" while ellipsis "usually also adds some hesitation or nervousness." Use `—` for flow, `...` only when you want the hesitation.

5. **Delete punctuation to bind reduced function-word runs** (`"and then i realized"` with no internal commas) — no punctuation = medium/no break, giving the rushed anacrusis.

6. **Stage tempo explicitly:** `[rushed]` on asides/setups, `[slowly]` on the payoff/last content word before a strong boundary (synthesizes final-lengthening), CAPS for focal stress.

7. **Handoffs:** end a turn on `...` for a trailing pass to the other host; open the receiving turn with a backchannel tag to overlap-in (`[chuckles] Right, but—`).

8. **Keep the LLM script relatively clean** and do the disfluency/pacing injection in this dedicated pass — do NOT ask the script-writing model to also embed "um"s as text.

**Example rewrite (before → after) of one exchange:**

- Before: `A: "That's interesting."` / `B: "Yeah. So the key point is that it scales."`
- After: `A: "[chuckles] That's — huh, interesting."` / `B: "yeah so the key point is it SCALES... [slowly] which nobody expected."`

---

## Concrete experiment plan — variants to A/B on our 8-turn exchange

Fix the same 8-turn script and the same voice pair (**Brian + Cassidy**), `seed=12345`, `output_format="mp3_44100_128"`, `model_id="eleven_v3"`. Vary ONE dimension at a time. Render, then blind-rank on: (i) inter-turn gap length, (ii) backchannel tightness, (iii) intra-utterance accel/decel presence, (iv) overall "two humans vs two robots."

**V0 — Baseline (current behavior).** Per-turn synthesis, 8 separate `convert` calls, concatenated; no `settings` (blind default); backchannels as standalone `"Mm-hm."` sentences; no tags. *This is the control that should sound robotic.*

**V1 — Joint synthesis only.** Identical script to V0, but **all 8 turns in ONE `convert` call**. Isolates the effect of cross-turn prosodic continuity (the SoundStorm lesson). Expect the biggest single jump.

**V2 — V1 + stability set.** Add `settings=ModelSettingsResponseModel(stability=0.5)`. Then a sub-variant `stability=0.4`. Isolates stability's effect on liveliness/tag-readiness. (Also render a `stability=1.0` negative control to confirm it sounds worst.)

**V3 — V2 + backchannel fusion.** Rewrite every backchannel per the scripting rules (lower-cased, dash/comma-fused to next clause, no standalone periods). Isolates the punctuation-driven gap fix.

**V4 — V3 + audio tags.** Add `[chuckles]`/`[laughs]`/`[sighs]` reactions, `[rushed]`/`[slowly]` tempo staging, `...` weight, CAPS stress. Isolates performed disfluency/tempo.

**V5 — V4 + ffmpeg post-processing.** Apply the gap/filler cleanup below. Isolates the safety-net's marginal gain on top of a good render.

**V6 — Narrative-tension rewrite (optional, content axis).** Take V4's audio treatment but rewrite the *script* to engineer mild disagreement / information-withholding / asymmetric host-guest roles (the NotebookLM content lesson), removing tells ("Let's dive in," "The document says…"). Tests whether pacing perception improves from conversational dynamics, not just acoustics.

**Metrics to log per variant** (validate against the numbers): backchannels < 1 s and often overlapping; inter-turn gaps ~200 ms; pre-boundary lengthening present and correlated with pause length. Use `silencedetect` to measure gaps objectively:

```bash
ffmpeg -i variant.wav -af silencedetect=noise=-40dB:d=0.15 -f null - 2>&1 | grep silence_
```

### ffmpeg fixes (exact) for V5

`atempo` time-stretches without pitch change (per-instance 0.5–2.0; chain for wider ranges; artifacts appear outside 0.5–2×).

- **Compress an over-long filler/backchannel** (bring `mm-hm` into its sub-second window):
  ```bash
  ffmpeg -i mmhm.wav -af "atempo=1.6" mmhm_fast.wav
  ```
- **Collapse dead-air gaps > 250 ms toward the ~200 ms norm:**
  ```bash
  ffmpeg -i in.wav -af "silenceremove=stop_periods=-1:stop_duration=0.25:stop_threshold=-40dB" out.wav
  ```
- Keep every stretch factor within 0.5–2× to avoid warble/echo on transients.

---

## REFERENCES

### NotebookLM
[1] Simon Willison, *NotebookLM's automatically generated podcasts are surprisingly effective* (quoting Steven Johnson, NYT Hard Fork), Sep 2024. [https://simonwillison.net/2024/Sep/29/notebooklm-audio-overview/](https://simonwillison.net/2024/Sep/29/notebooklm-audio-overview/)
[2] *How NotebookLM Audio Overview Works*, Neurl Creators. [https://neurlcreators.substack.com/p/how-notebooklm-audio-overview-works](https://neurlcreators.substack.com/p/how-notebooklm-audio-overview-works)
[3] Rob Allandale, *NotebookLM Audio Overviews — workflow teardown*. [https://roballandale.com/briefs/notebooklm-audio-overviews-workflow-teardown/](https://roballandale.com/briefs/notebooklm-audio-overviews-workflow-teardown/)
[4] *How NotebookLM Was Made*, Latent.Space (Raiza Martin & Usama Bin Shafqat). [https://www.latent.space/p/notebooklm](https://www.latent.space/p/notebooklm)
[5] Google DeepMind, *Pushing the frontiers of audio generation*. [https://deepmind.google/blog/pushing-the-frontiers-of-audio-generation/](https://deepmind.google/blog/pushing-the-frontiers-of-audio-generation/)
[6] Borsos et al., *SoundStorm: Efficient Parallel Audio Generation*, arXiv:2305.09636. [https://arxiv.org/abs/2305.09636](https://arxiv.org/abs/2305.09636)
[7] *SoundStorm-pytorch* reimplementation [https://github.com/rishikksh20/SoundStorm-pytorch](https://github.com/rishikksh20/SoundStorm-pytorch); *Pheme* conversational TTS, arXiv:2401.02839 [https://arxiv.org/pdf/2401.02839](https://arxiv.org/pdf/2401.02839)

### Pacing science (cited [Np] above)
[1p] APXML, *TTS Prosody Modeling and Control Techniques*. [https://apxml.com/courses/speech-recognition-synthesis-asr-tts/chapter-4-advanced-text-to-speech-synthesis/prosody-modeling-control-tts](https://apxml.com/courses/speech-recognition-synthesis-asr-tts/chapter-4-advanced-text-to-speech-synthesis/prosody-modeling-control-tts)
[2p] *No Verifiable Reward for Prosody: Preference-Guided Prosody Learning in TTS*, arXiv. [https://arxiv.org/html/2509.18531v2](https://arxiv.org/html/2509.18531v2)
[3p] *VoXtream2: Full-stream TTS with dynamic speaking rate control*, arXiv. [https://arxiv.org/pdf/2603.13518](https://arxiv.org/pdf/2603.13518)
[4p] *Final lengthening of pre-boundary syllables… as boundary strength levels increase*, Journal of Phonetics (ScienceDirect). [https://www.sciencedirect.com/science/article/pii/S0095447023000141](https://www.sciencedirect.com/science/article/pii/S0095447023000141)
[5p] *Cross-linguistic differences in durational cues for segmentation*, Memory & Cognition. [https://link.springer.com/article/10.3758/s13421-017-0700-9](https://link.springer.com/article/10.3758/s13421-017-0700-9)
[6p] Iowa State, *Rhythm — Teaching Pronunciation with Confidence*. [https://iastate.pressbooks.pub/teachingpronunciation/chapter/7-rhythm/](https://iastate.pressbooks.pub/teachingpronunciation/chapter/7-rhythm/)
[7p] Pronuncian, *Rhythm rule — American English Pronunciation*. [https://pronuncian.com/rhythm-rule](https://pronuncian.com/rhythm-rule)
[8p] San Diego Voice and Accent, *Word Reductions: Function Words*. [https://sandiegovoiceandaccent.com/american-english-rhythm-and-reductions/word-reductions-function-words](https://sandiegovoiceandaccent.com/american-english-rhythm-and-reductions/word-reductions-function-words)
[9p] *Anacrusis*, Grokipedia. [https://grokipedia.com/page/Anacrusis](https://grokipedia.com/page/Anacrusis)
[10p] Stivers T, et al., *Universals and cultural variation in turn-taking in conversation*, PNAS 2009. [https://www.pnas.org/doi/10.1073/pnas.0903616106](https://www.pnas.org/doi/10.1073/pnas.0903616106)
[11p] *Timing in turn-taking and its implications for processing models of language*, Frontiers in Psychology. [https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00731/full](https://www.frontiersin.org/journals/psychology/articles/10.3389/fpsyg.2015.00731/full)
[12p] *Distribution and Timing of Verbal Backchannels in Conversational Speech*, Languages (MDPI) 2025. [https://www.mdpi.com/2226-471X/10/8/194](https://www.mdpi.com/2226-471X/10/8/194)
[13p] *Real-Time Textless Dialogue Generation*, arXiv. [https://arxiv.org/pdf/2501.04877](https://arxiv.org/pdf/2501.04877)
[14p] Amazon, *SSML Reference — Alexa Skills Kit* (break strengths, ≤10 s). [https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html](https://developer.amazon.com/en-US/docs/alexa/custom-skills/speech-synthesis-markup-language-ssml-reference.html)
[15p] Telesign, *Voice — Use SSML for TTS* (comma≈strong, period≈x-strong). [https://developer.telesign.com/enterprise/docs/voice-use-ssml-for-tts](https://developer.telesign.com/enterprise/docs/voice-use-ssml-for-tts)
[16p] *Speaking-Rate-Controllable HiFi-GAN Using Feature Interpolation*, arXiv. [https://arxiv.org/pdf/2204.10561](https://arxiv.org/pdf/2204.10561)
[17p] Speechify API, *SSML — Control Pitch, Rate, Pauses & Emotion*. [https://docs.speechify.ai/tts/text-to-speech/features/ssml](https://docs.speechify.ai/tts/text-to-speech/features/ssml)
[18p] FFmpeg Micro, *atempo Filter: Change Audio Speed Without Pitch Shift*. [https://www.ffmpeg-micro.com/blog/ffmpeg-atempo-filter-change-audio-speed](https://www.ffmpeg-micro.com/blog/ffmpeg-atempo-filter-change-audio-speed)
[19p] Wikipedia, *Audio time stretching and pitch scaling*. [https://en.wikipedia.org/wiki/Audio_time_stretching_and_pitch_scaling](https://en.wikipedia.org/wiki/Audio_time_stretching_and_pitch_scaling)

### ElevenLabs controls (cited [EN] above)
[E1] *Elevenlabs Eleven v3 — Artlist Help*. [https://help.artlist.io/hc/en-us/articles/33143492937757-Elevenlabs-Eleven-v3](https://help.artlist.io/hc/en-us/articles/33143492937757-Elevenlabs-Eleven-v3)
[E2] *Eleven v3: Expressive AI Voice — Artlist Blog*. [https://artlist.io/blog/new-eleven-v3/](https://artlist.io/blog/new-eleven-v3/)
[E3] *Best practices — ElevenLabs Docs*. [https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)
[E4] *Text to Dialogue — ElevenLabs Docs*. [https://elevenlabs.io/docs/overview/capabilities/text-to-dialogue](https://elevenlabs.io/docs/overview/capabilities/text-to-dialogue)
[E5] *Text-to-Dialogue Convert — ElevenLabs API Reference*. [https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert)
[E6] *What is new in ElevenLabs V3 — Webfuse*. [https://www.webfuse.com/blog/what-is-new-in-elevenlabs-v3](https://www.webfuse.com/blog/what-is-new-in-elevenlabs-v3)
[E7] *Voice settings reference — elevenlabs/skills (GitHub)*. [https://github.com/elevenlabs/skills/blob/main/text-to-speech/references/voice-settings.md](https://github.com/elevenlabs/skills/blob/main/text-to-speech/references/voice-settings.md)
[E8] *ElevenLabs V3 Tutorial: Best Settings & Audio Tags — Moe Lueker*. [https://moelueker.com/blog/elevenlabs-v3-tutorial-best-settings-audio-tags-free-gpt-tool](https://moelueker.com/blog/elevenlabs-v3-tutorial-best-settings-audio-tags-free-gpt-tool)
[E9] *Best ElevenLabs Voices 2026 — AI Voice Review*. [https://aivoicereview.com/blog/best-elevenlabs-voices-2026](https://aivoicereview.com/blog/best-elevenlabs-voices-2026)
[E10] *ElevenLabs Voices: Full List with Voice IDs — json2video*. [https://json2video.com/ai-voices/elevenlabs/](https://json2video.com/ai-voices/elevenlabs/)
