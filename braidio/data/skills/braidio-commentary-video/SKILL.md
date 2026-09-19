---
name: braidio-commentary-video
description: >
  Turn a braidio commentary episode into a watchable video — a Ken Burns
  pan/zoom film over still images, cut to the narration, optionally captioned and
  published. Use when someone wants a commentary/analysis *video* rather than
  audio: "make a video essay about this song", "turn this episode into a video",
  "Ken Burns video over these images", "video version of the podcast", "publish
  this commentary to YouTube", "add visuals to the narration", "slideshow video
  with narration", "music video essay". Covers picking the format and fixing the
  robotic-TTS defaults, planning panels from the render's own timeline, sourcing
  freely-licensed stills, rendering with `burns`, building captions without ASR,
  and publishing privately with `yb`. For audio only, use the `braidio` skill;
  for generated footage, characters or shots, use `reelee`.
---

# braidio-commentary-video

A commentary video is the audio episode plus a picture track. Build the audio
first with the **`braidio`** skill, then this.

```bash
pip install 'braidio[video]'   # adds burns + pillow; ffmpeg must be on PATH
```

Everything below is `braidio.video` (panels, canvases, render) and
`braidio.captions` (subtitles). braidio fetches **no images** — that is the
caller's job, exactly as `SegmentSource` leaves audio acquisition to the caller.
**Use `illustration` to do that job** (see *Images* below); it is the fleet's
image-retrieval package and already carries licence, attribution and
same-subject deduplication. **Any text drawn on the picture — captions naming
what is on screen, a source line, context cards, the title card, the credits
roll — is `tituli`'s job** (see *On-screen text* below); do not hand-roll
`ImageDraw` overlays.

## The pipeline

```python
import braidio
from braidio.formats import FORMATS
from braidio.video import plan_spans, render_video, Panel, with_credits, credits_card

fmt = FORMATS["solo_explainer"]
path, timeline = braidio.render_format(  # 1. audio + exact beat timings
    fmt,
    script,
    source=source,
    out_path="ep.mp3",
    return_timeline=True,  # no delivery/config overrides needed
)
spans = plan_spans(timeline)  # 2. where the cuts fall
panels = [Panel(s.start, s.end, pick(s)) for s in spans]  # 3. YOUR choice of image
render_video(panels, audio_path="ep.mp3", out_path="ep.mp4")
```

**Never eyeball panel timings off a transcript.** `return_timeline=True` gives the
renderer's own `[start, duration)` per beat; `plan_spans` cuts on those boundaries
(splitting long beats, merging short ones) so the picture changes where the
narration changes subject.

`assign_stills(spans, stills)` cycles a pool without back-to-back repeats — right
when the images are interchangeable texture, wrong when relevance matters. Which
picture belongs over which sentence needs to know what is being *said*; each
`Span` carries `label`, `kind` and `beat_index` so you can choose.

## What actually controls pacing (read this before tuning anything)

An earlier version of this file told you to pass
`config=fmt.weave.with_(gap_turn_s=0.28, speed_jitter=0.07)`. **That advice was
wrong** for the whole of braidio ≤ 0.0.40: on the `render_format` /
`render_production` path those two fields were read by nothing. Renders with
`gap_turn_s=0.0`, `0.28` and `3.0` came out byte-identical. They were live only
inside `compose_narration`, which the format templates never call. Fixed in
braidio#64 — but know which knob acts on which path before you reach for one.

| Knob | Where it lives | What it does on the `render_format` path |
|---|---|---|
| `WeaveConfig.segmentation_unit` | config | **The master switch.** `"beat"` (the bare `WeaveConfig()` default) = one TTS call per narration beat, and then `gap_turn_s` / `speed_jitter` / `min_turn` / `max_turn` do nothing. `"sentence"` / `"clause"` / `"paragraph"` cut the beat into turns and switch the rest on |
| `WeaveConfig.gap_turn_s` | config | Silence at a **sentence** boundary between turns; other boundaries scale off it (a paragraph break ≈ 2.2×, a comma ≈ 0.5× — `braidio.pacing.BOUNDARIES`). Live only when `segmentation_unit != "beat"` |
| `WeaveConfig.speed_jitter`, `speed_base` | config | Per-turn speed jitter, **v2 only** — eleven v3 has no speed control, so a v3 delivery plans none (`Delivery.supports_speed`) |
| `WeaveConfig.min_turn` / `max_turn` | config | How many units one turn speaks. Fewer units per turn = more independent takes = more prosodic variety, and more inserted breath |
| `Narration.lead_gap_s` | **the beat** | Silence *before* a beat. Always live, on every path — this is the one that was doing the work all along. Put `0.3–0.5` on any beat that follows a clip |
| `Delivery` | render arg | `eleven_multilingual_v2` **cannot render `[audio tags]` at all**. Only a v3 delivery makes `[pause]` / `[dryly]` fire |

