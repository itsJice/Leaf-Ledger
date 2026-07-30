# Tree scope model — data-derived spec (Phases C & D)

Every number here was measured from the 223 imported historical recipes
(`historical_recipes` / `historical_recipe_components`), not invented. Source of
truth for the builder's Step 1 fields and Choose-Parts smart filters.

## Why the old fields were replaced

The builder asked for **Height · Width/canopy · Depth/density**. Measured reality:

- 177 of 223 recipes record dimensions, and only ever **height / width / depth**.
- **"Canopy" and "density" appear nowhere** in 223 recipes — they were blanks nobody filled.
- Fullness words are effectively absent from recipe names: `super full` 1, `full` 1,
  `slim` 0, `pencil` 0, `dense` 0.

So fullness is **emergent** (parts × quantity), not a recorded field. The model below
derives it instead of asking for it.

## 1. Canopy tiers — defined PER HEIGHT BAND

Canopy scales with height (6–7′ median 35″ → 9′+ median 62″), so a fixed XS–XL scale
would be misleading: 42″ is "full" on a 6′ tree and "standard" on a 9′ tree. Tiers are
therefore per band, so **"Medium" means the same visual fullness at any height**.

Raw percentiles (20/40/60/80) rounded to design-friendly numbers:

| Height band | n | XS | S | M | L | XL |
|---|---|---|---|---|---|---|
| `<5'`  | 9  | <15″ | 15–18″ | 18–24″ | 24–30″ | >30″ |
| `5-7'` | 11 | <28″ | 28–32″ | 32–36″ | 36–42″ | >42″ |
| `7-9'` | 18 | <36″ | 36–42″ | 42–45″ | 45–48″ | >48″ |
| `9'+`  | 3  | <54″ | 54–60″ | 60–66″ | 66–72″ | >72″ |

`9'+` has only n=3 — treat its tiers as provisional and refine as builds land.

## 2. Silhouette — NEW field (not inferable from history)

Every historical tree was built essentially round: **depth:width ratio 0.71 → 1.10,
median 1.00**. The flattest in 52 recipes is an 8′ Travelers Palm at 0.71 — nowhere near
a true flat-back. Zero recipes mention `wall`, `flat`, `corner`, or `3-side`.

So this is **capture-going-forward**, and it drives the depth value:

| Silhouette | depth : width | Use |
|---|---|---|
| **Full-round** (default) | 1.0 | freestanding, viewed 360° |
| **Corner** | ~0.66 | tucked into a corner |
| **3-sided / flat-back** | ~0.5 | flush against a wall |

## 3. Density — keyed to SPECIES, never pooled

Pooling species is meaningless. At an identical **7 feet**:

| 7′ tree | Stems |
|---|---|
| Areca Palm | **1** |
| Yucca | 1–6 |
| Dracaena | 5 |
| Fiddle | 5–10 |
| **Eucalyptus** | **16** |

**1 stem vs 16 at the same height.** Baselines must be `f(species, height)`.

### Seed baselines (stem/branch count)

| Species | 4′ | 6′ | 7′ | 8′ | 9′ | 10′ |
|---|---|---|---|---|---|---|
| Fiddle | 1 | 3–10 (avg 6.6) | 5–10 (avg 7.5) | 11–13 | — | — |
| Yucca | — | 7–8 | 1–6 | 17–23 | 17 | 25 |
| Dracaena | — | — | 5 | 10 | 24–26 | — |
| Eucalyptus | — | — | 16 | — | — | — |

### Two structural classes

- **Built-up** (Fiddle, Yucca, Dracaena, Eucalyptus) — density is a real dial.
- **Specimen** (Areca, Kentia, Travelers Palm, generic Palm) — **~1 stem**; one large
  potted plant, no build-up. Density barely applies; don't prompt for it.

A species with no history falls back to its class. **Every new build refines the baseline.**

### Counting caveat (see Phase A)

Historical `quantity` mixes packs and pieces — the same SKU `4" Green Succulent Stem 6/pk`
appears at FC $12.34 (a pack) and $2.05 (one stem), and one line reads `qty 0.25`.
Phase A's per-line detection writes `formulas.pack_analysis.pieces_used`; **density must
be computed from `pieces_used`, not raw `quantity`.** Note all 9 confirmed pack lines are
filler (cactus/fern/ivy/echeveria) — **zero are structural stems**, so the table above holds.

Only 141 of 603 product lines (23%) resolve to a catalog SKU, so pack size is unknowable
for the rest. Baselines are seed values with known noise on filler, not gospel.

## 4. Choose-Parts smart-filter vocabulary (Phase D)

Pre-applied but removable, per active scope slot.

**Top Dressing** — ranked by real usage:
`foam (32) · acrylic (24) · sheet moss (17) · natural lichen moss (15) · smooth foam ball (18) ·
mixed buff moon rock (9) · rocks (4) · reindeer moss (6) · star rocks (3)`

**Container** — real usage:
`zinc container · fiber resin planter · concrete bowl · pedestal container · fish bowl · newport pot`

Selecting **Container** must surface containers first — never dried botanicals.

## 5. Build-type list — DECIDED: add the historical types

`Plant & Bush` (74) outranks `Tree` (52), and none of these three existed in the builder.
**User decision: add them.** Final type list:

| Type | Recipes | Notes |
|---|---|---|
| **Plant & Bush** | **74** | NEW — the most-built product |
| Floral Arrangement | 61 | maps to existing "Arrangement" |
| Tree | 52 | full tree scope model above |
| **Container Only** | 15 | NEW — container + top dressing only, no plant material |
| Planter | 13 | existing |
| **Topiary** | 2 | NEW — thin history, seed from Tree |
| Drop-in / Custom | — | existing, no history |

Each type declares **which dimension fields apply** — e.g. canopy + silhouette are
meaningful for Tree / Plant & Bush / Topiary, but **not** for Container Only (no canopy)
or Drop-in. Do not render a field a type can't use.
