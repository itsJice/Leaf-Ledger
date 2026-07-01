# Select Artificial Onboarding Notes

## Status

- Wave: 1
- Type: Product-heavy florals/decor
- Status: Recon started

## Current Interpretation

Select Artificial should not proceed straight into adapter-building unless no better source exists. First ask for a supplier export, price book, product feed, or usable catalog file. Treat the Angular/API notes below as fallback extraction evidence only.

## Current Evidence

- Site: `https://selectartificials.com/`
- Login trigger: `Sign In or Register` opens a sign-in modal.
- Login hint from screenshot: username is the six-digit customer number; password is the billing zip code.
- Public homepage exposes category navigation, but product/pricing import must use a logged-in account session because our preferred pricing is account-specific.
- Public shop pages appear to be Angular/ServiceStack driven.
- Public category links use query parameters such as `/shop/?Category=Foliages&SubCategory=Foliage%20Bushes`.
- Likely product route found in bundled JavaScript: `QueryProducts.json`, but the correct authenticated service base/path still needs confirmation after login.

## App Integration Status

- Scraper key: `select_artificial`.
- Supplier-name inference added for `Select Artificial` / `Select Artificials`.
- Configure Catalog is wired to `discover_select_artificial_catalog`.
- Configure Catalog must log in with customer number/billing zip before category cache is accepted.
- Product Sync is intentionally blocked until the authenticated product API route that returns preferred pricing is captured.
- Readiness UI now recognizes Select Artificial and uses customer number/billing zip wording.
- Local supplier record `id=2` was updated to use `scraper_key = select_artificial`.
- Latest readiness result: credentials failed; next action is to update the Select customer number and billing zip.

## Recon Classification

- Preliminary difficulty: `C` until authenticated API/product route is confirmed.
- Reason: Angular-heavy shop UI with product modules in a large `DependencyHandler.axd` bundle. Public pages are good for category discovery, but pricing/product import must be authenticated.

## Source-First Next Actions

1. Ask Select Artificial for a current product export, price book, product feed, PDF catalog, or approved spreadsheet source with preferred pricing.
2. If a file/export exists, convert it to the standard supplier import format and run a small Product Library import proof.
3. If no usable source exists, confirm the saved Select Artificial credentials in the app.
4. Log in through the modal and verify preferred pricing is visible.
5. Use browser/network inspection or authenticated HTTP session to capture the real `QueryProducts.json` route and request shape.
6. Only then build a fallback adapter from the shared supplier template.
7. Run a 10-25 product proof import from one category such as `Foliage Bushes`.

## Verification

- 2026-06-05: Backend compile passed for Select scraper and scraper/supplier APIs.
- 2026-06-05: Supplier framework and Regency tests passed: `6 passed`.
- 2026-06-05: Frontend build passed.
- 2026-06-05: Temporary updated backend verified Select readiness support. Configure Catalog correctly blocked because credentials are not saved yet.
- 2026-06-05: After credentials were saved, Configure Catalog reached the Select login flow but the site rejected the saved customer number/billing zip. The supplier readiness API now reports `credential_status = failed`.

## Notes

- Use [SUPPLIER_ONBOARDING_CHECKLIST.md](SUPPLIER_ONBOARDING_CHECKLIST.md).
- Preserve supplier-specific fields in `raw_data`.
- Do not store credentials in GitHub.
