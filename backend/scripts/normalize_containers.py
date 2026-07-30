#!/usr/bin/env python3
"""Phase 0 — normalize the arrangement/container data model.

Built products ("designs") and rooms were BOTH stored in `arrangement_containers`,
with their real fields JSON-encoded into the `label` TEXT column behind two
prefixes, while the real columns sat NULL:

    label = 'LL_ROOM:{"name":...,"notes":...}'                     -> a ROOM
    label = 'LL_SCOPE:{"label":...,"room_id":...,"bucket_type":...,
                       "requested_quantity":...,"scope_notes":...}' -> a DESIGN

The encoded `room_id` inside LL_SCOPE points at the *pseudo-container id* of the
LL_ROOM row — not at `project_rooms.id`. So the single most important thing this
script does is RE-POINT every design's room reference to the new
`project_rooms.id` BEFORE the pseudo-container row is deleted. That step is
verified explicitly at the end; the script refuses to report success otherwise.

Rows whose label is plain text are left completely alone.

`scope_notes` may embed a `LL_BUILD_INTELLIGENCE:{...}` JSON blob on its own
line. It is copied VERBATIM — never re-encoded, never re-wrapped.

Dry-run by default; pass --commit to write (same convention as
scripts/load_all_findings.py). Idempotent and safe to re-run: a second run finds
nothing left to do.

    python scripts/normalize_containers.py             # dry run
    python scripts/normalize_containers.py --backup    # dry run + write backup
    python scripts/normalize_containers.py --commit    # back up, then write
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import dotenv  # noqa: E402

# .env.supabase is the authoritative connection for the hosted database, so it
# is loaded last and wins.
for _env in (".env", ".env.dev", ".env.supabase"):
    _path = BACKEND / _env
    if _path.exists():
        dotenv.load_dotenv(_path, override=True)

import asyncpg  # noqa: E402

ROOM_LABEL_PREFIX = "LL_ROOM:"
SCOPE_LABEL_PREFIX = "LL_SCOPE:"

MIGRATION_SQL = BACKEND / "migrations" / "004_normalize_containers.sql"

NEW_COLUMNS = {
    "build_type": "TEXT",
    "status": "TEXT NOT NULL DEFAULT 'draft'",
    "hero_image_url": "TEXT",
}

DDL = """
ALTER TABLE arrangement_containers
    ADD COLUMN IF NOT EXISTS bucket_type        TEXT,
    ADD COLUMN IF NOT EXISTS requested_quantity INTEGER NOT NULL DEFAULT 1,
    ADD COLUMN IF NOT EXISTS scope_notes        TEXT,
    ADD COLUMN IF NOT EXISTS build_type         TEXT,
    ADD COLUMN IF NOT EXISTS status             TEXT NOT NULL DEFAULT 'draft',
    ADD COLUMN IF NOT EXISTS hero_image_url     TEXT;

CREATE INDEX IF NOT EXISTS arrangement_containers_arrangement_idx
    ON arrangement_containers (arrangement_id, sort_order);
CREATE INDEX IF NOT EXISTS arrangement_containers_room_idx
    ON arrangement_containers (room_id);
CREATE INDEX IF NOT EXISTS arrangement_containers_build_type_idx
    ON arrangement_containers (build_type);
CREATE INDEX IF NOT EXISTS project_rooms_arrangement_idx
    ON project_rooms (arrangement_id, sort_order);
"""


# ---------------------------------------------------------------------------
# Label decoding (kept byte-faithful — do NOT "clean" scope_notes)
# ---------------------------------------------------------------------------

def _text_or_none(value) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value or None


def _label_text(value) -> str | None:
    """Trim only the human-facing label fields, never note bodies."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _quantity(value) -> int:
    try:
        return max(1, int(value or 1))
    except (TypeError, ValueError):
        return 1


def parse_room_label(label: str | None) -> dict | None:
    if not label or not label.startswith(ROOM_LABEL_PREFIX):
        return None
    try:
        data = json.loads(label[len(ROOM_LABEL_PREFIX):])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    name = _label_text(data.get("name"))
    if not name:
        return None
    return {"name": name, "notes": _text_or_none(data.get("notes"))}


