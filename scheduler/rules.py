#!/usr/bin/env python3
"""
TBDG scheduling RULES -- the single source of truth for what is legal.

`schedule.py` is a CONSTRUCTOR: ~90% of it is bin packing, DP over cut
positions and brute-force night grouping. You cannot mechanically derive a
validator from a constructor, so this module does not try. It holds the
rules as PREDICATES, which is what `validate.py` had been expressing
inline, and both `validate.py` and `build_review.py` now import from here.

The split that makes the review tool's guardrails possible:

  STATIC rules depend only on (client, date, crew). They are pure
  functions, so `build_review.py` evaluates them ahead of time for every
  (client x date x crew) combination and ships the ANSWER into the browser
  as a lookup table. There is no second implementation in JavaScript, so
  there is nothing to drift.

  DYNAMIC rules depend on what a day currently contains (the 30-minute
  radius, the day window, group cohesion). Those necessarily live in the
  browser because they change as the user edits -- but they are arithmetic
  and structure, not business prose, which is the cheap half to mirror.

Everything here is LOCAL: expressible over one client against one
(date, crew). No rule needs a global re-solve, which is precisely why
constraint-checking a proposed move is tractable in the UI.
"""
import datetime

import schedule as S

# ---------------------------------------------------------------------------
# Blocker codes. Anything in BLOCKERS is a hard NO; WARNINGS are advisory.
# The UI shows `msg`; `rule` ties it back to the validate.py check name.
# ---------------------------------------------------------------------------
# `soft` marks a rule that constrains how the scheduler BUILDS the base
# schedule but must not stop a human accommodating an explicit client
# request. The Saturday rules are the case in point: the scheduler should
# never put someone on a Saturday unprompted, but if the client rings up
# and asks for one, that is the client choosing it. validate.py still
# enforces these strictly against generated output; only the review tool
# treats them as "confirm this" rather than "no".
CODES = {
    "MC_DATE":    ("R1",  "Mi Cocina restaurants only run the Dallas nights, Nov 2-6", False),
    "MC_ONLY":    ("R1",  "Nov 2-6 is the Dallas Mi Cocina week -- nothing else is scheduled", False),
    "NOT_MC":     ("R1",  "Only Mi Cocina restaurants belong on a Dallas night", False),
    "CLUB_CREW":  ("R2",  "Country club jobs need Crew 1", False),
    "BANK_DATE":  ("R3",  "All 8 Capital Banks are pinned to Fri Nov 27", False),
    "BANK_ONLY":  ("R3",  "Fri Nov 27 is the Capital Bank run", False),
    "ROTARY":     ("R4",  "Rotary House is the Sunday Nov 29 exception", False),
    "SUNDAY":     ("R4",  "Nobody works Sunday except Rotary House on Nov 29", False),
    "BIZ_SAT":    ("R7",  "A business on a Saturday — confirm they'll be open", True),
    "SAT_HIST":   ("R12", "Didn't work a Saturday in 2025 — confirm the client wants one", True),
    "LOCKED":     ("PIN", "Client has deposited and reserved this date", False),
    "DROPPED":    ("DROP", "No 2026 install for this client", False),
    "NO_DATE":    ("CAL", "Not a working date", False),
    "THANKS":     ("CAL", "Thanksgiving", False),
    # PAST is never computed server-side (it depends on the real calendar
    # date when someone opens the tool, which build time can't know) --
    # listed here only so its message text has one home, same as every
    # other code.
    "PAST":       ("CAL", "Too early to move it there", False),
}
SOFT_CODES = {k for k, v in CODES.items() if v[2]}


def code_msg(code):
    return CODES.get(code, ("?", code, False))[1]


def is_soft(code):
    return code in SOFT_CODES


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------
THANKSGIVING = "2026-11-26"


