"""Designs — the built-product library.

A *design* is one `arrangement_containers` row: a thing that actually gets
built (a tree, a wreath, a centerpiece). It sits in a hierarchy

    Client → Project (`arrangements`) → Group (`project_rooms`) → Design

and is made of parts (`container_items` → `products`).

Two things make this module more than a SELECT:

1. **Two data shapes at once.** The columns this endpoint wants
   (`label`, `bucket_type`, `room_id`, `build_type`, `status`,
   `hero_image_url`) are being normalised by a parallel migration. Historically
   the same facts were JSON-encoded into the `label` column as
   `LL_SCOPE:{...}` / `LL_ROOM:{...}` with the real columns left NULL. Every
   read here prefers the normalised column and falls back to the encoded label,
   so the API returns the same answers before and after the migration lands.
   `LL_ROOM:` rows are groups, not designs, and are excluded.

2. **"Made of" search.** `materials` is the vocabulary behind "show me designs
   with moss" / "trees with ornaments". It is derived from every source we have:
   the design's saved parts, the build-intelligence blob embedded in
   `scope_notes`, and the historical recipe library. See `_materials_for`.

Facets are drill-down, exactly like `products.search_products`: each facet is
counted over the current query while ignoring its OWN selection, so picking one
client doesn't collapse the client list and you can still add a second.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/designs", tags=["designs"])

DATABASE_URL = os.environ.get("DATABASE_URL")

ROOM_LABEL_PREFIX = "LL_ROOM:"
SCOPE_LABEL_PREFIX = "LL_SCOPE:"
BUILD_INTELLIGENCE_MARKER = "LL_BUILD_INTELLIGENCE:"

MAX_LIMIT = 200
MAX_FACET_VALUES = 200


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


# ─── Defensive parsing ───────────────────────────────────────────────────────
# Everything below is fed by user-authored / machine-generated text that has
# already been reshaped once. None of it may ever raise: a malformed blob on one
# design must degrade that design's metadata, not 500 the whole library.


def _loads(raw: Any) -> Any:
    """json.loads that returns None instead of raising."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    if not isinstance(raw, str):
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def parse_scope_label(label: Optional[str]) -> dict:
    """Decode a legacy `LL_SCOPE:{...}` label. `{}` for anything else."""
    if not label or not label.startswith(SCOPE_LABEL_PREFIX):
        return {}
    parsed = _loads(label[len(SCOPE_LABEL_PREFIX):])
    return parsed if isinstance(parsed, dict) else {}


def parse_room_label(label: Optional[str]) -> dict:
    """Decode a legacy `LL_ROOM:{...}` label. `{}` for anything else."""
    if not label or not label.startswith(ROOM_LABEL_PREFIX):
        return {}
    parsed = _loads(label[len(ROOM_LABEL_PREFIX):])
    return parsed if isinstance(parsed, dict) else {}


def parse_build_intelligence(scope_notes: Optional[str]) -> dict:
    """Pull the build-intelligence JSON out of free-text scope notes.

    The notes are human text with a machine blob appended after a
    `LL_BUILD_INTELLIGENCE:` marker, e.g.

        Height: 7\\nCanopy size: full\\nLL_BUILD_INTELLIGENCE:{"build_type":...}

    The blob is nested/escaped JSON written by another service and has already
    survived one round of re-encoding, so it is parsed defensively — a trailing
    fragment or a truncated object yields `{}`, never an exception.
    """
    if not scope_notes or BUILD_INTELLIGENCE_MARKER not in scope_notes:
        return {}
    blob = scope_notes.split(BUILD_INTELLIGENCE_MARKER, 1)[1].strip()
    parsed = _loads(blob)
    if isinstance(parsed, dict):
        return parsed
    # Some writers append text after the JSON object. Retry on the balanced
    # prefix rather than giving up on an otherwise good blob.
    if blob.startswith("{"):
        depth, in_str, esc = 0, False, False
        for i, ch in enumerate(blob):
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    parsed = _loads(blob[: i + 1])
                    return parsed if isinstance(parsed, dict) else {}
    return {}


