""""Prefers WhatsApp" on roster people (Comments #56). A page published before
the field drops it, so a save whose person has no `prefersWhatsApp` key keeps
the stored choice; a page that knows it always sends true or false, so
switching it off works. FAKE people only."""
from app.apis import install_schedule as sched

STORED = {"roster": [{"id": "p1", "name": "Ana Test", "prefersWhatsApp": True},
                     {"id": "p2", "name": "Bo Test"}]}


def test_it_is_a_later_person_field():
    assert "prefersWhatsApp" in sched.LATER_PERSON_FIELDS


def test_old_page_save_without_the_key_keeps_it():
    out = sched.keep_stored_person_fields(
        {"roster": [{"id": "p1", "name": "Ana Test"}, {"id": "p2", "name": "Bo Test"}]}, STORED)
    assert out["roster"] == [{"id": "p1", "name": "Ana Test", "prefersWhatsApp": True},
                             {"id": "p2", "name": "Bo Test"}]


def test_new_page_save_switches_on_and_off():
    sent = {"roster": [{"id": "p1", "name": "Ana Test", "prefersWhatsApp": False},
                       {"id": "p2", "name": "Bo Test", "prefersWhatsApp": True}]}
    assert sched.keep_stored_person_fields(sent, STORED) == sent