**Defaults you no longer need to override.** `solo_explainer` and
`documentary_vo` now ship a v3 delivery *and* sentence-level pacing, so
`render_format(FORMATS["solo_explainer"], …)` with no overrides is the intended
sound. Override only to move away from that — and if you do pass a `config`,
remember you are replacing the format's, so start from `fmt.weave.with_(…)`,
never a bare `WeaveConfig()` (which would silently switch pacing back off).

## Two things that will still make it sound like AI

Two complaints from two real episodes, and they pull in **opposite** directions.
You need both gates.

**1. Under-tagged reads as somniferous.** The second episode's verdict was
exactly that word. Its script carried ten `[audio tags]` in 1371 words while
dutifully varying `voice_settings["stability"]` between 0.30 and 0.65 to get
"four registers". Measured: those two stability values are worth about **2 Hz**
of pitch range, whereas plain-vs-densely-tagged text is worth **54 Hz** (70.8 →
124.4). **Tags are the engine; stability is nearly noise.** Target **2–5 tags
per 100 words**, vary which tag, and gate it with
`braidio.audit_expressiveness(prose)`. The `braidio` skill has the full table.

**2. Over-written reads as kitsch.** The first episode's verdict. A draft landed
a designed turn of phrase at the end of *every* beat — 8 in 338 words. No
speaking human sustains that; it is the relentlessness, not any one sentence.
Budget **≤ 2 per 3 minutes** and let the rest be plain talk with contractions,
fragments and uneven sentence length.

The thing to ration is the **epigram**, not the tag. `audit_platitudes` catches
recycled tics, not over-writing, and says nothing at all about flatness — it
cannot be the only gate.

## Two recordings of the same work

A comparison piece — a studio master against a live take, two performances, a
text read twice — hits one wall immediately: `render_format(..., source=...)`
takes **exactly one** `SegmentSource`, and a token matcher scores the same lyric
line equally well in every recording of it. Which take a quote comes from is a
production decision, not something the reference text can carry.

```python
from braidio import NamespacedSegmentSource, TimedLineSegmentSource

source = NamespacedSegmentSource(
    {
        "1966": TimedLineSegmentSource(lines=studio_lines, asset_path="studio.mp3"),
        "1981": TimedLineSegmentSource(lines=live_lines, asset_path="live.mp3"),
    }
)

SegmentBeat("1981: and in the naked light i saw")  # -> the live master
```

An unknown prefix raises rather than falling through, deliberately: silently
picking the wrong recording ships one performance under commentary describing
another, which the listener cannot detect and a diff does not show.

**Such a piece needs the two-voice pattern at the same time** (see the `braidio`
skill). A comparison has to say *which recording is playing* — a `tituli` lower
third over every clip — **and** distinguish your argument from the documented
record. They arrive as one problem.

**And research each recording separately.** Annotation sources describe the
*work*. On a real episode the Genius entry for the studio version carried nine
annotations and the entry for the live version carried **zero**, while the live
recording's circumstances were the whole reason the episode existed. Ask
per recording: who made it, when, and what was happening.

## Images

**`illustration` is the fleet's image-finding package — use it rather than
writing an HTTP client against Commons or a stock API.** One `search()` over
Openverse / Wikimedia / Pexels / Pixabay, licence and attribution carried on
every hit, and `dedupe()` for the failure below.

```bash
pip install illustration
```
```python
import illustration

hits = illustration.search("a woman alone with a letter by candlelight", n=20)
keep = illustration.dedupe(hits)  # one image per SUBJECT
illustration.search("Category:Trinity Church (Manhattan)", source="wikimedia")
```