def parse_scope_label(label: str | None) -> dict | None:
    if not label or not label.startswith(SCOPE_LABEL_PREFIX):
        return None
    try:
        data = json.loads(label[len(SCOPE_LABEL_PREFIX):])
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    bucket_type = _label_text(data.get("bucket_type"))
    room_id = data.get("room_id")
    try:
        room_id = int(room_id) if room_id is not None else None
    except (TypeError, ValueError):
        room_id = None
    return {
        "label": _label_text(data.get("label")) or bucket_type or "Scope",
        "room_id": room_id,
        "bucket_type": bucket_type,
        "requested_quantity": _quantity(data.get("requested_quantity")),
        # VERBATIM — this may carry the LL_BUILD_INTELLIGENCE blob.
        "scope_notes": _text_or_none(data.get("scope_notes")),
    }


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------

def _json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def snapshot(conn) -> dict:
    containers = [dict(r) for r in await conn.fetch(
        "SELECT * FROM arrangement_containers ORDER BY id")]
    rooms = [dict(r) for r in await conn.fetch(
        "SELECT * FROM project_rooms ORDER BY id")]
    return {"arrangement_containers": containers, "project_rooms": rooms}


async def summarize(conn, heading: str) -> None:
    total = await conn.fetchval("SELECT COUNT(*) FROM arrangement_containers")
    encoded_rooms = await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers WHERE label LIKE $1", f"{ROOM_LABEL_PREFIX}%")
    encoded_scopes = await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers WHERE label LIKE $1", f"{SCOPE_LABEL_PREFIX}%")
    rooms = await conn.fetchval("SELECT COUNT(*) FROM project_rooms")
    cols = await container_columns(conn)
    with_bucket = await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers WHERE bucket_type IS NOT NULL")
    with_build = (await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers WHERE build_type IS NOT NULL")
        if "build_type" in cols else "n/a (column missing)")
    with_room = await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers WHERE room_id IS NOT NULL")

    print(f"\n--- {heading} ---")
    print(f"  arrangement_containers rows ....... {total}")
    print(f"    still LL_ROOM:-encoded .......... {encoded_rooms}")
    print(f"    still LL_SCOPE:-encoded ......... {encoded_scopes}")
    print(f"    plain / already normalized ...... {total - encoded_rooms - encoded_scopes}")
    print(f"    with real bucket_type ........... {with_bucket}")
    print(f"    with real build_type ............ {with_build}")
    print(f"    with real room_id FK ............ {with_room}")
    print(f"  project_rooms rows ................ {rooms}")


async def container_columns(conn) -> set[str]:
    rows = await conn.fetch("""
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'arrangement_containers'
    """)
    return {r["column_name"] for r in rows}


# ---------------------------------------------------------------------------
# Migration passes
# ---------------------------------------------------------------------------

async def move_rooms(conn, commit: bool) -> tuple[dict[int, int], list[str]]:
    """LL_ROOM pseudo-containers -> project_rooms.

    Returns {old_pseudo_container_id: project_rooms.id} plus a log.
    Matching on (arrangement_id, name, notes) is what makes a re-run a no-op:
    the second pass finds the room it created the first time.
    """
    mapping: dict[int, int] = {}
    log: list[str] = []
    rows = await conn.fetch(
        """
        SELECT id, arrangement_id, label, sort_order, created_at
        FROM arrangement_containers
        WHERE label LIKE $1
        ORDER BY arrangement_id, sort_order, id
        """,
        f"{ROOM_LABEL_PREFIX}%",
    )
    for row in rows:
        parsed = parse_room_label(row["label"])
        if not parsed:
            log.append(f"  container {row['id']}: UNPARSEABLE LL_ROOM label — left in place")
            continue

        room_id = await conn.fetchval(
            """
            SELECT id FROM project_rooms
            WHERE arrangement_id = $1 AND name = $2 AND COALESCE(notes, '') = COALESCE($3, '')
            ORDER BY sort_order, id LIMIT 1
            """,
            row["arrangement_id"], parsed["name"], parsed["notes"],
        )
        if room_id:
            log.append(f"  container {row['id']} -> project_rooms {room_id} (matched existing "
                       f"{parsed['name']!r})")
        elif commit:
            room_id = await conn.fetchval(
                """
                INSERT INTO project_rooms (arrangement_id, name, notes, sort_order, created_at, updated_at)
                VALUES ($1, $2, $3, $4, COALESCE($5, NOW()), NOW())
                RETURNING id
                """,
                row["arrangement_id"], parsed["name"], parsed["notes"],
                row["sort_order"] or 0,
                row["created_at"].replace(tzinfo=None) if row["created_at"] else None,
            )
            log.append(f"  container {row['id']} -> project_rooms {room_id} (INSERTED "
                       f"{parsed['name']!r})")
        else:
            room_id = -row["id"]  # dry-run placeholder, negative so it can't collide
            log.append(f"  container {row['id']} -> project_rooms <new> (would insert "
                       f"{parsed['name']!r}, arrangement {row['arrangement_id']})")
        mapping[row["id"]] = room_id
    return mapping, log


