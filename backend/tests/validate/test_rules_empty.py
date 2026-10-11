"""A required series that is present but empty must fail validation, never pass by omission."""

import pytest

from nzstats.adapters.migration import series as S
from nzstats.validate.rules import REQUIRED
from tests.validate.test_rules import _ps, _rules, good_bundle, run

DEFS = {
    "mig.m.arrivals": S.monthly_def("arrivals"),
    "mig.m.departures": S.monthly_def("departures"),
    "mig.m.net": S.monthly_def("net"),
    "mig.ry.arrivals": S.rolling_def("arrivals"),
    "mig.ry.departures": S.rolling_def("departures"),
    "mig.ry.net": S.rolling_def("net"),
    "mig.ry.net.nz": S.rolling_def("net", "nz"),
    "mig.ry.net.nonnz": S.rolling_def("net", "nonnz"),
    "mig.m.arrivals.nz": S.citizenship_monthly_def("nz"),
    "mig.m.arrivals.nonnz": S.citizenship_monthly_def("nonnz"),
}


@pytest.mark.parametrize("key", REQUIRED)
def test_empty_required_series_is_an_error(key) -> None:
    findings = run(good_bundle(**{key: _ps(DEFS[key], {})}))
    assert "empty_series" in _rules(findings)
