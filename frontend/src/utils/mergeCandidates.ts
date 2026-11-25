// The Clients page's "Merge into another client" picker (Comments #50): a
// duplicate card is folded into the client it duplicates. Kept out of the
// page so it can be tested without the page's API client.

/** The clients a card can be merged into: every other saved card whose name
 *  has every word typed in `query`, closest names first (the words it shares
 *  with the duplicate's own name), then A to Z. */
export function mergeCandidates(
  client: { id?: number | null; name: string },
  rows: { id?: number | null; name: string }[],
  query: string,
): { id: number; name: string }[] {
  const words = (s: string) =>
    s.toLowerCase().replace(/[^a-z0-9 ]/g, " ").split(" ").filter((w) => w.length > 1);
  const mine = new Set(words(client.name));
  const q = words(query);
  return rows
    .filter((r): r is { id: number; name: string } => r.id != null && r.id !== client.id && Boolean(r.name))
    .filter((r) => q.every((w) => words(r.name).some((t) => t.startsWith(w))))
    .map((r) => ({ r, shared: words(r.name).filter((w) => mine.has(w)).length }))
    .sort((a, b) => b.shared - a.shared || a.r.name.localeCompare(b.r.name))
    .map(({ r }) => ({ id: r.id, name: r.name }));
}
