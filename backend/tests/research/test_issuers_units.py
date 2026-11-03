"""Unit checks for the figure a "which" clause is compared with (Phase 4Q review round). SYNTHETIC sentences.

The verifier has other checks that can reject these sentences too, so the issuer function is tested directly: a figure it
cannot read must still block, whatever the unit, spelling or separator.
"""

import pytest

from nzstats.research import issuers

BLOCKS = [
    ("We expect output of ", "$3.5 billion in 2029, which the IMF expects to be 3.5 billion."),
    ("We expect output of ", "$3.5 billion in 2029, which the IMF expects to be $3.5 billion."),
    ("We expect output of ", "$1,500 million in 2029, which the IMF expects to be $1,500 million."),
    ("We expect inflation of ", "1,500% in 2029, which the IMF expects to be 1,500%."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be 3 percentage points."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be three per cent."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be 3."),
    ("We note growth of ", "3% in 2029, which the IMF expects to remain unchanged."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to stay at that level."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be unchanged."),
    ("We expect growth of ", "3% in 2029, which the IMF expected would be maintained."),
    # The comment must be all of the clause: a year that is "the same" or "of unchanged growth" keeps the figure.
    ("We expect growth of ", "3% in 2029, which the IMF expects to be the case this year."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be the same this year."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be a year of unchanged growth."),
    (
        "We expect growth of ",
        "3% in 2029, which the IMF expects to be a challenging year of unchanged growth.",
    ),
]
PASSES = [
    ("We expect growth of ", "3% in 2029, which the IMF expects to be 2 percentage points."),
    ("We expect inflation of ", "1,500% in 2029, which the IMF expects to be 2,500%."),
    ("We expect output of ", "$3.5 billion in 2029, which the IMF expects to be $4.5 billion."),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be a challenging year."),
    (
        "We expect growth of ",
        "3% in 2029, which the IMF expects to be a very challenging year in 2029.",
    ),
    ("We expect growth of ", "3% in 2029, which the IMF expects to be a tough and uncertain year."),
]


@pytest.mark.parametrize(("before", "after"), BLOCKS)
def test_a_figure_in_any_unit_is_still_the_imfs(before, after):
    assert issuers.third_parties_around(before, after, "treasury") == {"imf"}


@pytest.mark.parametrize(("before", "after"), PASSES)
def test_a_different_figure_or_none_is_not(before, after):
    assert issuers.third_parties_around(before, after, "treasury") == set()
