"""The credits card must not silently drop an attribution.

`credits_card`'s own docstring calls the card "part of the licence compliance,
not decoration" — and then, at a fixed 31px leading, ran the tail of a long roll
off the bottom of the frame and drew the footer over what was left. A real
43-image film credited 28 of them and looked entirely fine.

That is the failure mode these tests exist for: not a crash, not a wrong pixel,
but content quietly missing from a compliance artifact.

Run: ``python -m pytest tests/test_credits_card.py -q``
"""

from __future__ import annotations

import numpy as np
import pytest
from PIL import Image

from braidio.video import credits_card

CARD = (1920, 1080)


def roll(n: int, *, width: int = 60) -> list[str]:
    return [f"{i:03d} " + "x" * width for i in range(n)]


def ink_rows(path) -> np.ndarray:
    """Per-row count of non-background pixels — where anything was drawn."""
    array = np.asarray(Image.open(path).convert("L"))
    return (array > 40).sum(axis=1)


class TestEverythingFitsInsideTheFrame:
    @pytest.mark.parametrize("count", [5, 20, 28, 43, 60])
    def test_no_line_is_drawn_past_the_bottom(self, tmp_path, count):
        path = credits_card(
            roll(count),
            tmp_path / f"c{count}.jpg",
            heading="Images",
            footer="footer",
            size=CARD,
        )
        rows = ink_rows(path)
        # The last 20 rows must be clear — anything there has run off the edge.
        assert rows[-20:].sum() == 0

    def test_a_long_roll_still_draws_every_line(self, tmp_path):
        """The regression: 43 lines used to render as 28."""
        few = ink_rows(credits_card(roll(8), tmp_path / "few.jpg", size=CARD))
        many = ink_rows(credits_card(roll(43), tmp_path / "many.jpg", size=CARD))

        # Count distinct text bands rather than pixels, which vary with type size.
        def bands(rows):
            return sum(1 for a, b in zip(rows, rows[1:]) if a == 0 and b > 0)

        assert bands(many) >= 43, f"only {bands(many)} lines drawn"
        assert bands(few) >= 8

    def test_the_footer_does_not_overlap_the_roll(self, tmp_path):
        path = credits_card(
            roll(43),
            tmp_path / "c.jpg",
            heading="Images",
            footer="a footer line",
            size=CARD,
        )
        rows = ink_rows(path)
        # There must be a clear gap between the last credit and the footer.
        footer_top = 1080 - 96
        assert rows[footer_top - 12 : footer_top].sum() == 0

    def test_text_stays_inside_the_left_and_right_margins(self, tmp_path):
        path = credits_card(roll(43, width=90), tmp_path / "c.jpg", size=CARD)
        array = np.asarray(Image.open(path).convert("L"))
        columns = (array > 40).sum(axis=0)
        assert columns[:90].sum() == 0
        assert columns[-90:].sum() == 0


class TestItRefusesRatherThanTruncates:
    def test_an_impossible_roll_raises(self, tmp_path):
        """Better a loud failure than a card missing half its attributions."""
        with pytest.raises(ValueError, match="will not fit"):
            credits_card(roll(400), tmp_path / "c.jpg", size=(640, 360))

    def test_the_message_says_what_to_do(self, tmp_path):
        with pytest.raises(ValueError) as excinfo:
            credits_card(roll(400), tmp_path / "c.jpg", size=(640, 360))
        assert "licence" in str(excinfo.value)


class TestSmallRollsAreUnchanged:
    def test_a_short_roll_keeps_the_generous_setting(self, tmp_path):
        """Fitting must not shrink type that never needed shrinking."""
        small = ink_rows(credits_card(roll(6), tmp_path / "a.jpg", size=CARD))
        large = ink_rows(credits_card(roll(43), tmp_path / "b.jpg", size=CARD))

        def first_gap(rows):
            starts = [
                i for i, (a, b) in enumerate(zip(rows, rows[1:])) if a == 0 and b > 0
            ]
            return starts[2] - starts[1]

        assert first_gap(small) > first_gap(large)
