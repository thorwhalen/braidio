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
same-subject deduplication.

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
    return_timeline=True,          # no delivery/config overrides needed
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

Both bit on a real episode; the user's words were *"the pace is a bit robotic and
without pause and the expressions are a bit kitsch."*

**1. Write the performance into the text.** On a v3 delivery the script is the
control surface: inline `[audio tags]` (`[slowly]` on a punchline, `[rushed]` on
an aside, `[pause]` where a breath belongs) and punctuation (em-dash flows, `…`
adds weight, a period is a full stop). Sparingly — a tag on every sentence is the
"kitsch" half of that complaint.

**2. Epigram density is the actual tell.** A first draft landed a designed turn of
phrase at the end of *every* beat — 8 in 338 words. No speaking human sustains
that; it is the relentlessness, not any one sentence. Budget **≤ 2 per 3 minutes**
and let the rest be plain exposition with contractions and uneven sentence length.

`audit_platitudes` returns `[]` on copy like that — it catches recycled tics, not
over-writing. It cannot be the only gate.

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
still was too dark to read. Also watch for museum catalogue shots carrying scale
bars and accession stamps — on screen those read as a rights claim over your
whole frame. Crop them. And a transparent source (an SVG rendered to PNG, a
signature in black ink on nothing) flattens to an entirely black frame under a
naive `convert("RGB")`.

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

## Where this stops

braidio owns the cuts because only braidio knows where a beat ends; `burns` owns
the motion. Anything with generated footage, characters, shots or a storyboard is
**`reelee`** — which imports braidio, so the dependency cannot run the other way.
