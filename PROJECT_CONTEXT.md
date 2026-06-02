# Leaf & Ledger Project Context

## North Star
Leaf & Ledger is a centralized catalog and project system for The Branch Design Group. It replaces years of spreadsheet recipes, supplier browsing, image folders, pricing math, and mockup prep with one searchable product library and job workflow.

## Catalog Model
- Product Library is the general catalog across suppliers.
- Hearts mean favorites only.
- Plus means add this product to a client project bucket.
- Supplier data stays source-truth: exact supplier SKU, description, price, UOM, availability, dimensions, origin, material, and images.
- Search should work the way a designer thinks: color words, material, size, category, product type, supplier wording, and normalized supplier codes.

## Project Model
- Clients are the top level for real work. A client may be a homeowner, business, designer, or designer's client.
- Each client can have many projects/jobs, such as Dining Room, Beach House, Bookshelf, or Holiday Install.
- Projects replace the old Arrangements UI.
- Each project has buckets such as Tree, Garland, Bookshelf, Bookshelf 2, etc.
- Products added to a bucket start as saved ideas/candidates.
- Only selected products affect recipe math, purchase sheets, costs, markups, quotes, and invoices.
- V1 has a lightweight clients table for creating clients before projects exist. Projects still store the client name for simple attachment, and a fuller client profile can be expanded later for addresses, designers, notes, and project history.

## Future Workflow
- Recipe sheets and historic spreadsheets become standardized formulas.
- Selected bucket products plus recipe logic calculate quantities to order.
- Purchase sheets and client quote numbers come from selected products and pricing settings.
- AI mockups use project products and uploaded client-space photos to visualize the finished design.

## Effort Metrics
- 2026-05-29 instant-loading pass: Added/verified app bootstrap summaries, cached summary usage, paged Product Library loading, debounced catalog search, and global product filter metadata. Backend compile passed, frontend build passed, and local HTTP checks passed for bootstrap summary, product filter metadata, paged product search, and frontend routes: clients, projects, project detail, library, favorites, suppliers, invoice, and mockups.