def calendar():
    """Every date the business could legally work, with its kind.

    The review tool previously derived its date list from days that already
    had crews assigned, which silently hid 10 legal dates -- including the
    open days deliberately left in the schedule. A client asking for one of
    those could not be accommodated because the UI had no way to express it.
    """
    out = []
    for date in sorted(S.DOW):
        dow = S.DOW[date]
        if date in S.DALLAS_DAYS:
            kind = "dallas_night"
        elif date == S.BANK_FRIDAY:
            kind = "bank_friday"
        elif date == S.ROTARY_SUNDAY:
            kind = "rotary_sunday"
        elif date in S.SATURDAYS:
            kind = "saturday"
        elif date in S.OVERFLOW_TAIL:
            kind = "overflow_tail"
        elif date in S.STD_WEEKDAYS:
            kind = "hou_weekday"
        else:
            kind = "unused"
        out.append({"date": date, "dow": dow, "kind": kind,
                    "crews": list(S.CREWS)})
    return out


def was_saturday(iso):
    """Their 2025 install fell on a Saturday (drives R12)."""
    if not iso or len(iso) < 10:
        return False
    try:
        return datetime.date.fromisoformat(iso[:10]).weekday() == 5
    except ValueError:
        return False


# ---------------------------------------------------------------------------
# STATIC eligibility -- pure over (client, date, crew)
# ---------------------------------------------------------------------------
def static_blockers(c, date, crew, dow=None, kind=None):
    """Hard reasons this client cannot be worked on this date by this crew.

    Returns a list of codes; empty means the slot is statically legal (a
    dynamic check on the target day's contents still applies).
    """
    if dow is None:
        dow = S.DOW.get(date, "?")
    if kind is None:
        kind = next((d["kind"] for d in calendar() if d["date"] == date), "unused")

    out = []
    cat = c.get("category")
    biz = c.get("business")

    if c.get("install_2026_no_install"):
        out.append("DROPPED")
    if date == THANKSGIVING:
        out.append("THANKS")
    if kind == "unused":
        out.append("NO_DATE")

    # R1 -- the Dallas week is a closed system in both directions.
    if cat == "M Crowd":
        if date not in S.DALLAS_DAYS:
            out.append("MC_DATE")
    else:
        if date in S.DALLAS_DAYS:
            out.append("MC_ONLY")
        elif "2026-11-01" <= date <= "2026-11-07":
            out.append("MC_ONLY")
    if kind == "dallas_night" and cat != "M Crowd":
        out.append("NOT_MC")

    # R2 (country clubs need Crew 1) is deliberately NOT here. It is a
    # COVERAGE rule, not a per-card rule: joint days put the same stop on
    # two crews' cards, so "Crew 1 is among the crews working this stop
    # that day" can be true while this particular card is Crew 2. Checked
    # dynamically instead -- see `club_crew_ok`.

    # R3 -- the banks are one pinned run.
    if cat == "Capital Bank" and date != S.BANK_FRIDAY:
        out.append("BANK_DATE")

    # R4 -- Rotary owns the Sunday exception, and owns it alone.
    if cat == "Rotary House" and date != S.ROTARY_SUNDAY:
        out.append("ROTARY")
    if dow == "Sun" and cat != "Rotary House":
        out.append("SUNDAY")

    # R7 -- businesses off weekends, clubs and Rotary excepted. Sunday is
    # already hard-blocked above for everyone but Rotary, so this only ever
    # fires for Saturday, where it is advisory (see SOFT_CODES).
    if dow == "Sat" and biz == "Business" \
            and cat not in ("Rotary House", "Country Club"):
        out.append("BIZ_SAT")

    # R12 -- Saturdays are for clients who worked a Saturday in 2025.
    if dow == "Sat" and biz == "Residence" \
            and not was_saturday(c.get("prior_install_date", "")):
        out.append("SAT_HIST")

    # Deposited dates are immovable.
    confirmed = c.get("install_2026_confirmed")
    if confirmed and confirmed != date:
        out.append("LOCKED")

    # dedupe, preserve order
    seen, uniq = set(), []
    for x in out:
        if x not in seen:
            seen.add(x)
            uniq.append(x)
    return uniq


def club_crew_ok(category, crews_covering):
    """R2, as a coverage rule.

    A country-club stop is fine as long as Crew 1 is among the crews
    working it that day. On a joint day the stop sits on two cards, so
    judging a single card in isolation gives a false negative -- which is
    exactly what the cross-check against the live schedule caught.
    """
    if category != "Country Club":
        return True
    return any("Crew 1" in c for c in crews_covering)


