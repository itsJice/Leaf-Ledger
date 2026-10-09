"""A client's name, as parts (migrations/021).

``clients.name`` stays the one canonical spelling: every table that keeps a
client's name as text, the spreadsheet sync, the billing-export loader, the
Install Schedule page and every search match on it. The parts are how people
type it. Every client card offers the same four boxes and people fill
whichever apply:

    first_name, last_name   a person
    company                 a business name
    site                    a location ("House", "Nicklaus Clubhouse")

``compose_name`` turns them into the display name:

    Last, First                         "Scheib, Nataliya"
    Last, First - Location              "Byler, Kerri - House"
    Business                            "Hilton Garden Inn"
    Business | Location                 "The Club at Carlton Woods | Nicklaus Clubhouse"
    Business + a person                 "Serenity Retreat" (Tiffany Pardue is kept
                                        as the contact person, not in the name)

Businesses go by their business name (user, 2026-10-09): whenever a company
is set the name is the business, plus " | Location" when there is one
("Club at Carlton Woods | Trails"). The first and last name stay saved on
the card as the contact person.

Older "Business | Last, First" names (the rule before 2026-10-09) still
parse into the right parts; they just compose to the business name now,
which is a rename (``scripts/business_name_rule_impact.py`` lists them,
read-only). "Business | Location" names are unchanged.

``split_name`` reads parts back out of an existing name (the inverse, plus
reasons a human should check the guess). The columns are nullable: a client
the sync created, or one nobody has re-saved since the columns arrived, has
none, and ``name_parts`` derives them on the fly so the edit form always has
something to show. ``scripts/split_client_names.py`` uses the same parser to
propose a backfill (dry run first; it never changes ``name``).
"""

from __future__ import annotations

import re
from typing import Optional

PART_FIELDS = ("first_name", "last_name", "company", "site")
#: Every column the parts live in, in the order the API returns them.
NAME_PART_COLUMNS = PART_FIELDS

#: After a business name, before its location ("Business | Location").
BUSINESS_SEP = " | "
#: After a person's name, before their location.
PERSON_SITE_SEP = " - "

#: Words that make a "Last, First" shaped name look like a business (or a
#: placeholder line from the sheet) rather than a person.
_BUSINESS_WORDS = {
    "academy", "associates", "bank", "bros", "brothers", "cc", "center", "church",
    "club", "co", "college", "company", "corp", "corporate", "corporation",
    "daycare", "delivery", "design", "energy", "fee", "firm", "group",
    "hospital", "hotel", "inc", "inn", "install", "labor", "llc", "logistics",
    "ltd", "management", "manufacturing", "market", "office", "pickup", "properties",
    "property", "repair", "residence", "retreat", "school", "solutions", "store",
    "suites", "surgery", "takedown", "the", "university", "wealth",
}
#: Titles and suffixes: a person, but worth a human look (where does "Dr." go?).
_TITLES = {"dr", "mr", "mrs", "ms", "miss", "jr", "sr", "ii", "iii", "md", "phd"}
_WORD = re.compile(r"[A-Za-z0-9'&]+")
_DASH = re.compile(r"\s[-–—]\s?|\s?[-–—]\s|\S-[A-Z]")


