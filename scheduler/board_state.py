#!/usr/bin/env python3
"""The live board is the source of truth for dates -- helpers that keep it so.

Staff move stops around in the published review tool all season. Those edits
live in Postgres as the tool's *shared state*, keyed on the build version that
produced the page (`ll_app.install_schedule_state`). Two things used to make
a pipeline rebuild look like it had wiped everyone's dates:

  1. `schedule.py` re-solves from scratch unless `overrides.json` (the
     notebook) freezes the current assignments -- and the notebook was a
     manual export someone had to remember to make.
  2. A rebuild changes the version hash, and the tool only reads state for
     *its own* version, so a freshly published build opened with an empty
     board even though the previous build's state was still in the table.

This module is the shared machinery for closing both gaps:

  * `notebook_from_board()` -- turn the published build + its shared state
    into a notebook, exactly as the tool's own "Export notebook" would, so
    `sync_notebook.py` can refresh `overrides.json` before every rebuild.
  * `carry_state()` -- remap the previous build's shared state onto a new
    build (by client NAME, never row -- a sheet row insertion renumbers every
    row after it) and place clients new to the board at their baseline day,
    so `publish_pages.py` can hand the new version a board that matches what
    staff were looking at a minute earlier.

Nothing here writes a file or a row on import; the callers decide that.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(HERE, "..", "backend", ".env.supabase")

#: Rows at or above this are clients added in the tool / notebook, not sheet
#: rows. Mirrors `nextSyntheticRow` in build_review.py and the notebook's
#: `new_clients[].row`.
SYNTHETIC_ROW = 900000

#: Keys in a state snapshot that are keyed by client row, or contain rows.
#: Anything not listed here is carried verbatim.
ROW_KEYED_MAPS = ("comments", "lastScheduledFrom")
ROW_LISTS = ("notInstalling", "confirmed")


# ---------------------------------------------------------------------------
# environment / database
# ---------------------------------------------------------------------------
def load_env(path=ENV_FILE):
    """Populate os.environ from backend/.env.supabase without overriding
    anything already set (same rule publish_pages.py has always used)."""
    if not os.path.exists(path):
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            os.environ.setdefault(k, v.strip().strip('"').strip("'"))


def database_url():
    load_env()
    return os.environ.get("DATABASE_URL")


async def connect():
    import asyncpg
    url = database_url()
    if not url:
        raise SystemExit(
            f"DATABASE_URL not set (checked env and {ENV_FILE})."
        )
    return await asyncpg.connect(url, statement_cache_size=0)


def loads(raw):
    return json.loads(raw) if isinstance(raw, str) else raw


def now_ms():
    return int(datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000)


# ---------------------------------------------------------------------------
# the published page and its state
# ---------------------------------------------------------------------------
PAYLOAD_MARK = "const DATA = "


def extract_payload(html):
    """The tool embeds its whole dataset as `const DATA = {...};` -- pull that
    object back out. Raises ValueError if the page isn't a review tool."""
    i = html.find(PAYLOAD_MARK)
    if i < 0:
        raise ValueError("no embedded DATA payload -- not a review tool page")
    obj, _ = json.JSONDecoder().raw_decode(html[i + len(PAYLOAD_MARK):])
    return obj


def payload_version(payload):
    return (payload.get("spec") or {}).get("version")


async def fetch_published_payload(conn, season):
    row = await conn.fetchrow(
        "SELECT html, updated_at FROM ll_app.install_schedule_pages "
        " WHERE season = $1 AND name = 'index.html'",
        season,
    )
    if not row:
        return None, None
    return extract_payload(row["html"]), row["updated_at"]


async def fetch_state(conn, version):
    row = await conn.fetchrow(
        "SELECT state, updated_at FROM ll_app.install_schedule_state "
        " WHERE version = $1",
        version,
    )
    if not row:
        return None, None
    return loads(row["state"]) or {}, row["updated_at"]


async def write_state(conn, version, season, state, updated_by):
    """Create the shared-state row for `version` (plus its first history
    entry). Refuses to overwrite a row that already holds a placement --
    that is a real edit someone made, and this function is only ever
    supposed to fill an empty board."""
    existing, _ = await fetch_state(conn, version)
    if existing and existing.get("placement"):
        return False
    payload = json.dumps(state)
    async with conn.transaction():
        await conn.execute(
            "INSERT INTO ll_app.install_schedule_state "
            "(version, season, state, updated_by) "
            "VALUES ($1, $2, $3::jsonb, $4) "
            "ON CONFLICT (version) DO UPDATE "
            "SET state = EXCLUDED.state, season = COALESCE(EXCLUDED.season, "
            "ll_app.install_schedule_state.season), "
            "updated_by = EXCLUDED.updated_by, updated_at = now()",
            version, season, payload, updated_by,
        )
        await conn.execute(
            "INSERT INTO ll_app.install_schedule_history "
            "(version, season, state, updated_by) VALUES ($1, $2, $3::jsonb, $4)",
            version, season, payload, updated_by,
        )
    return True


