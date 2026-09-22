# braidio.textprep

Text preparation for scripts — clean OCR’d source, tidy authored lines.

Small, reusable helpers a commentary production reaches for repeatedly:

- [`clean_ocr()`](#braidio.textprep.clean_ocr) — normalize text extracted from PDFs/scans (ligatures,
  soft-hyphens, doubled hyphens, whitespace) so a TTS voice reads it cleanly.
- [`strip_speaker_labels()`](#braidio.textprep.strip_speaker_labels) — drop a leaked `"Host: "` / `"Chris: "`
  prefix that a writing model sometimes prepends and that would otherwise be
  read aloud.

These were duplicated in ad-hoc rendering scripts; they belong here so any
consumer (Hamilton and the next app) shares one implementation.

### Module Attributes

| [`LIGATURES`](#braidio.textprep.LIGATURES)   | Latin ligatures that OCR emits as single code points.   |
|--------------------------------------------------------------|---------------------------------------------------------|

### Functions

| [`clean_ocr`](#braidio.textprep.clean_ocr)(text, \*[, collapse_whitespace])   | Normalize OCR/PDF-extracted text for clean narration.                |
|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------|
| [`strip_speaker_labels`](#braidio.textprep.strip_speaker_labels)(text)                   | Remove a leading speaker-label prefix (e.g. `"Chris: "`) if present. |

### braidio.textprep.LIGATURES *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [str](https://docs.python.org/3/builtins/stdtypes.html#str)]* *= {'ﬀ': 'ff', 'ﬁ': 'fi', 'ﬂ': 'fl', 'ﬃ': 'ffi', 'ﬄ': 'ffl', 'ﬅ': 'ft', 'ﬆ': 'st'}*

Latin ligatures that OCR emits as single code points.

### braidio.textprep.clean_ocr(text, , collapse_whitespace=True)

Normalize OCR/PDF-extracted text for clean narration.

Expands ligatures, removes soft-hyphens (used at scan line-breaks), turns a
doubled hyphen `--` into an em-dash (so TTS phrases it as a pause), and
(by default) collapses runs of whitespace to single spaces.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)

### braidio.textprep.strip_speaker_labels(text)

Remove a leading speaker-label prefix (e.g. `"Chris: "`) if present.

Only strips a single leading `Word:` / `Host:` style label so it isn’t
read aloud; leaves colons that are part of the sentence untouched.

* **Return type:**
  [`str`](https://docs.python.org/3/builtins/stdtypes.html#str)