Read `illustration`'s own skill before sourcing pictures — it carries the
licence/attribution obligations in full.

Three things it exists to save you, each of which cost a real episode a rebuild:

**Same subject, different file.** A search for one person returns a painting,
engravings after it, and a library's re-scan of an engraving — different ids,
different bytes, one picture. Four of them shipped in one film, which then
looked like it had run out of pictures. `illustration.dedupe()` groups by
subject (DINOv2) and keeps the best copy; a perceptual hash does **not** catch
this, because those engravings genuinely differ pixel by pixel.

**Search guesses; categories are curated.** On Wikimedia,
`search("Hamilton Grange")` returns a branch *library* of that name;
`search("Category:Hamilton Grange National Memorial")` returns the house.

**Filenames are not evidence — look at a contact sheet before rendering.** On a
real run, plausible filenames returned an empty stadium exterior for "Taylor
Swift" and the Chiang Kai-shek Memorial in Taipei for "concert crowd"; a third
still was too dark to read. On another, `Category:Snare drums` returned museum
vitrines of **Nazi-flagged military drums** in its top six. Also watch for museum
catalogue shots carrying scale bars and accession stamps — on screen those read
as a rights claim over your whole frame. Crop them. And a transparent source (an
SVG rendered to PNG, a signature in black ink on nothing) flattens to an entirely
black frame under a naive `convert("RGB")`.

**The contact sheet is not enough on its own — read the title too.** Six stills
once passed a visual check and were still wrong: `Category:Crowds` returned
Library of Congress *portraits of jazz musicians*, a Dresden apartment block sat
under the words "tenement halls", and a 1910 hotel was captioned as a record
shop. A thumbnail tells you what a picture looks like, not what it is.

**A picture that is right-shaped but wrong-specific needs a label, not a
deletion.** A photograph of a genuine large concert in the right park that is
*not the concert you are discussing* is honest illustration the moment `tituli`
names it on screen ("The Beach Boys in Central Park, 1971 — not this concert"),
and an implicit false claim the moment it is unlabelled. Decide which you are
shipping.

**Queries come from the research, not from the topic.** "Illustrate the 1965
overdub" gives you generic studio stock; knowing *what the research turned up*
gives you the trade advertisement for the album that flopped, the Rembrandt of
the hand writing on the wall for the lyric's biblical reference, the period
Times Square sign for the "neon god". Do the research first and let it write the
query list.

**Downloading the bytes is its own job, with its own traps.** Wikimedia throttles
on **User-Agent policy**, not only on rate, and the failure looks exactly like a
rate limit: with a vague UA, `upload.wikimedia.org` returned HTTP 429 with
`Retry-After: 10` at roughly two successful requests per 100 seconds; with a
compliant `Tool/1.0 (https://url; email)` string the same URLs returned 200
immediately. Prefer the thumbnail service (`.../1280px-Name.jpg`) over the 15 MB
original you are about to downscale anyway. And **never cache on existence
alone** — a throttled first pass writes 330 px fallbacks, and every later run
"finds" them and never retries, so the whole film is built from 6× upscales
before anyone checks a pixel dimension.

**Compose the credit line; do not trust `attribution`.** For a minority of
Wikimedia hits it comes back as the bare author with no licence named at all,
while `license` and `license_url` on the same hit are correct — so rendering it
as documented ships "EliziR" as the entire credit for a CC BY-SA image. Build
the line from the parts and assert that every finished line names a licence.

`prepare_still` composites each image onto a blurred, darkened enlargement of
itself to reach 16:9, so portraits are not cover-cropped and no dead black bars
appear. `render_video` calls it for you.

## Panels that don't look like a slideshow

- 5–9 s per still (`MIN_PANEL_S` / `MAX_PANEL_S`); `plan_spans` enforces both.
- Motion is content-aware by default: `burns.content_aware_path_for` frames on the
  image's salient region, so a slow push stays on the subject instead of drifting
  off a face. Override with `path_for=`.
- Alternate `push` / `drift`, and never repeat a still back-to-back.
- One `ken_burns_film` pass, not per-panel renders plus a concat — that is what
  avoids a re-encode seam and a frozen frame at every cut.

Budget the render: ~5 minutes of wall clock for a 3-minute 1080p30 film.

