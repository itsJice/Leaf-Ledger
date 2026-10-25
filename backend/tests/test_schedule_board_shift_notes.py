"""Shift notes staff wrote on the Staffing tab (state.shiftNotes, see
shiftNotes in scheduler/review_template.html), read server-side: the lead
pages and the calendar feed show the note for the crew's day. Each Dallas
night is its own shift (10/24/2026); a note saved under a Dallas run's old
week key still covers every night of that run until a night gets its own.
"""
from app.libs import install_calendar as cal
from app.libs import schedule_board

from tests.test_schedule_board_dallas_nights import HOU, JAN1, JAN2, NOV1, PAYLOAD, state


def board(**extra):
    st = state(**extra)
    st["placement"] = {**st["placement"], "2": [NOV1, HOU]}
    return schedule_board.resolve("2026", PAYLOAD, st)


def test_houston_note_is_keyed_by_its_day_id():
    b = board(shiftNotes={HOU: {"text": "  Meet at 7:30  \r\n\n\n\nBring ladder ", "by": "a@x.com",
                                "at": "2026-10-25T01:31:00.000Z"}})
    assert b.shift_notes == {HOU: {"text": "Meet at 7:30\n\nBring ladder", "by": "a@x.com",
                                   "at": "2026-10-25T01:31:00.000Z"}}
    assert b.shift_note(b.days[HOU]) == "Meet at 7:30\n\nBring ladder"
    assert b.shift_note(b.days[NOV1]) == ""


def test_old_dallas_week_note_covers_every_night_of_its_run():
    b = board(dallasNights=["2027-01-02", "2027-01-03"],
              shiftNotes={"dallas|2027-01-02|Crew 1": {"text": "Park in back"}})
    assert b.shift_note(b.days[JAN1]) == "Park in back"
    assert b.shift_note(b.days[JAN2]) == ""


def test_a_dallas_night_note_is_keyed_by_its_day_id_and_wins():
    b = board(shiftNotes={"dallas|2026-11-02|Crew 1": {"text": "Week"}, NOV1: {"text": "Mon only"}})
    assert b.shift_note(b.days[NOV1]) == "Mon only"
    b2 = board(dallasNights=["2027-01-02"], shiftNotes={JAN1: {"text": "Sat only"}})
    assert b2.shift_note(b2.days[JAN1]) == "Sat only"
    assert b2.shift_note(b2.days[JAN2]) == ""


def test_notes_are_normalized_and_junk_dropped():
    raw = {"a": {"text": "x" * 2100, "by": 5, "at": 7}, "b": {"text": "   "}, "c": 5, 7: "seven",
           "d": " plain ", "e": ["x"], "f": {"text": 3}}
    assert schedule_board.norm_shift_notes(raw) == {"a": {"text": "x" * 2000, "by": "", "at": ""},
                                                    "d": {"text": "plain", "by": "", "at": ""}}
    assert schedule_board.norm_shift_notes(None) == {}
    assert schedule_board.norm_shift_notes(["a"]) == {}


def test_calendar_feed_description_carries_the_note():
    b = board(shiftNotes={HOU: {"text": "Gate code 1234"}})
    events = cal.day_events(b, b.days[HOU])
    assert events and all("Notes for the day: Gate code 1234" in e["description"] for e in events)
    plain = board()
    assert all("Notes for the day" not in e["description"] for e in cal.day_events(plain, plain.days[HOU]))


def test_lead_page_day_carries_the_note_beside_the_day_note():
    from app.apis.lead import _day_out
    b = board(shiftNotes={HOU: {"text": "Start at the church lot"}})
    out = _day_out(b, b.days[HOU], [], [])
    assert out["shiftNote"] == "Start at the church lot"
    assert "note" in out
    assert _day_out(board(), board().days[HOU], [], [])["shiftNote"] == ""
