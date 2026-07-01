# Catalog Extraction Design Notes

This document defines the narrow responsibility, interfaces, and handoff expectations for Leaf & Ledger's optional external extraction workspace.

## Mission

Produce inspectable CSV or JSON catalog artifacts when a supplier cannot provide an adequate structured source. The workspace does not write directly to the application database and does not make extraction the core Leaf & Ledger product.

## Inputs

- an approved source URL or source file;
- optional credentials supplied through environment variables or repository secrets;
- a supplier configuration with selectors or a supplier-specific adapter;
- a bounded product limit for smoke verification.

## Outputs

Each run writes products and a run report under an ignored `outputs/` directory. Export rows follow the fields documented in [the workspace README](README.md) and are validated before application import.

## Design rules

1. Prefer supplier exports, feeds, or approved files over portal traversal.
2. Never hard-code credentials or account identifiers.
3. Keep supplier-specific behavior behind configuration or a narrow adapter.
4. Preserve source URLs and raw fields for traceability.
5. Treat missing values as review state.
6. Bound smoke tests before attempting broad coverage.
7. Persist useful output before expensive follow-up work.
8. Do not bypass access controls or anti-automation protections.

## Handoff checklist

A new owner should be able to create a virtual environment, run a sample configuration with placeholder credentials, validate the resulting artifact, and explain why the output is imported through Leaf & Ledger rather than written directly to its database.

## Known limitations

- Selector-based automation is sensitive to markup changes.
- Authentication and commercial data visibility vary by account.
- Browser drivers add runtime and maintenance overhead.
- Successful extraction does not prove catalog completeness.
- Source permission and terms must be reviewed outside the codebase.

## When to stop

Stop investing in an adapter when a structured export is available, the source is not approved for automation, completeness cannot be validated, or maintenance cost exceeds the value of repeatable file intake.
