"""Tests for text prep + style audit. Audio-free / API-free."""

from __future__ import annotations

from braidio.style import audit_platitudes, platitude_rate
from braidio.textprep import clean_ocr, strip_speaker_labels


def test_clean_ocr_ligatures_and_soft_hyphens():
    assert clean_ocr("de­fenﬁce of the ﬂag") == "defence of the flag"
    assert clean_ocr("A -- B") == "A — B"                 # doubled hyphen → em-dash
    assert clean_ocr("a\n\n  b\t c") == "a b c"           # whitespace collapsed


def test_clean_ocr_can_keep_whitespace():
    assert clean_ocr("a\nb", collapse_whitespace=False) == "a\nb"


def test_strip_speaker_labels():
    assert strip_speaker_labels("Chris: hello there") == "hello there"
    assert strip_speaker_labels("Narrator:  it begins") == "it begins"
    # a colon mid-sentence is left alone
    assert strip_speaker_labels("The issue: money") == "The issue: money"
    assert strip_speaker_labels("no label here") == "no label here"


def test_audit_flags_known_tics_in_order():
    t = ("Listen to how the bass enters. Here's the thing: it isn't just a chord. "
         "That's the whole song in seven words. Feel the turn.")
    f = audit_platitudes(t)
    names = [x.pattern for x in f]
    assert "director-cue" in names and "heres-the" in names
    assert "negation-just" in names and "reduction" in names and "machinery-naming" in names
    # ordered by position in the text
    assert [x.start for x in f] == sorted(x.start for x in f)


def test_clean_commentary_scores_zero():
    clean = ("Jefferson opens by quoting the Declaration he wrote. The music bends "
             "into a Caribbean lilt on the word immigrant. He answers her love with a to-do list.")
    assert audit_platitudes(clean) == []
    assert platitude_rate(clean) == 0.0


def test_platitude_rate_per_1000_words():
    # one flagged hit in 10 words → 100 per 1000
    assert platitude_rate("here's the deal and then some more filler words here now") == 100.0
    assert platitude_rate("") == 0.0
