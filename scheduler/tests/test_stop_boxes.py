"""One box count everywhere the schedule shows boxes (review_template.html).

The user (2026-10-30): "Make sure that all the Mi Cocinas have their box
count visible on the install schedule tab." The Dallas takedown visits were
added in the tool with no count on their own card, so the stop rows said
"boxes?" and the January day totals were 0, while the Trailer Loader already
used the install's count. The schedule now reads the same number the load
lists do (stopBoxes -> loadBoxesFor): a Trailer Loader count, else the card,
else the install count of the same location. Every name is invented.
"""
import json

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js
from test_load_list import NODE

needs_node = pytest.mark.skipif(NODE is None, reason="node not installed")

FNS = ["parseBoxes", "cardBoxesFor", "loadBoxesFor", "stopBoxes", "stopBoxesTxt", "dayBoxes"]

C = {
    "1": {"name": "Test Cantina Uptown", "boxes": "6"},
    "2": {"name": "Test Cantina Lakewood", "boxes": "4"},
    "3": {"name": "Test Home", "boxes": ""},
    "900001": {"name": "Test Cantina Uptown", "visitType": "Takedown"},
    "900002": {"name": "Test Cantina Lakewood", "visitType": "Takedown"},
}


def run(load_stops, body):
    src = (f"const C={json.dumps(C)}; let loadStops={json.dumps(load_stops)};\n"
           + "\n".join(js_function(n) for n in FNS) + "\n" + body)
    return json.loads(run_js(src))


@needs_node
def test_a_takedown_with_no_card_count_shows_the_install_count():
    out = run({}, """console.log(JSON.stringify({
      td:stopBoxes('900001'), txt:stopBoxesTxt('900002','boxes?'),
      day:dayBoxes({stops:['900001','900002']})}));""")
    assert out == {"td": 6, "txt": "4 boxes", "day": 10}


@needs_node
def test_a_trailer_loader_count_wins_over_the_card():
    out = run({"2": {"boxes": 7}, "900001": {"boxes": 0}}, """console.log(JSON.stringify({
      inst:stopBoxes('2'), td:stopBoxes('900001'), day:dayBoxes({stops:['2','900001','3']})}));""")
    assert out == {"inst": 7, "td": 0, "day": 7}


@needs_node
def test_boxes_question_only_when_nobody_has_a_count():
    out = run({}, """console.log(JSON.stringify({b:stopBoxes('3'), txt:stopBoxesTxt('3','boxes?'),
      quiet:stopBoxesTxt('3')}));""")
    assert out == {"b": None, "txt": "boxes?", "quiet": ""}


def test_no_schedule_view_reads_the_card_count_directly():
    # Stop rows, peek, agenda, map tooltip, shift cards, crew sheet and the
    # Not installing / On hold lists all go through stopBoxes now.
    assert "c.boxes?" not in TEMPLATE and "c.boxes||" not in TEMPLATE
    assert "C[t.row].boxes" not in TEMPLATE
    assert "parseFloat(C[r].boxes)" not in TEMPLATE


@needs_node
def test_a_card_with_no_name_never_borrows_another_cards_count():
    src = ("const C={'1':{boxes:''}, '2':{boxes:5}}; let loadStops={};\n"
           + "\n".join(js_function(n) for n in FNS) + "\nconsole.log(JSON.stringify(stopBoxes('1')));")
    assert json.loads(run_js(src)) is None
