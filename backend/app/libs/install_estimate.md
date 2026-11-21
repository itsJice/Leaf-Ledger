# Install estimate spec

`install_estimate.py` suggests next season's on-site hours for one client.
It never invents hours: anything it needs and doesn't have comes back as
**NEEDS INPUT**.

## Inputs

- **History**: each past season's real on-site hours. Install Times
  (`ll_app.install_actuals_latest`, install visits summed per season) wins;
  a season with none there falls back to the card's `real_hours`.
- **This season's card**: `inventory` (type, size, qty), `boxes`.
- **Flags**: night (Dallas ZIP 75/76), commercial (board says Business),
  first year (no earlier season on the card).
- **Rates**: `ll_app.estimate_rates` (season, key, amount). A season uses its
  own value for a key, else the latest earlier season's. Edited in
  Settings > Install Estimates.

## Rules, in order

1. **Last real time.** Take the newest season with real hours.
   - Inventory on both cards and the same: that time, confidence **high**.
   - Inventory on both cards but different, and every needed rate set:
     scale by item-minutes now / item-minutes then, confidence **medium**.
   - Inventory changed but rates missing, or inventory not on both cards:
     the time unscaled, confidence **medium**, and the reason in the basis.
2. **Per item** (no real time yet): `setup + sum(rate x count)` minutes,
   times each factor that applies (night, commercial, first year),
   confidence **low**.
   - Trees by height: small up to 7.5 ft, medium 8 to 10, large 11 to 14,
     XL 15 and up. Garland by the foot (qty x length). Wreath, spray, swag,
     other per piece. Boxes per box.
3. **NEEDS INPUT**: no inventory, a tree or garland without a size, or any
   rate/factor that applies but isn't set. Hours are blank.

Hours round to the nearest quarter hour (at least 0.25).

## Rate keys

| Key | Unit |
|---|---|
| setup | min / job |
| tree_small, tree_medium, tree_large, tree_xl | min / tree |
| wreath, spray, swag, other | min / piece |
| garland_ft | min / ft |
| box | min / box |
| factor_night, factor_commercial, factor_first_year | multiplier |

## Seeding the rates

`fit_rates()` is a non-negative least-squares fit of minutes per key on
real jobs that have both a card inventory (or boxes) and real hours. A key
gets a value only when at least 3 jobs have it; the rest stay blank
(NEEDS INPUT). Factors are never fitted; staff set them.

## Where it shows

The client card's Christmas card shows "Suggested 2027: X h (basis)" with
an **Accept** button that writes `est_hours` on the 2027 season through the
normal season save (stamped as an app edit). Nothing changes without
Accept. 2026 prices are untouched. The schedule doesn't read it yet
(PR #155 wires card facts into the schedule).