async def normalize_scopes(conn, mapping: dict[int, int], commit: bool) -> list[str]:
    """LL_SCOPE:{...} -> real columns, with the room reference re-pointed."""
    log: list[str] = []
    rows = await conn.fetch(
        """
        SELECT id, arrangement_id, label
        FROM arrangement_containers
        WHERE label LIKE $1
        ORDER BY arrangement_id, sort_order, id
        """,
        f"{SCOPE_LABEL_PREFIX}%",
    )
    for row in rows:
        parsed = parse_scope_label(row["label"])
        if not parsed:
            log.append(f"  container {row['id']}: UNPARSEABLE LL_SCOPE label — left in place")
            continue

        encoded_room = parsed["room_id"]
        new_room, how = await resolve_room(conn, row["arrangement_id"], encoded_room, mapping)
        if encoded_room is not None and new_room is None:
            log.append(f"  container {row['id']}: room {encoded_room} could NOT be resolved "
                       f"— room_id left NULL (design kept)")

        if commit:
            await conn.execute(
                """
                UPDATE arrangement_containers SET
                    label              = $1,
                    bucket_type        = COALESCE($2, bucket_type),
                    build_type         = COALESCE(build_type, $2),
                    room_id            = COALESCE($3, room_id),
                    requested_quantity = $4,
                    scope_notes        = COALESCE(scope_notes, $5),
                    status             = COALESCE(status, 'draft')
                WHERE id = $6
                """,
                parsed["label"], parsed["bucket_type"],
                new_room if (new_room or 0) > 0 else None,
                parsed["requested_quantity"], parsed["scope_notes"], row["id"],
            )
        notes_len = len(parsed["scope_notes"] or "")
        has_bi = "LL_BUILD_INTELLIGENCE:" in (parsed["scope_notes"] or "")
        if new_room is None:
            shown = "NULL"
        elif new_room < 0:
            shown = "<new>"  # dry-run placeholder for a room not inserted yet
        else:
            shown = str(new_room)
        log.append(
            f"  container {row['id']}: label={parsed['label']!r} "
            f"bucket_type={parsed['bucket_type']!r} room {encoded_room} -> "
            f"{shown} ({how}) qty={parsed['requested_quantity']} "
            f"scope_notes={notes_len}ch{' +build-intel' if has_bi else ''}"
        )
    return log


async def resolve_room(conn, arrangement_id: int, encoded_room, mapping) -> tuple[int | None, str]:
    """Encoded room reference -> live project_rooms.id."""
    if encoded_room is None:
        return None, "no room"
    if encoded_room in mapping:
        return mapping[encoded_room], "re-pointed from pseudo-container"
    # Already a real project_rooms id (a partially-migrated or re-run database).
    exists = await conn.fetchval(
        "SELECT EXISTS(SELECT 1 FROM project_rooms WHERE id = $1 AND arrangement_id = $2)",
        encoded_room, arrangement_id,
    )
    if exists:
        return encoded_room, "already a project_rooms id"
    return None, "ORPHAN"


