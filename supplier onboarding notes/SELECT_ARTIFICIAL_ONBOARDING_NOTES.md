# Select Artificial Onboarding Notes

This case record summarizes the decision to prefer a structured source over brittle account-specific portal automation.

## Status

- Type: product-heavy decor catalog
- Integration: reconnaissance only
- Current interpretation: do not expand the adapter until source options and approved access are confirmed

## Findings

- The storefront is a client-rendered application with account-dependent catalog behavior.
- Public requests did not establish a complete product source.
- Authentication failure could be identified and surfaced as readiness state, but repository documentation should not encode account rules.

## Lesson

A known login screen is not evidence that a dependable catalog integration exists. Before building browser or API automation:

1. request an export, price book, feed, or usable catalog file;
2. confirm permitted access and catalog scope;
3. prove a bounded source path;
4. normalize a sample through the shared importer;
5. expand only when the sample is complete enough to justify maintenance.

## Resulting decision

Keep reconnaissance as evidence, leave account details outside Git, and treat further automation as fallback work rather than core product scope.