# ---------------------------------------------------------------------------
# name <-> row
# ---------------------------------------------------------------------------
def client_names(payload):
    """row -> name for every client baked into a build (sheet rows and the
    notebook's new_clients alike)."""
    return {int(r): c["name"] for r, c in (payload.get("clients") or {}).items()}


def name_map(payload, state=None):
    """row -> name for the board a person actually sees: the build's clients
    plus any client added in the tool (state.newClients). A build's own row
    wins a collision, which is also what the tool does on restore."""
    names = client_names(payload)
    for c in (state or {}).get("newClients") or []:
        try:
            names.setdefault(int(c["row"]), c["name"])
        except (KeyError, TypeError, ValueError):
            continue
    return names


def baseline_days(payload):
    """row -> [day id] as the build itself placed each client."""
    out = {}
    for d in payload.get("days") or []:
        for r in d.get("stops") or []:
            out.setdefault(int(r), []).append(d["id"])
    return out


def board_placement(payload, state):
    """What is on the board: the shared state's placement if it has one,
    else the build's own baseline (a build nobody has edited yet)."""
    if state and state.get("placement"):
        return {str(r): list(ids) for r, ids in state["placement"].items()}
    return {str(r): ids for r, ids in baseline_days(payload).items()}


# ---------------------------------------------------------------------------
# notebook
# ---------------------------------------------------------------------------
def default_day_meta(spec):
    k = spec.get("const") or {}
    return {"cat": "Standard", "anchored": True, "stacked": 1, "note": "",
            "win": k.get("DAY_CAP"), "lunchMin": k.get("LUNCH"),
            "half": [], "joint": "", "startRow": None}


def notebook_from_board(payload, state, prior_notebook=None):
    """Build a `tbdg-install-overrides` document from the published build and
    its shared state -- the same thing exportNotebook() in the tool writes.

    Every crew-day on the board is frozen: date, crew, stops (by name), and
    the day's window / lunch / anchoring / stacking / joint / half-day /
    lead-stop metadata from the build (a staff-added date gets the tool's
    own defaults, as it does on screen). Stop order follows the staff's
    manual order where they set one, else the build's route order.

    Returns (notebook, report). The report lists anything that could not be
    frozen so the caller can print it -- silence here is how a rebuild moves
    someone without anyone noticing.
    """
    spec = payload.get("spec") or {}
    meta = spec.get("dayMeta") or {}
    names = name_map(payload, state)
    base_order = {d["id"]: [int(r) for r in d.get("stops") or []]
                  for d in payload.get("days") or []}
    manual = {k: [int(x) for x in v]
              for k, v in ((state or {}).get("manualOrder") or {}).items()}
    calendar = {c["date"]: c for c in spec.get("calendar") or []}
    crews = set((spec.get("const") or {}).get("CREWS") or [])

    by_day = {}
    for r, ids in board_placement(payload, state).items():
        for did in ids:
            by_day.setdefault(did, []).append(int(r))

    report = {"unknown_rows": [], "bad_days": [], "days": 0, "stops": 0}
    days_out = []
    for did in sorted(by_day):
        rows = by_day[did]
        try:
            date, crew, _occ = did.split("|")
        except ValueError:
            report["bad_days"].append(did)
            continue
        if date not in calendar or (crews and crew not in crews):
            report["bad_days"].append(did)
            continue
        order = manual.get(did) or base_order.get(did) or []
        ordered = [r for r in order if r in rows] + sorted(r for r in rows if r not in order)
        stop_names = []
        for r in ordered:
            n = names.get(r)
            if n is None:
                report["unknown_rows"].append((did, r))
                continue
            stop_names.append(n)
        if not stop_names:
            continue
        m = meta.get(did) or default_day_meta(spec)
        half = [names[r] for r in (m.get("half") or []) if r in ordered and r in names]
        start = m.get("startRow")
        start_name = names.get(start) if start is not None and start in ordered else None
        days_out.append({
            "date": date, "crew": crew, "cat": m.get("cat", "Standard"),
            "stops": stop_names,
            "win": m.get("win"), "lunch": m.get("lunchMin"),
            "anchored": m.get("anchored", True), "stacked": m.get("stacked", 1),
            "joint": m.get("joint") or "", "half": half, "startRow": start_name,
            "note": m.get("note") or "",
        })
        report["days"] += 1
        report["stops"] += len(stop_names)

    # Clients that exist only because a notebook (or the tool) created them.
    # The build does NOT mark notebook-baked clients as synthetic, so the
    # tool's own export would silently drop them -- carry the prior
    # notebook's entries by name, then add anything the tool created since
    # (skipping an entry whose row the build already gave to someone else;
    # the tool never restores those either).
    new_clients = []
    seen = set()
    for c in (prior_notebook or {}).get("new_clients") or []:
        if c.get("name") and c["name"] not in seen:
            new_clients.append(c)
            seen.add(c["name"])
    build_names = client_names(payload)
    report["ghost_clients"] = []
    for c in (state or {}).get("newClients") or []:
        n = c.get("name")
        if not n or n in seen:
            continue
        try:
            row = int(c["row"])
        except (KeyError, TypeError, ValueError):
            continue
        if row in build_names and build_names[row] != n:
            report["ghost_clients"].append(n)
            continue
        new_clients.append(c)
        seen.add(n)

    notebook = {
        "kind": "tbdg-install-overrides",
        "version": payload_version(payload),
        "savedAt": datetime.datetime.now(datetime.timezone.utc)
                   .isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": "sync_notebook.py (live board)",
        "new_clients": new_clients,
        "days": days_out,
    }
    report["clients"] = len({n for d in days_out for n in d["stops"]})
    return notebook, report


