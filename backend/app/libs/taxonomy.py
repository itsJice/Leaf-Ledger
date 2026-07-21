"""Filter taxonomies: map noisy supplier values (colors, product types) to a
small set of clean, human-logical families for the Product Library dropdowns.

The dropdowns show families (e.g. "Green" covers olive/chartreuse/sage/GR).
Free-text search is deliberately NOT touched — it still matches the raw values,
so a designer can still search "chartreuse" or "olive" individually.
"""
from __future__ import annotations

import re
from typing import Optional

# ── Colors ────────────────────────────────────────────────────────────────────

# supplier 2-letter color codes (exact match)
_COLOR_CODES = {
    "gr": "Green", "wh": "White", "re": "Red", "bl": "Blue", "pk": "Pink",
    "br": "Brown", "bk": "Black", "go": "Gold", "ye": "Yellow", "cr": "Cream/Ivory",
    "si": "Silver", "be": "Beige/Natural", "or": "Orange", "pu": "Purple",
    "gy": "Gray", "mx": "Multi-color", "tt": "Multi-color", "na": "Beige/Natural",
    "bu": "Burgundy", "te": "Blue", "la": "Purple",
}

_MULTI_KEYWORDS = ["multi", "assorted", "rainbow", "variegated", "two-tone", "two tone", "color changing", "ombre", "harlequin"]

# (family, keywords) in priority order — first substring hit wins
_COLOR_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Multi-color", _MULTI_KEYWORDS),
    ("Green", ["green", "olive", "chartreuse", "sage", "moss", "fern", "forest", "emerald", "mint", "lime", "hunter", "kelly", "celadon", "avocado", "pistachio"]),
    ("White", ["white", "snow", "eggshell", "pearl", "frost"]),
    ("Cream/Ivory", ["cream", "ivory", "ecru", "bone", "vanilla", "almond"]),
    ("Burgundy", ["burgundy", "wine", "maroon", "merlot", "cranberry", "oxblood"]),
    ("Red", ["red", "crimson", "scarlet", "cardinal", "cherry", "ruby"]),
    ("Pink", ["pink", "blush", "fuchsia", "magenta", "rose"]),
    ("Coral/Peach", ["coral", "peach", "salmon", "apricot"]),
    ("Orange", ["orange", "rust", "terracotta", "terra cotta", "pumpkin", "tangerine", "amber"]),
    ("Yellow", ["yellow", "mustard", "lemon", "goldenrod"]),
    ("Gold", ["gold", "champagne"]),
    ("Blue", ["blue", "navy", "teal", "turquoise", "aqua", "cobalt", "denim", "sky", "indigo", "periwinkle", "cerulean"]),
    ("Purple", ["purple", "lavender", "lilac", "plum", "violet", "eggplant", "mauve", "orchid", "amethyst", "grape"]),
    ("Brown", ["brown", "chocolate", "coffee", "espresso", "mocha", "walnut", "chestnut", "cocoa", "hazelnut", "tobacco"]),
    ("Beige/Natural", ["beige", "natural", "khaki", "sand", "wheat", "camel", "taupe", "straw", "nude", "kraft", "burlap", "linen", "tan"]),
    ("Silver", ["silver", "platinum", "chrome", "nickel", "metallic"]),
    ("Gray", ["gray", "grey", "charcoal", "slate", "ash", "smoke", "graphite", "pewter"]),
    ("Black", ["black", "onyx", "ebony", "jet"]),
    ("Bronze/Copper", ["bronze", "copper", "brass"]),
    ("Clear", ["clear", "glass", "transparent", "crystal", "translucent"]),
]


def _color_from_keywords(text: str) -> Optional[str]:
    for family, keywords in _COLOR_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return family
    token = text.strip()
    if token in _COLOR_CODES:
        return _COLOR_CODES[token]
    return None


def color_families(value: Optional[str]) -> list[str]:
    """Every color family a value belongs to. A combo lists each specific color
    AND 'Multi-color' — e.g. 'RED/GREEN' -> ['Red', 'Green', 'Multi-color'] — so
    a two-tone item shows up under each of its colors and under Multi-color."""
    if not value:
        return []
    text = str(value).strip().lower()
    if not text:
        return []
    if text in _COLOR_CODES:
        return [_COLOR_CODES[text]]

    families: list[str] = []

    def add(fam: Optional[str]) -> None:
        if fam and fam not in families:
            families.append(fam)

    has_multi_kw = any(kw in text for kw in _MULTI_KEYWORDS)

    # decompose combos on separators (RED/GREEN, GR/BR, red & green)
    specific: list[str] = []
    if re.search(r"[/,&+]", text):
        for part in re.split(r"[/,&+]+", text):
            fam = _color_from_keywords(part.strip())
            if fam and fam != "Multi-color":
                specific.append(fam)

    if specific:
        for fam in specific:
            add(fam)
        if len(set(specific)) >= 2 or has_multi_kw:
            add("Multi-color")
        return families

    if has_multi_kw:
        return ["Multi-color"]
    whole = _color_from_keywords(text)
    return [whole] if whole else ["Other"]


def color_family(value: Optional[str]) -> Optional[str]:
    """Primary (first) color family — for display only."""
    families = color_families(value)
    return families[0] if families else None


# ── Product types ─────────────────────────────────────────────────────────────

