"""The printed crew sheet lists every assigned person in its own wrapping
Crew section, so a long crew never runs off the page."""
import pathlib

SRC = pathlib.Path(__file__).resolve().parents[1].joinpath("review_template.html").read_text()


def test_crew_sheet_has_a_crew_section_with_everyone():
    assert '<div class="crewbox"><div class="crewh">Crew (${cv.who.length})' in SRC
    assert "cv.who.map(pn=>`<li><b>${esc(pn.name)}</b>" in SRC


def test_crew_section_wraps_instead_of_running_off_the_page():
    assert ".crewbox ul{list-style:none;margin:0;padding:0;display:grid" in SRC
    assert ".shead > div:first-child{flex:1;min-width:0}" in SRC
