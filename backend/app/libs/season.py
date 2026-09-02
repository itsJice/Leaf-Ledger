"""Which Christmas season a date belongs to.

A season runs October through the following January: installs Oct-Dec,
takedowns spilling into January. The season is named for the year its October
falls in, so January still belongs to the season that started the previous
autumn -- on 15 Jan 2027 the crews are finishing the 2026 season, not starting
2027.

The boundary is 1 February. Before it, the current season is last October's; on
and after it, planning has moved to the coming autumn. That is what makes the
rollover automatic -- nobody has to remember to change a year.

    2026-09-02 -> 2026   (planning the coming season)
    2027-01-15 -> 2026   (still finishing it)
    2027-02-01 -> 2027   (rolled over)

NOTE: scheduler/season.py holds the same rule for the build pipeline, which
runs outside the deployed image and cannot import this one. Change both
together; backend/tests/test_season.py checks they agree.
"""

from __future__ import annotations

import datetime

SEASON_START_MONTH = 10   # October
SEASON_END_MONTH = 1      # through January
ROLLOVER_MONTH = 2        # 1 Feb: "next season" becomes "this season"


def season_for(today: datetime.date | None = None) -> int:
    """The season year `today` falls in (defaults to the real today)."""
    d = today or datetime.date.today()
    return d.year if d.month >= ROLLOVER_MONTH else d.year - 1


def season_span(season: int) -> tuple[datetime.date, datetime.date]:
    """(first day, last day) of a season -- 1 Oct through 31 Jan."""
    return (datetime.date(season, SEASON_START_MONTH, 1),
            datetime.date(season + 1, SEASON_END_MONTH, 31))


def season_of_date(iso: str) -> int:
    """The season an ISO date string belongs to."""
    return season_for(datetime.date.fromisoformat(iso[:10]))


def year_of_month(season: int, month: int) -> int:
    """Calendar year of a month within a season -- January is the year after."""
    return season + 1 if month < SEASON_START_MONTH else season


def takedown_cutoff(season: int) -> datetime.date:
    """Installs run through Christmas; anything later is takedown."""
    return datetime.date(season, 12, 25)


def nth_weekday(year: int, month: int, weekday: int, n: int) -> datetime.date:
    """The nth given weekday of a month. weekday: Mon=0 .. Sun=6."""
    d = datetime.date(year, month, 1)
    offset = (weekday - d.weekday()) % 7
    return d + datetime.timedelta(days=offset + 7 * (n - 1))


def thanksgiving(season: int) -> datetime.date:
    """US Thanksgiving -- the 4th Thursday of November."""
    return nth_weekday(season, 11, 3, 4)


def black_friday(season: int) -> datetime.date:
    return thanksgiving(season) + datetime.timedelta(days=1)


def sunday_after_thanksgiving(season: int) -> datetime.date:
    return thanksgiving(season) + datetime.timedelta(days=3)
