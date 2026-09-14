const FAVORITE_IDS_KEY = "leaf-ledger:favorite-product-ids:v1";

export function readFavoriteIds(): Set<number> {
  try {
    const parsed = JSON.parse(localStorage.getItem(FAVORITE_IDS_KEY) || "[]");
    // Drop null/undefined before coercing — `Number(null)` is 0, which would
    // otherwise smuggle a fake id 0 into the set.
    return new Set(
      Array.isArray(parsed) ? parsed.filter((x) => x != null).map(Number).filter(Number.isFinite) : []
    );
  } catch {
    return new Set();
  }
}

export function writeFavoriteIds(ids: Set<number>) {
  try {
    localStorage.setItem(FAVORITE_IDS_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // Ignore storage issues.
  }
}

export function setLocalFavorite(id: number, favorited: boolean): Set<number> {
  const ids = readFavoriteIds();
  if (favorited) ids.add(id);
  else ids.delete(id);
  writeFavoriteIds(ids);
  return ids;
}
