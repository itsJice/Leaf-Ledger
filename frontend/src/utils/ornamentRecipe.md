# Ornament Calculator — Rules Reference

Exact rules behind the in-app Ornament Calculator (`pages/OrnamentCalculator.tsx`),
reverse-engineered from Vickerman's public tool and reproduced verbatim in
[`ornamentRecipe.ts`](./ornamentRecipe.ts). This file is the human-readable spec;
the `.ts` module is the executable source of truth — keep them in sync.

**Verified against the live site:** 7.5 ft × 55 in → `3"×42, 4"×41, 4.75"×21, 6"×10`,
surface area 4,929 sq in, density 40%. SKU output verified against our own scraped
catalog (e.g. `N590603DMV` = "2.4" Red Matte Ball UV").

> Source pages: `vickerman.com/ornamentcalculator` (step 1) and
> `vickerman.com/Tools/OrnamentRecipe` (step 2). Both are fully client-side (Vue).

---

## Step 1 — Calculator

### 1. Tree surface area (cone model)

```
radius (in)  = (width_in − 20) / 2
height (in)  = (height_ft × 12) − 20        // both must be > 0, else no recipe
slant        = √(height² + radius²)
surfaceArea  = π·radius²  +  π·radius·slant  // cone base + lateral side
```

A tree needs **width > 20 in** and **height > 1.667 ft** (20 in) or it's "too small".

### 2. Coverage target

The recipe always fills to **40% coverage**:

```
recipeCoverage = surfaceArea × 0.40
```

### 3. Size family — by coverage bucket

The four ornament sizes used are chosen by which bucket `recipeCoverage` lands in:

| Recipe coverage (sq in) | Sizes (smallest → largest) |
| ----------------------- | -------------------------- |
| under 1,000             | 2.4", 3", 4", 4.75"        |
| 1,000 – 4,999           | 3", 4", 4.75", 6"          |
| 5,000 – 8,999           | 4", 4.75", 6", 8"          |
| 9,000 – 12,999          | 4.75", 6", 8", 10"         |
| 13,000 – 17,999         | 6", 8", 10", 12"           |
| 18,000 – 24,999         | 8", 10", 12", 15.75"       |
| 25,000 +                | 10", 12", 15.75", 20"      |

Sizes **2.75"** and **24"** exist as manual inputs but are **never auto-selected**.

### 4. Coverage split across the four sizes

Fixed split, smallest → largest: **20% / 35% / 25% / 20%**.

### 5. Quantity per size

```
planarArea(size) = π·(size/2)²                       // flat area of one ornament
quantity         = round( sizeCoverage / planarArea × 0.75 )
```

### 6. Live density (any set of quantities)

Recomputed on every edit to quantities, height, or width:

```
totalOrnamentArea = Σ  π·(size/2)² × qty
density %         = min(100, round( totalOrnamentArea / surfaceArea / 0.75 × 100 ))
```

### 7. Tree image (visual representation)

The tree photo reflects the live density, snapped down to the nearest 5%, capped at 90:

```
step  = min(90, floor(density / 5) × 5)              // 0,5,10,…,90
image = /ornament-calculator/tree_density_{step}.jpg
```

19 images (0–90) live in `public/ornament-calculator/`, copied from Vickerman's CDN
so the app is self-contained.

### 8. Pack summary ("To Order")

```
qtyPerPack === 1 → "{qty} each"
else             → "{ceil(qty / qtyPerPack)} packs of {qtyPerPack}"
```

### Ornament size table

Sizes come from the **N59 single-color ball line**. The 12 core sizes are from
Vickerman's page model; **1" and 1.6"** were added from our scraped catalog
(`catalog-extraction/outputs/vickerman-full`) — real N59 ball sizes missing from
Vickerman's public tool. Sizes **5", 5.5", 14"** exist in the wider catalog but have
no N59 size code, so they're excluded (can't form valid SKUs). **20"/24"** have no
N59 ball products but stay because the recipe's top bucket uses 20".

