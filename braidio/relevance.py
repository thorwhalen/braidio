"""How well a still relates to the words spoken over it — the scorer seam.

A picture track used to be placed with no recorded reason and no check, so an
off-topic still could not be explained, caught or tuned (thorwhalen/braidio#85:
a Dylan portrait over a sentence that no longer mentioned Dylan, a Beach Boys
frame under a tag naming a different concert). ``video_panels.plan`` now scores
every placement against its ``anchor_text`` through a **scorer**, and this
module is where scorers live.

A scorer has the shape of ``illustration``'s reranking ``Scorer`` —
``(query, items) -> scores`` — with the anchor text as the query and still
*bodies* (plain dicts) as the items, one score in ``[0, 1]`` per still. Batch
by design, so a model-backed scorer (illustration's SigLIP rerank, its VLM
judge) embeds the text once per span, not once per candidate.

The default, :func:`lexical_relevance`, needs nothing installed: the share of a
still's naming words (``subject``, ``title``, ``key``) that the anchor text
actually says. It is deliberately literal — it cannot see that a studio console
suits "Tom Wilson booked a rhythm section" — so a low score means *the words do
not name this picture*, which is the question a disclaimer or a decorative role
has to answer, not a verdict that the picture is bad.

Examples:
    >>> dylan = {"key": "dylan-1965", "subject": "Bob Dylan, 1965"}
    >>> said = "the same day as the sessions for Bob Dylan's Like a Rolling Stone"
    >>> round(lexical_relevance(said, [dylan])[0], 2)
    0.67
    >>> lexical_relevance("overdubbed electric guitar onto the tape", [dylan])
    [0.0]
    >>> resolve_scorer("lexical") is lexical_relevance
    True
"""

from __future__ import annotations

import re
from typing import Callable, Mapping, Sequence, Union

__all__ = [
    "DEFAULT_SCORER",
    "RELEVANCE_SCORERS",
    "RelevanceScorer",
    "lexical_relevance",
    "register_relevance_scorer",
    "resolve_scorer",
    "scorer_id",
]

RelevanceScorer = Callable[[str, Sequence[Mapping]], Sequence[float]]
"""``(anchor_text, still_bodies) -> one score in [0, 1] per still``."""

#: The still fields that NAME the picture. ``about`` and ``note`` are prose
#: about it (and ``note`` is rejection reasoning), so they would reward a
#: still for being discussed rather than for being what is said.
NAMING_FIELDS: tuple[str, ...] = ("subject", "title", "key")

_WORD = re.compile(r"[a-z0-9]+")
#: Words that name nothing. Small on purpose: this is our own authored text.
_STOPWORDS = frozenset(
    "a an and are as at be by for from has have in into is it its of on or "
    "that the their this to was were with not jpg jpeg png file category".split()
)
#: Shorter tokens are initials or noise ("s" of a possessive, "b" of "b&w").
_MIN_TOKEN_LEN = 2
#: Only strip a plural ``s`` from words long enough to have one.
_MIN_PLURAL_LEN = 4


def _tokens(text: str) -> set[str]:
    """Content words of ``text``, lower-cased, possessives and plurals folded.

    >>> sorted(_tokens("Bob Dylan's sessions, 1965"))
    ['1965', 'bob', 'dylan', 'session']
    """
    out = set()
    for w in _WORD.findall((text or "").lower().replace("'s", "")):
        if len(w) < _MIN_TOKEN_LEN or w in _STOPWORDS:
            continue
        if len(w) >= _MIN_PLURAL_LEN and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out


def lexical_relevance(anchor_text: str, stills: Sequence[Mapping]) -> list[float]:
    """Per still: the best share of a naming field's words that ``anchor_text`` says.

    The maximum over :data:`NAMING_FIELDS`, so a long Commons title does not
    dilute a short, exact subject.

    >>> beach = {"key": "central-park-decay",
    ...          "subject": "The Beach Boys in Central Park, 1971",
    ...          "title": "Beach Boys Good Vibrations from Central Park 1971"}
    >>> lexical_relevance("half a million people all getting the joke", [beach])
    [0.0]
    """
    said = _tokens(anchor_text)
    scores = []
    for body in stills:
        best = 0.0
        for field in NAMING_FIELDS:
            words = _tokens(str(body.get(field) or ""))
            if words:
                best = max(best, len(words & said) / len(words))
        scores.append(best)
    return scores


#: Registered scorers by id. The id is what a panel records in ``scorer``.
RELEVANCE_SCORERS: dict[str, RelevanceScorer] = {"lexical": lexical_relevance}
DEFAULT_SCORER = "lexical"


def register_relevance_scorer(name: str, scorer: RelevanceScorer) -> None:
    """Make ``scorer`` addressable by ``name`` (e.g. an illustration rerank adapter).

    >>> register_relevance_scorer("lexical", lexical_relevance)  # idempotent
    """
    if not callable(scorer):
        raise TypeError(f"relevance scorer {name!r} must be callable")
    RELEVANCE_SCORERS[str(name)] = scorer


def resolve_scorer(spec: Union[str, RelevanceScorer, None]) -> RelevanceScorer:
    """A scorer from a registered name, a callable, or ``None`` (the default)."""
    if spec is None:
        spec = DEFAULT_SCORER
    if callable(spec):
        return spec
    try:
        return RELEVANCE_SCORERS[str(spec)]
    except KeyError:
        raise ValueError(
            f"unknown relevance scorer {spec!r}; registered: "
            f"{sorted(RELEVANCE_SCORERS)} (or pass a callable)"
        ) from None


def scorer_id(spec: Union[str, RelevanceScorer, None]) -> str:
    """The id a panel records for ``spec``: its registered name, else its qualname.

    >>> scorer_id(None), scorer_id(lexical_relevance)
    ('lexical', 'lexical')
    """
    if spec is None:
        return DEFAULT_SCORER
    if not callable(spec):
        return str(spec)
    for name, fn in RELEVANCE_SCORERS.items():
        if fn is spec:
            return name
    return getattr(spec, "__qualname__", None) or type(spec).__name__
