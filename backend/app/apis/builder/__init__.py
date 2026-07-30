"""Builder intelligence — the measured numbers behind the design builder.

The builder used to ask for **Height · Width/canopy · Depth/density** as three
free-text boxes. Nobody filled the last two: across 223 imported historical
recipes the words "canopy" and "density" appear zero times, and only
height/width/depth were ever recorded. Fullness is therefore *emergent* — it
falls out of parts × pieces — so this module derives it instead of asking.

Everything served here is computed from the recipe corpus
(`historical_recipes` + `historical_recipe_components`), with the constant
tables in `app/docs/TREE_SCOPE_SPEC.md` as the approved rounding of that
measurement. Where a served constant comes from the spec, the response says so
and carries the live `measured` numbers next to it, so a disagreement is
visible rather than silent.

Three ideas do the real work:

1. **Canopy is per height band, not absolute.** 42″ is "full" on a 6′ tree and
   merely "standard" on a 9′ one, so the XS–XL cut points are defined inside
   each band (see `CANOPY_TIERS`). "Medium" then means the same visual fullness
   at every height.

2. **Density is keyed to species × height and never pooled.** At an identical
   7 feet an Areca Palm uses 1 stem and a Eucalyptus 16. A global baseline is
   not a compromise between those, it is meaningless. Species with no history
   fall back to their structural class (`built_up` vs `specimen`) and say so.

3. **Piece counts, not raw quantity.** Historical `quantity` mixes packs and
   pieces — the same succulent-stem SKU appears at FC $12.34 for a 6-pack and
   $2.05 for one stem. A parallel importer writes the resolved count to
   `formulas.pack_analysis.pieces_used`; every count here prefers that field
   and falls back to `quantity`, reporting which basis it actually used.

Sparse data is reported, never smoothed over: most species×height cells hold
1–5 recipes, so each density answer carries `n`, the observed min/max, and a
confidence signal.

The corpus is static between imports, so it is loaded once into memory and
every endpoint is a pure function over that snapshot — a warm request opens no
database connection at all (same pattern as `_SEARCH_CACHE` in
`app.apis.products`).
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
import statistics
import time
from collections import Counter, defaultdict
from typing import Any, Optional

import asyncpg
from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/builder", tags=["builder"])

DATABASE_URL = os.environ.get("DATABASE_URL")

SPEC_DOC = "app/docs/TREE_SCOPE_SPEC.md"


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


# ─── Constants: the spec's approved tables ───────────────────────────────────
# Each of these was measured from the corpus and rounded to design-friendly
# numbers. `_measure_canopy` below recomputes the raw percentiles on every load
# so `GET /canopy-tiers` can serve the approved cut points *and* the live
# measurement side by side.

# Half-open on the upper edge: `<5'` is height < 60″, `5-7'` is 60 ≤ h < 84 …
HEIGHT_BANDS: list[tuple[str, Optional[float], Optional[float]]] = [
    ("<5'", None, 60.0),
    ("5-7'", 60.0, 84.0),
    ("7-9'", 84.0, 108.0),
    ("9'+", 108.0, None),
]

# Four cut points per band → the five tiers XS/S/M/L/XL. Same convention as the
# bands: `min_in` inclusive, `max_in` exclusive, so a width lands in exactly one
# tier and 30″ on a <5′ tree is XL rather than ambiguously L-or-XL.
CANOPY_TIERS: dict[str, list[float]] = {
    "<5'": [15, 18, 24, 30],
    "5-7'": [28, 32, 36, 42],
    "7-9'": [36, 42, 45, 48],
    "9'+": [54, 60, 66, 72],
}

# n=3 in the corpus. Served, but flagged so the UI can say "refine as builds land".
PROVISIONAL_BANDS = {"9'+"}

TIER_KEYS = ["XS", "S", "M", "L", "XL"]
TIER_LABELS = {
    "XS": "Extra small",
    "S": "Small",
    "M": "Medium",
    "L": "Large",
    "XL": "Extra large",
}

# Silhouette is capture-going-forward, not history: every historical tree was
# built essentially round (depth:width 0.71 → 1.10, median 1.00) and zero
# recipes mention wall/flat/corner/3-side. It drives the depth value.
SILHOUETTES = [
    {
        "key": "full_round",
        "label": "Full-round",
        "depth_ratio": 1.0,
        "use": "freestanding, viewed 360°",
        "default": True,
    },
    {
        "key": "corner",
        "label": "Corner",
        "depth_ratio": 0.66,
        "use": "tucked into a corner",
        "default": False,
    },
    {
        "key": "flat_back",
        "label": "3-sided / flat-back",
        "depth_ratio": 0.5,
        "use": "flush against a wall",
        "default": False,
    },
]

# Density bands as multipliers of the species×height baseline. Derived, not
# picked: pooling every recipe's ratio-to-its-own-cell-median (n=122 recipes
# across the 33 species×height cells that hold 2+ recipes) gives
# p20=0.75, p50=1.00, p85=1.60, p95=2.24. Those four percentiles are the four
# bands. The *centre* is always species-specific — only the spread shape is
# pooled, because a cell with n=1 has no spread of its own to measure.
DENSITY_BANDS = [
    {"key": "sparse", "label": "Sparse", "multiplier": 0.75, "percentile": 20},
    {"key": "standard", "label": "Standard", "multiplier": 1.0, "percentile": 50},
    {"key": "full", "label": "Full", "multiplier": 1.6, "percentile": 85},
    {"key": "super_full", "label": "Super-Full", "multiplier": 2.25, "percentile": 95},
]
DENSITY_BAND_PERCENTILES = [20, 50, 85, 95]

# A cell with this many recipes describes its own spread better than the pooled
# shape does, so its bands come from its own percentiles.
_OWN_SPREAD_MIN_N = 4


# ─── Dimension parsing ───────────────────────────────────────────────────────
# `dimensions` is jsonb of human strings written by hand into spreadsheets:
# 6' · 36" · 58'' · 9 1/2" · 4.5' - 5' · and bare numbers. Bare numbers are
# inches, confirmed against the corpus: TT9-92122 records height "84" and is
# named 7' Fiddle Leaf Tree; TT9-92222 records "72" and is named 6'.

_LEN_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)(?:\s+(\d+)\s*/\s*(\d+))?\s*(.*)$")
_FEET_MARK = re.compile(r"^(?:'|ft|feet|foot)", re.IGNORECASE)
_INCH_MARK = re.compile(r"^(?:\"|''|in\b|inch)", re.IGNORECASE)


def _parse_one_length(text: str) -> Optional[float]:
    match = _LEN_RE.match(text)
    if not match:
        return None
    value = float(match.group(1))
    if match.group(2) and match.group(3) and float(match.group(3)):
        value += float(match.group(2)) / float(match.group(3))
    unit = (match.group(4) or "").strip()
    # Order matters: `''` and `"` are inches, a single `'` is feet.
    if _INCH_MARK.match(unit):
        return value
    if _FEET_MARK.match(unit):
        return value * 12.0
    return value  # bare number → inches


def parse_length_in(value: Any) -> Optional[float]:
    """A recorded dimension as inches. `None` for anything unreadable.

    Accepts numbers as-is and strings in every shape the sheets used, including
    ranges (`4.5' - 5'` → the midpoint, 57″).
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if value > 0 else None
    text = str(value).strip()
    if not text:
        return None
    # A range: parse both ends and take the midpoint. Split only on a dash that
    # separates two numbers, so `1-2"` inside a description can't confuse it.
    parts = [p.strip() for p in re.split(r"\s+(?:-|–|to)\s+", text) if p.strip()]
    if len(parts) == 2:
        low, high = _parse_one_length(parts[0]), _parse_one_length(parts[1])
        # An unmarked low end inherits the high end's unit ("4.5 - 5'").
        if low is not None and high is not None:
            if not re.search(r"['\"]|ft|in", parts[0]) and high > 12 and low <= 12:
                low *= 12.0
            return (low + high) / 2.0
        return low or high
    return _parse_one_length(text)


def height_band(height_in: Optional[float]) -> Optional[str]:
    """Which canopy band a height falls in. Upper edge exclusive."""
    if height_in is None:
        return None
    for key, low, high in HEIGHT_BANDS:
        if (low is None or height_in >= low) and (high is None or height_in < high):
            return key
    return None


def canopy_tier_for(height_in: Optional[float], width_in: Optional[float]) -> Optional[str]:
    """XS…XL for a width, judged inside its own height band."""
    band = height_band(height_in)
    if band is None or width_in is None:
        return None
    cuts = CANOPY_TIERS[band]
    for i, cut in enumerate(cuts):
        if width_in < cut:
            return TIER_KEYS[i]
    return TIER_KEYS[-1]


def format_height(height_in: Optional[float]) -> Optional[str]:
    """Inches → the way the shop writes it (`84` → `7'`, `42` → `42"`)."""
    if height_in is None:
        return None
    if height_in >= 60 and abs(height_in / 12 - round(height_in / 12, 1)) < 1e-9:
        feet = height_in / 12
        return f"{feet:g}'"
    return f'{height_in:g}"'


