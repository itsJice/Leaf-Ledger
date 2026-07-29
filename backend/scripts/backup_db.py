#!/usr/bin/env python3
"""
Full local backup of the app's cloud (Neon) database — no external tools needed.

Streams every table to newline-delimited JSON (memory-safe via a server cursor),
captures the schema (columns + indexes), and writes a manifest. Read-only; makes
no changes to the database.

Usage:
    python backup_db.py                 # dev DB (backend/.env.dev)
    python backup_db.py --prod          # prod DB (backend/.env.prod)
    python backup_db.py --out /path     # custom output dir
"""
from __future__ import annotations
import asyncio, json, sys
from pathlib import Path
from datetime import datetime
from decimal import Decimal

BACKEND = Path(__file__).resolve().parents[1]


def _default(o):
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime,)):
        return o.isoformat()
    return str(o)


async def main():
    import asyncpg
    env = "prod" if "--prod" in sys.argv else "dev"
    url = (BACKEND / f".env.{env}").read_text().split("DATABASE_URL=", 1)[1].splitlines()[0].strip()

    out = None
    if "--out" in sys.argv:
        out = Path(sys.argv[sys.argv.index("--out") + 1])
    if out is None:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        out = Path.home() / "Projects" / "leaf-and-ledger" / "db-backups" / f"neon-{env}-{stamp}"
    tables_dir = out / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    print(f"Backing up {env.upper()} database → {out}")
    conn = await asyncpg.connect(url, statement_cache_size=0)

    # Back up every app schema, not just public — purchase orders live in ll_app.
    tables = [(r["table_schema"], r["table_name"]) for r in await conn.fetch("""
        SELECT table_schema, table_name FROM information_schema.tables
        WHERE table_schema IN ('public','ll_app') AND table_type='BASE TABLE'
        ORDER BY table_schema, table_name""")]

    schema_sql = ["-- Leaf & Ledger DB schema snapshot", f"-- source: {env}  captured: {datetime.now().isoformat()}", ""]
    manifest = {"source_env": env, "captured_at": datetime.now().isoformat(), "tables": {}}

    for schema, t in tables:
        qname = f'"{schema}"."{t}"'
        label = t if schema == "public" else f"{schema}.{t}"
        cols = await conn.fetch("""
            SELECT column_name, data_type, is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema=$2 AND table_name=$1 ORDER BY ordinal_position""", t, schema)
        jsonb_cols = {c["column_name"] for c in cols if c["data_type"] in ("jsonb", "json")}

        # schema.sql: CREATE TABLE + indexes
        defs = []
        for c in cols:
            line = f'  "{c["column_name"]}" {c["data_type"]}'
            if c["column_default"]:
                line += f' DEFAULT {c["column_default"]}'
            if c["is_nullable"] == "NO":
                line += " NOT NULL"
            defs.append(line)
        if schema != "public":
            schema_sql.append(f'CREATE SCHEMA IF NOT EXISTS "{schema}";')
        schema_sql.append(f'CREATE TABLE {qname} (\n' + ",\n".join(defs) + "\n);")
        for ix in await conn.fetch(
                "SELECT indexdef FROM pg_indexes WHERE schemaname=$2 AND tablename=$1", t, schema):
            schema_sql.append(ix["indexdef"] + ";")
        schema_sql.append("")

        # stream data → ndjson
        n = 0
        dst = tables_dir / f"{label}.ndjson"
        with open(dst, "w") as f:
            async with conn.transaction():
                async for rec in conn.cursor(f'SELECT * FROM {qname}', prefetch=500):
                    row = dict(rec)
                    for jc in jsonb_cols:
                        v = row.get(jc)
                        if isinstance(v, str):
                            try:
                                row[jc] = json.loads(v)
                            except Exception:
                                pass
                    f.write(json.dumps(row, default=_default) + "\n")
                    n += 1
        size = dst.stat().st_size
        manifest["tables"][label] = {"schema": schema, "rows": n, "bytes": size,
                                     "columns": [dict(c) for c in cols]}
        print(f"  {label:<32} {n:>8} rows  {size/1e6:6.1f} MB")

    (out / "schema.sql").write_text("\n".join(schema_sql))
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, default=_default))
    (out / "README.md").write_text(
        f"# Leaf & Ledger — local database backup\n\n"
        f"- Source: **{env}** Neon database\n- Captured: {datetime.now().isoformat()}\n"
        f"- Tables: {len(tables)} (see `manifest.json` for row counts + column types)\n\n"
        f"## Contents\n- `tables/*.ndjson` — one file per table, one JSON object per row (JSONB fields parsed).\n"
        f"- `schema.sql` — table + index definitions (best-effort; no FK/constraint DDL).\n"
        f"- `manifest.json` — row counts, byte sizes, and full column schema per table.\n\n"
        f"## Restoring\nRecreate tables from `schema.sql` in any Postgres, then load each\n"
        f"`tables/<name>.ndjson` (each line is a row). This backup is self-contained\n"
        f"and depends on no cloud account.\n"
    )
    await conn.close()

    total_rows = sum(m["rows"] for m in manifest["tables"].values())
    total_mb = sum(m["bytes"] for m in manifest["tables"].values()) / 1e6
    print(f"\n✓ backup complete: {len(tables)} tables · {total_rows:,} rows · {total_mb:.1f} MB")
    print(f"  location: {out}")


if __name__ == "__main__":
    asyncio.run(main())