# ---------------------------------------------------------------------------
# Same-day groups -- clients that must be worked together.
# `first` names the stop that must lead the route; `min_crews` flags the
# jobs that need more than one crew on site.
# ---------------------------------------------------------------------------
SAME_DAY_GROUPS = [
    {"id": "a_hug_away", "label": "A Hug Away (3 locations)",
     "names": ["A Hug Away | Daycare \"A Creative Genius Academy Learning\"",
               "A Hug Away | Frazier, Marissa Residence",
               "A Hug Away | Office"],
     "first": None, "min_crews": 1,
     "why": "2026 Install Date column: \"1/3, 2/3, 3/3 Same Day\""},
    {"id": "lewis_lts", "label": "Holly Lewis + Love That Smile",
     "names": ["Lewis, Holly", "Love That Smile"],
     "first": "Love That Smile", "min_crews": 1,
     "why": "Same day per client; Love That Smile FIRST -- Holly's boxes are stored there"},
    {"id": "kerri_byler", "label": "Kerri Byler (3 Bellville locations)",
     "names": ["Byler, Kerri - House", "Byler, Kerri - Office",
               "Byler, Kerri - Store Buck Ferguson"],
     "first": None, "min_crews": 1,
     "why": "House/office/store kept together -- Bellville is 70min each way"},
    {"id": "schultea_pitcock", "label": "Schultea + Pitcock",
     "names": ["Schultea, Kathy", "Pitcock, James"],
     "first": None, "min_crews": 1,
     "why": "~19min apart in Clear Lake; paired to save a depot round-trip"},
    {"id": "musser_serenity", "label": "Musser + Serenity Retreat",
     "names": ["Musser, Kristy", "Serenity Retreat, Tiffany Pardue"],
     "first": None, "min_crews": 1,
     "why": "Both far west with no closer option -- one trip instead of two"},
    {"id": "sullivan_mattix", "label": "Sullivan + Mattix",
     "names": ["Sullivan, Kristine", "Mattix, Margaret & Rick"],
     "first": None, "min_crews": 1,
     "why": "~1.3min apart -- essentially the same address"},
    {"id": "citizens_group", "label": "Citizens Bank + Ingram + Northside",
     "names": ["Citizens State Bank", "Ingram, Donna", "Northside Import"],
     "first": None, "min_crews": 1,
     "why": "17-21min apart; combined so Citizens isn't a lone day"},
    {"id": "bourque_group", "label": "Bourque + Cain + Bergstrom",
     "names": ["Bourque, Stacey", "Cain, Andria",
               "Bergstrom, Debbie and Steve"],
     "first": None, "min_crews": 2,
     "why": "Bourque's house needs 2 full crews; worked with her Woodlands neighbours"},
]

# Stops that must lead their day's route, independent of any group.
FORCE_FIRST = {
    "Roane, Sheri": "Always wants a 9am start",
    "Jinks, Amy": "Likes to go first",
    "Love That Smile": "Holly Lewis's boxes are stored here -- must open first",
}

# Client-requested / confirmed dates asserted by validate.py.
PINS = {
    "Marek Bros": "2026-11-30",
    "The Club at Carlton Woods | Nicklaus Clubhouse": "2026-11-27",
    "The Club at Carlton Woods | Fazio Clubhouse": "2026-12-01",
    "Woodlands CC Players": "2026-11-25",
    "Woodlands CC Palmer": "2026-11-30",
    "Sims, Darcy": "2026-12-02",
}

# Clients whose "2026 Install Date" cell says no install this year.
NO_INSTALL = ["Gitu, Patrick", "Tenaris", "Valenzuela, Melinda"]


def window_reason(day):
    """Explain a non-standard window so the tool doesn't read it as headroom.

    Every one of these is a negotiated client exception, not slack to fill.
    """
    win = day.get("window_min", S.DAY_CAP)
    if win == S.DAY_CAP:
        return ""
    if day.get("category") == "M Crowd":
        return ("Mi Cocina night shift, 11pm-6:30am" if win == S.NIGHT
                else "Daytime install -- client requires business hours")
    note = (day.get("note") or "").strip()
    return note or f"Extended to {win // 60}h by client exception"