# ─── Species vocabulary ──────────────────────────────────────────────────────
# HARDCODED: the keyword→canonical-name map. There is no species column to read
# — the signal is free text in the recipe description and its component lines —
# so the vocabulary itself has to be written down. Everything *about* each
# species (how many recipes, at what heights, how many pieces, whether density
# is a real dial) is measured from the corpus. Order matters: the first hit
# wins, so specific names precede the generic "Palm".

_SPECIES_VOCAB: list[tuple[str, tuple[str, ...]]] = [
    ("Fiddle", ("fiddle",)),
    ("Yucca", ("yucca",)),
    ("Dracaena", ("dracaena", "draceana")),
    ("Eucalyptus", ("eucalyptus",)),
    ("Areca", ("areca",)),
    ("Kentia", ("kentia",)),
    ("Travelers Palm", ("travelers palm", "traveller", "traveler")),
    ("Bamboo", ("bamboo",)),
    ("Ficus", ("ficus",)),
    ("Croton", ("croton",)),
    ("Chinese Mahogany", ("mahogany",)),
    ("Schefflera", ("schefflera", "scheffel")),
    ("Zamia", ("zamia",)),
    ("Sansevieria", ("sansevieria", "sanseveria", "mother in-law", "mother in law")),
    ("Bay Leaf", ("bay leaf",)),
    ("Olive", ("olive",)),
    ("Monstera", ("monstera", "monster leaf")),
    ("Fern", ("fern",)),
    ("Agave", ("agave",)),
    ("Echeveria", ("echeveria", "echeverria")),
    ("Cactus", ("cactus",)),
    ("Aloe", ("aloe",)),
    ("Tillandsia", ("tillandsia", "thilansia")),
    ("Succulent", ("succulent", "suculent", "sedeveria", "sedum", "aeonium",
                   "donkey tail", "string of pearls")),
    ("Grass", ("grass", "equisetum", "chive")),
    ("Orchid", ("orchid", "phalaenopsis", "cymbidium")),
    ("Amaryllis", ("amaryllis",)),
    ("Tulip", ("tulip",)),
    ("Hydrangea", ("hydrangea",)),
    ("Magnolia", ("magnolia",)),
    ("Protea", ("protea",)),
    ("Laurel", ("laurel",)),
    ("Palm", ("palm",)),
]

# "Palm Fiber" / "Coco Palm Fiber" are top-dressing mechanics, not a palm. They
# appear on 16 lines, mostly inside Amaryllis and Dracaena pom-pom trees, and
# left in they hand generic "Palm" a fake 21–31-piece baseline.
_SPECIES_NOISE = ("palm fiber", "coco palm", "palm fibre")

# Pinned by the spec. `specimen` means ~1 stem — one large potted plant, no
# build-up — so density barely applies and the builder should not prompt for it.
_SPEC_SPECIMEN = {"Areca", "Kentia", "Travelers Palm", "Palm"}
_SPEC_BUILT_UP = {"Fiddle", "Yucca", "Dracaena", "Eucalyptus"}

# A species the corpus never names still gets an answer: its class decides the
# fallback. Anything unrecognised is treated as built-up (the common case: 29 of
# the 33 species in the corpus are) and labelled as a guess.
_DEFAULT_CLASS = "built_up"

# Below this median piece count a species is behaving like a specimen whatever
# its name, so the class is confirmed from data rather than only asserted.
_SPECIMEN_PIECE_CEILING = 1.5


def detect_species(*texts: Optional[str]) -> Optional[str]:
    """Canonical species/style for a build, from its description and parts."""
    for text in texts:
        if not text:
            continue
        blob = str(text).lower()
        for noise in _SPECIES_NOISE:
            blob = blob.replace(noise, " ")
        for name, keys in _SPECIES_VOCAB:
            if any(key in blob for key in keys):
                return name
    return None


def normalize_species(value: Optional[str]) -> Optional[str]:
    """Resolve caller input (`"fiddle leaf fig"`, `"YUCCA"`) to a canonical name."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    for name, _ in _SPECIES_VOCAB:
        if text.lower() == name.lower():
            return name
    return detect_species(text)


# ─── Scope slots ─────────────────────────────────────────────────────────────
# The canonical filter scopes. A build type's slot list maps its own labels onto
# these, so two slots ("Accent Plant" and "Main Plant") can share one filter
# vocabulary without the UI having to know that.

SLOT_CLASSES = {
    "plant_material": "Plant material",
    "trunks": "Trunks & Branches",
    "top_dressing": "Top Dressing",
    "container": "Container",
    "accent": "Accent / Decor",
}

# Ordered: first hit wins. Top dressing precedes plant material because a
# mechanics line reads "foam, moss"; trunks precede plant material because
# "34\" Fiddle Leaf Branch" is foliage while "8' Dragonwood pole" is a trunk,
# and both contain wood/branch words.
_SLOT_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("top_dressing", ("top dressing", "mechanic", "foam", "moss", "lichen", "acrylic",
                      "rock", "stone", "gravel", "geode", "geos", "sand", "palm fiber",
                      "coco palm")),
    ("trunks", ("dragonwood", "dragon wood", "dragtk", "woodpole", "wood pole", "poles",
                "maple", "mapple", "birch", "trunk", "ghostwood", "winterwood",
                "driftwood", "manzanita", "willow")),
    ("plant_material", ("leaf", "leaves", "spray", "bush", "branch", "stem", "frond",
                        "palm", "grass", "fern", "foliage", "greenery", "plant", "tree",
                        "bundle", "succulent", "cactus", "echeveria", "echeverria",
                        "agave", "sedeveria", "sedum", "aloe", "orchid", "phalaenopsis",
                        "cymbidium", "amaryllis", "tulip", "hydrangea", "magnolia",
                        "protea", "tillandsia", "yucca", "dracaena", "eucalyptus",
                        "ficus", "croton", "bamboo", "zamia", "sansevieria", "monstera",
                        "laurel", "equisetum", "chive", "staghorn", "donkey", "aeonium",
                        "lily", "salvia", "topiary", "cycus", "cycas", "mahogany",
                        "schefflera", "scheffel", "soft touch", "tongue", "pearls",
                        "calla", "olive")),
    ("container", ("container", "pot", "vase", "cylinder", "bowl", "urn", "planter",
                   "basket", "tile", "boat", "compote", "cont.", "plate", "vessel",
                   "zinc", "cement", "concrete", "ceramic", "resin", "terra")),
    ("accent", ("ribbon", "ornament", "ball", "berry", "pinecone", "dust", "pick",
                "decor", "bottle")),
]


def classify_slot(component_label: Optional[str], *texts: Optional[str]) -> str:
    """Which scope slot a recipe line belongs to.

    `component_label` is authoritative when it says `container` — the importer
    read that from the sheet's own container section.
    """
    if (component_label or "").strip().lower() == "container":
        return "container"
    blob = " ".join(str(t or "") for t in texts).lower()
    for slot, keys in _SLOT_RULES:
        if any(key in blob for key in keys):
            return slot
    return "other"


# ─── Build types ─────────────────────────────────────────────────────────────
# HARDCODED: which fields a type can use, and its slot template. Slot *labels*
# match the ones the builder already renders (see LEGACY_TOP_DOWN_SLOT_ORDERS in
# the frontend) so saved parts keep resolving; the order here is bottom-up —
# leaves/accent at the top of the list, container at the bottom — mirroring how
# the piece is physically assembled.
#
# The three new types (Plant & Bush, Container Only, Topiary) came out of the
# corpus, where Plant & Bush at 74 recipes outranks Tree at 52. `recipe_count`
# on every type is measured, so the UI can order by what actually gets built.

_ALL_FIELDS = ("height", "width", "canopy", "silhouette", "depth", "species", "density")

BUILD_TYPES: list[dict[str, Any]] = [
    {
        "key": "plant_bush",
        "label": "Plant & Bush",
        "aliases": ["Plant & Bush", "Plant and Bush", "Bush", "Plant"],
        "fields": ("height", "width", "canopy", "silhouette", "depth", "species", "density"),
        "slots": [
            ("Accent Greenery", "plant_material"),
            ("Main Plant", "plant_material"),
            ("Top Dressing", "top_dressing"),
            ("Container", "container"),
        ],
        "notes": "The most-built product in the corpus. Trunks appear in only 4% of "
                 "these recipes, so there is no Trunks & Branches slot.",
    },
    {
        "key": "floral_arrangement",
        "label": "Floral Arrangement",
        "aliases": ["Floral Arrangement", "Arrangement", "Orchid Arrangement",
                    "Succulent Arrangement", "Foliage Arrangement"],
        "fields": ("height", "width", "depth", "species", "density"),
        "slots": [
            ("Accent Material", "plant_material"),
            ("Focal Material", "plant_material"),
            ("Finish/Top Dressing", "top_dressing"),
            ("Container/Base", "container"),
        ],
        "notes": "Maps to the builder's existing \"Arrangement\". Canopy tiers are a "
                 "tree-scope measurement and are not offered here.",
    },
    {
        "key": "tree",
        "label": "Tree",
        "aliases": ["Tree", "Tree / Plant", "Fiddle Fig"],
        "fields": ("height", "width", "canopy", "silhouette", "depth", "species", "density"),
        "slots": [
            ("Leaves", "plant_material"),
            ("Trunks & Branches", "trunks"),
            ("Top Dressing", "top_dressing"),
            ("Container", "container"),
        ],
        "notes": "The full tree scope model: canopy tiers per height band, silhouette, "
                 "species-keyed density.",
    },
    {
        "key": "container_only",
        "label": "Container Only",
        "aliases": ["Container Only", "Container", "Vessel"],
        "fields": ("height", "width", "depth"),
        "slots": [
            ("Top Dressing", "top_dressing"),
            ("Container", "container"),
        ],
        "notes": "Container + top dressing, no plant material — so no canopy, "
                 "silhouette or density. See `data_note`.",
        "data_note": "13 of the 15 corpus recipes carrying this label DO have plant "
                     "material: the importer's keyword rule fires on the word "
                     "\"container\", including in \"(Container NOT included)\" — which is "
                     "how five 9–10' Dracaena pom-pom trees landed here. The slot "
                     "template follows the type's intended meaning, not that history.",
    },
    {
        "key": "planter",
        "label": "Planter",
        "aliases": ["Planter", "Container Garden", "Floor Container"],
        "fields": ("height", "width", "depth", "species", "density"),
        "slots": [
            ("Accent Plant", "plant_material"),
            ("Main Plant", "plant_material"),
            ("Finish/Top Dressing", "top_dressing"),
            ("Container/Planter", "container"),
        ],
        "notes": None,
    },
    {
        "key": "topiary",
        "label": "Topiary",
        "aliases": ["Topiary"],
        "fields": ("height", "width", "canopy", "silhouette", "depth", "species", "density"),
        "slots": [
            ("Leaves", "plant_material"),
            ("Trunks & Branches", "trunks"),
            ("Top Dressing", "top_dressing"),
            ("Container", "container"),
        ],
        "notes": "Thin history (2 recipes, one of them an empty sheet) — seeded from "
                 "Tree. Treat its defaults as provisional.",
        "seed_from": "tree",
    },
    {
        "key": "drop_in",
        "label": "Drop-in",
        "aliases": ["Drop-in", "Drop-in Arrangement", "Drop In", "Client Container"],
        "fields": ("height", "width", "depth", "species", "density"),
        "slots": [
            ("Finish", "top_dressing"),
            ("Accent Material", "plant_material"),
            ("Main Material", "plant_material"),
            ("Drop-in Base", "container"),
        ],
        "notes": "No corpus history. Drops into a container the client already owns, "
                 "so canopy and silhouette do not apply.",
    },
    {
        "key": "custom",
        "label": "Custom",
        "aliases": ["Custom", "Custom Arrangement"],
        "fields": ("height", "width", "depth", "species", "density"),
        "slots": [],
        "notes": "No corpus history. Free-form: slots are named by the designer.",
    },
]

_BUILD_TYPE_BY_ALIAS: dict[str, dict[str, Any]] = {}
for _bt in BUILD_TYPES:
    _BUILD_TYPE_BY_ALIAS[_bt["key"]] = _bt
    for _alias in _bt["aliases"]:
        _BUILD_TYPE_BY_ALIAS[_alias.strip().lower()] = _bt


def resolve_build_type(value: Optional[str]) -> Optional[dict[str, Any]]:
    """Caller input (`tree`, `Tree`, `Drop-in Arrangement`) → the type record."""
    if not value or not str(value).strip():
        return None
    return _BUILD_TYPE_BY_ALIAS.get(str(value).strip().lower())


# ─── Corpus loading ──────────────────────────────────────────────────────────

_RECIPE_SQL = """
    SELECT id, source_file_id, item_code, product_family, build_type, description,
           source_collection, recipe_year, dimensions, container_details,
           pricing_summary, visual_reference_count
    FROM historical_recipes