| Size (in) | Size code | Qty / pack | Planar area (sq in) | Auto-used? |
| --------- | --------- | ---------- | ------------------- | ---------- |
| 1         | 03        | 18         | 0.785               | no         |
| 1.6       | 54        | 96         | 2.011               | no         |
| 2.4       | 06        | 24         | 4.524               | yes        |
| 2.75      | 07        | 12         | 5.940               | no         |
| 3         | 08        | 12         | 7.069               | yes        |
| 4         | 10        | 6          | 12.566              | yes        |
| 4.75      | 12        | 4          | 17.721              | yes        |
| 6         | 15        | 4          | 28.274              | yes        |
| 8         | 20        | 1          | 50.265              | yes        |
| 10        | 25        | 1          | 78.540              | yes        |
| 12        | 30        | 1          | 113.097             | yes        |
| 15.75     | 40        | 1          | 194.828             | yes        |
| 20        | 45        | 1          | 314.159             | yes        |
| 24        | 46        | 1          | 452.389             | no         |

---

## Step 2 — Select Colors

Splits the per-size quantities across one or more **color blocks**, each with a
color, a share of the tree (%), and one or more **finishes** (each with its own %).

### Quantity per line item

```
qty = round( sizeQty × (colorPct / 100) × (finishPct / 100) )   // dropped if 0
packsNeeded = ceil( qty / qtyPerPack )
```

If more than one color block is used, their shares should total 100% (a warning
shows otherwise). Finish % defaults to 50.

### SKU rules

```
Clear   (X):            N59{sizeCode}{colorCode}V
Sequin  (Q) / Glitter(G): N59{sizeCode}{colorCode}D{finishCode}
everything else:        N59{sizeCode}{colorCode}D{finishCode}V
```

Example: 3" (08) · Red (03) · Shiny (S) → `N590803DSV`.

### Finishes

| Finish | Code |
| ------ | ---- |
| Candy   | C |
| Glitter | G |
| Matte   | M |
| Pearl   | P |
| Shiny   | S |
| Clear   | X |
| Sequin  | Q |

### Colors

58 colors, name + 2-digit code (full list in `COLORS` in `ornamentRecipe.ts`).
Swatch hex values in the module are our own UI approximations — Vickerman ships
names/codes only.

### Outputs

- **Copy** — tab-separated `Item Number` / `Packs Needed`
- **Export CSV** — `ItemNumber,Quantity` → `Ornament_Order_{YYYY-MM-DD}.csv`
- **Share link** — encodes per-size quantities as `?{sizeCode}={qty}` params

### Catalog matcher (all suppliers + future uploads)

Composable SKUs only work for Vickerman — no other supplier encodes size/color/
finish into the part number, and you can't pre-write a formula for a supplier you
haven't onboarded. So alongside the Vickerman generator, Step 2 also calls a
catalog matcher that returns **real orderable products across every supplier**:

- **Endpoint:** `POST /api/products/ornament-match` (backend `app/apis/products`).
  Body: `{ lines: [{ size, quantity, color? }], suppliers?: string[], per_line? }`.
  Returns real products per line: supplier, `supplier_sku`, price, image, size,
  packs — ranked by size closeness then color match.
- **How it generalizes:** matches by **size + color**, not by SKU. Sizes come from
  the `diameter_in`/`width_in`/`height_in` columns or are parsed from the product
  name (mm/cm → inches). The ball-ornament index is cached in-process with a short
  TTL, so newly-uploaded catalogs appear automatically — no per-supplier code.
- Frontend renders these as product cards (image via `/api/products/image-proxy`),
  with a "Vickerman only" filter. The Order panel still shows Vickerman's original
  composable SKUs unchanged.

### Product images (not from SKU)

The Vickerman image CDN filenames are **inconsistent** (some use the color name,
e.g. `N59Red03DMV_1000.jpg`; others the code), so a product photo can't be derived
from the SKU reliably. Real photos + prices live in our Product Library — matching a
generated SKU there is the intended integration (the page shows color swatches for
now).

---

## Leaf & Ledger recipe mode (our design team's rules)