# ---------------------------------------------------------------------------
# carrying state onto a new build
# ---------------------------------------------------------------------------
def carry_state(old_payload, old_state, new_payload, season=None):
    """Remap a previous build's shared state onto a new build.

    Everything keyed by row is re-keyed by client NAME through the two
    builds' client tables. A client the new build no longer has is dropped
    (and reported). A client the new build has that the old board never
    placed -- new to the season, or freshly given an address -- is placed at
    the new build's own baseline day, so it appears instead of vanishing.
    Roster, staffing, comments, confirmations, "not installing", manual
    stop order and the move log all come along.

    Returns (new_state, report).
    """
    old_names = name_map(old_payload, old_state)
    new_names = client_names(new_payload)
    new_rows = {n: r for r, n in new_names.items()}
    old_synthetic = {}
    for c in (old_state or {}).get("newClients") or []:
        try:
            old_synthetic[int(c["row"])] = c["name"]
        except (KeyError, TypeError, ValueError):
            pass

    report = {"dropped": [], "added": [], "renumbered": []}

    def remap(row):
        try:
            r = int(row)
        except (TypeError, ValueError):
            return None
        n = old_names.get(r)
        if n is None:
            return None
        nr = new_rows.get(n)
        if nr is not None:
            if nr != r:
                report["renumbered"].append((n, r, nr))
            return nr
        if r >= SYNTHETIC_ROW and old_synthetic.get(r) == n:
            return r          # the tool recreates it from newClients
        return None

    state = dict(old_state or {})

    placement = {}
    for r, ids in (old_state.get("placement") or {}).items():
        nr = remap(r)
        if nr is None:
            report["dropped"].append(old_names.get(int(r), str(r)))
            continue
        placement[str(nr)] = list(ids)

    for key in ROW_LISTS:
        out = []
        for r in old_state.get(key) or []:
            nr = remap(r)
            if nr is not None and nr not in out:
                out.append(nr)
        state[key] = out

    for key in ROW_KEYED_MAPS:
        out = {}
        for r, v in (old_state.get(key) or {}).items():
            nr = remap(r)
            if nr is not None:
                out[str(nr)] = v
        state[key] = out

    manual = {}
    for did, rows in (old_state.get("manualOrder") or {}).items():
        kept = [nr for nr in (remap(r) for r in rows) if nr is not None]
        if kept:
            manual[did] = kept
    state["manualOrder"] = manual

    moves = []
    for m in old_state.get("moves") or []:
        # Only a move that names a real client row is re-keyed; an entry
        # with no row (a date/day-level change) is log text and carries as-is.
        if isinstance(m, dict) and m.get("row") is not None:
            nr = remap(m["row"])
            if nr is None:
                continue
            m = dict(m, row=nr)
        moves.append(m)
    state["moves"] = moves

    # Clients on the new build that the old board never decided about.
    covered = set(placement) | {str(r) for r in state["notInstalling"]}
    base = baseline_days(new_payload)
    for r, n in sorted(new_names.items()):
        if str(r) in covered:
            continue
        if r in base:
            placement[str(r)] = list(base[r])
            report["added"].append((n, list(base[r])))
    state["placement"] = placement

    state["version"] = payload_version(new_payload)
    if season:
        state["season"] = str(season)
    state["savedAt"] = now_ms()
    state["carriedFrom"] = payload_version(old_payload)
    return state, report
