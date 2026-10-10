"""The read-only board-vs-card dates report (scripts/report_board_vs_card_dates.py)."""
import asyncio
import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
report = importlib.import_module("report_board_vs_card_dates")

from app.libs.schedule_board import resolve  # noqa: E402

PAYLOAD = {
    "spec": {"version": "v1"},
    "clients": {"1": {"name": "Jinks, Amy"}, "2": {"name": "Crane Worldwide"},
                "3": {"name": "Gala Hall", "visitType": "Takedown"}, "4": {"name": "Gala Hall"},
                "5": {"name": "Nobody Known"}, "6": {"name": "Same Card"}},
    "days": [
        {"id": "2026-11-07|A|0", "stops": [1]},
        {"id": "2026-11-18|A|0", "stops": [2, 6]},
        {"id": "2026-11-21|B|0", "stops": [3]}, {"id": "2026-11-20|A|0", "stops": [4]},
        {"id": "2026-11-19|A|0", "stops": [5]},
    ],
}
# staff moved Amy to the 13th on the board
STATE = {"placement": {"1": ["2026-11-13|B|0"], "2": ["2026-11-18|A|0"], "3": ["2026-11-21|B|0"],
                       "4": ["2026-11-20|A|0"], "5": ["2026-11-19|A|0"], "6": ["2026-11-18|A|0"]}}

CARDS = [
    {"id": 41, "name": "Amy Jinks", "sheet_name": None, "former_names": [], "summary": "Scheduled 11/07/2026",
     "detail": {"install_date": "2026-11-07"}},
    {"id": 42, "name": "Crane Worldwide", "sheet_name": None, "former_names": [], "summary": "", "detail": None},
    {"id": 43, "name": "Gala Hall", "sheet_name": None, "former_names": [], "summary": "",
     "detail": {"install_date": "2026-11-20"}},
    {"id": 44, "name": "Same Card", "sheet_name": None, "former_names": [], "summary": "",
     "detail": {"install_date": "2026-11-18"}},
]


def test_lists_only_mismatches_board_wins():
    board = resolve("2026", PAYLOAD, STATE)
    dates = report.board_dates(board, "2026-12-25")
    # the event teardown (row 3) is not Gala Hall's install
    assert dates["gala hall"]["install"] == "2026-11-20" and "takedown" not in dates["gala hall"]
    rows = report.compare(dates, CARDS, "2026")
    got = [(r["client"], r["board_date"], r["card_date"], r["problem"], r["matched_by"]) for r in rows]
    assert got == [
        ("Jinks, Amy", "2026-11-13", "2026-11-07", "different date", "same words, different order"),
        ("Crane Worldwide", "2026-11-18", "", "no 2026 season card", "name"),
        ("Nobody Known", "2026-11-19", "", "no matching client on the Clients tab", ""),
    ]
    assert rows[0]["board_crew"] == "Crew 1"


def test_report_only_selects():
    """Every statement the report sends is a SELECT -- it can't change anything."""
    seen = []

    class Conn:
        async def fetchrow(self, sql, *a):
            seen.append(sql)
            if "install_schedule_pages" in sql:
                import json
                return {"html": "x const DATA = " + json.dumps(PAYLOAD) + ";"}
            return {"state": STATE}

        async def fetch(self, sql, *a):
            seen.append(sql)
            return [dict(c) for c in CARDS]

    board, cards = asyncio.run(report.read_live(Conn(), "2026"))
    assert len(cards) == 4 and board.version == "v1"
    assert seen and all(s.lstrip().upper().startswith("SELECT") for s in seen)
