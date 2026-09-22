"""One client, one season: the fields in ``client_activity.detail`` and the
rules every writer of that row shares.

Three things write a client's ``christmas_install`` row for a season:

* ``scheduler/sync_clients.py`` -- the spreadsheet sync. It rebuilds the row
  from the sheet on every run.
* ``app.apis.install_schedule`` -- the scheduling tool's save, which writes
  the not-installing / on-hold decision through to the client record.
* ``app.apis.clients`` -- the Clients tab's per-season editor (storing with
  us, fees, notes, the same flags).

Before this module each of them carried its own copy of the summary wording
and its own idea of what survives a re-sync (only ``not_installing`` did,
by a hand-written special case). The app is the source of truth, so the
rule is now general and lives here:

**A value edited in the app is recorded in ``detail["app_edits"]`` (key ->
ISO timestamp of the edit) and the sync never overwrites it.** Everything
else in the row is the sheet's to refresh. ``not_installing``, ``hold`` and
``was_scheduled`` are only ever set by the app, so they are carried forward
whether or not they are stamped -- rows written before stamping existed
still have to survive.

The scheduler pipeline imports this through ``scheduler/season.py``'s
sys.path bridge, the same way it reaches ``app.libs.season`` -- so there is
one summary function, not three that must be kept in step by hand.
"""
from __future__ import annotations

import datetime as _dt
from typing import Any

#: Rendered verbatim by the Clients tab next to a badge that already shows
#: the season year -- so no "this year" / "2026 season" in the text.
NOT_INSTALLING_SUMMARY = "Not installing"
#: Fallback when no install date is on record. Not "not scheduled" -- for the
#: older seasons the date simply was never tracked, which is a different thing.
NO_DATE_SUMMARY = "No date recorded"
HOLD_SUMMARY = "On hold"
CANCELLED_SUMMARY = "Cancelled before install"

APP_EDITS_KEY = "app_edits"

#: Flags only the app sets. Carried across a re-sync even when unstamped.
APP_FLAGS = ("not_installing", "hold", "was_scheduled")

#: ``clients.time_preference`` values (migrations/015). Per client, not per
#: season: a daycare that needs mornings needs them every year.
TIME_PREFERENCES = ("morning", "afternoon", "late")

#: Every per-season key the app may write, with how its value is coerced.
#: The whitelist is the API contract for PUT /clients/{id}/seasons/{season}:
#: an unknown key is a 400, not a silent write of arbitrary JSON.
#:
#: The keys are deliberately the same ones the sheet sync writes, so a value
#: has one name whether it came from the spreadsheet or from a person.
SEASON_FIELDS: dict[str, str] = {
    # status
    "not_installing": "bool",
    "hold": "bool",
    # storage
    "storing": "bool",
    "boxes": "int",
    # money
    "install_fee": "money",
    "takedown_fee": "money",
    "storage_fee": "money",
    "total": "money",
    "ideal_total": "money",
    "invoice_total": "money",
    # dates
    "install_date": "date",
    "takedown_date": "date",
    # crew and hours
    "crew": "text",
    "crew_size": "int",
    "est_hours": "number",
    "real_hours": "number",
    "takedown_order": "int",
    "takedown_est_hours": "number",
    "takedown_real_hours": "number",
    "specialty": "text",
    # words
    "notes": "text",
    "production_notes": "text",
    "confirmation_notes": "text",
}


def now_iso() -> str:
    """Module-level so a test can pin it."""
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def mdy(iso_date: str) -> str:
    """ISO "YYYY-MM-DD" -> "MM/DD/YYYY" (US format, like the rest of the app).
    Anything not cleanly YYYY-MM-DD comes back unchanged rather than raising."""
    parts = str(iso_date).split("-")
    if len(parts) != 3:
        return str(iso_date)
    y, m, d = parts
    return f"{m}/{d}/{y}"


def season_total(detail: dict) -> float | None:
    """The season's total: the sheet's total if it has one, else the fees
    summed -- the same fallback summarize() has always used."""
    total = detail.get("total")
    if total is None and detail.get("install_fee") is not None:
        total = round((detail.get("install_fee") or 0)
                      + (detail.get("takedown_fee") or 0)
                      + (detail.get("storage_fee") or 0), 2)
    try:
        return float(total) if total is not None else None
    except (TypeError, ValueError):
        return None


def summarize(detail: dict | None) -> str:
    """The one-line summary the Clients tab shows for a season.

    Derived from ``detail`` alone so any writer produces the same line for
    the same row, and so the line can be rebuilt when a flag is cleared.
    """
    d = detail or {}
    if d.get("cancelled"):
        return CANCELLED_SUMMARY
    if d.get("not_installing"):
        was = d.get("was_scheduled") or d.get("install_date")
        return (f"{NOT_INSTALLING_SUMMARY} — previously scheduled {mdy(was)}"
                if was else NOT_INSTALLING_SUMMARY)
    bits = []
    if d.get("install_date"):
        bits.append(f"Scheduled {mdy(d['install_date'])}")
    else:
        bits.append(NO_DATE_SUMMARY)
    total = season_total(d)
    if total:
        bits.append(f"${total:,.0f}")
    line = " · ".join(bits)
    return f"{HOLD_SUMMARY} · {line}" if d.get("hold") else line


