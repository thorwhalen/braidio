# braidio.style

Style audit — flag the recycled rhetorical tics in commentary text.

The companion, in code, to `misc/docs/style/anti-platitude-checklist.md`: scan
authored commentary for the empty structural platitudes a writing model falls
back on, so a production can self-check (and measure) instead of eyeballing.

> from braidio.style import audit_platitudes, platitude_rate
> findings = audit_platitudes(commentary_text)   # [{pattern, match, start}, …]
> rate = platitude_rate(commentary_text)          # flagged hits per 1000 words

Not every match is a crime — the guide says these moves are fine *sparingly*; the
value is the RATE and which patterns dominate. Chiasmus (“the X that did Y is the
X that does Z”) isn’t reliably regex-detectable and is intentionally omitted.

### Module Attributes

| [`PLATITUDE_PATTERNS`](#braidio.style.PLATITUDE_PATTERNS)   | name → compiled pattern for the detectable overused moves.   |
|-----------------------------------------------------------------------|--------------------------------------------------------------|

### Functions

| [`audit_platitudes`](#braidio.style.audit_platitudes)(text)          | Return every [`Finding`](#braidio.style.Finding) in `text`, in document order.   |
|----------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------------|
| [`platitude_rate`](#braidio.style.platitude_rate)(text, \*[, per]) | Flagged hits per `per` words (default 1000).                                                          |

### Classes

| [`Finding`](#braidio.style.Finding)(pattern, match, start)   | One flagged platitude.   |
|-----------------------------------------------------------------------------------|--------------------------|

### *class* braidio.style.Finding(pattern, match, start)

Bases: [`object`](https://docs.python.org/3/builtins/functions.html#object)

One flagged platitude.

### braidio.style.PLATITUDE_PATTERNS *: [dict](https://docs.python.org/3/builtins/stdtypes.html#dict)[[str](https://docs.python.org/3/builtins/stdtypes.html#str), [Pattern](https://docs.python.org/3/library/re.html#re.Pattern)]* *= {'director-cue': re.compile('\\\\b(?:listen to|notice|watch|catch)\\\\s+(?:how|what|the)\\\\b', re.IGNORECASE), 'heres-the': re.compile("\\\\bhere'?s the\\\\b", re.IGNORECASE), 'machinery-naming': re.compile('\\\\bthe (?:turn|tell|button|trick|move|thesis)\\\\b', re.IGNORECASE), 'negation-just': re.compile("\\\\bisn'?t just\\\\b", re.IGNORECASE), 'reduction': re.compile("\\\\b(?:that'?s the whole|the whole \\\\w+ in|in (?:two|three|four|five|six|seven|eight|nine|ten|\\\\d+) words)\\\\b", re.IGNORECASE)}*

name → compiled pattern for the detectable overused moves.

### braidio.style.audit_platitudes(text)

Return every [`Finding`](#braidio.style.Finding) in `text`, in document order.

* **Return type:**
  [`list`](https://docs.python.org/3/builtins/stdtypes.html#list)[[`Finding`](#braidio.style.Finding)]

### braidio.style.platitude_rate(text, , per=1000)

Flagged hits per `per` words (default 1000). 0.0 for empty text.

* **Return type:**
  [`float`](https://docs.python.org/3/builtins/functions.html#float)