"""

_COMPONENT_SQL = """
    SELECT id, recipe_id, line_order, component_label, vendor, supplier_sku,
           description, quantity, first_cost, landed_cost, retail, extended_total,
           formulas
    FROM historical_recipe_components
    ORDER BY recipe_id, line_order
"""


async def _fetch_corpus_rows(conn) -> tuple[list, list]:
    """The two raw table reads. Stubbed wholesale in tests — no DB required."""
    return list(await conn.fetch(_RECIPE_SQL)), list(await conn.fetch(_COMPONENT_SQL))


def _jsonish(value: Any) -> Any:
    """jsonb from asyncpg arrives as text on some drivers, dict on others."""
    if value is None or isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
    return None


def _as_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def component_pieces(component: dict) -> tuple[float, str]:
    """How many *pieces* this line contributes, and where that number came from.

    `quantity` is ambiguous — it mixes packs and pieces — so a parallel importer
    resolves each line into `formulas.pack_analysis.pieces_used`. Prefer that
    when it is there and fall back to `quantity` when it is not, which is what
    makes this correct both before and after that work lands.
    """
    formulas = _jsonish(component.get("formulas")) or {}
    if isinstance(formulas, dict):
        pack = formulas.get("pack_analysis")
        if isinstance(pack, dict):
            pieces = _as_float(pack.get("pieces_used"))
            if pieces is not None:
                return pieces, "pack_analysis"
    return _as_float(component.get("quantity")) or 0.0, "quantity"


def _percentile(values: list[float], pct: float) -> Optional[float]:
    """Linear-interpolated percentile. `None` for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * pct / 100.0
    low, high = math.floor(k), math.ceil(k)
    if low == high:
        return ordered[int(k)]
    return ordered[low] + (ordered[high] - ordered[low]) * (k - low)


def _round_pieces(value: Optional[float]) -> Optional[int]:
    """Piece counts are shown as whole stems; the corpus has 0.068-of-a-bale lines."""
    if value is None:
        return None
    return max(0, int(round(value)))


def _build_corpus(recipe_rows: list, component_rows: list) -> dict[str, Any]:
    """Turn the two raw tables into everything the endpoints serve. Pure."""
    by_recipe: dict[Any, list[dict]] = defaultdict(list)
    piece_basis_counts: Counter = Counter()

    for row in component_rows:
        comp = dict(row)
        pieces, basis = component_pieces(comp)
        comp["_pieces"] = pieces
        comp["_piece_basis"] = basis
        piece_basis_counts[basis] += 1
        comp["_slot"] = classify_slot(
            comp.get("component_label"),
            comp.get("description"),
            comp.get("supplier_sku"),
            comp.get("vendor"),
        )
        by_recipe[comp.get("recipe_id")].append(comp)

    recipes: list[dict[str, Any]] = []
    for row in recipe_rows:
        rec = dict(row)
        dims = _jsonish(rec.get("dimensions")) or {}
        pricing = _jsonish(rec.get("pricing_summary")) or {}
        comps = by_recipe.get(rec.get("id"), [])

        height = parse_length_in(dims.get("height") if isinstance(dims, dict) else None)
        width = parse_length_in(dims.get("width") if isinstance(dims, dict) else None)
        depth = parse_length_in(dims.get("depth") if isinstance(dims, dict) else None)

        # The spec's density metric: pieces across every `product` line. It is
        # deliberately generous (a Dragonwood pole counts) because that is what
        # reproduces the approved seed baselines — an 8' Fiddle at 11–13.
        product_pieces = sum(c["_pieces"] for c in comps
                             if (c.get("component_label") or "") == "product")
        # The narrower reading: only lines that classify as plant material. This
        # is the honest "structural stems" number and is what decides whether a
        # species behaves like a specimen.
        plant_pieces = sum(c["_pieces"] for c in comps if c["_slot"] == "plant_material")

        component_text = " ".join(str(c.get("description") or "") for c in comps)
        species = (detect_species(rec.get("description"))
                   or detect_species(component_text))

        cost = _as_float(pricing.get("component_total")) if isinstance(pricing, dict) else None
        if cost is None:
            cost = sum(_as_float(c.get("extended_total")) or 0.0 for c in comps) or None
        retail = _as_float(pricing.get("retail")) if isinstance(pricing, dict) else None
        wholesale = _as_float(pricing.get("wholesale")) if isinstance(pricing, dict) else None

        build_type = (rec.get("build_type") or "").strip() or None

        # Junk filter, derived rather than listed by id. Two shapes of junk:
        # blank sheets that never got a build type (6 recipes), and sheets that
        # parsed but priced to nothing — TT9-9522 "Bay Leaf Topiary" is one
        # line with no values. Neither should ever be suggested as a build.
        priced = bool((cost or 0) > 0 or (retail or 0) > 0)
        usable = bool(build_type and priced and comps)

        recipes.append({
            "id": rec.get("id"),
            "item_code": (rec.get("item_code") or "").strip() or None,
            "build_type": build_type,
            "description": (rec.get("description") or "").strip() or None,
            "product_family": rec.get("product_family"),
            "source_collection": rec.get("source_collection"),
            "recipe_year": rec.get("recipe_year"),
            "height_in": height,
            "width_in": width,
            "depth_in": depth,
            "height_band": height_band(height),
            "canopy_tier": canopy_tier_for(height, width),
            "depth_ratio": (depth / width) if (depth and width) else None,
            "species": species,
            "pieces": product_pieces,
            "plant_pieces": plant_pieces,
            "cost": cost,
            "retail": retail,
            "wholesale": wholesale,
            "component_count": len(comps),
            "slots": sorted({c["_slot"] for c in comps}),
            "usable": usable,
        })

    corpus: dict[str, Any] = {
        "built_at": time.time(),
        "recipe_count": len(recipes),
        "component_count": len(component_rows),
        "recipes": recipes,
        "piece_basis": _summarize_piece_basis(piece_basis_counts),
    }
    corpus["build_type_counts"] = _measure_build_types(recipes)
    corpus["canopy"] = _measure_canopy(recipes)
    corpus["silhouette"] = _measure_silhouette(recipes)
    corpus["species"] = _measure_species(recipes)
    corpus["density_cells"] = _measure_density_cells(recipes)
    corpus["class_cells"] = _measure_class_cells(recipes, corpus["species"])
    corpus["slot_vocab"] = _measure_slot_vocab(by_recipe)
    corpus["common_builds"] = _measure_common_builds(recipes)
    return corpus


