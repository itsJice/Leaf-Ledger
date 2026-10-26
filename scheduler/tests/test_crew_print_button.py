"""The crew card's print icon prints its run sheet (not the swap button), and
the sheet's weekday is never '?'."""
import pathlib, re

SRC = pathlib.Path(__file__).resolve().parents[1].joinpath("review_template.html").read_text()


def test_print_icon_is_bound_by_its_own_class():
    assert 'class="printbtn picon sheetbtn"' in SRC
    assert "card.querySelector('.sheetbtn').onclick" in SRC
    assert "card.querySelector('.printbtn:not(.remcardbtn)')" not in SRC


def test_run_sheet_heading_uses_a_real_weekday():
    assert "${esc(dowName(d))} ${fmtMDYYYY(d.date)}</h1>" in SRC
    assert "${esc(d.dow)} ${fmtMDYYYY(d.date)}</h1>" not in SRC
    body = re.search(r"function dowName\(d\)\{(.*?)\n\}", SRC, re.S).group(1)
    assert "'?'" in body and "getUTCDay" in body