def strip_build_intelligence(scope_notes: Optional[str]) -> Optional[str]:
    """The human-readable half of scope notes, without the machine blob."""
    if not scope_notes:
        return None
    text = scope_notes.split(BUILD_INTELLIGENCE_MARKER, 1)[0].strip()
    return text or None


def _csv_list(value: Optional[str]) -> list[str]:
    """`"a,b , c"` → `["a", "b", "c"]`. Empty/None → `[]`."""
    if not value:
        return []
    return [p.strip() for p in value.split(",") if p.strip()]


# Placeholder labels that carry no "made of" meaning. They come from catch-all
# product categories and from the recipe library's unclassified line items, and
# would otherwise sit at the top of the materials facet matching everything.
_MATERIAL_STOPWORDS = {
    "other", "others", "product", "products", "item", "items", "misc",
    "miscellaneous", "general", "unknown", "none", "n/a", "na", "tbd", "test",
}


def _clean_material(value: Any) -> Optional[str]:
    """Normalise one material token, or None if it isn't usable vocabulary.

    Rejects the numeric/one-character junk that leaks into component labels and
    vendor lists (`"1.2"`, `"6.0"`) plus the meaningless catch-all labels above,
    so the facet list stays a readable "made of" vocabulary.
    """
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip(" \t\n\r-–—/,;")
    if len(text) < 2 or len(text) > 60:
        return None
    if not re.search(r"[A-Za-z]", text):
        return None
    if text.lower() in _MATERIAL_STOPWORDS:
        return None
    return text


def _material_key(material: str) -> str:
    """Dedup key that folds punctuation and a trailing plural.

    A design's own part label ("Container") and the catalog's category for the
    product filling it ("Containers") describe the same material — collapse
    them so the facet shows one entry, not two that split the count.
    """
    key = re.sub(r"[^a-z0-9]+", "", material.lower())
    # Only a real plural loses its 's' — "Moss" and "Cactus" are not plurals of
    # "Mos" and "Cactu", and merging them would corrupt the vocabulary.
    if len(key) > 3 and key.endswith("s") and not key.endswith(("ss", "us", "is")):
        return key[:-1]
    return key


def _f(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _iso(value: Any) -> Optional[str]:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value) if value is not None else None


def _sort_key_dt(value: Any) -> datetime:
    """Sortable timestamp — naive and aware values are compared safely."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return datetime.min.replace(tzinfo=timezone.utc)


# ─── Schema probing ──────────────────────────────────────────────────────────


async def _existing_columns(conn, table: str) -> set[str]:
    rows = await conn.fetch(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = $1
        """,
        table,
    )
    return {r["column_name"] for r in rows}


async def _table_exists(conn, table: str) -> bool:
    try:
        return bool(await conn.fetchval("SELECT to_regclass($1) IS NOT NULL", f"public.{table}"))
    except asyncpg.PostgresError:
        return False


# ─── Loading ─────────────────────────────────────────────────────────────────


async def _load_parts(conn) -> dict[int, list[dict]]:
    """Saved parts per design, joined to the product catalog.

    `container_items` is close to empty today (designs are still being built in
    the UI), so most designs legitimately come back with zero parts and a zero
    cost. That is the expected steady state right now, not a failure.
    """
    cols = await _existing_columns(conn, "container_items")
    if not cols:
        return {}
    part_label = "ci.part_label" if "part_label" in cols else "NULL::text AS part_label"
    part_order = "ci.part_order" if "part_order" in cols else "ci.id AS part_order"
    status = "ci.status" if "status" in cols else "'selected'::text AS status"
    rows = await conn.fetch(
        f"""
        SELECT ci.id, ci.container_id, ci.product_id, ci.quantity,
               {part_label}, {part_order}, {status},
               p.name AS product_name, p.supplier_sku, p.category, p.subcategory,
               p.material, p.current_price, p.photo_url, p.image_urls, p.raw_data
        FROM container_items ci
        LEFT JOIN products p ON p.id = ci.product_id
        ORDER BY ci.container_id, {"ci.part_order" if "part_order" in cols else "ci.id"}, ci.id
        """
    )
    parts: dict[int, list[dict]] = defaultdict(list)
    for r in rows:
        raw = _loads(r["raw_data"]) or {}
        norm = raw.get("normalized") if isinstance(raw, dict) else None
        norm = norm if isinstance(norm, dict) else {}
        images = [u for u in (list(r["image_urls"] or []) + [r["photo_url"]]) if u]
        qty = int(r["quantity"] or 1)
        price = float(r["current_price"]) if r["current_price"] is not None else None
        parts[r["container_id"]].append({
            "id": r["id"],
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "sku": r["supplier_sku"],
            "part_label": r["part_label"],
            "quantity": qty,
            "unit_price": price,
            "line_total": round((price or 0.0) * qty, 2),
            "photo_url": images[0] if images else None,
            "status": r["status"],
            "_material_hints": [r["part_label"], r["category"], r["subcategory"],
                                r["material"], norm.get("class")],
        })
    return parts


