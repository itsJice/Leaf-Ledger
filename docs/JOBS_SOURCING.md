# Sourcing worksheets (Jobs) — scope and trajectory

## Where the line is today (decided Sept 3, 2026)

The designers keep their paper. Two artifacts are **not** replaced by the app:

- the TBDG **Manufacturing Order** (Xmas and Regular), and
- the **purple sheet**: after the builders pull what they already have from
  inventory onto the shelf assigned to that client, they write down the
  *difference* they still need.

The purchaser is fully electronic and already lives in Catalog Search. The app
picks up where he does. The **Sourcing** tab is his worksheet, one per client
job, and replaces the binder printout and the Drive tracking spreadsheet:

1. He transcribes the purple sheet's lines (item, spec, need quantity).
2. For each line he checks **open orders** first (market buys entered as POs are
   offered before anything is bought and can be allocated to the job), then
   picks from the **catalog**; pack size, packs to order, adjusted unit cost and
   overage fill in. Sold-out items keep a **substitution** chain. Follow-ups
   become tasks.
3. **Send to purchase orders** creates one PO per vendor or appends to an open
   one. POs carry status, vendor order number, expected arrival, freight, and
   per-line **check-in**.
4. The **tracking sheet** exports in the exact column layout he uses today,
   with product pictures on the rows, so the binder printout is unchanged.

The job's stage is derived from its lines: New → Sourcing → Ordered →
Receiving → Complete.

## What was built and then held back

The first cut of this work modelled the whole process end to end: the MO
header and pieces ordered as intake, the purple sheet with an "on shelf"
column, a builders' build sheet, and a Manufacturing Order PDF generated from
the job. The team is not ready to move the designers off paper, so those parts
are **out of the UI but still in the code and schema**, ready to switch on:

| Piece | Where it lives | Status |
|---|---|---|
| Pieces ordered (12 ft tree × 1 …) | `ll_app.job_pieces`, `/api/jobs/{id}/pieces` | API only |
| MO header fields (designer, sidemark, delivery, plug location …) | `ll_app.jobs.intake` and columns | API only |
| Shelf pull per need line | `ll_app.material_needs.shelf_qty` | API only, 0 by default |
| Build sheet for the builders | removed from `Jobs.tsx` (in git history) | Not shown |
| Manufacturing Order PDF | `backend/app/apis/jobs/export.py::manufacturing_order_pdf` | Not routed |
| Built / installed marks | `ll_app.jobs.built_at`, `installed_at` | API only |

## Trajectory, when the designers are ready

1. **Purple sheet in-app.** The designers enter the need list themselves, with
   the shelf column, and the buyer's worksheet starts pre-filled. Nothing else
   changes for him.
2. **Pieces and the MO header** entered at intake, so the job knows what was
   ordered and the MO PDF can be generated from it (the PDF already renders the
   header, piece specs, the PRODUCT list from sourcing, a TIME log, and notes).
3. **Build sheet** for the bench: per piece, what is on the shelf, what is still
   coming, pictures of what was actually ordered.
4. **Collections / recipes** propose the need list from the pieces ordered,
   using the builder's recipe intelligence and the Ornament Calculator.
5. **Approval and cash release** by vendor, with preparer / approver roles.

Each step is additive; the schema already has the columns.
