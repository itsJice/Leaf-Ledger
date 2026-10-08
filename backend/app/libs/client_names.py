"""A client's name, as parts (migrations/021).

``clients.name`` stays the one canonical spelling: every table that keeps a
client's name as text, the spreadsheet sync, the billing-export loader, the
Install Schedule page and every search match on it. The parts are how people
type it:

* a **person**: first name + last name, shown as ``"Last, First"``
  (the Christmas spreadsheet's own convention, e.g. ``"Scheib, Nataliya"``);
* a **business**: company + an optional location/site, shown as
  ``"Company | Site"`` or just ``"Company"``
  (``"The Club at Carlton Woods | Nicklaus Clubhouse"``, ``"A Hug Away | Daycare"``).

``compose_name`` builds the display name from the parts; ``split_name`` reads
parts back out of an existing name. The parts columns are nullable: a client
the sync created, or one nobody has re-saved since the columns arrived, has
none, and ``name_parts`` derives them on the fly so the edit form always has
something to show. ``scripts/split_client_names.py`` uses the same parser to
propose a backfill (dry run first; it never changes ``name``).
"""

from __future__ import annotations

import re
from typing import Optional

CLIENT_TYPES = ("person", "business")
PART_FIELDS = ("first_name", "last_name", "company", "site")
#: Every column the parts live in, in the order the API returns them.
NAME_PART_COLUMNS = ("client_type",) + PART_FIELDS

#: The separator between a company and its site. Spaces on both sides, so a
#: "|" inside a word never splits it.
SITE_SEP = " | "

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


def _clean(value: Optional[str]) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _words(text: str) -> list[str]:
    return [w.lower() for w in _WORD.findall(text or "")]


def compose_name(client_type: Optional[str], first_name: Optional[str] = None,
                 last_name: Optional[str] = None, company: Optional[str] = None,
                 site: Optional[str] = None) -> str:
    """The canonical display name for a set of parts ("" when there is none).

    Person: ``"Last, First"`` (just one of them when the other is blank).
    Business: ``"Company | Site"``, or ``"Company"`` with no site.
    """
    if client_type == "person":
        last, first = _clean(last_name), _clean(first_name)
        if last and first:
            return f"{last}, {first}"
        return last or first
    if client_type == "business":
        comp, where = _clean(company), _clean(site)
        if comp and where:
            return f"{comp}{SITE_SEP}{where}"
        return comp or where
    return ""


def _empty(client_type: str) -> dict:
    return {"client_type": client_type, "first_name": None, "last_name": None,
            "company": None, "site": None}


