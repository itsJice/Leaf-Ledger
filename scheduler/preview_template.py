#!/usr/bin/env python3
"""Preview review_template.html changes against the LIVE schedule, locally.

Reads the published tool page from Postgres (read-only), keeps its embedded
data byte for byte -- so its build version, and therefore the shared state
staff have saved, still match -- and re-wraps it in this checkout's
template. Writes cache/preview_index.html (gitignored: it holds client PII).

Point a local backend at it with

    INSTALL_SCHEDULE_PREVIEW_PAGE=../scheduler/cache/preview_index.html

and the app's Install Schedule tab shows the new template on real data,
without publishing anything. Usage: ./preview_template.py [--season 2026]
"""
import argparse
import asyncio
import json
import os

import board_state
import season as season_lib

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "cache", "preview_index.html")


def subs(season: int) -> dict:
    """The same season tokens build_review.py substitutes (kept in step by hand)."""
    start, end = season_lib.season_span(season)
    years = {m: season_lib.year_of_month(season, m) for m in (10, 11, 12, 1)}
    return {
        "__SEASON__": str(season),
        "__SEASON_NEXT__": str(season + 1),
        "__SEASON_PREV__": str(season - 1),
        "__SPAN_START__": start.isoformat(),
        "__SPAN_END__": end.isoformat(),
        "__CUTOFF__": season_lib.takedown_cutoff(season).isoformat(),
        "__Y_OCT__": str(years[10]),
        "__Y_NOV__": str(years[11]),
        "__Y_DEC__": str(years[12]),
        "__Y_JAN__": str(years[1]),
    }


async def main(season):
    conn = await board_state.connect()
    try:
        if season is None:
            season = await conn.fetchval(
                "SELECT season FROM ll_app.install_schedule_pages WHERE name = 'index.html' "
                "ORDER BY season DESC LIMIT 1")
        html = await conn.fetchval(
            "SELECT html FROM ll_app.install_schedule_pages WHERE season = $1 AND name = 'index.html'",
            str(season))
    finally:
        await conn.close()
    if not html:
        raise SystemExit(f"no published {season} page")
    i = html.index(board_state.PAYLOAD_MARK) + len(board_state.PAYLOAD_MARK)
    _, end = json.JSONDecoder().raw_decode(html, i)
    payload = html[i:end]

    page = open(os.path.join(HERE, "review_template.html"), encoding="utf-8", newline="").read()
    for tok, val in subs(int(season)).items():
        page = page.replace(tok, val)
    page = page.replace("__DATA__", payload)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(page)
    print(f"wrote {OUT} ({season}, build {board_state.payload_version(json.loads(payload))})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--season")
    asyncio.run(main(ap.parse_args().season))
