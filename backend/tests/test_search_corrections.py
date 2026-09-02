"""Spelling corrections for catalog search: ranked by edit distance, with the
catalog's own word frequencies breaking ties. The candidate lists here are the
real trigram neighbours measured against the live vocabulary on 2026-09-02."""
from app.apis.products import _edit_distance, _rank_corrections


def test_swap_is_one_edit():
    assert _edit_distance("ornamnet", "ornament") == 1
    assert _edit_distance("wreathe", "wreath") == 1
    assert _edit_distance("candel", "candle") == 1
    assert _edit_distance("burlap", "burl") == 2
    assert _edit_distance("same", "same") == 0


def test_real_word_beats_vendor_typo_at_same_distance():
    near = [("ornamanet", 1), ("ornamnt", 22), ("ornam", 12), ("orname", 6),
            ("orna", 117), ("ornament", 9399), ("ornaments", 1191)]
    assert _rank_corrections("ornamnet", near, None, skip_known=True)[0] == "ornament"


def test_transposition_reaches_candle_not_candy():
    near = [("candeh", 1), ("candelabra", 77), ("cand", 4), ("candy", 2331),
            ("candl", 2), ("candle", 3369), ("candles", 357)]
    assert _rank_corrections("candel", near, None, skip_known=True)[0] == "candle"


def test_known_word_is_left_alone():
    # "burlap" is in 438 product names; "burl" in 21. Nothing to correct.
    assert _rank_corrections("burlap", [("burl", 21), ("burled", 1)], 438, skip_known=True) == []


def test_vendor_typo_of_common_word_still_corrects():
    # "garlnd" appears 83 times, "garland" 3,949: the ratio says typo.
    out = _rank_corrections("garlnd", [("garland", 3949), ("garl", 76), ("garalnd", 8)], 83, skip_known=True)
    assert out[0] == "garland"
    out = _rank_corrections("ribon", [("ribbon", 6246), ("riboon", 1), ("rib", 25)], 2, skip_known=True)
    assert out[0] == "ribbon"


def test_short_words_allow_one_edit_only():
    # One edit on a four-letter word is a typo; two is a different word.
    near = [("bold", 3), ("golden", 900), ("gild", 1), ("goal", 50), ("gourd", 40)]
    assert _rank_corrections("gold", near, None, skip_known=True) == ["bold", "gild"]


def test_skip_known_false_corrects_everything():
    near = [("burl", 21), ("burled", 1)]
    assert _rank_corrections("burlap", near, 438, skip_known=False) == ["burl", "burled"]