def _clean(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def person_name(first_name: Optional[str], last_name: Optional[str]) -> str:
    last, first = _clean(last_name), _clean(first_name)
    if last and first:
        return f"{last}, {first}"
    return last or first


def compose_name(first_name: Optional[str] = None, last_name: Optional[str] = None,
                 company: Optional[str] = None, site: Optional[str] = None) -> str:
    """The canonical display name for a set of parts ("" when there is no
    person or business name -- a location alone isn't a name).

    A business goes by its business name: with a company set, the person
    (if any) is the contact and is left out of the name."""
    business, where = _clean(company), _clean(site)
    if business:
        return f"{business}{BUSINESS_SEP}{where}" if where else business
    person = person_name(first_name, last_name)
    if person:
        return f"{person}{PERSON_SITE_SEP}{where}" if where else person
    return ""


def compose_name_before_20261009(first_name: Optional[str] = None, last_name: Optional[str] = None,
                                 company: Optional[str] = None, site: Optional[str] = None) -> str:
    """The rule before 2026-10-09 ("Business | Last, First", "Business |
    Location"). Only for reports that compare old and new names."""
    person = person_name(first_name, last_name)
    business, where = _clean(company), _clean(site)
    if person:
        if where:
            person = f"{person}{PERSON_SITE_SEP}{where}"
        return f"{business}{BUSINESS_SEP}{person}" if business else person
    if business:
        return f"{business}{BUSINESS_SEP}{where}" if where else business
    return ""


def duplicate_name_message(parts: Optional[dict], name: str, default: str) -> str:
    """The 409 message when ``name`` is already another client's.

    Businesses go by the business name alone, so two cards for one business
    (two contact people, no location) now compose the same name. Say how to
    tell them apart instead of just "taken"."""
    if parts and parts.get("company"):
        return (f'{default}: "{name}". A business goes by its business name, so add a '
                f'Location to tell two of its cards apart (e.g. "{name}{BUSINESS_SEP}Office").')
    return default


def kind_of(parts: dict) -> str:
    """'person', 'business' or 'business + person' -- for reports only."""
    person = bool(parts.get("first_name") or parts.get("last_name"))
    business = bool(parts.get("company"))
    return "business + person" if person and business else "person" if person else "business"


def _empty() -> dict:
    return dict.fromkeys(PART_FIELDS)


def _person_checks(n: str, last: str, first: str, reasons: list) -> None:
    wordset = set(_words(n))
    if "&" in n or "and" in wordset:
        reasons.append("two people (& / and)")
    if wordset & _TITLES:
        reasons.append("has a title (Dr., Mr., Jr.)")
    if "family" in wordset:
        reasons.append("says Family")
    if any(ch in n for ch in "()/"):
        reasons.append("has ( ) or /")
    if len(_words(last)) > 2 or len(_words(first)) > 2:
        reasons.append("many words on one side of the comma")
    if any(ch.isdigit() for ch in last + first):
        reasons.append("has a number")
    if _DASH.search(first):
        reasons.append("a dash in the first name (a location?)")


def _split_person(text: str) -> Optional[tuple[str, str, Optional[str]]]:
    """"Last, First" or "Last, First - Location" -> (last, first, location),
    or None when it doesn't have exactly one comma with words both sides."""
    if text.count(",") != 1:
        return None
    last, rest = (_clean(x) for x in text.split(",", 1))
    if not last or not rest:
        return None
    first, where = rest, None
    if PERSON_SITE_SEP in rest:
        first, where = (_clean(x) for x in rest.split(PERSON_SITE_SEP, 1))
        if not first:
            return None
    return last, first, where or None


def split_name(name: Optional[str]) -> tuple[dict, list[str]]:
    """Propose parts for an existing name, plus why a human should check it.

    * "Business | rest": rest is a person ("Last, First", maybe with
      " - Location") when it has exactly one comma, else the location.
      "Business | Location" reads back exactly. "Business | Last, First"
      (the style before 2026-10-09) parses as before but now composes to
      just the business (+ " | Location"), so it carries a "would read"
      reason: renaming it is a separate, approved step;
    * one comma: a person ("Last, First"), and " - Location" after the
      first name is their location ("Byler, Kerri - House");
    * anything else: the whole name is the business name.

    The second value lists reasons the guess is unsure ([] when it is
    confident). A proposal is never allowed to change how the name reads:
    if its parts don't compose back to exactly ``name``, that is a reason too.
    """
    n = _clean(name)
    reasons: list[str] = []
    parts = _empty()
    if not n:
        return parts, ["blank name"]

    if "|" in n:
        if BUSINESS_SEP in n:
            company, rest = (_clean(x) for x in n.split(BUSINESS_SEP, 1))
        else:  # "Hanover|Viridian" -- a bar without spaces
            company, rest = (_clean(x) for x in n.split("|", 1))
            reasons.append("bar without spaces")
        parts["company"] = company or None
        if "|" in rest:
            reasons.append("more than one |")
        person = _split_person(rest)
        if person:
            parts["last_name"], parts["first_name"], parts["site"] = person
            reasons.append("a business and a person -- check which is which")
            _person_checks(rest, person[0], person[1], reasons)
        else:
            parts["site"] = rest or None
            if "," in rest:
                reasons.append("commas in the location")
        if "," in company:
            reasons.append("comma in the business name (a person's name?)")
    else:
        person = _split_person(n)
        name_words = set(_words(f"{person[0]} {person[1]}")) if person else set()
        if person and not (name_words & (_BUSINESS_WORDS - _TITLES)):
            parts["last_name"], parts["first_name"], parts["site"] = person
            _person_checks(n, person[0], person[1], reasons)
        else:
            parts["company"] = n
            words = _words(n)
            wordset = set(words)
            if person:
                reasons.append("comma, but has a business word")
            elif "," in n:
                reasons.append("more than one comma" if n.count(",") > 1 else "comma with nothing on one side")
            elif _DASH.search(n):
                reasons.append("has a dash (a location?)")
            elif "family" in wordset:
                reasons.append("says Family")
            elif any(ch in n for ch in "()/"):
                reasons.append("has ( ) or /")
            elif len(words) == 1 and n.isalpha() and not n.isupper() and not wordset & _BUSINESS_WORDS:
                # "Hellums", "Schieb", "Juban": a family name on its own, or a
                # one-word business ("Flotek")? Only a person can tell.
                reasons.append("one word: a last name or a business?")
            elif (2 <= len(words) <= 3 and not wordset & _BUSINESS_WORDS
                  and re.fullmatch(r"[A-Za-z' .]+", n) and not n.isupper()):
                # "Amy Allen", "Bergstorm Debbie": probably a person typed
                # without the comma, but which word is the last name is a guess.
                reasons.append("no comma, but looks like a person's name")

    composed = compose_name(**parts)
    if composed != n:
        reasons.append(f'would read "{composed}"')
    if n != (name or ""):
        reasons.append("extra spaces in the stored name")
    return parts, reasons


def has_saved_parts(row: dict) -> bool:
    return any(row.get(k) for k in PART_FIELDS)


def name_parts(row: dict) -> dict:
    """The parts to show for a client row: the saved ones when the row has
    any, otherwise derived from ``name`` (``name_parts_saved`` says which)."""
    if has_saved_parts(row):
        out = {k: row.get(k) or None for k in PART_FIELDS}
        out["name_parts_saved"] = True
        return out
    parts, _ = split_name(row.get("name"))
    return {**parts, "name_parts_saved": False}


class NamePartsError(ValueError):
    """Parts that cannot make a name (the API turns it into a 400)."""


def clean_parts(first_name: Optional[str], last_name: Optional[str],
                company: Optional[str], site: Optional[str]) -> dict:
    """Validate and normalise parts from a request.

    The person's first and last name are kept even when a company is set
    (they are the contact person); they just don't show in the name. The
    same checks apply either way, so a later edit that clears the company
    still makes a clean "Last, First"."""
    out = {"first_name": _clean(first_name) or None, "last_name": _clean(last_name) or None,
           "company": _clean(company) or None, "site": _clean(site) or None}
    if not (out["first_name"] or out["last_name"] or out["company"]):
        raise NamePartsError("Enter a first or last name, or a business name")
    if any("|" in (v or "") for v in out.values()):
        raise NamePartsError("Names can't contain |")
    if any("," in (out[k] or "") for k in ("first_name", "last_name")):
        raise NamePartsError("First and last names can't contain a comma")
    return out