Selectable on the calculator next to the Vickerman rules (`buildLeafLedgerRecipe` /
`buildRecipeFor` in `ornamentRecipe.ts`). Vickerman's surface area, density meter,
quantity rounding and tree images are unchanged; what differs is where the quantities
come from. Full reasoning: `Vickerman Ornament Rules/designer-recipe-plan.md`.

### Source of truth: the golden table

The recipes the designers signed off on 2026-09-03, at the default widths (height x 6.5):

| Tree | 3" | 4" | 4.75" | 6" | 8" | 10" | 12" | Pieces |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 7.5 ft x 49 in | 25 | 12 | 16 | 16 | 8 | – | – | 77 |
| 8 ft x 52 in | – | 25 | 30 | 20 | 10 | 8 | – | 93 |
| 10 ft x 65 in | – | 36 | 36 | 30 | 20 | 12 | – | 134 |
| 12 ft x 78 in | – | – | 40 | 30 | 17 | 15 | 10 | 112 |

An exact row at its table width and the default slider position is returned **verbatim**.

### Everything else

- **Between rows** (e.g. 9 ft): interpolate each size linearly between the neighbouring
  rows, then apply the rules below.
- **Beyond the table** (< 7.5 ft or > 12 ft): top-heavy formula on Vickerman's surface
  area — 5 sizes stepping down from the top size, coverage shares 25/25/20/17/13 from the
  largest down, at 44% coverage (the 12 ft row's density).
- **Different width**: scale the row by surface-area ratio against the table width.
- **Coverage slider**: 40 = the recipe as approved; other positions scale it linearly.

### Designer rules applied to every derived recipe

1. **Top size** = height in feet as inches, rounded up to a stocked size — except a tree
   of 8 ft or more never tops out at 8" (8 ft -> 10").
2. **At least 8 of the top size.** It is the design, never an accent.
3. **Quantities in multiples of the color count** — even by default (two-color designs);
   see Modifiers below.
4. **Size floor by height:** 3" only up to 7.5 ft; 4" only up to 10 ft.

Why: big trees have big gaps and small ornaments disappear into them; the top two
sizes carry about half of all ornament area in every approved recipe (Vickerman's split
is the reverse). Coverage is *not* what the designers steer by — the approved rows run
from 44% to 72% by Vickerman's meter.

Derived examples at default widths: 9 ft -> `4"x30, 4.75"x34, 6"x26, 8"x16, 10"x10` (116);
15 ft -> `6"x38, 8"x28, 10"x20, 12"x18, 15.75"x10` (114).

### Modifiers

Three modifiers sit on top of the table (designer rules 4, 6, 7). Leaf & Ledger mode
only — the calculator hides them under the Vickerman rules. `buildLeafLedgerRecipe` /
`buildRecipeFor` take them as `options: { style?, colorCount? }`; the width profile is a
width, so it goes in as `widthIn`.

**Width profile** (`WIDTH_PROFILES`, `widthForProfile`, `profileForWidth`) — inches of
width per foot of height, read off the designers' enhancer table:

| Profile | in / ft | From | 7.5 ft | 10 ft | 12 ft |
| --- | --- | --- | --- | --- | --- |
| Pencil | 4.2 | 7.5' 30–32" | 32 | 42 | 50 |
| Slim | 5.6 | 7–7.5' 40–45" | 42 | 56 | 67 |
| Standard | 6.5 | the golden table (`LL_WIDTH_PER_FT`) | 49 | 65 | 78 |
| Full | 7.8 | upper ends of 9.5–10' 60–82" and 12' 73–86" | 59 | 78 | 94 |

`widthForProfile` rounds to whole inches. `profileForWidth` returns the nearest profile
when the tree's own ratio is within ±6% of it, else `null` = custom (7.5 ft x 49 in ->
standard; 12 ft x 60 in -> custom). On the calculator the Profile control sets the width
and keeps it following height at that ratio until a width is typed by hand (Custom).
The recipe itself scales with width by surface area as before; the profile's real job
is the width bucket in the enhancer lookup, which keys off the same width.