def _summarize_piece_basis(counts: Counter) -> dict[str, Any]:
    total = sum(counts.values())
    resolved = counts.get("pack_analysis", 0)
    if total == 0:
        primary = "quantity"
    elif resolved == 0:
        primary = "quantity"
    elif resolved == total:
        primary = "pack_analysis"
    else:
        primary = "mixed"
    return {
        "primary": primary,
        "lines_total": total,
        "lines_from_pack_analysis": resolved,
        "lines_from_quantity": counts.get("quantity", 0),
        "note": ("`formulas.pack_analysis.pieces_used` is present on "
                 f"{resolved}/{total} component lines; the rest fall back to raw "
                 "`quantity`, which mixes packs and pieces."),
    }


def _measure_build_types(recipes: list[dict]) -> dict[str, dict[str, int]]:
    counts: dict[str, dict[str, int]] = defaultdict(lambda: {"recipes": 0, "usable": 0})
    for rec in recipes:
        key = rec["build_type"] or "__unlabelled__"
        counts[key]["recipes"] += 1
        if rec["usable"]:
            counts[key]["usable"] += 1
    return dict(counts)


def _measure_canopy(recipes: list[dict]) -> dict[str, dict[str, Any]]:
    """Live width percentiles per height band, over Tree recipes.

    Tree-only is the subset the spec measured: it reproduces its n of
    9 / 11 / 18 / 3 exactly. Widths from arrangements and plant-and-bush builds
    are not canopies and would drag the bands down.
    """
    groups: dict[str, list[float]] = defaultdict(list)
    for rec in recipes:
        if rec["build_type"] == "Tree" and rec["height_band"] and rec["width_in"]:
            groups[rec["height_band"]].append(rec["width_in"])
    out: dict[str, dict[str, Any]] = {}
    for band, _low, _high in HEIGHT_BANDS:
        widths = groups.get(band, [])
        out[band] = {
            "n": len(widths),
            "p20": _percentile(widths, 20),
            "p40": _percentile(widths, 40),
            "p60": _percentile(widths, 60),
            "p80": _percentile(widths, 80),
            "median": statistics.median(widths) if widths else None,
            "min": min(widths) if widths else None,
            "max": max(widths) if widths else None,
        }
    return out


def _measure_silhouette(recipes: list[dict]) -> dict[str, Any]:
    ratios = [r["depth_ratio"] for r in recipes
              if r["depth_ratio"] and r["build_type"] in ("Tree", "Plant & Bush", "Topiary")]
    tree_ratios = [r["depth_ratio"] for r in recipes
                   if r["depth_ratio"] and r["build_type"] == "Tree"]
    def _stats(values):
        if not values:
            return {"n": 0}
        return {"n": len(values), "min": round(min(values), 2),
                "max": round(max(values), 2),
                "median": round(statistics.median(values), 2)}
    return {"tree": _stats(tree_ratios), "tree_like": _stats(ratios)}


def _measure_species(recipes: list[dict]) -> dict[str, dict[str, Any]]:
    """Per-species facts: how many recipes, which build types, which class."""
    seen: dict[str, dict[str, Any]] = {}
    for name, _keys in _SPECIES_VOCAB:
        seen[name] = {
            "name": name,
            "recipe_count": 0,
            "usable_recipe_count": 0,
            "build_types": Counter(),
            "build_types_usable": Counter(),
            "heights_in": [],
            "pieces": [],
            "plant_pieces": [],
        }
    for rec in recipes:
        if not rec["species"]:
            continue
        entry = seen[rec["species"]]
        entry["recipe_count"] += 1
        if rec["usable"]:
            entry["usable_recipe_count"] += 1
        if rec["build_type"]:
            entry["build_types"][rec["build_type"]] += 1
            if rec["usable"]:
                entry["build_types_usable"][rec["build_type"]] += 1
        if rec["height_in"]:
            entry["heights_in"].append(rec["height_in"])
        if rec["pieces"] > 0:
            entry["pieces"].append(rec["pieces"])
        entry["plant_pieces"].append(rec["plant_pieces"])

    out: dict[str, dict[str, Any]] = {}
    for name, entry in seen.items():
        pieces = entry["pieces"]
        plant = [p for p in entry["plant_pieces"] if p > 0]
        median_plant = statistics.median(plant) if plant else None
        # Class: the spec's pins first, then the data's own verdict, then default.
        if name in _SPEC_SPECIMEN:
            klass, basis = "specimen", "spec"
        elif name in _SPEC_BUILT_UP:
            klass, basis = "built_up", "spec"
        elif median_plant is not None and median_plant <= _SPECIMEN_PIECE_CEILING:
            klass, basis = "specimen", "measured"
        elif median_plant is not None:
            klass, basis = "built_up", "measured"
        else:
            klass, basis = _DEFAULT_CLASS, "default"
        agrees = None
        if basis == "spec" and median_plant is not None:
            measured = "specimen" if median_plant <= _SPECIMEN_PIECE_CEILING else "built_up"
            agrees = measured == klass
        out[name] = {
            "name": name,
            "structural_class": klass,
            "class_basis": basis,
            "class_agrees_with_data": agrees,
            "recipe_count": entry["recipe_count"],
            "usable_recipe_count": entry["usable_recipe_count"],
            "build_types": dict(entry["build_types"]),
            "build_types_usable": dict(entry["build_types_usable"]),
            "heights_ft": sorted({round(h / 12) for h in entry["heights_in"]}),
            "median_pieces": round(statistics.median(pieces), 2) if pieces else None,
            "median_structural_pieces": round(median_plant, 2) if median_plant else None,
            "density_applies": klass != "specimen",
        }
    return out


def _measure_density_cells(recipes: list[dict]) -> dict[str, dict[str, Any]]:
    """One cell per species × whole foot of height. Keyed `"Fiddle|8"`."""
    cells: dict[str, dict[str, list[Any]]] = defaultdict(
        lambda: {"pieces": [], "plant": [], "recipes": []})
    for rec in recipes:
        if not rec["species"] or not rec["height_in"] or rec["pieces"] <= 0:
            continue
        key = f"{rec['species']}|{round(rec['height_in'] / 12)}"
        cells[key]["pieces"].append(rec["pieces"])
        cells[key]["plant"].append(rec["plant_pieces"])
        cells[key]["recipes"].append(rec["item_code"] or f"#{rec['id']}")
    return {key: _cell_stats(value) for key, value in cells.items()}


def _cell_stats(cell: dict[str, list]) -> dict[str, Any]:
    pieces = cell["pieces"]
    plant = [p for p in cell["plant"] if p > 0]
    return {
        "n": len(pieces),
        "baseline": statistics.median(pieces),
        "min": min(pieces),
        "max": max(pieces),
        "values": sorted(round(p, 3) for p in pieces),
        "structural_baseline": statistics.median(plant) if plant else None,
        "structural_min": min(plant) if plant else None,
        "structural_max": max(plant) if plant else None,
        "examples": cell["recipes"][:6],
    }


def _measure_class_cells(recipes: list[dict],
                         species: dict[str, dict]) -> dict[str, dict[str, Any]]:
    """Fallback cells for a species with no history: class × height in feet."""
    cells: dict[str, list[float]] = defaultdict(list)
    for rec in recipes:
        if not rec["species"] or not rec["height_in"] or rec["pieces"] <= 0:
            continue
        klass = species[rec["species"]]["structural_class"]
        cells[f"{klass}|{round(rec['height_in'] / 12)}"].append(rec["pieces"])
        cells[klass].append(rec["pieces"])
    return {key: {"n": len(v), "baseline": statistics.median(v),
                  "min": min(v), "max": max(v)}
            for key, v in cells.items()}


