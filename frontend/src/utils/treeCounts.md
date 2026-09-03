# Tree counts — the calibration loop

The ornament calculator's golden table (`ornamentRecipe.ts`, `GOLDEN_RECIPES`)
is the designer's instinct written down once. Tree counts are how it keeps
improving: every time a crew installs or tears down a tree they record what was
**actually** on it — pieces per ornament size plus enhancers. Each record is a
candidate golden-table row, and the Tree Counts page shows where the approved
table and reality have drifted apart. *"Next time we take one down, take note."*

Nothing here writes the golden table. A designer reviews the averages and, when
one is approved, pastes the generated snippet into `GOLDEN_RECIPES` by hand.

## Files

| File | Role |
| --- | --- |
| `utils/treeCounts.ts` | Types + pure helpers (averaging, drift, snippet). No fetch, no React. |
| `pages/TreeCounts.tsx` | The page at `/tree-counts`: count form, recorded list, table vs reality. |
| `backend/app/apis/tree_counts/__init__.py` | The API. |
| `backend/migrations/014_tree_counts.sql` | The table DDL, for a rebuilt database. |
| `backend/tests/test_tree_counts_api.py` | Endpoint tests against an in-memory fake connection. |

## API

All routes require a signed-in user (every `/api` router does; see
`backend/main.py`). Call them with `apiFetch` so the Supabase token is attached.

| Method | Path | Body / query | Returns |
| --- | --- | --- | --- |
| `POST` | `/api/tree-counts` | `TreeCountInput` (below) | the stored `TreeCountRecord` |
| `GET` | `/api/tree-counts` | `?height_ft=9&tolerance_ft=0.25&limit=500` (all optional) | `TreeCountRecord[]`, newest first |
| `DELETE` | `/api/tree-counts/{id}` | — | `{ deleted: 1, id }`, or 404 |

```ts
interface TreeCountInput {
  kind: "install" | "teardown";
  height_ft: number;            // > 0, <= 60
  width_in: number;             // > 0, <= 400
  profile?: string | null;      // free text, e.g. "slim" — optional
  style?: string | null;        // free text, e.g. "classic red & gold" — optional
  label?: string | null;        // client / site, free text — optional
  counts: Record<string, number>; // size in inches (string key, "4.75") -> pieces
  enhancers: number;            // >= 0
  notes?: string | null;
}
```

Server-side validation (pydantic, `TreeCountIn`):

- `kind` must be `install` or `teardown`; dimensions and `enhancers` are range-checked.
- `counts` keys must parse as a size in inches (0 < size <= 48); `"4"`, `"4.0"`
  and `4` collapse to one key `"4"`. Values must be whole numbers >= 0; zero and
  blank entries are dropped, so a size with nothing on the tree is simply absent
  (the same convention the golden table uses).
- A record with no ornaments **and** no enhancers is rejected (400).
- Text fields are trimmed and capped (200 chars; notes 4000).
- `created_by` / `created_name` come from the verified Supabase user
  (`AuthorizedUser`), never from the body.

`GET` with `height_ft` returns records whose height is within `tolerance_ft`
(default 0.25 ft) — the same window the page averages over.

## Storage

Table `ll_app.tree_counts`, one row per counted tree. `ll_app` is where the app's
own tables live (`feedback`, `user_preferences`, `install_schedule_*`), as
opposed to the catalog tables in `public`. Following that convention the API
creates the table lazily on first use with `CREATE TABLE IF NOT EXISTS`; the
identical DDL is in `backend/migrations/014_tree_counts.sql` so a rebuilt
database can be given it up front. **There is nothing the deployer must run** —
the first request creates the table — but running the migration is harmless.

```
id, recorded_at, kind, height_ft, width_in, profile, style, label,
counts (jsonb), enhancers, notes, created_by, created_name
```

Records are team-wide: anyone signed in can list or delete any record.

## Helpers (`treeCounts.ts`)

- `COUNT_SIZES` — the grid columns: `ORNAMENT_OPTIONS` from 3" to 15.75".
- `countsFromForm(form)` — text cells -> counts map; blanks/zeros dropped.
- `totalPieces(counts)` — sum of pieces (enhancers excluded).
- `recordsNearHeight(records, heightFt, tol = 0.25)`.
- `averageCounts(records)` — mean per size, width and enhancers. A record with
  no entry for a size is a real zero, so every record is in every denominator.
- `driftCell(approved, actual)` — the drift rule (below).
- `roundToEven(n)` — nearest even integer.
- `goldenRowSnippet(heightFt, widthIn, quantities)` — paste-ready TypeScript.
- `compareToTable(records)` — one `TableComparisonRow` per `GOLDEN_RECIPES` entry.

## The drift rule

For each golden height, records within ±0.25 ft are averaged per size and
compared with the approved row. A size is **flagged** when

```
|average − approved| >= 4 pieces
  OR |average − approved| / approved >= 20%
  OR approved == 0 and average > 0     (crews hang a size the recipe never asked for)
```

A flagged cell is highlighted amber on the page; a row with any flagged size
shows a "drift" badge. Thresholds are `DRIFT_MIN_PIECES` and `DRIFT_MIN_PCT`.

## Copy as golden row

Builds `{ heightFt: 9, widthIn: 59, quantities: { 4: 26, 4.75: 30, ... } },`
from the average: sizes ascending, zeros dropped, each quantity rounded to the
nearest **even** number (golden quantities are per-color pairs; designs are
usually two colors). The width is the approved row's width, not the recorded
average, because the table's rows are defined at the default widths. Paste it
into `GOLDEN_RECIPES` in `ornamentRecipe.ts` once the designer has approved it.