## Captions — from the script, never from ASR

```python
(out_dir / "ep.srt").write_text(braidio.captions_for(script, timeline, max_chars=42))
```

You authored the words and the timeline says when they play, so recognising them
back out of the mix pays an API to recover something never lost — and does it
worse (a measured pass turned "purse sets up hurts" into "Perse sets up herts").
`captions_for` also clamps cues so the weave's beat crossfades don't produce
overlapping subtitles.

## Credits are a licence obligation

CC BY and CC BY-SA are *conditional*: the attribution is the condition. Generate
the roll from the same manifest that recorded the fetches so the card cannot drift
from what was used, and put credits in **both** the end card and the description.

```python
card = credits_card(lines, "card.jpg", heading="Images: Wikimedia Commons …")
panels = with_credits(panels, card, duration_s=11.0)
# pad the audio to match, or the film outruns it:
#   ffmpeg -y -i ep.mp3 -af apad=pad_dur=11 -c:a aac ep_padded.m4a
```

## On-screen text — use `tituli`, never hand-rolled `ImageDraw`

A found-image film needs labels the narration never gives: who or what is on
screen (a museum label with a small source line), context a cold viewer lacks,
and a designed credits roll. `pip install tituli` (`tituli[saliency]` adds
`burns.salient_box` as its subject-avoidance seam) and read its skill.

```python
from tituli import (
    Frame,
    Span,
    Label,
    UNLABELLED,
    schedule_labels,
    TimedOverlay,
    note,
    resolve,
)
from tituli.video import overlay

f = Frame.blank((1920, 1080)).with_delivery("youtube")  # keeps the subtitle band clear
cards = [
    TimedOverlay(
        note(["What Hamilton is", "…"], headline="Before we go on", frame=f),
        12.0,
        18.0,
        weight=2,
    )
]
spans = [Span(p.start, p.end, key=p.still) for p in panels]
labels = schedule_labels(
    spans,
    lambda s: Label(title, attribution) if known(s) else UNLABELLED,
    suppressed_by=cards,
)
overlay(
    "ep.mp4", resolve([*cards, *labels]), "ep_captioned.mp4"
)  # one ffmpeg pass onto the FINISHED film
```

Rules it already enforces: composite onto the finished motion video (text
burned into a still would pan and zoom with the picture); one label per still
on first appearance and again only after 150 s; a label suppressed by a heavier
card is not counted as shown; `None` from `label_for` raises — say
`UNLABELLED` for a deliberately unlabelled still, because an unlabelled still
beside a labelled one is an implicit claim. For the end card,
`tituli.Credits.from_lines(lines)` takes the same `lines` as `credits_card`
and `credits_cards` / `credits_crawl` never truncate an attribution.

## Publishing (`yb`)

```python
from yb.youtube import CaptionTrack, VideoMetadata, publish_video

publish_video(
    "ep.mp4",
    VideoMetadata(
        title=...,
        description=...,
        category_id="10",
        default_audio_language="en",
        contains_synthetic_media=True,
    ),  # the narration is TTS — disclose it
    privacy_status="private",
    playlist="TW Uploads",
    captions=[CaptionTrack(path="ep.srt", language="en", name="English")],
    thumbnail="thumb.jpg",
)
```

See the **`yb-publish`** skill for the full surface. Verify what actually landed
(`video_metadata(id, group="status")`) rather than trusting the response.

## Rights — the part that decides whether it can ever be public

A clip of a commercial master gets `rights="copyright-third-party"` (anything but
`"public-domain"`, which is the whole of `PUBLISHABLE_CLIP_RIGHTS`). Then
`Profile.PERSONAL` renders it and `Profile.PUBLISHED` drops it — run
`plan_production(script, Profile.PUBLISHED)` to see exactly what a public cut
would lose.

**Such a video stays private.** Brief excerpts under commentary are a fair-use
*argument*, not a cleared licence, and downloading granted nothing. Private is the
correct setting, not a placeholder — say so rather than leaving it ambiguous.

## The graph path — the picture track as data (the studio)

Everything above is the one-shot script path: `Panel` objects in a Python
list, rendered once. For a production a person will **reopen and re-edit** —
swap a still, change a move, replace a take, re-render — the picture track
lives in the project graph instead, as four `lacing` bodies on the
`commentary_weave` genre (the commentary-studio plan, §3):