async def repoint_stale_room_fks(conn, mapping: dict[int, int], commit: bool) -> list[str]:
    """Defensive: any real room_id column still pointing at a pseudo-container."""
    log: list[str] = []
    for old_id, new_id in mapping.items():
        if new_id is None or new_id < 0:
            continue
        stale = await conn.fetch(
            "SELECT id FROM arrangement_containers WHERE room_id = $1", old_id)
        if not stale:
            continue
        log.append(f"  room_id {old_id} -> {new_id} on containers "
                   f"{[r['id'] for r in stale]}")
        if commit:
            await conn.execute(
                "UPDATE arrangement_containers SET room_id = $1 WHERE room_id = $2",
                new_id, old_id)
    return log


async def delete_pseudo_rooms(conn, mapping: dict[int, int], commit: bool) -> list[str]:
    """Drop the LL_ROOM rows — only once nothing points at them any more."""
    log: list[str] = []
    for old_id, new_id in sorted(mapping.items()):
        referrers = [r["id"] for r in await conn.fetch(
            "SELECT id FROM arrangement_containers WHERE room_id = $1", old_id)]
        item_count = await conn.fetchval(
            "SELECT COUNT(*) FROM container_items WHERE container_id = $1", old_id)
        if referrers:
            log.append(f"  container {old_id}: KEPT — still referenced by {referrers} "
                       f"(re-point failed, investigate)")
            continue
        if item_count:
            log.append(f"  container {old_id}: KEPT — holds {item_count} container_items "
                       f"(would lose data)")
            continue
        if commit:
            await conn.execute("DELETE FROM arrangement_containers WHERE id = $1", old_id)
            log.append(f"  container {old_id}: DELETED (room now project_rooms {new_id})")
        else:
            log.append(f"  container {old_id}: would DELETE (room -> project_rooms "
                       f"{'<new>' if new_id < 0 else new_id})")
    return log


async def backfill_build_type(conn, commit: bool) -> int:
    """Rows that already used the real columns still need build_type."""
    if "build_type" not in await container_columns(conn):
        return 0
    n = await conn.fetchval(
        "SELECT COUNT(*) FROM arrangement_containers "
        "WHERE build_type IS NULL AND bucket_type IS NOT NULL")
    if n and commit:
        await conn.execute(
            "UPDATE arrangement_containers SET build_type = bucket_type "
            "WHERE build_type IS NULL AND bucket_type IS NOT NULL")
    return n


async def verify(conn) -> list[str]:
    """Post-conditions. Any line returned here is a FAILURE."""
    problems: list[str] = []

    leftover_rooms = await conn.fetch(
        "SELECT id FROM arrangement_containers WHERE label LIKE $1", f"{ROOM_LABEL_PREFIX}%")
    if leftover_rooms:
        problems.append(f"{len(leftover_rooms)} LL_ROOM: rows remain: "
                        f"{[r['id'] for r in leftover_rooms]}")

    leftover_scopes = await conn.fetch(
        "SELECT id FROM arrangement_containers WHERE label LIKE $1", f"{SCOPE_LABEL_PREFIX}%")
    if leftover_scopes:
        problems.append(f"{len(leftover_scopes)} LL_SCOPE: rows remain: "
                        f"{[r['id'] for r in leftover_scopes]}")

    # Every room reference must resolve to a live room in the SAME arrangement.
    dangling = await conn.fetch("""
        SELECT ac.id, ac.room_id, ac.arrangement_id
        FROM arrangement_containers ac
        LEFT JOIN project_rooms pr ON pr.id = ac.room_id
        WHERE ac.room_id IS NOT NULL
          AND (pr.id IS NULL OR pr.arrangement_id <> ac.arrangement_id)
    """)
    if dangling:
        problems.append("room references that do not resolve: "
                        + str([(r["id"], r["room_id"]) for r in dangling]))

    cols = await container_columns(conn)

    # Anything with a bucket_type must have a matching build_type.
    if "build_type" in cols:
        missing_build = await conn.fetch(
            "SELECT id FROM arrangement_containers "
            "WHERE bucket_type IS NOT NULL AND build_type IS NULL")
        if missing_build:
            problems.append(f"rows with bucket_type but no build_type: "
                            f"{[r['id'] for r in missing_build]}")
    else:
        problems.append("column build_type is missing")

    if "status" in cols:
        null_status = await conn.fetchval(
            "SELECT COUNT(*) FROM arrangement_containers WHERE status IS NULL")
        if null_status:
            problems.append(f"{null_status} rows with NULL status")
    else:
        problems.append("column status is missing")

    if "hero_image_url" not in cols:
        problems.append("column hero_image_url is missing")

    return problems


