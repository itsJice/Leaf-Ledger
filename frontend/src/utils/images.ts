/**
 * Route an external image through the backend image proxy. Falsy input
 * ("" / null / undefined) gives `undefined`.
 *
 * Verbatim copy of the identical inline `proxied` helpers in CatalogPickPane.tsx,
 * Sourcing.tsx, Orders.tsx and OrnamentCalculator.tsx (see images.test.ts).
 */
export const proxiedImageUrl = (url?: string | null) =>
  url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined;