# (family, keywords) priority order — more specific families first
_TYPE_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Lighting", ["light set", "led", "bulb", "stringer", "socket", "starburst", "motif", "light sphere", "coaxial", "lamp", "prelit", "pre-lit"]),
    ("Ornament", ["ornament"]),
    ("Wreath", ["wreath"]),
    ("Garland", ["garland"]),
    ("Tree", ["tree", "topiary"]),
    ("Ribbon & Bows", ["ribbon", "bow"]),
    ("Berries & Pods", ["berry", "berries", "pod", "pinecone", "pine cone", "cone"]),
    ("Spray & Picks", ["spray", "pick"]),
    ("Floral Stems", ["stem", "floral", "flower", "poinsettia", "rose", "peony", "hydrangea", "bloom"]),
    ("Greenery & Foliage", ["greenery", "bush", "grass", "foliage", "succulent", "palm", "fern", "ivy", "botanical", "moss", "boxwood", "leaf", "branch"]),
    ("Container & Base", ["container", "vase", "pot ", "planter", "urn", "base", "stand"]),
    ("Decor & Figurines", ["figurine", "sign", "candle", "lantern", "stocking", "skirt", "pillow", "snowman", "santa", "nativity", "decor", "wood", "teardrop"]),
]


def product_type_family(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    text = str(value).strip().lower()
    if not text or text == "physical":  # generic placeholder, not a real type
        return None
    for family, keywords in _TYPE_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                return family
    return "Other"


# ── Categories ────────────────────────────────────────────────────────────────
# Every product gets a real category (no "Other"). Grouped by what the item IS,
# using source category + subcategory + listed_under + product type + name.
# Priority order matters — first keyword hit wins.
_CATEGORY_KEYWORDS: list[tuple[str, list[str]]] = [
    ("Ornaments", ["ornament", "bauble", "finial drop", "tree topper", "topper"]),
    ("Trees", ["christmas tree", "artificial tree", "alpine tree", "pencil tree", "tabletop tree", "potted tree", "spiral tree", "cedar tree", "pine tree"]),
    ("Wreaths & Garland", ["wreath", "garland", "swag", "roping"]),
    ("Ribbon & Bows", ["ribbon", "bow ", " bow", "mesh roll", "deco mesh"]),
    ("Lighting", ["light set", "led", "string light", "fairy light", "lamp", "bulb", "lumin", "sconce", "chandelier", "novelty light", "starburst", "light sphere", "motif light"]),
    ("Candles & Lanterns", ["candle", "votive", "tealight", "tea light", "lantern", "luminary", "flameless"]),
    ("Botanicals & Fillers", ["dried", "preserved", "moss", "berry", "berries", "pod", "pinecone", "pine cone", " cone", "branch", "twig", "filler", "botanical", "reindeer", "cotton", "wheat", "seedpod", "acorn", "nut", "bark", "curly willow", "grapevine"]),
    ("Florals", ["floral", "flower", "rose", "peony", "hydrangea", "poinsettia", "orchid", "tulip", "dahlia", "sunflower", "lily", "magnolia", "ranunculus", "bloom", "bouquet", "spray", "pick", "stem", "blossom", "petal", "silk flower"]),
    ("Greenery & Plants", ["greenery", "foliage", "fern", "grass", "ivy", "succulent", "palm", "boxwood", "eucalyptus", "cactus", "cacti", "leaf", "leaves", "bush", "shrub", "vine", "topiary", "air plant", "plant", "hosta", "philo", "monstera", "cedar", "pine ", "cypress", "juniper"]),
    ("Rugs & Textiles", ["rug", "pillow", "cushion", "throw", "blanket", "bedding", "duvet", "sheet set", "curtain", "drape", "tapestry", "textile", "towel", "runner"]),
    ("Rocks & Stone", ["rock", "stone", "gravel", "pebble", "agate", "geode", "boulder", "aggregate", "marble chip", "river rock"]),
    ("Containers & Vases", ["container", "vase", " pot", "pots", "planter", "urn", "jardiniere", "jar", "canister", "compote", "trough", "bucket", "pail", "bin", "basket", "crock", "cachepot", "cache pot", "tin"]),
    ("Furniture & Storage", ["furniture", "table", "chair", "stool", "bench", "shelf", "shelving", "cabinet", "trellis", "storage", "organizer", "organization", "rack", "hook", "desk", "dresser", "ottoman", "console", "plant stand", "easel"]),
    ("Home Décor", ["sculpture", "figurine", "statue", "mirror", "wall art", "wall d", "frame", "sign", "decor", "decorative", "clock", "bookend", "book", "box", "trunk", "orb", "sphere", "bowl", "plate", "tray", "platter", "dish", "charger", "pedestal", "riser", "candlestick", "candle holder", "vessel", "gift", "napkin", "coaster", "placemat", "figure", "ornamental", "accent"]),
]


def category_family(*signals: Optional[str]) -> str:
    """Assign one real category from any available text signals (source category,
    subcategory, listed_under, product type, product name). Never returns 'Other'
    — a genuinely unmatched item falls back to 'Home Décor'."""
    text = " ".join(str(s) for s in signals if s).lower()
    if not text.strip():
        return "Home Décor"
    for family, keywords in _CATEGORY_KEYWORDS:
        for keyword in keywords:
            if keyword in text:
                # guard: tree accessories are not trees
                if family == "Trees" and any(a in text for a in ("skirt", "collar", "stand", "storage bag")):
                    continue
                return family
    return "Home Décor"