**Style** (`DesignStyle`) — the golden table is *traditional*. *Contemporary* keeps the
top two sizes as they are (they are the design) and multiplies every smaller size by
`LL_CONTEMPORARY_FILL = 0.7` before rounding — a first guess for the designers, who only
described it as "patterns, fewer ornaments". 12 ft x 78 in contemporary ->
`4.75"x28, 6"x22, 8"x12, 10"x16, 12"x10` (88 vs 112).

**Colors** (`colorCount`, 1–4, default `LL_DEFAULT_COLOR_COUNT = 2`) — every quantity
rounds to the nearest multiple of the color count, and the minimum top-size count is 8
rounded *up* to a multiple of it (`leafLedgerMinTopCount`: 8 / 8 / 9 / 8 for 1–4 colors).
Enhancer counts and the in-enhancer split round the same way. 12 ft x 78 in with three
colors -> `4.75"x39, 6"x30, 8"x18, 10"x15, 12"x9`. Going to Step 2 with untouched color
blocks seeds one block per color with equal shares (34 / 33 / 33 for three).

**When the verbatim row applies:** an approved height, at its table width, slider at 40,
traditional style, two colors. Any modifier turns the row into an input to the rounding
rules instead.

### Enhancers

Enhancers (picks/sprays) are a parallel bill of materials, counted from the designers'
own table by tree height **and** width bucket (`ENHANCER_TABLE`, `enhancerLookup` /
`enhancerCount` in `ornamentRecipe.ts`). Leaf & Ledger mode only — Vickerman's tool has
no enhancers, so nothing changes there.

| Tree (height, width) | Enhancers |
| --- | --- |
| 7.5' 30–32" pencil | 8 |
| 7–7.5' 40–45" | 8 |
| 7.5' 48–65" | 14 |
| 8.5–9' 49–50" | 16 |
| 8.5–9' 57–80" | 18 |
| 9.5–10' 60–82" | 24 |
| 12' 60–72" | 30 |
| 12' 73–86" | 36 |
| 14' | 48 |
| 15' | 60 |

Open conflict: the designer also said "an 8 has 24 enhancers" in conversation, which
the table doesn't support (8 ft interpolates to 16). The table wins until she confirms.

**Lookup order** (`enhancerLookup`), every result rounded to a multiple of the color
count (even by default):

1. **Table** — a row whose height range (single heights ±0.25 ft) and width bucket both fit.
2. **Nearest width** — the height fits but no bucket does: the closest bucket at that height
   (7.5 ft x 36 in -> pencil row, 8).
3. **Between rows** — no height fits: interpolate linearly between the nearest rows below
   and above, each picked by width as in 1–2 (11 ft x 72 in -> between 24 and 30 -> 28;
   8 ft x 52 in -> between 14 and 16 -> 16).
4. **Beyond the table** — under 7 ft or over 15 ft: the end row's count scaled by surface
   area against the row's width (bucket edge nearest the tree, or the default width when
   the row has no bucket), never below 0 (16 ft x 104 in -> 70).

**Allocation** (`enhancerAllocation`) — a first guess for the designers to react to:

```
ENHANCER_MAX_SIZE_IN = 4.75   // sizes this big and under split between tree and enhancers
ENHANCER_SHARE       = 0.5    // share of such a size that goes into the enhancers

inEnhancers = floor(qty × ENHANCER_SHARE / 2) × 2   // even; the odd piece stays loose
loose       = qty − inEnhancers
```

Larger sizes are all loose, and so is everything when the tree has no enhancers. The
calculator's enhancer count follows the table until edited by hand (then the edited count
drives the split). Example, 10 ft x 65 in (24 enhancers): `4" 18 loose / 18 in enhancers,
4.75" 18 / 18`, 6" and up all loose. Step 2's Copy / Export CSV append a final
`Enhancers, <count>` line when the count is above 0.

### Purchase list

