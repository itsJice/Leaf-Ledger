// Constants for the product library: category/unit vocabularies, colour
// decoding tables, cache keys, and category/pill colour maps.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { LIBRARY_CACHE_KEY } from "../../constants";

export const CATEGORIES = ["containers", "wood", "greenery", "florals", "trees"];
export const UNITS = ["stem", "pot", "flat", "bunch", "each"];
export const INITIAL_CARD_RENDER_LIMIT = 48;
export const KNOWN_COLOR_WORDS = [
  "aqua", "beige", "black", "blue", "blush", "bronze", "brown", "burgundy", "camel",
  "charcoal", "cinnamon", "clear", "coffee", "copper", "coral", "cream", "crimson",
  "delphinium", "flame", "gold", "gray", "green", "honey", "indigo", "iridescent",
  "ivory", "lavender", "lilac", "lime", "mauve", "mint", "moss", "mustard", "olive",
  "orange", "orchid", "peach", "peacock", "pearl", "pink", "platinum", "purple",
  "red", "rose", "royal", "rubrum", "salmon", "seafoam", "silver", "smoke", "tan",
  "taupe", "teal", "tomato", "turquoise", "violet", "white", "yellow",
];
export const ALLSTATE_COLOR_CODE_MAP: Record<string, string[]> = {
  AQ: ["Aqua"],
  BE: ["Beige"],
  BK: ["Black"],
  BL: ["Blue"],
  BR: ["Brown"],
  BU: ["Blue"],
  CL: ["Clear"],
  CP: ["Copper"],
  CR: ["Cream"],
  CW: ["Clear", "White"],
  FS: ["Frost", "Silver"],
  GO: ["Gold"],
  GR: ["Green"],
  GY: ["Gray"],
  IV: ["Ivory"],
  LV: ["Lavender"],
  MO: ["Moss"],
  MX: ["Mixed"],
  OR: ["Orange"],
  PE: ["Pearl"],
  PK: ["Pink"],
  PU: ["Purple"],
  RE: ["Red"],
  RO: ["Rose"],
  SI: ["Silver"],
  TA: ["Tan"],
  TE: ["Teal"],
  WH: ["White"],
  YL: ["Yellow"],
};
export const AVAILABILITY_FILTERS = [
  "Available today",
  "Within 1-4 months",
  "Over 4 months",
  "Sold out / unavailable",
  "Future ETA",
] as const;

// Re-exported for callers that historically imported this from the Library page.
export { LIBRARY_CACHE_KEY };
export const LIBRARY_METADATA_CACHE_KEY = "leaf-ledger:library-filter-metadata:v1";
export const LIBRARY_CACHE_RAW_KEYS = [
  "Description",
  "ColorGrp",
  "Season",
  "Class",
  "Material Breakdown",
  "Country of Origin",
  "Avail. Qty",
  "Avail. Qty: *",
  "ProdLength",
  "ProdWeight",
  "BoxWeight",
  "CsWeight",
  "Box LxWxH",
  "Case LxWxH",
  "CaseCube",
  "Oversize",
  "SugRetail",
  "UPC",
  "MinQty",
  "BoxQty",
  "CaseQty",
  "CatalogVol",
  "CatPage",
  "P-CatVol",
  "P-CatPage",
  "allstate_subcategory",
  "Item No",
  "detail_status",
  "image_status",
];
export const PRODUCT_TYPE_RULES: Array<{ label: string; keywords: string[] }> = [
  { label: "Ribbon", keywords: [" ribbon ", " trim ", " bow "] },
  { label: "Spray", keywords: [" spray "] },
  { label: "Pick", keywords: [" pick "] },
  { label: "Ornament", keywords: [" ornament ", " finial ", " topper "] },
  { label: "Wreath", keywords: [" wreath "] },
  { label: "Garland", keywords: [" garland "] },
  { label: "Tree", keywords: [" tree "] },
  { label: "Stem", keywords: [" stem "] },
  { label: "Bush", keywords: [" bush "] },
  { label: "Bundle", keywords: [" bundle "] },
  { label: "Floral", keywords: [" floral ", " flower ", " bloom "] },
  { label: "Container", keywords: [" vase ", " pot ", " planter ", " container ", " bowl ", " urn "] },
];

// ─── Category colour dots ─────────────────────────────────────────────────────
// Identity colours, not theme colours — a category keeps its hue in both modes.
// They resolve through `--cat-*` in index.css only so the dark theme can lift
// them off a near-black page; the light values are the originals unchanged.
export const CATEGORY_COLORS: Record<string, string> = {
  // rich display categories (from category_group)
  "Florals": "rgb(var(--cat-florals))",
  "Greenery & Plants": "rgb(var(--cat-greenery))",
  "Trees": "rgb(var(--cat-trees))",
  "Wreaths & Garland": "rgb(var(--cat-wreaths))",
  "Ornaments": "rgb(var(--cat-ornaments))",
  "Ribbon & Bows": "rgb(var(--cat-ribbon))",
  "Botanicals & Fillers": "rgb(var(--cat-botanicals))",
  "Lighting": "rgb(var(--cat-lighting))",
  "Candles & Lanterns": "rgb(var(--cat-candles))",
  "Containers & Vases": "rgb(var(--cat-containers))",
  "Home Décor": "rgb(var(--cat-decor))",
  "Rugs & Textiles": "rgb(var(--cat-textiles))",
  "Furniture & Storage": "rgb(var(--cat-furniture))",
  "Rocks & Stone": "rgb(var(--cat-stone))",
  // legacy slugs (manual products). `containers` has always shared the
  // botanicals ochre rather than the "Containers & Vases" rust.
  containers: "rgb(var(--cat-botanicals))",
  wood: "rgb(var(--cat-wood))",
  greenery: "rgb(var(--cat-greenery))",
  florals: "rgb(var(--cat-florals))",
  trees: "rgb(var(--cat-trees))",
};

// ─── Stale price check ───────────────────────────────────────────────────────
export const STALE_DAYS = 30;

// Keys already surfaced elsewhere in the modal or that are internal plumbing —
// excluded from the catch-all "All Captured Attributes" list.
export const RAW_ATTRS_HIDE = new Set([
  "image_urls", "source_photo_url", "needs_review_flag", "additional_image_urls",
  "gallery_images_json", "image_count", "source_photo_url",
]);
