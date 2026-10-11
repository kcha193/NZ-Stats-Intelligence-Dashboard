import pytest

from nzstats.insights.format import dir_word, fmt_int, fmt_net, fmt_signed


@pytest.mark.parametrize(
    ("v", "text"), [(20350.0, "20,350"), (0.0, "0"), (-38335.4, "-38,335"), (999.5, "1,000")]
)
def test_fmt_int(v, text) -> None:
    assert fmt_int(v) == text


def test_fmt_signed() -> None:
    assert fmt_signed(12.0) == "+12"
    assert fmt_signed(-12.0) == "-12"
    assert fmt_signed(0.0) == "0"


def test_fmt_net_words() -> None:
    assert fmt_net(20350.0) == "a net gain of 20,350 people"
    assert fmt_net(-38335.0) == "a net loss of 38,335 people"
    assert fmt_net(0.0) == "no net change"


def test_dir_word() -> None:
    assert (dir_word(5.0), dir_word(-5.0), dir_word(0.0)) == ("rose", "fell", "was unchanged")
