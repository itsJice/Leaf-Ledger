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
`buildRecipeFor` in `ornamentRecipe.ts`). It keeps Vickerman's surface-area, 40%
coverage, quantity-rounding, density meter and tree images unchanged — only **which
sizes** and **how coverage is split** differ. Source: designer working session,
2026-08-20, reconciled against Vickerman's formula.

### Why

Big trees have big gaps; small ornaments disappear into them (especially next to
enhancers/picks). The team would rather fill small gaps with foliage than with small
ornaments. Vickerman's buckets put a 12 ft tree in 4"–8" balls (~207 pieces); the
designers use 4.75"–12" (~114 pieces) at the *same* 40% coverage.

### Rules

1. **Top size = tree height in feet, as inches, rounded up to a stocked size.**
   12 ft → 12", 10 ft → 10", 9 ft → 10", 8 ft → 8", 15 ft → 15.75". Ladder:
   2.4, 3, 4, 4.75, 6, 8, 10, 12, 15.75, 20 (capped at 20).
2. **Five sizes**, stepping down the ladder from the top size (fewer if the ladder runs out).
3. **Coverage split evenly** across the sizes (20% each with five).
4. **Under 8 ft the top size is an accent** — it gets 5% of coverage and the rest is
   split evenly across the remaining sizes ("mostly 6-inch, some 8").
5. **Default width** = height × 6.5 in/ft (the ratio that makes the 12 ft calibration
   land at 40%); width stays editable and stops auto-following once edited.

### Calibration

Designers' 12 ft recipe: `12"×8, 10"×10, 8"×18, 6"×30, 4.75"×48` = 114 pieces. By
Vickerman's density formula that is 40% on a 12 ft × 78 in tree, with coverage split
21/18/21/20/20% — i.e. an even split. The rule set reproduces it as
`12"×8, 10"×11, 8"×17, 6"×30, 4.75"×48`.

| Tree | Sizes | L&L pieces | Vickerman pieces (same tree) |
| ---- | ----- | ---------- | ---------------------------- |
| 12 ft × 78 in | 4.75–12" | ~114 | ~207 (4–8") |
| 9 ft × 59 in | 4–10" | see calculator | 4–8" |
| 7.5 ft × 55 in | 3–8" (8" accent) | see calculator | 3–6" (42/41/21/10) |

Open with the designers: the 7 ft "some 8-inch" accent share (5% is a first guess),
and whether 4.75" belongs on 7 ft trees.

---

## Notes & gotchas

- Everything is a pure function of `(height, width, quantities, colorBlocks)` — no
  server round-trip. Editing any input recomputes density, image, packs, and totals.
- Rounding uses JS `Math.round` (half-up), matching Vickerman.
- This is a **planning estimate**, not an exact model of a specific tree or ornament.
- If Vickerman changes their bucket thresholds, split, or SKU pattern, update
  `ornamentRecipe.ts` and this file together.
