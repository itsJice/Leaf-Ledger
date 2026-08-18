# Retiring the in-memory search index

**STATUS (2026-08-18): COMPLETE — all four phases. The index is deleted.**
The parity gate passed clean — 20 queries x 2 paths, 0 defects, against a fresh
reference (an earlier "15-defect" run was the cached reference being a day
behind a mid-day supplier import; the harness now detects that). Process RSS at
boot: 27 MB vs ~892 MB. Phase 4 done same day at the owner's direction: the index, its disk cache,
the warm task and the parity harness (no reference left to diff against) are
removed. `SEARCH_INDEX_ENABLED` no longer exists.

## Why

Catalog search is served from an in-memory index holding every active product.
At 166,029 products that measures **5,371 bytes per product ≈ 892 MB**, with a
peak nearer 1.3 GB while it builds.

That is more memory than the Render web service has, so the instance is
OOM-killed. Render restarts it, the restart rebuilds the index, the rebuild
streams the entire catalog out of Supabase, and it OOMs again:

```
build index → read whole catalog (egress) → ~1.3 GB peak → OOM
     ↑                                                        ↓
     └────────────── Render restarts the service ─────────────┘
```

That loop is what exhausted the organisation's monthly bandwidth allowance
(19.82 GB against a 5.5 GB quota) and took the app offline — including logins,
because Supabase Auth lives in the same project.

The index exists because the database used to be too slow to search directly.
That is no longer true: trigram GIN indexes on `name`, `supplier_sku` and
`description` now make keyword search indexable, and `SEARCH_INDEX_ENABLED=0`
already serves search from SQL (measured from a laptop: browse 2.3s, keyword
6.6s, item number 1.0s — all faster in-region).

**Two things are missing before the index can be deleted: facets, and typo
tolerance.** Everything below exists to close that gap.

## What the catalog actually looks like

| | |
|---|---|
| Active products | 166,029 (537 MB) |
| Growth that triggered this | Michaels +46,477, NewPro +5,699 (95k → 166k) |

Facet values live in JSONB, **not** in the legacy columns — those are far
sparser and must not be used:

| Facet source | Rows populated | Legacy column |
|---|---|---|
| `raw_data->'normalized'->>'color'` | 122,142 | `color` — only 19,325 |
| `raw_data->'normalized'->>'finish'` | 48,326 | `finish` — only 13,641 |
| `raw_data->'normalized'->>'size_in'` | 93,951 | — |
| `raw_data->>'category_group'` | 166,029 | — |
| `raw_data->'color_families'` | 18,389 | JSON **array**, multi-valued |

`color_families` is multi-valued on purpose: an item can be Red *and* Green
*and* Multi-color, and must appear under each.

## Measure everything at least three times

This instance is slow and wildly inconsistent. The same grouped count has
measured **13s, 16s, 21s, 27s, 29s and 73s**. Single measurements here are
worthless — always take a median over several runs, or you will "optimise"
based on noise. A partial expression index on the finish path appeared to make
that query *slower* on one run, which is exactly the trap.

## Phases

### 1 — Schema that makes facet aggregation fast
Decide empirically between expression indexes (no lock), STORED generated
columns (fast, but adding one **rewrites the 537 MB table under an exclusive
lock** — real downtime), or a summary table refreshed on import. Deliver
`migrations/006_facet_indexes.sql`. A GIN index covers `color_families`
containment.

### 2 — Facets and typo tolerance in SQL
Reproduce the existing facet contract exactly, including **drill-down**: each
dimension is counted *ignoring its own selection* (so choosing one colour does
not collapse the colour list) while other dimensions' filters still apply.
Seven naive GROUP BYs over 166k rows will be far too slow — prefer a single
pass with `FILTER`/`GROUPING SETS`, and **cache the unfiltered counts**, which
only change on import and cover most page loads.

Typo tolerance moves to `pg_trgm` similarity. Exact matches must outrank fuzzy
ones, correctly-spelled queries must not pay for it, and **item numbers must
stay exact** — `N590321-2` must never fuzzy-match a different SKU.

### 3 — Prove parity, then switch
Diff both paths over a real query matrix: totals, result ids *and order*, and
every facet dimension. The in-memory index is the reference implementation.
Known-acceptable difference: the SQL path returns a capped total
(`total_is_capped`) instead of an exact count above the cap. Only after parity
holds does `SEARCH_INDEX_ENABLED=0` become the default.

### 4 — Delete the index
Remove `_build_search_index`, the disk cache, the warm-up task and the
single-flight lock. That is ~892 MB of memory and the entire crash loop gone.

## Rules while doing this work

- **Egress is the constraint.** Aggregates and LIMITed queries are cheap;
  never `SELECT` whole rows across the catalog, never stream the full table
  repeatedly. Build the in-memory index at most once per run when comparing.
- **Keep both paths working** until parity is proven. The flag chooses.
- 293 tests pass today; do not regress them.

## Related settings

| Setting | Purpose |
|---|---|
| `SEARCH_INDEX_ENABLED=0` | Skip the index; serve search from SQL (the escape hatch, and eventually the default) |
| `SEARCH_INDEX_TTL` | Cache lifetime, default 24h — the catalog only changes on import |
| `SEARCH_INDEX_CACHE_DIR` | Persist the built index so a restart reloads from disk instead of re-reading the catalog |
| `SEARCH_INDEX_PREFETCH` | Rows per cursor round trip (default 10,000) |

Render also needs the service kept **always-on** and adequately sized; a
sleeping or undersized instance re-triggers the rebuild loop.
