"""Expected calendar refreshes are Auckland 06:00 instants: correct across both daylight-saving changes."""

from datetime import UTC, datetime, timedelta

import pytest

from nzstats.clock import AKL
from nzstats.ops.schedule import last_refresh_due, missed_refreshes, next_refresh_due
from nzstats.scheduler.jobs import build_scheduler

GRACE = timedelta(hours=2)


def utc(*args: int) -> datetime:
    return datetime(*args, tzinfo=UTC)


def test_the_refresh_instants_follow_local_time_not_a_fixed_utc_offset() -> None:
    # NZ daylight time began Sun 27 Sep 2026 at 02:00 NZST: 06:00 is +12:00 on the 26th and +13:00 on the 27th.
    assert last_refresh_due(utc(2026, 9, 26, 16, 59)) == utc(2026, 9, 25, 18, 0)
    assert last_refresh_due(utc(2026, 9, 26, 17, 0)) == utc(2026, 9, 26, 17, 0)
    assert last_refresh_due(utc(2026, 9, 26, 17, 0)).astimezone(AKL).hour == 6
    assert next_refresh_due(utc(2026, 9, 26, 17, 0)) == utc(2026, 9, 27, 17, 0)


def test_the_gap_between_refreshes_is_23_hours_into_dst_and_25_hours_out_of_it() -> None:
    into = next_refresh_due(utc(2026, 9, 25, 18, 0)) - utc(2026, 9, 25, 18, 0)
    # NZ daylight time ended Sun 4 Apr 2027 at 03:00 NZDT.
    out_of = next_refresh_due(utc(2027, 4, 2, 17, 0)) - utc(2027, 4, 2, 17, 0)
    assert (into, out_of) == (timedelta(hours=23), timedelta(hours=25))


@pytest.mark.parametrize(
    ("last_success", "now", "missed"),
    [
        # Succeeded at 06:00:30 NZST on 26 Sep. At 08:05 NZDT next day the 27th's refresh is 2 h late and unrun.
        # Only 25 h have passed, so a "24 h + grace" rule would call this healthy: it is not.
        (utc(2026, 9, 25, 18, 0, 30), utc(2026, 9, 26, 19, 5), 1),
        (utc(2026, 9, 25, 18, 0, 30), utc(2026, 9, 26, 18, 59), 0),  # still inside the grace window
        (utc(2026, 9, 26, 17, 0, 30), utc(2026, 9, 26, 19, 5), 0),  # the 27th's refresh ran
        # Out of daylight time: the 25-hour day. Refresh ran 06:00:30 NZDT on 3 Apr; 4 Apr's is due 18:00Z on the 3rd.
        (utc(2027, 4, 2, 17, 0, 30), utc(2027, 4, 3, 19, 59), 0),
        (utc(2027, 4, 2, 17, 0, 30), utc(2027, 4, 3, 20, 1), 1),
        (utc(2027, 4, 3, 18, 0, 30), utc(2027, 4, 3, 20, 1), 0),
    ],
)
def test_missed_refreshes_across_daylight_saving_changes(last_success, now, missed) -> None:
    assert missed_refreshes(last_success, now, GRACE) == missed


def test_a_laptop_asleep_through_three_mornings_misses_three_refreshes() -> None:
    last = utc(2026, 10, 25, 17, 0, 30)  # ran 06:00 NZDT Mon 26 Oct
    # 07:00 Fri 30 Oct: Tue, Wed and Thu mornings are missed; Friday's is still inside its grace window.
    assert missed_refreshes(last, utc(2026, 10, 29, 18, 0), GRACE) == 3


def test_a_success_before_a_due_instant_does_not_cover_it() -> None:
    # 16:59Z is one minute before Mon 26 Oct's 06:00 NZDT, so that morning is missed; Tue's is within grace at 07:00.
    assert missed_refreshes(utc(2026, 10, 25, 16, 59), utc(2026, 10, 26, 18, 0), GRACE) == 1


def test_no_success_at_all_is_capped_by_the_horizon() -> None:
    assert missed_refreshes(None, utc(2026, 10, 30, 3, 0), GRACE, horizon_days=5) == 5


def test_the_scheduled_refresh_is_the_one_the_health_check_expects(rt) -> None:
    trigger = build_scheduler(rt).get_job("refresh_calendar").trigger
    fields = {f.name: str(f) for f in trigger.fields}
    expected = last_refresh_due(utc(2026, 10, 30, 3, 0)).astimezone(AKL)
    assert (fields["hour"], fields["minute"]) == (str(expected.hour), str(expected.minute))
    assert str(trigger.timezone) == "Pacific/Auckland"
