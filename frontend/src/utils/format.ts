export function formatCurrency(value: number | null | undefined): string {
  if (value == null) return "—";
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value);
}

export function formatDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export function formatDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  return new Date(value).toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

export function categoryLabel(cat: string): string {
  const map: Record<string, string> = {
    // New categories
    containers: "Containers",
    wood: "Wood",
    greenery: "Greenery",
    florals: "Florals",
    trees: "Trees",
    // Scraper-produced categories
    accents: "Accents",
    // Legacy (kept for backward compat)
    plant: "Plant",
    container: "Container",
    filler: "Filler",
    accent: "Accent",
    other: "Other",
    supplies: "Supplies",
    moss: "Moss",
    branches: "Branches",
    botanicals: "Botanicals",
    preserved: "Preserved",
    seasonal: "Seasonal",
    stems: "Stems",
    foliage: "Foliage",
    succulents: "Succulents",
    topiaries: "Topiaries",
    wreaths: "Wreaths",
    baskets: "Baskets",
    vases: "Vases",
    risers: "Risers",
    pedestals: "Pedestals",
    liners: "Liners",
  };
  return map[cat] || cat;
}

export function unitLabel(unit: string): string {
  const map: Record<string, string> = {
    stem: "stem",
    pot: "pot",
    flat: "flat",
    bunch: "bunch",
    each: "each",
  };
  return map[unit] || unit;
}
