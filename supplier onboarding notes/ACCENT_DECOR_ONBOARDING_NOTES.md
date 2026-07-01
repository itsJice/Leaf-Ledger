# Accent Decor Onboarding Notes

This case record captures the maintainable lessons from a portal-based supplier integration without retaining account-specific instructions or operational identifiers.

## Status

- Type: product-heavy decor catalog
- Integration: legacy portal adapter plus shared catalog intake
- Current interpretation: useful maintenance reference, not the default onboarding pattern

## What worked

- Supplier-aware credential states prevented extraction and price synchronization from running with unverified access.
- Category discovery and cached catalog scope reduced repeated navigation.
- Product normalization retained source images, dimensions, style, and supplier wording.
- Readiness reporting distinguished imported rows from products that were actually usable in search and project workflows.
- Image storage exposed conflicts and retry state rather than reporting false success.

## What did not generalize

- Account activation and sign-in behavior was specific to the supplier portal.
- Alternate entry points and changing page structure increased maintenance cost.
- A successful login did not guarantee that catalog scope, price visibility, and image access were complete.

## Resulting decisions

1. Keep account instructions and credentials outside the repository.
2. Require a credential check before starting account-dependent work.
3. Prefer a supplier-provided catalog file when available.
4. Preserve portal automation as a fallback adapter behind the shared import and readiness contracts.
5. Treat missing prices or images as review state, not parser success.

## Verification checklist

- Credential state is explicit without revealing account data.
- A bounded catalog sample parses into the shared product shape.
- Repeated import does not create duplicate active supplier SKUs.
- Images and source provenance survive normalization.
- Failed or conflicting jobs expose a safe next action.

See [Supplier Connector Contract](SUPPLIER_CONNECTOR_CONTRACT.md) for the stable interface.
