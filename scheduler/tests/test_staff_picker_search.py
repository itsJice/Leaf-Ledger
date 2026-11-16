"""Staff this shift: search by name, and full names that are never cut off
(user, 2026-11-16, the office manager staffing crews on her phone). FAKE
names only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node not installed")

HELPERS = "\n".join(js_function(n) for n in ("stfFoldKey", "stfLooseKey", "stfNameMatches"))
NAMES = ["Christian Doe", "Cristian J. Roe", "Chris Poe", "José Núñez", "Ana Kim", "Jhon Vale", "Hector Day"]


def matches(q):
    return json.loads(run_js(HELPERS + f"""
      const names={json.dumps(NAMES)};
      console.log(JSON.stringify(names.filter(n=>stfNameMatches(n, {json.dumps(q)}))));"""))


def test_chri_finds_christian_and_cristian():
    assert matches("chri") == ["Christian Doe", "Cristian J. Roe", "Chris Poe"]


def test_accents_and_case_do_not_matter():
    assert matches("JOSE") == ["José Núñez"]
    assert matches("nunez") == ["José Núñez"]
    assert matches("Núñ") == ["José Núñez"]


def test_last_name_and_several_words():
    assert matches("roe") == ["Cristian J. Roe"]
    assert matches("cris roe") == ["Cristian J. Roe"]
    assert matches("christian d") == ["Christian Doe"]


def test_short_queries_match_word_starts_only():
    # "an" starts "Ana" but is also inside "Christian": only word starts count.
    assert matches("an") == ["Ana Kim"]
    assert matches("k") == ["Ana Kim"]


def test_sound_alike_spellings():
    assert matches("john") == ["Jhon Vale"]
    assert matches("ector") == ["Hector Day"]
    assert matches("bale") == ["Jhon Vale"]


def test_empty_query_matches_everyone_and_nonsense_matches_no_one():
    assert matches("") == NAMES
    assert matches("   ") == NAMES
    assert matches("zzzz") == []
    assert matches("xq") == []


def test_picker_has_the_search_box_and_wraps_names():
    src = TEMPLATE
    assert 'id="stfq"' in src and 'id="stfqx"' in src
    assert 'placeholder="Search by name"' in src
    # The name sits in its own span with the tags after it, so tags wrap
    # under the name instead of cutting it off.
    assert '<span class="asgbody"><span class="asgn">' in src
    assert "#stfdlg .asgbody .asgn{flex:0 1 auto;white-space:normal" in src
    # Searching looks past the training filter, and says so per person.
    assert "if(query) pick.showAll=true;" in src
    assert "NOT TRAINED" in src


def test_default_still_schedules_only_from_training():
    src = TEMPLATE
    assert "return p.title==='Lead' || attendedTraining(p, o.staffing, o.trainingDays);" in src
    assert "stfUntrainedMem = localStorage.getItem(STF_UNTRAINED_KEY)==='1';" in src
