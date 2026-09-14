"""Characterisation tests for the label-decoding helpers in ``app.apis.designs``.

These pin TODAY's behaviour so a later refactor can be checked against it. In
particular ``designs.parse_room_label`` / ``designs.parse_scope_label`` and the
same-named helpers in ``app.apis.arrangements`` decode the SAME ``LL_ROOM:`` /
``LL_SCOPE:`` prefixes but with DIFFERENT semantics:

* designs returns the raw decoded dict (or ``{}``), with no trimming, no
  required keys, no defaults, and it never raises;
* arrangements trims every text field, requires ``name`` (room) / fills in
  defaults (scope), and returns ``None`` on failure -- including when the
  JSON payload is a dict-with-non-string values or not a dict at all (it
  used to raise ``AttributeError`` for those; fixed to return None instead).

They must not be merged without a deliberate decision -- see the
``test_*_disagree*`` cases at the bottom for concrete inputs.
"""

import pytest

from app.apis import arrangements, designs
from app.apis.designs import parse_room_label, parse_scope_label


# ─── designs.parse_room_label ────────────────────────────────────────────────


@pytest.mark.parametrize(
    "label, expected",
    [
        (None, {}),
        ("", {}),
        ("   ", {}),
        ("Front Porch", {}),
        # prefix is case-sensitive and must be at position 0
        ('ll_room:{"name":"Foyer"}', {}),
        (' LL_ROOM:{"name":"Foyer"}', {}),
        # empty / malformed payloads degrade to {} rather than raising
        ("LL_ROOM:", {}),
        ("LL_ROOM:not json", {}),
        ('LL_ROOM:"just a string"', {}),
        ("LL_ROOM:null", {}),
        ("LL_ROOM:[1, 2]", {}),
        ("LL_ROOM:42", {}),
        # well-formed payloads come back verbatim: no trimming, no key filtering
        ('LL_ROOM:{"name":"Foyer","notes":null}', {"name": "Foyer", "notes": None}),
        ('LL_ROOM:{"name":"  Foyer  ","notes":"  keep spaces  "}', {"name": "  Foyer  ", "notes": "  keep spaces  "}),
        ('LL_ROOM:{"name":""}', {"name": ""}),
        ('LL_ROOM:{"notes":"no name key"}', {"notes": "no name key"}),
        ('LL_ROOM:{"name":42}', {"name": 42}),
        ('LL_ROOM:{"name":"Foyer","extra":[1,2],"n":7}', {"name": "Foyer", "extra": [1, 2], "n": 7}),
        ('LL_ROOM:{"name":"Mixed CASE Room"}', {"name": "Mixed CASE Room"}),
        ("LL_ROOM:{}", {}),
        # wrong prefix family
        ('LL_SCOPE:{"label":"Tree"}', {}),
    ],
)
def test_parse_room_label_snapshot(label, expected):
    assert parse_room_label(label) == expected


# ─── designs.parse_scope_label ───────────────────────────────────────────────


@pytest.mark.parametrize(
    "label, expected",
    [
        (None, {}),
        ("", {}),
        ("Tree", {}),
        ("LL_SCOPE:", {}),
        ("LL_SCOPE:[]", {}),
        ('ll_scope:{"label":"Tree"}', {}),
        ("LL_SCOPE:{}", {}),
        # raw passthrough: nothing normalised, nothing defaulted
        (
            'LL_SCOPE:{"label":"  Tree ","room_id":"7","bucket_type":null,"requested_quantity":"0"}',
            {"label": "  Tree ", "room_id": "7", "bucket_type": None, "requested_quantity": "0"},
        ),
        ('LL_ROOM:{"name":"Foyer"}', {}),
    ],
)
def test_parse_scope_label_snapshot(label, expected):
    assert parse_scope_label(label) == expected


# ─── designs vs arrangements: same prefix, different semantics ───────────────


def test_room_label_disagreement_trimming_and_empty_notes():
    """The canonical disagreement: designs returns the payload untouched,
    arrangements trims ``name`` and turns a blank ``notes`` into ``None``."""
    label = 'LL_ROOM:{"name":"  Foyer  ","notes":""}'
    assert designs.parse_room_label(label) == {"name": "  Foyer  ", "notes": ""}
    assert arrangements.parse_room_label(label) == {"name": "Foyer", "notes": None}


def test_room_label_disagreement_missing_or_blank_name():
    # designs keeps the row; arrangements rejects it (None), because it needs a name
    assert designs.parse_room_label('LL_ROOM:{"name":""}') == {"name": ""}
    assert arrangements.parse_room_label('LL_ROOM:{"name":""}') is None
    assert designs.parse_room_label('LL_ROOM:{"notes":"x"}') == {"notes": "x"}
    assert arrangements.parse_room_label('LL_ROOM:{"notes":"x"}') is None


def test_room_label_disagreement_on_failure_value():
    # "nothing decodable" is {} in designs but None in arrangements
    for label in (None, "", "Front Porch", "LL_ROOM:", "LL_ROOM:not json"):
        assert designs.parse_room_label(label) == {}
        assert arrangements.parse_room_label(label) is None


def test_room_label_disagreement_non_dict_payload():
    """designs swallows a non-dict payload into {}; arrangements now returns
    its own failure value, None, for the same input (fixed: it used to raise
    AttributeError from ``list.get`` / ``int.strip`` escaping its narrower
    except tuple)."""
    assert designs.parse_room_label("LL_ROOM:[1, 2]") == {}
    assert arrangements.parse_room_label("LL_ROOM:[1, 2]") is None

    assert designs.parse_room_label('LL_ROOM:{"name":42}') == {"name": 42}
    assert arrangements.parse_room_label('LL_ROOM:{"name":42}') is None


def test_scope_label_disagreement_defaults_and_normalisation():
    label = 'LL_SCOPE:{"label":"  Tree ","requested_quantity":"0","scope_notes":" "}'
    assert designs.parse_scope_label(label) == {
        "label": "  Tree ",
        "requested_quantity": "0",
        "scope_notes": " ",
    }
    assert arrangements.parse_scope_label(label) == {
        "label": "Tree",
        "room_id": None,
        "bucket_type": None,
        "requested_quantity": 1,
        "scope_notes": None,
    }
    # and on the empty object: designs {} vs arrangements fully-defaulted dict
    assert designs.parse_scope_label("LL_SCOPE:{}") == {}
    assert arrangements.parse_scope_label("LL_SCOPE:{}") == {
        "label": "Scope",
        "room_id": None,
        "bucket_type": None,
        "requested_quantity": 1,
        "scope_notes": None,
    }


def test_arrangements_scope_label_vs_designs_room_label_never_both_decode():
    """The two prefix families are disjoint: an LL_SCOPE label is a design for
    arrangements.parse_scope_label and 'not a room' ({}) for
    designs.parse_room_label, and vice versa."""
    scope = 'LL_SCOPE:{"label":"Tree","room_id":20}'
    assert designs.parse_room_label(scope) == {}
    assert arrangements.parse_scope_label(scope) == {
        "label": "Tree",
        "room_id": 20,
        "bucket_type": None,
        "requested_quantity": 1,
        "scope_notes": None,
    }
    room = 'LL_ROOM:{"name":"Foyer"}'
    assert designs.parse_room_label(room) == {"name": "Foyer"}
    assert arrangements.parse_scope_label(room) is None