def split_name(name: Optional[str]) -> tuple[dict, list[str]]:
    """Propose parts for an existing name, plus why a human should check it.

    Rules (the plan the user approved, 10/8/26):

    * contains ``" | "`` -> business: company | site;
    * exactly one comma and it looks like a person -> person: last, first;
    * otherwise -> business, company only (the whole name).

    The second value lists reasons the guess is unsure ([] when it is
    confident). A proposal is never allowed to change how the name reads:
    if its parts don't compose back to exactly ``name``, that is a reason too.
    """
    n = _clean(name)
    reasons: list[str] = []
    if not n:
        return _empty("business"), ["blank name"]
    words = _words(n)
    wordset = set(words)

    if "|" in n:
        parts = _empty("business")
        if SITE_SEP in n:
            company, site = n.split(SITE_SEP, 1)
        else:  # "Hanover|Viridian" -- a bar without spaces
            company, site = n.split("|", 1)
            reasons.append("bar without spaces")
        parts["company"], parts["site"] = _clean(company) or None, _clean(site) or None
        if SITE_SEP in (site or "") or "|" in (site or ""):
            reasons.append("more than one |")
        if "," in (company or ""):
            reasons.append("comma in the company part (a person's name?)")
        if "," in (site or ""):
            reasons.append("comma in the site (a person's name?)")
    elif n.count(",") == 1:
        last, first = (_clean(x) for x in n.split(",", 1))
        lw, fw = _words(last), _words(first)
        business = bool(wordset & _BUSINESS_WORDS - _TITLES)
        if not last or not first:
            parts = _empty("business")
            parts["company"] = n
            reasons.append("comma with nothing on one side")
        elif business:
            parts = _empty("business")
            parts["company"] = n
            reasons.append("comma, but has a business word")
        else:
            parts = _empty("person")
            parts["last_name"], parts["first_name"] = last, first
            if "&" in n or "and" in wordset:
                reasons.append("two people (& / and)")
            if wordset & _TITLES:
                reasons.append("has a title (Dr., Mr., Jr.)")
            if "family" in wordset:
                reasons.append("says Family")
            if any(ch in n for ch in "()/"):
                reasons.append("has ( ) or /")
            if re.search(r"\s[-–—]\s?|\s?[-–—]\s", n):
                reasons.append("has a dash (a site?)")
            if len(lw) > 2 or len(fw) > 2:
                reasons.append("many words on one side of the comma")
            if any(ch.isdigit() for ch in n):
                reasons.append("has a number")
    else:
        parts = _empty("business")
        parts["company"] = n
        if n.count(",") > 1:
            reasons.append("more than one comma")
        elif re.search(r"\s[-–—]\s?|\s?[-–—]\s|\S-[A-Z]", n):
            reasons.append("has a dash (a site?)")
        elif "family" in wordset:
            reasons.append("says Family")
        elif any(ch in n for ch in "()/"):
            reasons.append("has ( ) or /")
        elif (len(words) == 1 and n.isalpha() and not n.isupper()
              and not wordset & _BUSINESS_WORDS):
            # "Hellums", "Schieb", "Juban": a family name on its own, or a
            # one-word company ("Flotek")? Only a person can tell.
            reasons.append("one word: a last name or a company?")
        elif (2 <= len(words) <= 3 and not wordset & _BUSINESS_WORDS
              and re.fullmatch(r"[A-Za-z' .]+", n)
              and not n.isupper()):
            # "Amy Allen", "Bergstorm Debbie": probably a person typed
            # without the comma, but which word is the last name is a guess.
            reasons.append("no comma, but looks like a person's name")

    composed = compose_name(**parts)
    if composed != n:
        reasons.append(f'would read "{composed}"')
    if _clean(name) != (name or ""):
        reasons.append("extra spaces in the stored name")
    return parts, reasons


def name_parts(row: dict) -> dict:
    """The parts to show for a client row: the saved ones when the row has
    them, otherwise derived from ``name`` (``name_parts_saved`` says which)."""
    client_type = row.get("client_type")
    if client_type in CLIENT_TYPES:
        out = {"client_type": client_type}
        for key in PART_FIELDS:
            out[key] = row.get(key) or None
        out["name_parts_saved"] = True
        return out
    parts, _ = split_name(row.get("name"))
    return {**parts, "name_parts_saved": False}


class NamePartsError(ValueError):
    """Parts that cannot make a name (the API turns it into a 400)."""


def clean_parts(client_type: Optional[str], first_name: Optional[str], last_name: Optional[str],
                company: Optional[str], site: Optional[str]) -> dict:
    """Validate and normalise parts from a request. Only the fields that
    belong to the type are kept; the others are cleared, so switching a
    client from person to business doesn't leave a stale first name behind."""
    t = (client_type or "").strip().lower()
    if t not in CLIENT_TYPES:
        raise NamePartsError("client_type must be person or business")
    out = _empty(t)
    if t == "person":
        out["first_name"] = _clean(first_name) or None
        out["last_name"] = _clean(last_name) or None
        if not out["last_name"] and not out["first_name"]:
            raise NamePartsError("A person needs a first or last name")
        for v in (out["first_name"], out["last_name"]):
            if v and ("|" in v or "," in v):
                raise NamePartsError("Names can't contain a comma or |")
    else:
        out["company"] = _clean(company) or None
        out["site"] = _clean(site) or None
        if not out["company"]:
            raise NamePartsError("A business needs a company name")
        if "|" in (out["company"] or "") or "|" in (out["site"] or ""):
            raise NamePartsError("Company and site can't contain |")
    return out
