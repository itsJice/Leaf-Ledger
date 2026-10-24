"""Hand-set Overall rating on the roster (user, 2026-10-24: "give the ability
to just select the overall rating"). ratings.overall (1-10) wins wherever
overall shows or sorts; without it, overall is the average of the traits as
before. It has to survive normalisation and the stale-tab merge. FAKE people
only."""
import json
import re
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_stale_tab_merge import MERGE

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")


def _const_block(name):
    m = re.search(rf"^const {name}=\[.*?^\];", TEMPLATE, re.M | re.S)
    assert m, name
    return m.group(0)


def _const_line(name):
    m = re.search(rf"^const {name}=.*$", TEMPLATE, re.M)
    assert m, name
    return m.group(0)


HELPERS = "\n".join([
    _const_block("RATING_DIMENSIONS"),
    _const_line("RATING_KEYS"),
    _const_line("RATING_OVERALL"),
    _const_line("RATING_MAX"),
] + [js_function(n) for n in (
    "normRatings", "ratingOf", "traitAverage", "handOverall", "overallOf", "overallRating")])


def run(body, extra=""):
    return json.loads(run_js(extra + "\n" + HELPERS + "\n" + body))


def test_no_hand_set_overall_is_the_trait_average():
    out = run("""console.log(JSON.stringify([
      overallRating({ratings:{speed:8, design:6}}),
      overallRating({ratings:{speed:7, design:8}}),
      overallRating({ratings:{}}),
      overallRating({}),
      overallRating(null),
    ]))""")
    assert out == [7, 8, 0, 0, 0]          # 7.5 rounds up to the next half-star


def test_hand_set_overall_wins_over_the_traits():
    out = run("""console.log(JSON.stringify([
      overallRating({ratings:{speed:2, design:2, overall:8}}),
      overallRating({ratings:{overall:7}}),
      overallOf({speed:10, overall:3}),
      handOverall({speed:10}),
      handOverall({overall:6}),
    ]))""")
    assert out == [8, 7, 3, 0, 6]


def test_out_of_range_overall_falls_back_to_the_average():
    out = run("""console.log(JSON.stringify([
      overallRating({ratings:{speed:6, overall:0}}),
      overallRating({ratings:{speed:6, overall:11}}),
      overallRating({ratings:{speed:6, overall:'x'}}),
    ]))""")
    assert out == [6, 6, 6]


def test_normalising_keeps_overall_and_drops_junk():
    out = run("""console.log(JSON.stringify([
      normRatings({speed:4, overall:8, bogus:5}),
      normRatings({overall:'7'}),
      normRatings({overall:0, speed:12}),
    ]))""")
    assert out == [{"speed": 4, "overall": 8}, {"overall": 7}, {}]


def test_overall_is_a_rating_key_in_normroster():
    # normRoster runs every person's ratings through normRatings; that is the
    # whitelist that would silently drop ratings.overall.
    assert "ratings: normRatings(p.ratings)" in js_function("normRoster")


MERGE_SCENARIO = """
const P=(id,first,r)=>({id, first, last:'Test', name:first+' Test', title:'General Installer',
  lang:'Both', gender:'Female', email:'', phone:'', notes:'', ratings:r||{}, texts:[],
  times:['day','night'], dates:['2026-10-26'], active:true});
const clone=x=>JSON.parse(JSON.stringify(x));
const BASE={placement:{}, approved:[], moves:[], comments:{}, staffing:{}, newClients:[],
  roster:[P('p1','Ana',{speed:6}), P('p2','Luis',{speed:4, overall:6})]};
"""


def merge(body):
    return json.loads(run_js(MERGE + "\n" + MERGE_SCENARIO + "\n" + body))


def test_merge_keeps_overall_set_here_when_someone_else_saved():
    out = merge("""
      const mine=clone(BASE); mine.roster[0].ratings.overall=8;      // set by hand here
      const theirs=clone(BASE); theirs.roster[0].ratings.design=4;   // a trait rated elsewhere
      theirs.roster[1].notes='Has a truck';
      console.log(JSON.stringify(mergeShared(BASE, mine, theirs)));
    """)
    assert out["conflicts"] == [] and out["hard"] == []
    roster = {p["id"]: p for p in out["state"]["roster"]}
    assert roster["p1"]["ratings"] == {"speed": 6, "design": 4, "overall": 8}
    assert roster["p2"]["ratings"] == {"speed": 4, "overall": 6}
    assert roster["p2"]["notes"] == "Has a truck"


def test_merge_keeps_overall_set_elsewhere_when_this_tab_rates_a_trait():
    out = merge("""
      const mine=clone(BASE); mine.roster[1].ratings.design=9;       // trait here
      const theirs=clone(BASE); theirs.roster[1].ratings.overall=9;  // overall elsewhere
      console.log(JSON.stringify(mergeShared(BASE, mine, theirs)));
    """)
    roster = {p["id"]: p for p in out["state"]["roster"]}
    assert roster["p2"]["ratings"] == {"speed": 4, "design": 9, "overall": 9}


def test_merge_clearing_overall_here_goes_back_to_the_average():
    out = merge("""
      const mine=clone(BASE); delete mine.roster[1].ratings.overall;
      console.log(JSON.stringify(mergeShared(BASE, mine, clone(BASE))));
    """)
    roster = {p["id"]: p for p in out["state"]["roster"]}
    assert roster["p2"]["ratings"] == {"speed": 4}


def test_editor_overall_row_is_a_picker_with_a_hint():
    src = js_function("drawPerRatings")
    assert "ratingPickStars(RATING_OVERALL" in src
    assert "Set by hand" in src and "Average of the traits" in src
    assert "—" not in src                                  # no em dashes in the UI text
