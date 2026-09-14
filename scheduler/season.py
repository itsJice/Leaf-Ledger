"""Which Christmas season a date belongs to.

This used to be a byte-for-byte duplicate of backend/app/libs/season.py,
kept in sync by hand, because the build pipeline runs outside the deployed
backend image and couldn't import it -- see the old RULES.md warning
("scheduler/season.py holds the same rule for the build pipeline... change
both together; backend/tests/test_season.py checks they agree").

It still can't import the backend as an installed package, but backend/ is
a sibling directory in this same repo checkout, so putting it on sys.path
and importing the real module directly costs nothing and removes the
by-hand-duplicate risk entirely: there is now exactly one implementation,
and this file is a re-export of it.

A season runs October through the following January: installs Oct-Dec,
takedowns spilling into January. The season is named for the year its
October falls in, so January still belongs to the season that started the
previous autumn -- on 15 Jan 2027 the crews are finishing the 2026 season,
not starting 2027. The rollover boundary is 1 February.

    2026-09-02 -> 2026   (planning the coming season)
    2027-01-15 -> 2026   (still finishing it)
    2027-02-01 -> 2027   (rolled over)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "backend"))

# Importing app.libs.season must not (and does not) pull in FastAPI or the
# DB: backend/app/__init__.py doesn't exist (an implicit namespace package)
# and backend/app/libs/__init__.py is empty, so nothing runs on import
# beyond this one module.
from app.libs.season import *  # noqa: F401,F403,E402

# Explicit re-export of every name scheduler/*.py imports from `season`
# (`import season` then `season.<name>`, or `from season import <name>`):
# prep.py, schedule.py, rules.py, build_review.py and the callers that used
# to have their own current_season() (now scheduler/common.py) between them
# use all of these. `import *` above already binds them; listed again here
# so a linter (and a human) can see the public surface without reading
# app/libs/season.py.
from app.libs.season import (  # noqa: F401,E402
    SEASON_START_MONTH,
    SEASON_END_MONTH,
    ROLLOVER_MONTH,
    season_for,
    season_span,
    season_of_date,
    year_of_month,
    takedown_cutoff,
    nth_weekday,
    thanksgiving,
    black_friday,
    sunday_after_thanksgiving,
)
