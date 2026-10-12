#!/usr/bin/env python3
"""
One-off backfill for Install Changes: recover older Install Schedule states
from backups into ll_app.install_schedule_history_archive, so the Changes list
runs from the season's first plan onward (user, 2026-10-12: "track all the
changes from the beginning of time").

Until 2026-10-12 the app kept only the newest 200 saves per schedule build, so
the earliest saves are gone from ll_app.install_schedule_history. This script
finds them again, READ-ONLY, in:

  * the pre-purge git bundle (git-history-backups/...before-purge.bundle):
    the scheduler's committed plans of 7/30-8/1, before client data was
    purged from git. Each distinct plan becomes a kind='plan' row.
  * the full database dump (db-backups/full-*/leaf-ledger.dump): its
    install_schedule_history rows, read with pg_restore.
  * JSON backups in db-backups/ that hold a saved state or history rows
    (install-schedule-2026-09-24/install_schedule_history.json, the
    roster-*.json / board-before-*.json "state before a write" backups,
    schedule-state-*/, install_schedule_state-*.json).
  * the live page backups (_schedule-backups/index-*.html, db-backups/**.html):
    their embedded DATA is checked; every one so far is the current build, the
    same plan the live page already gives the feed, so they add nothing.

A candidate is skipped when the live history already has it (same build and
moment, or the same build and identical state), or when another source
already supplied it. Nothing here writes the real history table.

Default is a DRY RUN on a read-only connection: it prints what it would add
(counts per source and build, the date range in Central time). No client
data is printed.

    cd backend && .venv/bin/python scripts/backfill_schedule_history.py           # dry run
    cd backend && .venv/bin/python scripts/backfill_schedule_history.py --go      # write the archive

--go inserts in one transaction with ON CONFLICT (dedupe_key) DO NOTHING, so a
re-run adds nothing twice. It creates the archive table if the app hasn't yet.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.libs.schedule_changes import CENTRAL  # noqa: E402

ROOT = Path("/Users/justice/Projects/leaf-and-ledger")
DB_BACKUPS = ROOT / "db-backups"
SCHEDULE_BACKUPS = ROOT / "_schedule-backups"
BUNDLE = ROOT / "git-history-backups" / "leaf-ledger-full-backup-before-purge.bundle"
PG_RESTORE = "/opt/homebrew/opt/libpq/bin/pg_restore"
#: Huge or unrelated backup folders (old platforms, catalog dumps).
SKIP_DIRS = ("neon-", "old-platform", "suppliers-", "history-2015")
SEASON = "2026"
MARK = re.compile(r"const\s+DATA\s*=\s*")
STAMP = re.compile(r"(20\d{6})[-_T]?(\d{6})")


def canon(state: Any) -> str:
    return hashlib.sha1(json.dumps(state, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def as_dt(v: Any) -> Optional[datetime]:
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    if isinstance(v, (int, float)) and v > 1e12:
        return datetime.fromtimestamp(v / 1000, timezone.utc)
    if isinstance(v, str) and v:
        try:
            d = datetime.fromisoformat(v.replace("Z", "+00:00").replace(" ", "T", 1))
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
    return None


def stamp_from_name(name: str) -> Optional[datetime]:
    """Backups are named ...-YYYYMMDD-HHMMSS in Central time."""
    m = STAMP.search(name)
    if not m:
        return None
    return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=CENTRAL)


def ct(d: datetime) -> str:
    c = d.astimezone(CENTRAL)
    return f"{c.month}/{c.day}/{c.year} {(c.hour % 12) or 12}:{c.minute:02d} {'AM' if c.hour < 12 else 'PM'} CT"


def candidate(*, kind: str, version: Optional[str], state: dict, created_at: datetime,
              updated_by: Optional[str], source: str, source_ref: str, season: Optional[str] = None) -> dict:
    return {
        "kind": kind,
        "version": version or state.get("version"),
        "season": str(season or state.get("season") or SEASON)[:4],
        "state": state,
        "updated_by": updated_by,
        "created_at": created_at,
        "source": source,
        "source_ref": source_ref,
        "hash": canon(state),
    }


# ─── Sources ─────────────────────────────────────────────────────────────────

def plan_state(payload: dict) -> dict:
    days = [
        {"id": d["id"], "date": d.get("date"), "crew": d.get("crew"), "stops": list(d.get("stops") or [])}
        for d in payload.get("days") or [] if isinstance(d, dict) and d.get("id")
    ]
    placement: dict[str, list[str]] = {}
    for d in days:
        for r in d["stops"]:
            placement.setdefault(str(r), []).append(d["id"])
    clients = {str(r): c.get("name") for r, c in (payload.get("clients") or {}).items()
               if isinstance(c, dict) and c.get("name")}
    return {"placement": placement, "planClients": clients, "planDays": days}


def from_git_plans(bundle: Path, notes: list[str]) -> list[dict]:
    if not bundle.is_file():
        notes.append(f"git bundle not found: {bundle}")
        return []
    tmp = Path(tempfile.mkdtemp(prefix="ll-plans-"))
    try:
        subprocess.run(["git", "clone", "-q", "--bare", str(bundle), str(tmp / "b.git")], check=True)
        g = ["git", "-C", str(tmp / "b.git")]
        log = subprocess.run(g + ["log", "--all", "--reverse", "--format=%H %aI", "--",
                                  "scheduler/review.html"], capture_output=True, text=True, check=True).stdout
        out, last = [], None
        for line in filter(None, log.splitlines()):
            sha, at = line.split()
            html = subprocess.run(g + ["show", f"{sha}:scheduler/review.html"],
                                  capture_output=True, text=True).stdout
            m = MARK.search(html)
            if not m:
                continue
            payload, _ = json.JSONDecoder().raw_decode(html[m.end():])
            st = plan_state(payload)
            key = canon(st["placement"])
            if key == last:
                continue  # same plan committed again
            last = key
            version = (payload.get("spec") or {}).get("version") or f"plan-{key[:12]}"
            out.append(candidate(kind="plan", version=version, state=st, created_at=as_dt(at),
                                 updated_by="schedule-build", source="git-plan", source_ref=sha[:12]))
        return out
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


_COPY_ESC = re.compile(r"\\(.)")
_COPY_MAP = {"t": "\t", "n": "\n", "r": "\r", "b": "\b", "f": "\f", "v": "\v", "\\": "\\"}


def copy_field(v: str) -> Optional[str]:
    if v == "\\N":
        return None
    return _COPY_ESC.sub(lambda m: _COPY_MAP.get(m.group(1), m.group(1)), v)


def from_dump(dump: Path, notes: list[str]) -> list[dict]:
    if not dump.is_file() or not Path(PG_RESTORE).is_file():
        notes.append(f"dump not read: {dump}")
        return []
    proc = subprocess.run([PG_RESTORE, "-a", "-n", "ll_app", "-t", "install_schedule_history", "-f", "-", str(dump)],
                          capture_output=True, text=True)
    cols, out = None, []
    for line in proc.stdout.splitlines():
        if line.startswith("COPY ll_app.install_schedule_history"):
            cols = [c.strip() for c in line[line.index("(") + 1:line.index(")")].split(",")]
            continue
        if cols is None or line == "\\.":
            if line == "\\.":
                cols = None
            continue
        row = dict(zip(cols, (copy_field(v) for v in line.split("\t"))))
        state = json.loads(row["state"]) if row.get("state") else None
        if not isinstance(state, dict):
            continue
        out.append(candidate(kind="save", version=row.get("version"), state=state,
                             created_at=as_dt(row.get("created_at")), updated_by=row.get("updated_by"),
                             season=row.get("season"), source="db-dump",
                             source_ref=f"{dump.parent.name}#id={row.get('id')}"))
    return out


def _walk(roots: Iterable[Path], suffixes: tuple[str, ...]) -> Iterable[Path]:
    for root in roots:
        if not root.exists():
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith(SKIP_DIRS) and d not in ("node_modules", ".git")]
            for f in fn:
                if f.endswith(suffixes):
                    yield Path(dp) / f


def is_state(d: Any) -> bool:
    return isinstance(d, dict) and ("placement" in d or "staffing" in d) and "planClients" not in d


def from_json_backups(roots: list[Path], notes: list[str]) -> list[dict]:
    out = []
    for p in _walk(roots, (".json",)):
        if "planned" in p.name:
            continue  # a dry run's planned state, never written
        if p.stat().st_size > 60_000_000:
            continue
        try:
            data = json.loads(p.read_text())
        except (ValueError, UnicodeDecodeError):
            continue
        ref = str(p.relative_to(ROOT))
        rows = data if isinstance(data, list) else [data]
        for i, r in enumerate(rows):
            if not isinstance(r, dict):
                continue
            state = r.get("state") if isinstance(r.get("state"), dict) else (r if is_state(r) else None)
            if not is_state(state):
                continue
            at = (as_dt(r.get("created_at")) or as_dt(r.get("updated_at")) or as_dt(state.get("savedAt"))
                  or stamp_from_name(p.name))
            if not at:
                notes.append(f"no timestamp, skipped: {ref}")
                continue
            out.append(candidate(kind="save", version=r.get("version"), state=state, created_at=at,
                                 updated_by=r.get("updated_by"), season=r.get("season"),
                                 source="json-backup", source_ref=f"{ref}#{i}" if len(rows) > 1 else ref))
    return out


def page_versions(roots: list[Path]) -> Counter:
    seen: Counter = Counter()
    for p in _walk(roots, (".html",)):
        try:
            s = p.read_text(errors="ignore")
        except OSError:
            continue
        m = MARK.search(s)
        if not m:
            continue
        try:
            payload, _ = json.JSONDecoder().raw_decode(s[m.end():])
        except ValueError:
            continue
        version = (payload.get("spec") or {}).get("version")
        if version:  # map.html pages carry route data, not a plan
            seen[version] += 1
    return seen


# ─── Plan ────────────────────────────────────────────────────────────────────

async def live_index(conn) -> tuple[set, set, Optional[datetime], Counter]:
    """(version, created_at) and (version, state hash) of every live history row."""
    at_keys, hash_keys, earliest, per_version = set(), set(), None, Counter()
    rows = await conn.fetch("SELECT version, created_at, state::text AS s FROM ll_app.install_schedule_history")
    for r in rows:
        at_keys.add((r["version"], r["created_at"]))
        hash_keys.add((r["version"], canon(json.loads(r["s"]))))
        earliest = r["created_at"] if earliest is None or r["created_at"] < earliest else earliest
        per_version[r["version"]] += 1
    return at_keys, hash_keys, earliest, per_version


def choose(cands: list[dict], at_keys: set, hash_keys: set) -> list[dict]:
    """What's missing from live history, each snapshot once. Sources are
    tried in the order given; the first to supply a state wins."""
    keep, seen_at, seen_hash = [], set(at_keys), set(hash_keys)
    for c in cands:
        if c["created_at"] is None:
            continue
        if c["kind"] == "plan":
            key = f"plan:{canon(c['state']['placement'])}"
            if key in {k["dedupe_key"] for k in keep}:
                continue
            keep.append({**c, "dedupe_key": key})
            continue
        at_key, hash_key = (c["version"], c["created_at"]), (c["version"], c["hash"])
        if at_key in seen_at or hash_key in seen_hash:
            continue
        seen_at.add(at_key)
        seen_hash.add(hash_key)
        keep.append({**c, "dedupe_key": f"save:{c['version']}:{c['created_at'].isoformat()}:{c['hash'][:16]}"})
    keep.sort(key=lambda c: c["created_at"])
    return keep


def load_database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    env = BACKEND / ".env.supabase"
    for line in env.read_text().splitlines() if env.is_file() else []:
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise SystemExit("DATABASE_URL not set and backend/.env.supabase has none")


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--go", action="store_true", help="write the archive (default: dry run)")
    args = ap.parse_args()

    import asyncpg

    notes: list[str] = []
    cands: list[dict] = []
    cands += from_git_plans(BUNDLE, notes)
    for dump in sorted(DB_BACKUPS.glob("full-*/leaf-ledger.dump")):
        cands += from_dump(dump, notes)
    cands += from_json_backups([DB_BACKUPS, SCHEDULE_BACKUPS], notes)
    pages = page_versions([SCHEDULE_BACKUPS, DB_BACKUPS])

    conn = await asyncpg.connect(load_database_url(), statement_cache_size=0)
    try:
        if not args.go:
            await conn.execute("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY")
        at_keys, hash_keys, live_earliest, live_versions = await live_index(conn)
        keep = choose(cands, at_keys, hash_keys)

        print(f"Live history: {sum(live_versions.values())} saves, earliest {ct(live_earliest) if live_earliest else '-'}")
        for v, n in sorted(live_versions.items(), key=lambda kv: kv[0] or ""):
            print(f"  build {v}: {n} saves")
        print(f"Page backups with a plan: {sum(pages.values())} files, builds {dict(pages)}"
              " (the current build's plan; the live page already supplies it)")
        print(f"Candidates found: {len(cands)} ({dict(Counter(c['source'] for c in cands))})")
        print(f"Would add to ll_app.install_schedule_history_archive: {len(keep)} snapshots")
        if keep:
            print(f"  earliest {ct(keep[0]['created_at'])}, latest {ct(keep[-1]['created_at'])}")
            for (src, kind), n in sorted(Counter((c["source"], c["kind"]) for c in keep).items()):
                print(f"  {src} / {kind}: {n}")
            for v, n in sorted(Counter(c["version"] for c in keep).items(), key=lambda kv: kv[0] or ""):
                print(f"  build {v}: {n}")
            unknown = sum(1 for c in keep if not c["updated_by"])
            print(f"  writer unknown (shown as 'Unknown (from backup)'): {unknown}")
            size = sum(len(json.dumps(c["state"])) for c in keep)
            print(f"  about {size / 1e6:.1f} MB of state")
        for n in notes:
            print("note:", n)
        if not args.go:
            print("DRY RUN: nothing written. Re-run with --go to write the archive.")
            return

        from app.apis.schedule_changes import DDL

        async with conn.transaction():
            await conn.execute(DDL)
            added = 0
            for c in keep:
                status = await conn.execute(
                    "INSERT INTO ll_app.install_schedule_history_archive "
                    "(kind, version, season, state, updated_by, created_at, source, source_ref, dedupe_key) "
                    "VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9) ON CONFLICT (dedupe_key) DO NOTHING",
                    c["kind"], c["version"], c["season"], json.dumps(c["state"]), c["updated_by"],
                    c["created_at"], c["source"], c["source_ref"], c["dedupe_key"])
                added += status.endswith(" 1")
        total = await conn.fetchval("SELECT count(*) FROM ll_app.install_schedule_history_archive")
        print(f"Wrote {added} rows; the archive now holds {total}.")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
