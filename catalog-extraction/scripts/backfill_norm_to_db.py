#!/usr/bin/env python3
"""
Backfill canonical normalized attributes into the app's Neon products table.

ADDITIVE ONLY: writes a new `normalized` key into each product's existing
`raw_data` JSONB (original raw_data keys preserved). The app DB role is DML-only
(no CREATE/ALTER), so this needs no schema change. Recomputes from DB columns +
the learned SKU grammar so the DB stays self-sufficient.

Query it via: raw_data->'normalized'->>'canonical_key', ->>'class', etc.
(A future owner-run migration can promote these to indexed columns for search.)

Usage:
    python backfill_norm_to_db.py            # dev DB (backend/.env.dev)
    python backfill_norm_to_db.py --prod     # prod DB (backend/.env.prod)
"""
from __future__ import annotations
import asyncio, json, re, sys, collections
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sku_grammar_learner import (  # noqa: E402
    decode, color_family, color_from_code, size_in, finish_of, lead_alpha,
)
from normalize_catalog import classify, specific_color, size_bucket, merge  # noqa: E402

BACKEND = HERE.parents[1] / "backend"
GRAMMAR = json.loads((HERE.parents[0] / "outputs" / "sku-grammar" / "grammar.json").read_text())

NORM_VERSION = 1


def resolve_grammar(supplier_name: str):
    """Map a DB supplier name to a learned grammar (match on first word)."""
    if not supplier_name:
        return {}
    if supplier_name in GRAMMAR:
        return GRAMMAR[supplier_name]
    first = re.sub(r'[^a-z]', '', supplier_name.lower().split()[0])
    for k, g in GRAMMAR.items():
        if re.sub(r'[^a-z]', '', k.lower().split()[0]) == first:
            return g
    return {}


def clean(v):
    return v.strip() if isinstance(v, str) else v


def normalize(p, grammar):
    sku = p["supplier_sku"] or ""
    name, desc = p["name"], p["description"]
    raw = p["raw_data"] or {}
    if isinstance(raw, str):
        try: raw = json.loads(raw)
        except Exception: raw = {}
    ptype = raw.get("product_type") or p["subcategory"]

    lc, lcf, _ = decode(sku, grammar.get("color", []))
    ls, lsf, _ = decode(sku, grammar.get("size", []))
    lf, lff, _ = decode(sku, grammar.get("finish", []))

    color, ccf, cprov, ccon = merge([
        (specific_color(name), 0.92, "name"),
        (color_from_code(p["color"]), 0.9, "column"),
        (clean(lc), lcf, "sku"),
        (specific_color(desc), 0.72, "desc"),
        (color_family(name), 0.6, "name_multi"),
    ])
    dim = None
    for dc in ("diameter_in", "width_in", "height_in"):
        if p[dc] is not None:
            dim = float(p[dc]); break
    size, scf, sprov, scon = merge([
        (size_in(name), 0.9, "name"),
        (dim, 0.8, "column"),
        (float(ls) if ls else None, lsf, "sku"),
    ])
    finish, fcf, fprov, fcon = merge([
        (finish_of(name), 0.9, "name"),
        (clean(lf), lff, "sku"),
        (finish_of(desc), 0.7, "desc"),
    ])
    color, finish = clean(color), clean(finish)

    pack = p["case_qty"]
    if not pack:
        m = re.search(r'(\d+)\s*(?:/|per\s)\s*(?:bx|box|bag|bg|pk|pack|set)', name or "", re.I)
        pack = int(m.group(1)) if m else None
    cls = classify(name, ptype)
    ck = "|".join([cls or "?", size_bucket(size), (color or "?").lower(), (finish or "any").lower()])
    confs = [c for c in (ccf, scf, fcf) if c]
    conf = round(sum(confs) / len(confs), 3) if confs else 0.0
    review = conf < 0.5 or ccon or scon or fcon           # calibrated: conflict OR very-low conf
    obj = {
        "class": cls, "size_in": (round(size, 2) if size is not None else None),
        "color": color, "finish": finish, "pack_qty": (int(pack) if pack else None),
        "canonical_key": ck, "confidence": conf, "needs_review": bool(review),
        "provenance": {"color": cprov, "size": sprov, "finish": fprov}, "version": NORM_VERSION,
    }
    return (p["id"], json.dumps(obj))


async def main():
    import asyncpg
    envf = ".env.prod" if "--prod" in sys.argv else ".env.dev"
    url = (BACKEND / envf).read_text().split("DATABASE_URL=", 1)[1].splitlines()[0].strip()
    print(f"DB: {envf}  (adding norm_* columns — additive)")
    conn = await asyncpg.connect(url, statement_cache_size=0)

    # --new-only: enrich only products not yet normalized or below the current
    # NORM_VERSION. This is the "auto-enrich after import" path — cheap + idempotent.
    only_new = "--new-only" in sys.argv
    where = ("WHERE NOT (raw_data ? 'normalized') "
             f"OR COALESCE((raw_data->'normalized'->>'version')::int, 0) < {NORM_VERSION}") if only_new else ""

    sup = {r["id"]: r["name"] for r in await conn.fetch("SELECT id, name FROM suppliers")}
    rows = await conn.fetch(f"""
        SELECT id, supplier_id, supplier_sku, name, description, color, finish,
               diameter_in, width_in, height_in, case_qty, subcategory, raw_data
        FROM products {where}""")
    print(f"computing norm for {len(rows):,} products{' (new/stale only)' if only_new else ''}…")
    if not rows:
        print("nothing to enrich — all products already at norm_version", NORM_VERSION)
        await conn.close()
        return
    gcache = {sid: resolve_grammar(nm) for sid, nm in sup.items()}
    recs = [normalize(p, gcache.get(p["supplier_id"], {})) for p in rows]

    # additive write: merge a `normalized` key into existing raw_data (batched)
    UPD = """UPDATE products p
             SET raw_data = COALESCE(p.raw_data, '{}'::jsonb) || jsonb_build_object('normalized', d.norm)
             FROM (SELECT unnest($1::int[]) AS id, unnest($2::jsonb[]) AS norm) d
             WHERE p.id = d.id"""
    B = 2000
    for i in range(0, len(recs), B):
        chunk = recs[i:i + B]
        await conn.execute(UPD, [r[0] for r in chunk], [r[1] for r in chunk])
        print(f"  …{min(i+B, len(recs)):,}/{len(recs):,}", end="\r")

    # coverage report (query the JSONB)
    tot = await conn.fetchval("SELECT COUNT(*) FROM products")
    ball = await conn.fetchval("SELECT COUNT(*) FROM products WHERE raw_data->'normalized'->>'class'='ball_ornament'")
    colr = await conn.fetchval("SELECT COUNT(*) FROM products WHERE raw_data->'normalized'->>'color' IS NOT NULL")
    print(f"\n✓ backfilled {len(recs):,} rows into raw_data.normalized · {tot:,} total")
    print(f"  ball ornaments: {ball:,} · products with color: {colr:,}")
    top = await conn.fetch("""SELECT raw_data->'normalized'->>'canonical_key' ck, COUNT(*) n FROM products
        WHERE raw_data->'normalized'->>'class'='ball_ornament' GROUP BY 1 ORDER BY n DESC LIMIT 6""")
    print("  top ball-ornament canonical keys:")
    for r in top: print(f"    {str(r['ck']):<34} {r['n']}")
    await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