# ---------------------------------------------------------------------------

async def main() -> int:
    commit = "--commit" in sys.argv
    want_backup = commit or "--backup" in sys.argv

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set (looked in backend/.env, .env.dev, .env.supabase)")
        return 2

    conn = await asyncpg.connect(url, statement_cache_size=0)
    try:
        print(f"{'COMMIT' if commit else 'DRY RUN'} — normalize arrangement_containers")
        await summarize(conn, "BEFORE")

        cols = await container_columns(conn)
        missing = [c for c in NEW_COLUMNS if c not in cols]

        # ---- backup -----------------------------------------------------
        if want_backup:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            backup_path = Path(__file__).resolve().parent / f"normalize_containers_backup_{stamp}.json"
            data = await snapshot(conn)
            backup_path.write_text(json.dumps(data, indent=2, default=_json_default))
            print(f"\nbackup written: {backup_path} "
                  f"({len(data['arrangement_containers'])} containers, "
                  f"{len(data['project_rooms'])} rooms)")

        # ---- DDL --------------------------------------------------------
        print("\n=== 1. schema ===")
        if missing:
            print(f"  missing columns: {', '.join(missing)}")
            if commit:
                await conn.execute(DDL)
                print(f"  applied {MIGRATION_SQL.name} DDL")
            else:
                print("  would apply ADD COLUMN IF NOT EXISTS + indexes")
        else:
            print("  all columns present (build_type, status, hero_image_url)")
            if commit:
                await conn.execute(DDL)
                print("  DDL re-applied (idempotent)")

        # ---- data -------------------------------------------------------
        if commit:
            tx = conn.transaction()
            await tx.start()
        try:
            print("\n=== 2. LL_ROOM: -> project_rooms ===")
            mapping, log = await move_rooms(conn, commit)
            print("\n".join(log) or "  nothing to do")

            print("\n=== 3. LL_SCOPE: -> real columns (room refs re-pointed) ===")
            print("\n".join(await normalize_scopes(conn, mapping, commit)) or "  nothing to do")

            print("\n=== 4. re-point any stale room_id FK ===")
            print("\n".join(await repoint_stale_room_fks(conn, mapping, commit)) or "  none stale")

            print("\n=== 5. delete LL_ROOM pseudo-containers ===")
            print("\n".join(await delete_pseudo_rooms(conn, mapping, commit)) or "  nothing to do")

            print("\n=== 6. backfill build_type from bucket_type ===")
            n = await backfill_build_type(conn, commit)
            print(f"  {n} row(s) {'updated' if commit else 'would be updated'}")

            if commit:
                problems = await verify(conn)
                if problems:
                    print("\nVERIFY FAILED — rolling back:")
                    for p in problems:
                        print(f"  ! {p}")
                    await tx.rollback()
                    return 1
                await tx.commit()
        except Exception:
            if commit:
                await tx.rollback()
            raise

        await summarize(conn, "AFTER" if commit else "AFTER (unchanged — dry run)")

        if commit:
            print("\n=== verification ===")
            problems = await verify(conn)
            if problems:
                for p in problems:
                    print(f"  ! {p}")
                return 1
            print("  OK  no LL_ROOM:/LL_SCOPE: rows remain")
            print("  OK  every room reference resolves to a project_rooms row in the same arrangement")
            print("  OK  every design with a bucket_type has a build_type")
            print("  OK  status is non-null everywhere")
            for r in await conn.fetch("""
                SELECT ac.id, ac.arrangement_id, ac.label, ac.build_type, ac.room_id, pr.name AS room_name
                FROM arrangement_containers ac
                LEFT JOIN project_rooms pr ON pr.id = ac.room_id
                ORDER BY ac.arrangement_id, ac.sort_order, ac.id
            """):
                print(f"    design {r['id']:>3} arr={r['arrangement_id']:>3} "
                      f"build_type={str(r['build_type']):<16} room_id={str(r['room_id']):<6} "
                      f"room={r['room_name']!r:<28} label={r['label']!r}")
        else:
            print("\nDRY RUN — nothing was written. Re-run with --commit.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