Designer rules 8 and 9: the output is a bill of materials Charles can pull, named by its
tree configuration, and when two adjacent sizes cost about the same per square inch of
coverage the bigger one wins. Engine: `treeConfigLabel`, `sizeSwapSuggestions`,
`applySizeSwap` in `ornamentRecipe.ts`; the calculator wires them into Step 2. Available
in both modes — under the Vickerman rules the label simply has no profile or style.

**Config label** (`treeConfigLabel`) — parts joined by ` · `, unknown parts left out:

```
<height> ft <profile>        // or "<height> ft × <width> in" with no profile (custom / Vickerman)
 · <style>                   // Leaf & Ledger only
 · <Color> + <Color> + …     // the color blocks that have a color, in order, de-duplicated
```

`9 ft standard · traditional · Red + Gold`; Vickerman mode, 7.5 ft × 55 in, Red ->
`7.5 ft × 55 in · Red`. It heads Step 2, and every export: Copy's first line, Export CSV's
first row as `# <label>` (columns unchanged), and Copy for Charles.

**Build purchase list** — one click fills every order line that has no pick yet with its
best catalog match: the first match with `color_match`, else the first match (the backend
already ranks by size closeness, then color). It goes through the same picker as a manual
pick, honours the "Vickerman only" filter, and never replaces a pick made by hand.

**Catalog prices are per pack.** `price` on a catalog match is the product's
`current_price`, which for Vickerman is the pack price (`Price` on the portal, before
`PricePerPiece`; a 4" ball "6/Bag" lists at about $12) and `case_qty` is the pieces per
pack (`QtyPerPack`), so `packs_needed = ceil(pieces / case_qty)` and:

```
pricePerPiece = price / max(1, case_qty)
estimate      = Σ packs_needed × price          // shown under the picks, labelled "estimate"
```

Picks without a price are counted but left out of the estimate.

**Size swaps** (`sizeSwapSuggestions`, `LL_SIZE_SWAP_TOLERANCE = 0.15` — a first guess) —
for each pair of adjacent sizes present in the recipe (smaller → next larger), with the
per-piece price of each size taken from its picks (weighted by pieces when a size has one
pick per color; sizes without a pick are skipped):

```
costPerSqIn(size) = pricePerPiece / planarArea(size)

suggest when  costPerSqIn(larger) ≤ costPerSqIn(smaller) × (1 + tolerance)
toQty         = round( fromQty × planarArea(smaller) / planarArea(larger) )   // same coverage,
                                                                              // to a multiple of
                                                                              // the color count,
                                                                              // never below one set
extraCost     = toQty × price(larger) − fromQty × price(smaller)
```

The top size is never swapped away. Suggestions are independent: applying one
(`applySizeSwap`) zeroes the smaller size, adds `toQty` to the larger one in the
calculator's quantities (the source of truth), and clears the picks for both sizes so
their pack counts get re-matched; the panel then recomputes. Example, the 10 ft recipe
with per-piece prices 4" $1.00 / 4.75" $1.10 / 6" $2.50: 4" costs $0.0796/sq in and 4.75"
$0.0621, so `4" ×36 → 4.75" ×26` is suggested (−$7.40); 6" costs $0.0884, over
4.75"'s ×1.15, so no 4.75" → 6" swap. Under the Vickerman rules the color count for the
rounding is the number of color blocks with a color chosen.

**Copy for Charles** — plain text he can paste into a message: the label, then one line per
size `N × size"` (with `(loose / in enhancers)` when the split applies), `Enhancers: N` when
there are any, then a blank line and the picked lines as
`Supplier SKU — size" Color Finish · packs pk (pieces pcs)`.

---

## Notes & gotchas

- Everything is a pure function of `(height, width, quantities, colorBlocks)` — no
  server round-trip. Editing any input recomputes density, image, packs, and totals.
- Rounding uses JS `Math.round` (half-up), matching Vickerman.
- This is a **planning estimate**, not an exact model of a specific tree or ornament.
- If Vickerman changes their bucket thresholds, split, or SKU pattern, update
  `ornamentRecipe.ts` and this file together.