# ─── Slot vocabulary (Choose Parts) ──────────────────────────────────────────
# DERIVED: the search terms per slot are the most-recurring 1–3-word phrases in
# the descriptions of the recipe lines that classify into that slot, counted by
# how many distinct recipes used them. That reproduces the spec's ranked Top
# Dressing list (foam 32 · acrylic 24 · smooth foam ball 18 · sheet moss 17 …)
# without any of it being typed in here.

_VOCAB_STOPWORDS = set("""
a an and or the of in on with for to per each set pcs pc pack bag bags plus
not included lg sm med small large tall short size new used total qty quantity
item items line lines none null tbd
""".split())

_VOCAB_MIN_RECIPES = 2
_VOCAB_MAX_TERMS = 16
# A shorter phrase that mostly appears inside a longer one is a fragment, not
# vocabulary: "moon" occurs on 12 recipes and 9 of them say "buff moon rock",
# so "moon" is dropped and the phrase kept. Generic-but-real terms survive
# because they are used far more widely than any one phrase ("moss" on 52
# recipes vs "sheet moss" on 21).
_SUBPHRASE_SUPPRESSION = 0.7

# The sheets' own section headings, not searchable product vocabulary. 107 lines
# read literally "Top Dressing / Mechanics" — that is the slot's name.
_VOCAB_PLACEHOLDERS = {
    "mechanics", "top", "top dressing", "top dressing mechanics", "dressing mechanics",
    "dressing", "product", "products", "removable", "head", "removable head",
    "additional", "charge", "additional charge", "misc", "other",
}


def _vocab_tokens(text: Optional[str]) -> list[str]:
    """Description → searchable words, with sizes and punctuation stripped."""
    blob = (text or "").lower()
    blob = re.sub(r"\d+(?:\.\d+)?\s*(?:''|\"|'|in\b|inch(?:es)?\b|ft\b)?", " ", blob)
    blob = re.sub(r"[^a-z\s&+-]", " ", blob)
    return [w for w in blob.split() if len(w) > 2 and w not in _VOCAB_STOPWORDS]


def _vocab_phrases(words: list[str]) -> set[str]:
    out = set(words)
    out |= {f"{words[i]} {words[i + 1]}" for i in range(len(words) - 1)}
    out |= {f"{words[i]} {words[i + 1]} {words[i + 2]}" for i in range(len(words) - 2)}
    return out


def _fold_plurals(phrases: dict[str, set]) -> dict[str, set]:
    """Merge `rocks` into `rock` so one term isn't split across both spellings."""
    merged: dict[str, set] = {}
    for phrase, rids in phrases.items():
        singular = re.sub(r"(?<=[a-z]{3})s$", "", phrase)
        key = singular if (singular != phrase and singular in phrases) else phrase
        merged.setdefault(key, set()).update(rids)
    return merged


def _measure_slot_vocab(by_recipe: dict) -> dict[str, list[dict]]:
    counts: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))
    for comps in by_recipe.values():
        for comp in comps:
            for phrase in _vocab_phrases(_vocab_tokens(comp.get("description"))):
                if phrase in _VOCAB_PLACEHOLDERS:
                    continue
                counts[comp["_slot"]][phrase].add(comp.get("recipe_id"))

    out: dict[str, list[dict]] = {}
    for slot, phrases in counts.items():
        phrases = _fold_plurals(phrases)
        scored = {p: len(rids) for p, rids in phrases.items() if len(rids) >= _VOCAB_MIN_RECIPES}
        kept = []
        for phrase, n in scored.items():
            longer = [m for other, m in scored.items()
                      if other != phrase and f" {phrase} " in f" {other} "]
            if longer and max(longer) >= n * _SUBPHRASE_SUPPRESSION:
                continue
            kept.append({"term": phrase, "recipes": n})
        kept.sort(key=lambda t: (-t["recipes"], len(t["term"]), t["term"]))
        kept = kept[:_VOCAB_MAX_TERMS]
        top = kept[0]["recipes"] if kept else 1
        for entry in kept:
            entry["weight"] = round(entry["recipes"] / top, 3)
            entry["source"] = "derived"
        out[slot] = kept
    return out


# HARDCODED: slot → catalog taxonomy. The recipe corpus records vendor SKUs and
# free text, never a catalog category, so this bridge cannot be derived — but
# every value below is a real `category_group` from `products` and every list is
# ordered by how well it serves the slot. `exclude_categories` is what makes
# "selecting Container must surface containers first, never dried botanicals"
# actually true against `/api/products/search`.
_SLOT_CATALOG: dict[str, dict[str, Any]] = {
    "container": {
        "categories": ["Containers & Vases"],
        "exclude_categories": ["Botanicals & Fillers", "Florals", "Ornaments"],
        "product_types": ["Container & Base"],
        "colors": [],
    },
    "top_dressing": {
        "categories": ["Botanicals & Fillers", "Rocks & Stone", "Home Décor"],
        "exclude_categories": [],
        "product_types": [],
        "colors": ["Green", "Beige/Natural", "Brown"],
    },
    "plant_material": {
        "categories": ["Greenery & Plants", "Florals", "Trees", "Botanicals & Fillers"],
        "exclude_categories": ["Ornaments", "Ribbon & Bows", "Lighting"],
        "product_types": ["Greenery & Foliage", "Floral Stems", "Spray & Picks", "Tree"],
        "colors": ["Green"],
    },
    "trunks": {
        "categories": ["Botanicals & Fillers", "Greenery & Plants"],
        "exclude_categories": ["Ornaments", "Ribbon & Bows"],
        "product_types": [],
        "colors": ["Brown", "Beige/Natural"],
    },
    "accent": {
        "categories": ["Home Décor", "Ornaments", "Ribbon & Bows"],
        "exclude_categories": [],
        "product_types": ["Ornament", "Decor & Figurines", "Ribbon & Bows"],
        "colors": [],
    },
    "other": {"categories": [], "exclude_categories": [], "product_types": [], "colors": []},
}


# ─── Common builds ───────────────────────────────────────────────────────────


def _measure_common_builds(recipes: list[dict]) -> list[dict[str, Any]]:
    """Recurring build signatures: build type × species × whole foot of height.

    Only usable recipes with a recorded height take part — a suggestion whose
    job is to pre-fill Step 1 is worthless without one.
    """
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for rec in recipes:
        if not rec["usable"] or not rec["height_in"]:
            continue
        groups[(rec["build_type"], rec["species"], round(rec["height_in"] / 12))].append(rec)

    builds = []
    for (build_type, species, height_ft), members in groups.items():
        heights = [m["height_in"] for m in members]
        widths = [m["width_in"] for m in members if m["width_in"]]
        depths = [m["depth_in"] for m in members if m["depth_in"]]
        pieces = [m["pieces"] for m in members if m["pieces"] > 0]
        plant = [m["plant_pieces"] for m in members if m["plant_pieces"] > 0]
        costs = [m["cost"] for m in members if m["cost"]]
        retails = [m["retail"] for m in members if m["retail"]]

        height_in = statistics.median(heights)
        width_in = statistics.median(widths) if widths else None
        names = Counter(m["description"] for m in members if m["description"])
        name = names.most_common(1)[0][0] if names else None
        if not name:
            label = species or build_type
            name = f"{format_height(height_in)} {label}".strip()

        builds.append({
            "name": name,
            "build_type": build_type,
            "species": species,
            "recipe_count": len(members),
            "height_in": round(height_in, 1),
            "height_display": format_height(height_in),
            "width_in": round(width_in, 1) if width_in else None,
            "depth_in": round(statistics.median(depths), 1) if depths else None,
            "canopy_tier": canopy_tier_for(height_in, width_in),
            "height_band": height_band(height_in),
            "silhouette": "full_round",
            "pieces": _round_pieces(statistics.median(pieces)) if pieces else None,
            "structural_pieces": _round_pieces(statistics.median(plant)) if plant else None,
            "typical_component_cost": round(statistics.median(costs), 2) if costs else None,
            "typical_retail": round(statistics.median(retails), 2) if retails else None,
            "item_codes": sorted({m["item_code"] for m in members if m["item_code"]})[:6],
            "example_recipe_ids": [m["id"] for m in members][:6],
        })
    builds.sort(key=lambda b: (-b["recipe_count"], -(b["height_in"] or 0), b["name"]))
    return builds


# ─── In-process cache ────────────────────────────────────────────────────────
# Every endpoint is a pure function of this snapshot, so a warm request never
# touches the database. The corpus only changes when a recipe import runs.

_CACHE: dict[str, Any] = {"ts": 0.0, "corpus": None}
_TTL = 3600  # 1 hour — the recipe corpus is static between imports
_LOAD_LOCK = asyncio.Lock()


def _cache_fresh() -> bool:
    return _CACHE["corpus"] is not None and (time.time() - _CACHE["ts"]) < _TTL


async def corpus() -> dict[str, Any]:
    """The cached corpus snapshot, loading it on first use."""
    if _cache_fresh():
        return _CACHE["corpus"]
    # Single-flight: two cold requests must not each build their own copy.
    async with _LOAD_LOCK:
        if _cache_fresh():
            return _CACHE["corpus"]
        conn = await get_conn()
        try:
            recipe_rows, component_rows = await _fetch_corpus_rows(conn)
        finally:
            await conn.close()
        built = _build_corpus(recipe_rows, component_rows)
        _CACHE.update(ts=time.time(), corpus=built)
        return built