def stamp(detail: dict, keys, when: str | None = None) -> dict:
    """Record that ``keys`` were set in the app (so the sync leaves them)."""
    edits = detail.get(APP_EDITS_KEY)
    if not isinstance(edits, dict):
        edits = {}
    when = when or now_iso()
    for k in keys:
        edits[k] = when
    detail[APP_EDITS_KEY] = edits
    return detail


def unstamp(detail: dict, keys) -> dict:
    """Forget an app edit -- the next sync may refresh the key again."""
    edits = detail.get(APP_EDITS_KEY)
    if isinstance(edits, dict):
        for k in keys:
            edits.pop(k, None)
        if not edits:
            detail.pop(APP_EDITS_KEY, None)
    return detail


def app_owned_keys(detail: dict | None) -> set[str]:
    d = detail or {}
    edits = d.get(APP_EDITS_KEY)
    owned = set(edits.keys()) if isinstance(edits, dict) else set()
    owned.update(k for k in APP_FLAGS if d.get(k) not in (None, False, ""))
    return owned


def merge_sheet_detail(prior: dict | None, fresh: dict) -> dict:
    """What the sync should store: the sheet's fresh record, with every
    app-owned value from the prior row kept on top of it."""
    out = dict(fresh)
    if not prior:
        return out
    for k in app_owned_keys(prior):
        if k in prior:
            out[k] = prior[k]
    edits = prior.get(APP_EDITS_KEY)
    if isinstance(edits, dict) and edits:
        out[APP_EDITS_KEY] = dict(edits)
    return out


def supplement_detail(prior: dict | None, extra: dict) -> dict:
    """Add sheet-sourced values to an existing row without disturbing what
    it already has from the app. Used when the current sheet carries a
    column about an EARLIER season (last season's real hours, crew, invoice
    total, takedown date) that belongs on that season's row."""
    out = dict(prior or {})
    owned = app_owned_keys(prior)
    for k, v in extra.items():
        if v is None or k in owned:
            continue
        out[k] = v
    return out


# ─── coercion for the app-side editor ────────────────────────────────────────


class FieldError(ValueError):
    pass


def _as_bool(v: Any) -> bool | None:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "yes", "y", "1"):
        return True
    if s in ("false", "no", "n", "0"):
        return False
    raise FieldError(f"expected yes/no, got {v!r}")


def _as_number(v: Any, *, integer: bool = False, money: bool = False):
    if v is None or v == "":
        return None
    try:
        n = float(str(v).replace("$", "").replace(",", "").strip())
    except ValueError:
        raise FieldError(f"expected a number, got {v!r}") from None
    if integer:
        if n != int(n):
            raise FieldError(f"expected a whole number, got {v!r}")
        return int(n)
    return round(n, 2) if money else n


def _as_date(v: Any) -> str | None:
    if v is None or v == "":
        return None
    s = str(v).strip()[:10]
    try:
        return _dt.date.fromisoformat(s).isoformat()
    except ValueError:
        raise FieldError(f"expected YYYY-MM-DD, got {v!r}") from None


def _as_text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def coerce_field(key: str, value: Any):
    """Validate one app-side edit. Raises FieldError on an unknown key or a
    value that does not fit the key's type. An empty string clears the key."""
    kind = SEASON_FIELDS.get(key)
    if kind is None:
        raise FieldError(f"unknown season field {key!r}")
    if kind == "bool":
        return _as_bool(value)
    if kind == "int":
        return _as_number(value, integer=True)
    if kind == "money":
        return _as_number(value, money=True)
    if kind == "number":
        return _as_number(value)
    if kind == "date":
        return _as_date(value)
    return _as_text(value)


def apply_edits(detail: dict | None, fields: dict, when: str | None = None) -> dict:
    """Apply a person's per-season edits to a detail dict and stamp them.

    A ``None`` (or "") value clears the key and drops its stamp, so the sheet
    may fill it again. ``hold`` and ``not_installing`` are exclusive: setting
    either true clears the other, and marking not-installing remembers the
    date the client was pulled off of (``was_scheduled``) so the summary can
    say so.
    """
    d = dict(detail or {})
    cleaned = {k: coerce_field(k, v) for k, v in fields.items()}
    set_keys, clear_keys = [], []
    for k, v in cleaned.items():
        if v is None or v is False and k in ("hold", "not_installing"):
            d.pop(k, None)
            clear_keys.append(k)
        else:
            d[k] = v
            set_keys.append(k)
    if cleaned.get("not_installing"):
        d.pop("hold", None)
        clear_keys.append("hold")
        if d.get("install_date") and not d.get("was_scheduled"):
            d["was_scheduled"] = d["install_date"]
    elif "not_installing" in cleaned:  # explicitly cleared
        d.pop("was_scheduled", None)
    if cleaned.get("hold"):
        d.pop("not_installing", None)
        d.pop("was_scheduled", None)
        clear_keys.append("not_installing")
    stamp(d, set_keys, when)
    unstamp(d, clear_keys)
    return d