async def _load_recipe_materials(conn) -> dict[str, set[str]]:
    """Component vocabulary from the historical recipe library, keyed by build type.

    Another agent is populating `historical_recipes` in parallel; until it does
    the tables are empty and this contributes nothing. Both the missing-table
    and the empty-table cases return `{}` rather than failing.
    """
    if not await _table_exists(conn, "historical_recipe_components"):
        return {}
    if not await _table_exists(conn, "historical_recipes"):
        return {}
    try:
        rows = await conn.fetch(
            """
            SELECT LOWER(COALESCE(hr.build_type, '')) AS build_type,
                   hrc.component_label
            FROM historical_recipe_components hrc
            JOIN historical_recipes hr ON hr.id = hrc.recipe_id
            WHERE hrc.component_label IS NOT NULL
            """
        )
    except asyncpg.PostgresError:
        return {}
    out: dict[str, set[str]] = defaultdict(set)
    for r in rows:
        material = _clean_material(r["component_label"])
        bt = (r["build_type"] or "").strip()
        if material and bt:
            out[bt].add(material)
    return out


def _materials_for(design: dict, parts: list[dict], intel: dict,
                   recipe_materials: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """Everything this design is *made of*, plus its free-text search terms.

    Three sources, folded together and de-duplicated:

    1. **Saved parts** — the part label the design assigned ("Top Dressing"),
       and the catalog's own words for the chosen product (category, material).
    2. **Build intelligence** — the `components[].label` vocabulary embedded in
       `scope_notes` ("Moss / Fiber", "Trunks & Branches", "Leaves / Greenery").
       This is the main source today, because most designs have no saved parts
       yet but every design generated through the builder carries this blob.
    3. **Historical recipes** — component labels observed on past builds of the
       same build type, when that library has been populated.

    Component `examples` and `search_terms` ("Fiddle Leaf Branch", "Sheet Moss",
    "Rocks") deliberately do NOT become materials — they'd explode the facet
    list into thousands of one-off SKU names. They go into the search blob
    instead, so searching "fiddle leaf" still finds the tree that uses one.
    """
    materials: list[str] = []
    seen: set[str] = set()
    terms: list[str] = []

    def add(value: Any) -> None:
        material = _clean_material(value)
        if material and _material_key(material) not in seen:
            seen.add(_material_key(material))
            materials.append(material)

    for part in parts:
        for hint in part["_material_hints"]:
            add(hint)
        if part["product_name"]:
            terms.append(str(part["product_name"]))
        if part["sku"]:
            terms.append(str(part["sku"]))

    components = intel.get("components")
    if isinstance(components, list):
        for component in components:
            if not isinstance(component, dict):
                continue
            add(component.get("label"))
            for key in ("examples", "search_terms", "vendors"):
                values = component.get(key)
                if isinstance(values, list):
                    terms.extend(str(v) for v in values if v)

    build_type = design.get("build_type")
    if build_type:
        for material in sorted(recipe_materials.get(str(build_type).lower(), ())):
            add(material)

    return materials, terms


async def _load_designs(conn) -> list[dict]:
    """Every design in the library, fully resolved, as plain dicts.

    Read as one pass rather than per-request SQL filtering: the working set is
    small (tens to low thousands of designs), and materials/build-type live
    inside JSON text that only Python can unpack — so filtering and faceting
    both happen in memory over this list, the same shape `products.search`
    uses.
    """
    cols = await _existing_columns(conn, "arrangement_containers")
    if not cols:
        return []

    def col(name: str, sql_type: str = "text") -> str:
        """The real column once the migration lands, a typed NULL until then."""
        return f"ac.{name}" if name in cols else f"NULL::{sql_type} AS {name}"

    has_rooms = await _table_exists(conn, "project_rooms")
    room_join = "LEFT JOIN project_rooms pr ON pr.id = ac.room_id" if (
        has_rooms and "room_id" in cols
    ) else ""
    room_select = "pr.id AS room_pk, pr.name AS room_name" if room_join else (
        "NULL::int AS room_pk, NULL::text AS room_name"
    )
    updated = "ac.updated_at" if "updated_at" in cols else "NULL::timestamptz AS updated_at"

    rows = await conn.fetch(f"""
        SELECT ac.id, ac.arrangement_id, ac.label, ac.created_at,
               {col('bucket_type')}, {col('scope_notes')},
               {col('requested_quantity', 'int')}, {col('room_id', 'int')},
               {col('build_type')}, {col('status')}, {col('hero_image_url')},
               {updated}, {room_select},
               a.name AS project_name, a.client_name,
               a.updated_at AS project_updated_at
        FROM arrangement_containers ac
        JOIN arrangements a ON a.id = ac.arrangement_id
        {room_join}
        WHERE COALESCE(ac.label, '') NOT LIKE '{ROOM_LABEL_PREFIX}%'
        ORDER BY ac.id
    """)

    # Legacy groups: before `project_rooms`, a group was itself an
    # arrangement_containers row carrying an LL_ROOM label, and a design's
    # encoded `room_id` pointed at that row's id. Resolve those names so
    # pre-migration designs still report the group they belong to.
    legacy_groups: dict[int, str] = {}
    for r in await conn.fetch(
        "SELECT id, label FROM arrangement_containers WHERE label LIKE $1",
        f"{ROOM_LABEL_PREFIX}%",
    ):
        name = parse_room_label(r["label"]).get("name")
        if name:
            legacy_groups[r["id"]] = str(name)

    parts_by_container = await _load_parts(conn)
    recipe_materials = await _load_recipe_materials(conn)

    designs: list[dict] = []
    for r in rows:
        scope = parse_scope_label(r["label"])

        # Normalised column first, encoded label second — this is the whole
        # before/after-migration contract, applied field by field.
        name = r["label"] if not scope else scope.get("label")
        name = (str(name).strip() if name else "") or "Untitled design"
        bucket_type = r["bucket_type"] or scope.get("bucket_type")
        scope_notes = r["scope_notes"] or scope.get("scope_notes")
        quantity = r["requested_quantity"] or scope.get("requested_quantity") or 1

        intel = parse_build_intelligence(scope_notes)

        group_id = r["room_pk"]
        group_name = r["room_name"]
        if group_id is None:
            legacy_room_id = r["room_id"] if r["room_id"] is not None else scope.get("room_id")
            try:
                legacy_room_id = int(legacy_room_id) if legacy_room_id is not None else None
            except (TypeError, ValueError):
                legacy_room_id = None
            if legacy_room_id is not None and legacy_room_id in legacy_groups:
                group_id, group_name = legacy_room_id, legacy_groups[legacy_room_id]

        # build_type: the real column wins; otherwise the builder recorded it in
        # the intelligence blob; otherwise the old bucket_type carried it.
        build_type = r["build_type"] or intel.get("build_type") or bucket_type
        build_type = str(build_type).strip() if build_type else None

        parts = parts_by_container.get(r["id"], [])
        design = {
            "id": r["id"],
            "name": name,
            "build_type": build_type,
            "status": (r["status"] or "draft"),
            "client_name": r["client_name"],
            "project_id": r["arrangement_id"],
            "project_name": r["project_name"],
            "group_id": group_id,
            "group_name": group_name,
            "item_count": len(parts),
            "total_cost": round(sum(p["line_total"] for p in parts), 2),
            "hero_image_url": r["hero_image_url"],
            "updated_at": _iso(r["updated_at"] or r["created_at"] or r["project_updated_at"]),
            "_sort_dt": _sort_key_dt(r["updated_at"] or r["created_at"] or r["project_updated_at"]),
            "_parts": parts,
            "_quantity": int(quantity or 1),
            "_scope_notes": strip_build_intelligence(scope_notes),
            "_intel": intel,
        }
        materials, terms = _materials_for(design, parts, intel, recipe_materials)
        design["materials"] = materials
        design["_blob"] = " ".join(str(x) for x in [
            name, r["project_name"], r["client_name"], group_name, build_type,
            design["_scope_notes"] or "", " ".join(materials), " ".join(terms),
        ] if x).lower()
        designs.append(design)

    # One spelling per material across the whole library. Two designs can arrive
    # at the same material by different routes ("Container" from a part label,
    # "Containers" from the catalog category); without this the facet would list
    # both and split the count, and picking one would miss the other's designs.
    spellings: dict[str, Counter] = defaultdict(Counter)
    for d in designs:
        for m in d["materials"]:
            spellings[_material_key(m)][m] += 1
    canonical = {k: c.most_common(1)[0][0] for k, c in spellings.items()}
    for d in designs:
        d["materials"] = list(dict.fromkeys(canonical[_material_key(m)] for m in d["materials"]))
    return designs


def _public(design: dict) -> dict:
    """Strip the internal `_`-prefixed working fields off a design."""
    return {k: v for k, v in design.items() if not k.startswith("_")}


# ─── Endpoints ───────────────────────────────────────────────────────────────
# Declared before `/{design_id}` so the literal paths win the route match.


@router.get("/list")
async def list_designs(
    search: Optional[str] = None,
    clients: Optional[str] = None,
    projects: Optional[str] = None,
    groups: Optional[str] = None,
    build_types: Optional[str] = None,
    materials: Optional[str] = None,
    sort: str = "recent",
    limit: int = 48,
    offset: int = 0,
):
    """The design library: a filtered page of designs plus drill-down facets.

    Every filter is CSV multi-select and matches on the displayed value, which
    is what the sidebar sends back from `facets`. `search` is AND-across-words
    over name, project, client, group, build type, materials and the part /
    example names behind them — so "fiddle leaf" finds a tree built from a
    Fiddle Leaf Branch even though "fiddle" appears in no column.

    Facets are drill-down: each facet is counted while ignoring its OWN
    selection, so choosing one client doesn't collapse the client list and a
    second can still be added. Selections in the OTHER facets do apply, so the
    counts always describe the query you're actually in.
    """
    conn = await get_conn()
    try:
        designs = await _load_designs(conn)
    finally:
        await conn.close()

    sel_clients = {c.lower() for c in _csv_list(clients)}
    sel_projects = {p.lower() for p in _csv_list(projects)}
    sel_groups = {g.lower() for g in _csv_list(groups)}
    sel_types = {b.lower() for b in _csv_list(build_types)}
    sel_materials = {m.lower() for m in _csv_list(materials)}
    terms = [t for t in (search or "").lower().split() if t]

    # Base set: the always-on filter (keyword). Facets and results are both
    # derived from here, so the sidebar reflects whatever was searched.
    base = [d for d in designs if all(t in d["_blob"] for t in terms)]

    def one(value: Any) -> list[str]:
        return [str(value)] if value else []

    # (facet key, current selection, value extractor). An item passes a
    # dimension when the selection is empty OR intersects the item's values.
    dim_defs = [
        ("clients", sel_clients, lambda d: one(d["client_name"])),
        ("projects", sel_projects, lambda d: one(d["project_name"])),
        ("groups", sel_groups, lambda d: one(d["group_name"])),
        ("build_types", sel_types, lambda d: one(d["build_type"])),
        ("materials", sel_materials, lambda d: list(d["materials"])),
    ]
    counters: dict[str, Counter] = {key: Counter() for key, _, _ in dim_defs}

    out: list[dict] = []
    for d in base:
        vals = [get(d) for _, _, get in dim_defs]
        fails = []
        for j, (_key, selected, _get) in enumerate(dim_defs):
            if selected and not (selected & {v.lower() for v in vals[j]}):
                fails.append(j)
                if len(fails) > 1:
                    break
        nfail = len(fails)
        if nfail == 0:
            out.append(d)
        # Count each facet over items that pass every OTHER facet (drill-down):
        # nfail==0 counts everywhere; nfail==1 counts only its single failing dim.
        if nfail == 0:
            for (key, _s, _g), values in zip(dim_defs, vals):
                for v in values:
                    counters[key][v] += 1
        elif nfail == 1:
            key = dim_defs[fails[0]][0]
            for v in vals[fails[0]]:
                counters[key][v] += 1

    sorters = {
        "recent": lambda d: (-d["_sort_dt"].timestamp(), d["name"].lower()),
        "name": lambda d: (d["name"].lower(), -d["_sort_dt"].timestamp()),
        "cost": lambda d: (-d["total_cost"], d["name"].lower()),
        "type": lambda d: ((d["build_type"] or "￿").lower(), d["name"].lower()),
    }
    out.sort(key=sorters.get(sort, sorters["recent"]))

    total = len(out)
    off = max(0, offset)
    lim = max(1, min(limit, MAX_LIMIT))
    page = out[off:off + lim]

    def by_count(counter: Counter) -> list[dict]:
        ordered = sorted(counter.items(), key=lambda kv: (-kv[1], str(kv[0]).lower()))
        return [{"value": v, "count": n} for v, n in ordered[:MAX_FACET_VALUES]]

    return {
        "items": [_public(d) for d in page],
        "total": total,
        "limit": lim,
        "offset": off,
        "facets": {key: by_count(counters[key]) for key, _, _ in dim_defs},
    }


@router.get("/hierarchy")
async def get_hierarchy():
    """Client → Project → Group, for the create form's cascading pickers.

    Clients come from the saved `clients` table *and* from project rows that
    name a client never saved as a record — otherwise a project would offer a
    client the picker can't show. Those unsaved names carry `id: null`.
    """
    conn = await get_conn()
    try:
        client_rows = await conn.fetch("SELECT id, name FROM clients ORDER BY name")
        project_rows = await conn.fetch(
            "SELECT id, name, client_name FROM arrangements ORDER BY name"
        )
        group_rows = []
        if await _table_exists(conn, "project_rooms"):
            group_rows = await conn.fetch(
                "SELECT id, name, arrangement_id FROM project_rooms ORDER BY sort_order, id"
            )
    finally:
        await conn.close()

    clients = [{"id": r["id"], "name": r["name"]} for r in client_rows]
    known = {(r["name"] or "").strip().lower() for r in client_rows}
    for r in project_rows:
        name = (r["client_name"] or "").strip()
        if name and name.lower() not in known:
            known.add(name.lower())
            clients.append({"id": None, "name": name})
    clients.sort(key=lambda c: c["name"].lower())

    return {
        "clients": clients,
        "projects": [
            {"id": r["id"], "name": r["name"], "client_name": r["client_name"]}
            for r in project_rows
        ],
        "groups": [
            {"id": r["id"], "name": r["name"], "project_id": r["arrangement_id"]}
            for r in group_rows
        ],
    }


class DesignCreate(BaseModel):
    name: str
    build_type: Optional[str] = None
    client_name: Optional[str] = None
    project_id: Optional[int] = None
    project_name: Optional[str] = None
    group_id: Optional[int] = None
    group_name: Optional[str] = None


@router.post("/create")
async def create_design(body: DesignCreate, request: Request):
    """Create a design, creating its project and group on the way if needed.

    The form lets you either pick an existing project/group or type a new name,
    so this accepts `project_id` OR `project_name` (same for the group) and
    resolves whichever arrived. Names are matched case-insensitively against
    what already exists before inserting, so typing an existing project's name
    joins it rather than creating a duplicate.
    """
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=422, detail="name is required")
    if body.project_id is None and not (body.project_name or "").strip():
        raise HTTPException(status_code=422, detail="project_id or project_name is required")

    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        # ── Project ───────────────────────────────────────────────────────────
        if body.project_id is not None:
            project = await conn.fetchrow(
                "SELECT id, name, client_name FROM arrangements WHERE id = $1", body.project_id
            )
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            project_id = project["id"]
            # An explicit client on the request updates a project that has none.
            if (body.client_name or "").strip() and not (project["client_name"] or "").strip():
                await conn.execute(
                    "UPDATE arrangements SET client_name = $2, updated_at = NOW() WHERE id = $1",
                    project_id, body.client_name.strip(),
                )
        else:
            project_name = body.project_name.strip()
            client_name = (body.client_name or "").strip() or None
            project_id = await conn.fetchval(
                """
                SELECT id FROM arrangements
                WHERE LOWER(name) = LOWER($1)
                  AND COALESCE(LOWER(client_name), '') = COALESCE(LOWER($2), '')
                ORDER BY id LIMIT 1
                """,
                project_name, client_name,
            )
            if project_id is None:
                project_id = await conn.fetchval(
                    """
                    INSERT INTO arrangements (name, client_name, created_by)
                    VALUES ($1, $2, $3) RETURNING id
                    """,
                    project_name, client_name, user_id,
                )

        # ── Group ─────────────────────────────────────────────────────────────
        group_id: Optional[int] = None
        if await _table_exists(conn, "project_rooms"):
            if body.group_id is not None:
                group_id = await conn.fetchval(
                    "SELECT id FROM project_rooms WHERE id = $1 AND arrangement_id = $2",
                    body.group_id, project_id,
                )
                if group_id is None:
                    raise HTTPException(status_code=404, detail="Group not found in this project")
            elif (body.group_name or "").strip():
                group_name = body.group_name.strip()
                group_id = await conn.fetchval(
                    """
                    SELECT id FROM project_rooms
                    WHERE arrangement_id = $1 AND LOWER(name) = LOWER($2)
                    ORDER BY sort_order, id LIMIT 1
                    """,
                    project_id, group_name,
                )
                if group_id is None:
                    group_id = await conn.fetchval(
                        """
                        INSERT INTO project_rooms (arrangement_id, name, sort_order)
                        VALUES ($1, $2, COALESCE(
                            (SELECT MAX(sort_order) + 1 FROM project_rooms WHERE arrangement_id = $1), 0))
                        RETURNING id
                        """,
                        project_id, group_name,
                    )

        # ── Design ────────────────────────────────────────────────────────────
        # Write the normalised columns, but only the ones that exist yet — the
        # migration adding build_type/status/hero_image_url may not have landed.
        cols = await _existing_columns(conn, "arrangement_containers")
        build_type = (body.build_type or "").strip() or None
        fields: list[tuple[str, Any]] = [("arrangement_id", project_id), ("label", name)]
        if "bucket_type" in cols:
            fields.append(("bucket_type", build_type))
        if "room_id" in cols:
            fields.append(("room_id", group_id))
        if "build_type" in cols:
            fields.append(("build_type", build_type))
        if "status" in cols:
            fields.append(("status", "draft"))
        if "sort_order" in cols:
            fields.append(("sort_order", 0))

        names = ", ".join(f for f, _ in fields)
        placeholders = ", ".join(f"${i + 1}" for i in range(len(fields)))
        design_id = await conn.fetchval(
            f"INSERT INTO arrangement_containers ({names}) VALUES ({placeholders}) RETURNING id",
            *[v for _, v in fields],
        )
        await conn.execute("UPDATE arrangements SET updated_at = NOW() WHERE id = $1", project_id)

        designs = await _load_designs(conn)
    finally:
        await conn.close()

    created = next((d for d in designs if d["id"] == design_id), None)
    if created is None:
        raise HTTPException(status_code=500, detail="Design was created but could not be read back")
    return _public(created)


@router.get("/{design_id}")
async def get_design(design_id: int):
    """One design with its parts, for the detail view.

    The design fields are identical to a `/list` item, plus `items[]` (the
    saved parts with product name, sku, photo, qty and price), the human half
    of `scope_notes`, and `build_intelligence` — the parsed component plan the
    builder recorded, which is what the detail view uses to show which parts
    are still unfilled.
    """
    conn = await get_conn()
    try:
        designs = await _load_designs(conn)
    finally:
        await conn.close()

    design = next((d for d in designs if d["id"] == design_id), None)
    if design is None:
        raise HTTPException(status_code=404, detail="Design not found")

    payload = _public(design)
    payload["items"] = [
        {k: v for k, v in part.items() if not k.startswith("_")} for part in design["_parts"]
    ]
    payload["requested_quantity"] = design["_quantity"]
    payload["scope_notes"] = design["_scope_notes"]
    payload["build_intelligence"] = design["_intel"] or None
    return payload