def _provenance(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "recipes_analyzed": data["recipe_count"],
        "components_analyzed": data["component_count"],
        "piece_basis": data["piece_basis"],
        "spec": SPEC_DOC,
    }


# ─── 1. Build types ──────────────────────────────────────────────────────────


@router.get("/build-types")
async def get_build_types():
    """The type list, each with its bottom-up slot template and live counts.

    Ordered by how much history backs the type, so the UI leads with what the
    shop actually builds — Plant & Bush (74) ahead of Tree (52) — and the
    history-less types (Drop-in, Custom) sit at the end.

    `fields` is exhaustive and honest: a type never advertises a field it can't
    use, so Container Only carries no canopy or silhouette and Drop-in carries
    no canopy at all.
    """
    data = await corpus()
    counts = data["build_type_counts"]

    items = []
    for spec in BUILD_TYPES:
        measured = counts.get(spec["label"], {"recipes": 0, "usable": 0})
        item = {
            "key": spec["key"],
            "label": spec["label"],
            "aliases": spec["aliases"],
            "recipe_count": measured["recipes"],
            "usable_recipe_count": measured["usable"],
            "has_history": measured["recipes"] > 0,
            "slots": [
                {"order": i, "label": label, "scope": scope,
                 "scope_label": SLOT_CLASSES[scope]}
                for i, (label, scope) in enumerate(spec["slots"])
            ],
            "slot_order": "bottom_up",
            "fields": {field: field in spec["fields"] for field in _ALL_FIELDS},
            "applies": list(spec["fields"]),
            "notes": spec.get("notes"),
        }
        if spec.get("seed_from"):
            item["seed_from"] = spec["seed_from"]
        if spec.get("data_note"):
            item["data_note"] = spec["data_note"]
        items.append(item)

    items.sort(key=lambda i: (-i["recipe_count"], i["label"]))
    return {
        "build_types": items,
        "field_definitions": {
            "height": "Overall finished height.",
            "width": "Overall finished width — the canopy diameter on tree-like builds.",
            "canopy": "XS–XL fullness, judged inside the build's own height band.",
            "silhouette": "Full-round / corner / flat-back; sets depth from width.",
            "depth": "Front-to-back depth. Derived from width × silhouette when unset.",
            "species": "Species or style, e.g. Fiddle, Yucca, Orchid.",
            "density": "Sparse → Super-Full, as pieces around the species×height baseline.",
        },
        "unlabelled_recipes": counts.get("__unlabelled__", {}).get("recipes", 0),
        "provenance": _provenance(data),
    }


# ─── 2. Species ──────────────────────────────────────────────────────────────


@router.get("/species")
async def get_species(build_type: Optional[str] = None, include_empty: bool = True):
    """The species/style list, each tagged `built_up` or `specimen`.

    `built_up` means density is a real dial (a 7′ Eucalyptus is 16 stems).
    `specimen` means ~1 stem — one large potted plant — so the builder should
    not prompt for density at all (a 7′ Areca Palm is 1).

    `build_type` narrows the list to species that type has actually been built
    from. `include_empty=false` drops the vocabulary entries the corpus never
    names (they are returned by default so a designer can still pick Croton or
    a generic Palm and get a class-based answer).
    """
    data = await corpus()
    resolved_type = resolve_build_type(build_type)
    if build_type and not resolved_type:
        raise HTTPException(status_code=400, detail=f"Unknown build_type: {build_type}")

    items = []
    for entry in data["species"].values():
        if resolved_type:
            aliases = {a.lower() for a in resolved_type["aliases"]}
            matched = {bt: n for bt, n in entry["build_types"].items()
                       if bt.strip().lower() in aliases}
            if not matched:
                continue
            recipe_count = sum(matched.values())
            # Counts must narrow together: a Tree-filtered list reporting the
            # species' whole-corpus usable count is a number nobody can act on.
            usable_count = sum(n for bt, n in entry["build_types_usable"].items()
                               if bt.strip().lower() in aliases)
        else:
            matched = entry["build_types"]
            recipe_count = entry["recipe_count"]
            usable_count = entry["usable_recipe_count"]
        if not include_empty and recipe_count == 0:
            continue
        items.append({
            "name": entry["name"],
            "structural_class": entry["structural_class"],
            "class_basis": entry["class_basis"],
            "class_agrees_with_data": entry["class_agrees_with_data"],
            "density_applies": entry["density_applies"],
            "recipe_count": recipe_count,
            "usable_recipe_count": usable_count,
            "build_types": matched,
            "heights_ft": entry["heights_ft"],
            "median_pieces": entry["median_pieces"],
            "median_structural_pieces": entry["median_structural_pieces"],
        })
    items.sort(key=lambda s: (-s["recipe_count"], s["name"]))

    return {
        "species": items,
        "build_type": resolved_type["label"] if resolved_type else None,
        "classes": {
            "built_up": "Assembled from many stems/branches — density is a real dial.",
            "specimen": "~1 stem: one large potted plant, no build-up. Density barely applies.",
        },
        "unclassified_recipes": sum(1 for r in data["recipes"] if not r["species"]),
        "provenance": _provenance(data),
    }


# ─── 3. Canopy tiers ─────────────────────────────────────────────────────────


@router.get("/canopy-tiers")
async def get_canopy_tiers(height_in: Optional[float] = None,
                           height: Optional[str] = None,
                           width_in: Optional[float] = None):
    """XS–XL canopy cut points for a height, plus the silhouette options.

    Tiers are defined *inside* each height band, because canopy scales with
    height: 42″ is Full on a 6′ tree and Standard on a 9′ one. Defining them per
    band is what makes "Medium" mean the same visual fullness everywhere.

    Pass `height_in=84` or `height=7'` (both accepted, same shapes the sheets
    use). Pass `width_in` too and the response says which tier that width lands
    in. Omit height entirely for the whole table.
    """
    data = await corpus()
    resolved = height_in if height_in is not None else parse_length_in(height)
    if (height_in is not None or height) and resolved is None:
        raise HTTPException(status_code=400, detail=f"Could not read a height from {height!r}")

    def _band_payload(band_key: str) -> dict[str, Any]:
        cuts = CANOPY_TIERS[band_key]
        edges = [None] + list(cuts) + [None]
        tiers = []
        for i, key in enumerate(TIER_KEYS):
            low, high = edges[i], edges[i + 1]
            if low is None:
                label = f'<{high:g}"'
            elif high is None:
                label = f'>{low:g}"'
            else:
                label = f'{low:g}–{high:g}"'
            tiers.append({
                "key": key, "label": TIER_LABELS[key],
                "min_in": low, "max_in": high, "range_label": label,
            })
        measured = data["canopy"][band_key]
        return {
            "band": band_key,
            "tiers": tiers,
            "default_tier": "M",
            "default_width_in": measured["median"],
            "provisional": band_key in PROVISIONAL_BANDS,
            "n": measured["n"],
            "measured": measured,
            "spec_matches_measured": _spec_matches(cuts, measured),
        }

    payload: dict[str, Any] = {
        "bounds_note": "min_in inclusive, max_in exclusive — a width lands in exactly one tier.",
        "silhouettes": SILHOUETTES,
        "silhouette_measured": data["silhouette"],
        "silhouette_note": ("Silhouette is capture-going-forward: every historical tree "
                            "was built essentially round (median depth:width 1.00) and no "
                            "recipe mentions wall / flat / corner / 3-side."),
        "source": f"{SPEC_DOC} §1, cut points verified against the corpus on load",
        "provenance": _provenance(data),
    }

    if resolved is None:
        payload["bands"] = [_band_payload(key) for key, _l, _h in HEIGHT_BANDS]
        return payload

    band_key = height_band(resolved)
    payload.update(_band_payload(band_key))
    payload["height_in"] = resolved
    payload["height_display"] = format_height(resolved)
    if width_in is not None:
        payload["width_in"] = width_in
        payload["matched_tier"] = canopy_tier_for(resolved, width_in)
    return payload


def _spec_matches(cuts: list[float], measured: dict[str, Any]) -> Optional[bool]:
    """Whether the spec's rounded cut points still bracket the live percentiles.

    Cheap regression alarm: if a later import moves a band's real percentiles
    more than 3″ away from the approved numbers, the response says so instead of
    quietly serving stale constants.
    """
    keys = ["p20", "p40", "p60", "p80"]
    if measured["n"] < 3 or any(measured[k] is None for k in keys):
        return None
    return all(abs(cuts[i] - measured[keys[i]]) <= 3.0 for i in range(4))


# ─── 4. Density ──────────────────────────────────────────────────────────────


