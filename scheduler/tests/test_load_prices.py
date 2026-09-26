"""load_prices.py -- reading the billing export that went to clients.

No database and no workbook file: the parser is fed rows shaped like the
review page's xlsx export (header row matched by text, a spacer, a TOTAL
footer). Every name is invented.
"""
import pytest

import load_prices as L

HEADER = ("Bill-to name/company", "PHONE", "EMAIL", "ADDRESS", "CITY", "ST", "ZIP", "Install date",
          "2026 install price", "2026 takedown price", "2026 storage price", "2026 TOTAL invoice",
          "2025 total invoice (actual)", "Pricing basis", "Repairs & install notes", "Billing notes")


def row(name, inst=None, tdwn=None, stor=None, total=None, basis=None, prev=None):
    return (name, None, None, "1 Elm", "Testville", "TX", "77001", "11/12/2026",
            inst, tdwn, stor, total, prev, basis, None, None)


def test_parse_export_reads_by_header_text_and_skips_footer():
    rows = [
        HEADER,
        row("Test Client A", 472.5, 472.5, 750, 1695, "2025 invoice +5% (storage: boxes × $75, no uplift)", 1650),
        row("Test Club", basis="Club contract — priced separately"),
        row("Test Storage Only", stor=300, basis="MANUAL — storage known (boxes × $75), install/takedown need manual pricing"),
        row("Test Donation", 0, 0, 0, 0, "Donation — free install"),
        row("", 1, 1, 1, 3, "a blank name is not a client"),
        tuple([None] * len(HEADER)),
        ("TOTAL — 4 clients (2 priced)", None, None, None, None, None, None, None, 472.5, 472.5, 1050, 1695, None, None, None, None),
    ]
    recs = L.parse_export(rows)
    assert [r["name"] for r in recs] == ["Test Client A", "Test Club", "Test Storage Only", "Test Donation"]
    assert recs[0]["fields"] == {"install_fee": 472.5, "takedown_fee": 472.5, "storage_fee": 750.0,
                                 "total": 1695.0, "price_basis": "2025 invoice +5% (storage: boxes × $75, no uplift)"}
    # unpriced rows keep their nulls -- an unpriced job is not a $0 job
    assert recs[1]["fields"] == {"install_fee": None, "takedown_fee": None, "storage_fee": None,
                                 "total": None, "price_basis": "Club contract — priced separately"}
    assert recs[2]["fields"]["storage_fee"] == 300.0 and recs[2]["fields"]["total"] is None
    # a donation is a real $0, not a blank
    assert recs[3]["fields"]["total"] == 0.0 and recs[3]["fields"]["install_fee"] == 0.0
    assert L.summarize_parsed(recs) == {"rows": 4, "priced": 2, "install": 472.5, "takedown": 472.5,
                                        "storage": 1050.0, "total": 1695.0}


def test_parse_export_accepts_any_column_order_and_season():
    header = ("2027 TOTAL invoice", "Pricing basis", "Bill-to name/company", "2027 storage price",
              "2027 install price", "2027 takedown price")
    recs = L.parse_export([header, (900, "x", "Test Client B", 100, 400, 400)])
    assert recs == [{"name": "Test Client B", "fields": {
        "install_fee": 400.0, "takedown_fee": 400.0, "storage_fee": 100.0, "total": 900.0, "price_basis": "x"}}]


@pytest.mark.parametrize("header", [
    ("Bill-to name/company", "2026 install price"),                       # money columns missing
    ("Client name", "2026 install price", "2026 takedown price", "2026 storage price",
     "2026 TOTAL invoice", "Pricing basis"),                                # wrong name column
    ("Bill-to name/company", "install price", "takedown price", "storage price", "TOTAL invoice",
     "Pricing basis"),                                                       # no season prefix
])
def test_parse_export_refuses_an_unfamiliar_header(header):
    with pytest.raises(SystemExit):
        L.parse_export([header, tuple(["Test"] + [1] * (len(header) - 1))])
    with pytest.raises(SystemExit):
        L.parse_export([])


def test_is_priced_counts_any_money_column():
    assert L.is_priced({"install_fee": None, "takedown_fee": None, "storage_fee": 300.0, "total": None})
    assert L.is_priced({"install_fee": 0.0, "takedown_fee": 0.0, "storage_fee": 0.0, "total": 0.0})  # a donation
    assert not L.is_priced({"install_fee": None, "takedown_fee": None, "storage_fee": None, "total": None,
                            "price_basis": "MANUAL — no 2025 invoice and no rate-card estimate"})
