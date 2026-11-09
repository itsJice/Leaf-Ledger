"""T-shirt size on roster people (Comments #26). A page published before the
field drops it, so a save whose person has no `shirt` key keeps the stored
size; a page that knows the field always sends the key, so clearing works.
FAKE people only."""
import inspect

from app.apis import install_schedule as sched

STORED = {"roster": [{"id": "p1", "name": "Ana Test", "shirt": "M"},
                     {"id": "p2", "name": "Bo Test"}]}


def test_old_page_save_without_the_key_keeps_the_stored_size():
    out = sched.keep_stored_person_fields(
        {"roster": [{"id": "p1", "name": "Ana Test"}, {"id": "p2", "name": "Bo Test"}]}, STORED)
    assert out["roster"] == [{"id": "p1", "name": "Ana Test", "shirt": "M"},
                             {"id": "p2", "name": "Bo Test"}]


def test_new_page_save_sets_and_clears():
    sent = {"roster": [{"id": "p1", "name": "Ana Test", "shirt": ""},
                       {"id": "p2", "name": "Bo Test", "shirt": "2XL"}]}
    assert sched.keep_stored_person_fields(sent, STORED) == sent


def test_new_people_and_odd_documents_pass_through():
    sent = {"roster": [{"id": "p9", "name": "New Person"}, "junk"]}
    assert sched.keep_stored_person_fields(sent, STORED) == sent
    assert sched.keep_stored_person_fields({"roster": [{"id": "p1"}]}, None) == {"roster": [{"id": "p1"}]}
    assert sched.keep_stored_person_fields({"teams": []}, STORED) == {"teams": []}


def test_put_state_applies_it():
    assert "keep_stored_person_fields(state, stored)" in inspect.getsource(sched.put_state)