@router.get("/density")
async def get_density(species: Optional[str] = None,
                      height_in: Optional[float] = None,
                      height: Optional[str] = None,
                      build_type: Optional[str] = None):
    """Baseline piece count and Sparse→Super-Full bands for a species at a height.

    The baseline is always `f(species, height)` and never a pooled global
    number: at an identical 7 feet an Areca Palm uses 1 stem and a Eucalyptus
    16, so a shared baseline would be wrong for both. Only the *spread* around
    the baseline is pooled, because most cells hold too few recipes to have a
    spread of their own — see `DENSITY_BANDS`.

    The answer degrades in named steps rather than pretending: exact
    species×height cell → the same species at the nearest recorded height →
    the species at any height → its structural class. `source`, `n` and
    `confidence` always say which one you got.
    """
    data = await corpus()
    resolved_height = height_in if height_in is not None else parse_length_in(height)
    if (height_in is not None or height) and resolved_height is None:
        raise HTTPException(status_code=400, detail=f"Could not read a height from {height!r}")

    requested = (species or "").strip() or None
    canonical = normalize_species(requested)
    known = data["species"].get(canonical) if canonical else None

    notes: list[str] = []
    if requested and not canonical:
        notes.append(f"{requested!r} is not in the recipe vocabulary — answering from the "
                     f"{_DEFAULT_CLASS} class.")
    klass = known["structural_class"] if known else _DEFAULT_CLASS
    class_basis = known["class_basis"] if known else "default"

    height_ft = round(resolved_height / 12) if resolved_height else None
    resolution = _resolve_density(data, canonical, klass, height_ft)
    notes.extend(resolution["notes"])

    applies = klass != "specimen"
    baseline = resolution["baseline"]
    bands = _density_bands(baseline, resolution["cell"], applies)

    if not applies:
        notes.append("Specimen species: ~1 stem, one large potted plant. Density barely "
                     "applies — don't prompt for it.")

    return {
        "requested_species": requested,
        "species": canonical,
        "structural_class": klass,
        "class_basis": class_basis,
        "density_applies": applies,
        "height_in": resolved_height,
        "height_ft": height_ft,
        "height_display": format_height(resolved_height),
        "build_type": (resolve_build_type(build_type) or {}).get("label"),
        "baseline_pieces": _round_pieces(baseline),
        "baseline_pieces_exact": round(baseline, 3) if baseline is not None else None,
        "n": resolution["n"],
        "observed_min": _round_pieces(resolution["min"]),
        "observed_max": _round_pieces(resolution["max"]),
        "observed_values": resolution["values"],
        "structural_baseline_pieces": _round_pieces(resolution["structural"]),
        "confidence": resolution["confidence"],
        "source": resolution["source"],
        "examples": resolution["examples"],
        "bands": bands,
        "default_band": "standard",
        "basis": {
            "metric": "product_lines",
            "definition": ("pieces summed across every `product` component line — the "
                           "metric the spec's seed baselines were measured with, so a "
                           "Dragonwood pole counts alongside a Fiddle branch"),
            "piece_field": data["piece_basis"]["primary"],
            "structural_metric": ("pieces on lines that classify as plant material only "
                                  "— the narrower 'stems' reading"),
        },
        "notes": notes,
        "provenance": _provenance(data),
    }


def _resolve_density(data: dict, species: Optional[str], klass: str,
                     height_ft: Optional[int]) -> dict[str, Any]:
    """Walk the fallback chain and report exactly which rung answered."""
    cells = data["density_cells"]
    notes: list[str] = []

    def _from_cell(cell: dict, source: str, scale: float = 1.0) -> dict[str, Any]:
        return {
            "baseline": cell["baseline"] * scale,
            "n": cell["n"],
            "min": cell["min"] * scale,
            "max": cell["max"] * scale,
            "values": cell["values"] if scale == 1.0 else None,
            "structural": cell.get("structural_baseline"),
            "examples": cell.get("examples", []),
            "confidence": _confidence(cell["n"], source),
            "source": source,
            "cell": cell if scale == 1.0 else None,
            "notes": notes,
        }

    if species and height_ft is not None:
        exact = cells.get(f"{species}|{height_ft}")
        if exact:
            return _from_cell(exact, "species_height")

    if species and height_ft is not None:
        # Nearest recorded height for this species, within 2 feet, scaled by the
        # height ratio. Beyond 2 feet the shape of the build has changed too much.
        candidates = []
        for key, cell in cells.items():
            name, _, ft = key.rpartition("|")
            if name != species:
                continue
            distance = abs(int(ft) - height_ft)
            if distance <= 2:
                candidates.append((distance, int(ft), cell))
        if candidates:
            candidates.sort(key=lambda c: (c[0], -c[2]["n"]))
            distance, ft, cell = candidates[0]
            scale = height_ft / ft if ft else 1.0
            notes.append(f"No {species} recipe at {height_ft}′; scaled from the "
                         f"{ft}′ cell (n={cell['n']}) by {scale:.2f}.")
            return _from_cell(cell, "species_nearby_height", scale)

    if species:
        pooled = [v for key, cell in cells.items()
                  if key.rpartition("|")[0] == species for v in cell["values"]]
        if pooled:
            notes.append(f"No {species} recipe near that height; pooled every recorded "
                         f"{species} build instead.")
            return {
                "baseline": statistics.median(pooled), "n": len(pooled),
                "min": min(pooled), "max": max(pooled), "values": sorted(pooled),
                "structural": None, "examples": [],
                "confidence": _confidence(len(pooled), "species_any_height"),
                "source": "species_any_height", "cell": None, "notes": notes,
            }

    if klass == "specimen":
        notes.append("Specimen fallback: one plant. No history for this species at any height.")
        return {"baseline": 1.0, "n": 0, "min": 1.0, "max": 1.0, "values": [],
                "structural": 1.0, "examples": [], "confidence": "none",
                "source": "class_fallback", "cell": None, "notes": notes}

    class_cell = (data["class_cells"].get(f"{klass}|{height_ft}") if height_ft is not None
                  else None) or data["class_cells"].get(klass)
    if class_cell:
        notes.append(f"No history for this species — fell back to the {klass} class "
                     f"(n={class_cell['n']}). This is a class average, not a baseline "
                     f"for this species. Every new build refines it.")
        return {"baseline": class_cell["baseline"], "n": 0, "min": class_cell["min"],
                "max": class_cell["max"], "values": [], "structural": None,
                "examples": [], "confidence": "none", "source": "class_fallback",
                "cell": None, "notes": notes}

    notes.append("No history at all for this species or class — no baseline invented.")
    return {"baseline": None, "n": 0, "min": None, "max": None, "values": [],
            "structural": None, "examples": [], "confidence": "none",
            "source": "no_data", "cell": None, "notes": notes}


def _confidence(n: int, source: str) -> str:
    """How much to trust the number. Most cells hold 1–5 recipes."""
    if source == "class_fallback" or n <= 0:
        return "none"
    if source != "species_height":
        return "low"
    if n >= 6:
        return "medium"
    if n >= 3:
        return "low"
    return "very_low"


def _density_bands(baseline: Optional[float], cell: Optional[dict],
                   applies: bool = True) -> list[dict[str, Any]]:
    """Sparse → Super-Full as piece counts around the baseline.

    A cell with 4+ recipes describes its own spread, so its bands come from its
    own percentiles; thinner cells borrow the corpus-wide spread shape.

    For a specimen species every band is the baseline: a 1-stem Areca Palm has
    no Super-Full, and manufacturing one would be the exact fabrication this
    module exists to avoid. `density_applies: false` is the real answer.
    """
    if baseline is None:
        return []
    own = cell and cell["n"] >= _OWN_SPREAD_MIN_N and cell.get("values")
    bands = []
    for i, band in enumerate(DENSITY_BANDS):
        if not applies:
            value, basis = baseline, "specimen_flat"
        elif own:
            value = _percentile(list(cell["values"]), DENSITY_BAND_PERCENTILES[i])
            basis = "observed_percentile"
        else:
            value = baseline * band["multiplier"]
            basis = "pooled_spread"
        bands.append({
            "key": band["key"],
            "label": band["label"],
            "pieces": _round_pieces(value),
            "multiplier": round(value / baseline, 3) if baseline else None,
            "percentile": band["percentile"],
            "basis": basis,
        })
    if not applies:
        return bands
    # Percentiles of a tiny sample can tie, and rounding can flatten the low end.
    # Anchor Standard on the baseline itself and keep the rungs above it strictly
    # apart, so the four bands stay four distinct choices in the UI.
    standard = _round_pieces(baseline) or 0
    bands[0]["pieces"] = min(bands[0]["pieces"] or 0, standard)
    bands[1]["pieces"] = standard
    for i in (2, 3):
        bands[i]["pieces"] = max(bands[i]["pieces"] or 0, (bands[i - 1]["pieces"] or 0) + 1)
    return bands


# ─── 5. Common builds ────────────────────────────────────────────────────────


