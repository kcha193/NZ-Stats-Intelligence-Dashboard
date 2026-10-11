import pytest

from nzstats.domain import Adjustment, Frequency, SeriesDef
from nzstats.stats.compat import IncompatibleSeries, check_compatible, compatible


def _s(key: str, **kw) -> SeriesDef:
    base = dict(
        key=key,
        name=key,
        unit="people",
        frequency=Frequency.MONTHLY,
        adjustment=Adjustment.NONE,
        definition="d",
        definition_id="mig",
        category="migration",
    )
    base.update(kw)
    return SeriesDef(**base)


def test_same_concept_is_compatible() -> None:
    assert compatible(_s("a"), _s("b"))


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"frequency": Frequency.ROLLING_ANNUAL}, "frequency"),
        ({"unit": "percent"}, "unit"),
        ({"adjustment": Adjustment.SEASONALLY_ADJUSTED}, "adjustment"),
        ({"definition_id": "other"}, "definition"),
    ],
)
def test_incompatible_reasons(override, reason) -> None:
    with pytest.raises(IncompatibleSeries, match=reason):
        check_compatible(_s("a"), _s("b", **override))
    assert not compatible(_s("a"), _s("b", **override))