| Body | What it is | The interval |
|---|---|---|
| `still/v1` | an image + its **rights** (the seven `illustration.RIGHTS_FIELDS`, same names) + its **editorial label** (`labelled`, `subject`) + an optional `crop` | none |
| `video-panel/v1` | a still shown over a span, with an **authored** move (`move`, `zoom`, `focus`, `seed`, or an explicit `path`) | a `MediaRef` on the episode audio |
| `video-cut/v1` | a rendered mp4 — `stage="motion"` (frames) or `"delivered"` (text composited) — with `panel_ids`, `audio_artifact_id`, `profile`, `published` | none |
| `label-track/v1` | a timed card that is not per-still: `title` / `context` / `tag` / `note` | a `MediaRef` on the episode audio |

Three transforms, all free, local CPU:

```python
import nw
from braidio.transforms import (
    VIDEO_PANELS_TRANSFORM,      # "video_panels.plan"  episode + stills -> panels
    VIDEO_CUT_RENDER_TRANSFORM,  # "video_cut.render"   panels -> the motion mp4 (minutes)
    VIDEO_CUT_FINISH_TRANSFORM,  # "video_cut.finish"   motion + labels -> the delivered mp4 (seconds)
)
plan = nw.get_transform(VIDEO_PANELS_TRANSFORM)
panels = plan.execute(project, *plan.plan(project, TransformInputs(primary=(episode,)),
                      params={"picks": {"0003": ["eliza-earl"]}})).annotations
render = nw.get_transform(VIDEO_CUT_RENDER_TRANSFORM)
motion = render.execute(project, *render.plan(project, TransformInputs(primary=panels))).annotations[0]
finish = nw.get_transform(VIDEO_CUT_FINISH_TRANSFORM)
cut = finish.execute(project, *finish.plan(project, TransformInputs(primary=(motion,)),
                     params={"label": "v1", "credits_s": 11.0})).annotations[0]
```

Rules that fall out of the shape, each of which cost a real production:

- **Cuts land on the episode's persisted timeline.** `weave_to_episode` now
  writes `EpisodeRenderBodyV1.timeline`; for a project woven before that,
  `braidio.transforms.episode_timeline(project, episode)` reconstructs it
  through the same layout the mixer used. Never eyeball times off a transcript.
- **`still_id` is the still's annotation id, not its artifact id.** Changing
  *which* picture is a patch to the panel; changing the *bytes* is a new still
  with a new `artifact_id`, then that patch. Re-pointing an artifact record in
  place stales nothing (the digest never covers bytes) and ships the wrong
  picture silently.
- **The label lives on the still, so a re-cut cannot drop it.** `labelled` is
  required: `True` needs a `subject`; `False` means "this picture deliberately
  names nobody" (tituli's `UNLABELLED`). A still with no decision is refused.
- **The credit is composed from the parts** (`braidio.bodies.credit_line`),
  never the provider's `attribution` string, and a still with no `license`
  cannot be credited — `video_cut.finish` with `credits_s > 0` raises at plan
  time rather than rolling a credit that names no licence.
- **The move is intent, resolved against the image at render time**
  (`burns.resolve_move`), and `seed` is minted from the beat, not the
  ordinal — so reordering panels, re-weaving, or swapping a still keeps each
  panel's move. A hand-corrected `path` (`BurnsPath.to_dict()`) overrides it.
- **A label edit re-runs only the text pass.** The motion cut's `cache_key`
  covers what reaches a pixel and nothing editorial; after a `subject` edit the
  motion cut reads stale, re-plans to the same key, and is served from the
  cache while `video_cut.finish` re-composites. A move edit re-renders.
- **The planner is one-shot per episode.** Re-running `video_panels.plan` on
  an episode that already has a track returns that track (panels are what you
  edit *after* planning); `force=True` writes a fresh one. After a re-weave,
  carry choices forward with `picks_from_panels(old_panels, index)`.

## Where this stops

braidio owns the cuts because only braidio knows where a beat ends; `burns` owns
the motion. Anything with generated footage, characters, shots or a storyboard is
**`reelee`** — which imports braidio, so the dependency cannot run the other way.