@router.get("/common-builds")
async def get_common_builds(build_type: Optional[str] = None,
                            species: Optional[str] = None,
                            limit: int = 25):
    """"Builds we make often" — recurring signatures, ready to pre-fill Step 1.

    A signature is build type × species × whole foot of height, ordered by how
    many recipes recur inside it. Every field the builder's Step 1 asks for is
    filled: height, width/canopy tier, depth, piece count and typical cost.

    Junk is excluded rather than ranked low, on derived rules, not an id list:
    a recipe with no build type (6 blank sheets), one that priced to nothing
    (TT9-9522 "Bay Leaf Topiary" is a single valueless line), or one with no
    recorded height cannot pre-fill anything.
    """
    data = await corpus()
    resolved_type = resolve_build_type(build_type)
    if build_type and not resolved_type:
        raise HTTPException(status_code=400, detail=f"Unknown build_type: {build_type}")
    canonical = normalize_species(species)
    if species and not canonical:
        raise HTTPException(status_code=400, detail=f"Unknown species: {species}")

    aliases = {a.lower() for a in resolved_type["aliases"]} if resolved_type else None
    items = [b for b in data["common_builds"]
             if (aliases is None or (b["build_type"] or "").lower() in aliases)
             and (canonical is None or b["species"] == canonical)]

    total = len(items)
    safe_limit = max(1, min(int(limit if limit is not None else 25), 100))
    excluded = sum(1 for r in data["recipes"] if not r["usable"] or not r["height_in"])
    return {
        "builds": items[:safe_limit],
        "total": total,
        "limit": safe_limit,
        "build_type": resolved_type["label"] if resolved_type else None,
        "species": canonical,
        "excluded_recipes": excluded,
        "exclusion_rules": [
            "no build_type (blank sheets)",
            "no priced components (parsed but valueless sheets)",
            "no recorded height (cannot pre-fill Step 1)",
        ],
        "provenance": _provenance(data),
    }


# ─── 6. Scope filters ────────────────────────────────────────────────────────


@router.get("/scope-filters")
async def get_scope_filters(slot: Optional[str] = None, build_type: Optional[str] = None):
    """Smart-filter defaults for a Choose-Parts scope slot.

    Returned as **suggestions with weights, never mandates**: the UI pre-applies
    them and the designer must be able to take any of them off. `filters` holds
    values that work as-is against `/api/products/search` (`categories`,
    `colors`, `product_types` — real `category_group` / `color_families` /
    `type_family` values), and `search_terms` are the phrases the shop's own
    recipes actually used for that slot, ranked by how many recipes used them.

    `exclude_categories` is the other half of the contract: picking Container
    has to surface containers first and never dried botanicals.

    Pass a `slot` — either a canonical scope (`container`, `top_dressing`,
    `plant_material`, `trunks`, `accent`) or a build type's own slot label
    ("Finish/Top Dressing") — or omit it for every scope.
    """
    data = await corpus()
    resolved_type = resolve_build_type(build_type)
    if build_type and not resolved_type:
        raise HTTPException(status_code=400, detail=f"Unknown build_type: {build_type}")

    wanted = _resolve_slot(slot)
    if slot and wanted is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown slot: {slot}. Known scopes: {sorted(SLOT_CLASSES)}",
        )

    scopes = [wanted] if wanted else [s for s in SLOT_CLASSES]
    if resolved_type and not wanted:
        allowed = {scope for _label, scope in resolved_type["slots"]}
        scopes = [s for s in scopes if s in allowed]

    items = [_scope_payload(data, scope, resolved_type) for scope in scopes]
    return {
        "slots": items,
        "build_type": resolved_type["label"] if resolved_type else None,
        "contract": {
            "mandatory": False,
            "removable": True,
            "note": ("Pre-apply these, then let the designer remove any of them. "
                     "Weights are 0–1, normalised within each list."),
        },
        "searchable_via": "/api/products/search",
        "provenance": _provenance(data),
    }


_SLOT_LABEL_INDEX: dict[str, str] = {}
for _bt in BUILD_TYPES:
    for _label, _scope in _bt["slots"]:
        _SLOT_LABEL_INDEX[_label.strip().lower()] = _scope
for _scope, _label in SLOT_CLASSES.items():
    _SLOT_LABEL_INDEX[_label.strip().lower()] = _scope


def _resolve_slot(value: Optional[str]) -> Optional[str]:
    """`"Finish/Top Dressing"` / `"top_dressing"` / `"Container"` → a scope key."""
    if not value or not str(value).strip():
        return None
    text = str(value).strip()
    if text in SLOT_CLASSES:
        return text
    key = text.lower().replace(" ", "_").replace("-", "_").replace("/", "_")
    if key in SLOT_CLASSES:
        return key
    return _SLOT_LABEL_INDEX.get(text.lower())


# Best-effort catalog verification of the derived terms. `/api/products/search`
# ANDs a query's words, so a phrase the shop writes ("soda woodpoles") can be
# real vocabulary and still match nothing in the catalog. Those terms are
# demoted, never dropped — the shop's own words stay visible.
#
# It reuses the in-memory index `app.apis.products` has already built rather
# than querying: pulling name+description for 95k rows costs ~11s and 27 MB, and
# duplicating that here would make every cold builder request pay for it. When
# that index is cold the verdict is simply unknown (`None`), which is the honest
# answer and costs nothing.
_TERM_VERDICT: dict[str, Any] = {"products_ts": None, "verified": {}}


def _catalog_index() -> Optional[list]:
    """The product search index if it happens to be warm, else `None`."""
    try:
        from app.apis import products as _products
        return _products._SEARCH_CACHE.get("rows") or None
    except Exception:
        return None


def _catalog_index_stamp() -> Any:
    """When that index was built — the verdict cache's invalidation key."""
    try:
        from app.apis import products as _products
        return _products._SEARCH_CACHE.get("ts")
    except Exception:
        return None


def _term_verdicts(terms: set[str]) -> Optional[dict[str, bool]]:
    """`{term: matches_the_catalog}` — or `None` if the catalog index is cold."""
    index = _catalog_index()
    if not index:
        return None
    ts = _catalog_index_stamp()
    if _TERM_VERDICT["products_ts"] != ts:
        _TERM_VERDICT.update(products_ts=ts, verified={})
    cache = _TERM_VERDICT["verified"]
    for term in terms:
        if term in cache:
            continue
        words = term.split()
        # Early exit on the first hit: a common term costs almost nothing, and
        # only a genuinely dead one pays for a full pass.
        cache[term] = any(all(w in row["blob"] for w in words) for row in index)
    return {term: cache[term] for term in terms}


def _scope_payload(data: dict, scope: str,
                   build_type: Optional[dict]) -> dict[str, Any]:
    catalog = _SLOT_CATALOG.get(scope, _SLOT_CATALOG["other"])
    terms = [dict(t) for t in data["slot_vocab"].get(scope, [])]
    verdicts = _term_verdicts({t["term"] for t in terms})
    for entry in terms:
        entry["catalog_verified"] = None if verdicts is None else verdicts[entry["term"]]
    if verdicts is not None:
        # Verified terms first, then by weight — so a pre-applied filter always
        # returns products, while the unmatched vocabulary stays inspectable.
        terms.sort(key=lambda t: (not t["catalog_verified"], -t["recipes"], t["term"]))

    def _weighted(values: list[str]) -> list[dict[str, Any]]:
        # Ordered best-first; the weight is the position, so the UI can show a
        # confident first pick without treating the tail as equally good.
        return [{"value": v, "weight": round(1.0 - (i * 0.15), 3), "source": "mapping"}
                for i, v in enumerate(values)]

    labels = []
    for spec in BUILD_TYPES:
        for label, slot_scope in spec["slots"]:
            if slot_scope == scope and (build_type is None or spec is build_type):
                labels.append({"build_type": spec["label"], "slot_label": label})

    payload = {
        "slot": scope,
        "label": SLOT_CLASSES.get(scope, scope),
        "used_as": labels,
        "filters": {
            "categories": _weighted(catalog["categories"]),
            "product_types": _weighted(catalog["product_types"]),
            "colors": _weighted(catalog["colors"]),
        },
        "exclude_categories": catalog["exclude_categories"],
        "search_terms": terms,
        "recipe_lines": sum(1 for r in data["recipes"] if scope in r["slots"]),
        "derivation": {
            "search_terms": "recurring 1–3-word phrases in this slot's recipe lines, "
                            "counted by distinct recipes",
            "categories": "hardcoded slot→catalog bridge (the corpus records vendor SKUs "
                          "and free text, never a catalog category)",
            "catalog_verified": ("true/false when the product index is warm — whether the "
                                 "term matches any catalog product. null means the index "
                                 "was cold and the term is unchecked, not bad."),
        },
    }
    if scope == "container":
        payload["ordering_note"] = ("Containers first, never dried botanicals — see "
                                    "`exclude_categories`.")
    return payload


# ─── Diagnostics ─────────────────────────────────────────────────────────────


@router.get("/health")
async def get_health():
    """What the cache is holding and which piece basis it measured with."""
    data = await corpus()
    return {
        "cached": _cache_fresh(),
        "cache_age_s": round(time.time() - _CACHE["ts"], 1),
        "ttl_s": _TTL,
        "recipes": data["recipe_count"],
        "components": data["component_count"],
        "piece_basis": data["piece_basis"],
        "density_cells": len(data["density_cells"]),
        "common_builds": len(data["common_builds"]),
        "species_with_history": sum(1 for s in data["species"].values()
                                    if s["recipe_count"] > 0),
    }
