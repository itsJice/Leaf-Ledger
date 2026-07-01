# Regency Onboarding Notes

This case record summarizes source discovery and parser lessons while leaving account-specific access details outside the repository.

## Status

- Type: product-heavy decor catalog
- Integration: bounded parser and import verification
- Current interpretation: validated source pattern with further full-catalog work intentionally gated

## Findings

- Public category pages expose product links and useful descriptive fields.
- Product details can include multiple images and attributes that should remain in raw source data.
- Price and availability may depend on authenticated access and therefore cannot be assumed from public reconnaissance.
- Category naming requires normalization without discarding the supplier's original label.

## What worked

- Reconnaissance separated public catalog structure from account-dependent fields.
- A bounded parser could produce rows accepted by the shared importer.
- Parser tests covered representative product detail and normalization behavior.

## What remains uncertain

- Full catalog coverage and pagination require source-specific verification.
- Authenticated commercial fields must be tested with approved access outside the repository.
- Seasonal catalog changes may alter category and product coverage.

## Resulting decision

Request a structured supplier export first. Use the existing parser only when an approved export is unavailable, validate it on a bounded sample, and import through the shared preview and commit flow.
