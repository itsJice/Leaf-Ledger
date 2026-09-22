/**
 * Address suggestions while typing, so a street can be completed to a full
 * street / city / state / ZIP without leaving the form (staff usually have
 * the street but not the ZIP).
 *
 * Photon (photon.komoot.io) is OpenStreetMap's typeahead service: no key,
 * CORS open, fair use. Results are biased toward the Houston depot. The
 * scheduler's "New client" form uses the same service and the same shaping
 * (scheduler/review_template.html), so a pick reads the same in both places.
 * A street-level match keeps the house number that was typed.
 */

export type AddressSuggestion = {
  line1: string;
  place: string;
  city: string;
  state: string;
  zip: string;
  lat: number;
  lon: number;
};

const DEPOT = { lat: 29.8306, lon: -95.4546 };
const STATE_ABBR: Record<string, string> = {
  Texas: "TX", Louisiana: "LA", Oklahoma: "OK", Arkansas: "AR", "New Mexico": "NM",
};

type PhotonFeature = {
  properties?: Record<string, string | undefined>;
  geometry?: { coordinates?: [number, number] };
};

export function shapeSuggestion(f: PhotonFeature, typed: string): AddressSuggestion {
  const p = f.properties || {};
  const num = p.housenumber || (/^\s*(\d+[A-Za-z]?)\s+/.exec(typed) || [])[1] || "";
  const street = p.street || (p.type === "street" ? p.name : "") || "";
  const place = p.type !== "street" && p.name && p.name !== street ? p.name : "";
  const line1 = [num, street].filter(Boolean).join(" ") || place;
  const [lon, lat] = f.geometry?.coordinates || [0, 0];
  return {
    line1,
    place: place && place !== line1 ? place : "",
    city: p.city || p.district || "",
    state: (p.state && STATE_ABBR[p.state]) || p.state || "",
    zip: p.postcode || "",
    lat,
    lon,
  };
}

export function shapeSuggestions(features: PhotonFeature[], typed: string): AddressSuggestion[] {
  const out = features
    .filter((f) => (f.properties || {}).country === "United States")
    .filter((f) => ["house", "street"].includes((f.properties || {}).type || ""))
    .map((f) => shapeSuggestion(f, typed))
    .filter((s) => s.line1 && s.zip);
  return out.filter((s, i) => out.findIndex((t) => t.line1 === s.line1 && t.zip === s.zip) === i);
}

export async function fetchAddressSuggestions(query: string, signal?: AbortSignal): Promise<AddressSuggestion[]> {
  const q = query.trim();
  if (q.length < 4) return [];
  const url = `https://photon.komoot.io/api/?q=${encodeURIComponent(q)}&limit=6&lang=en&lat=${DEPOT.lat}&lon=${DEPOT.lon}`;
  const res = await fetch(url, { signal });
  if (!res.ok) return [];
  const json = await res.json();
  return shapeSuggestions(Array.isArray(json?.features) ? json.features : [], q);
}

export function suggestionLabel(s: AddressSuggestion): string {
  return `${s.line1}${s.place ? ` (${s.place})` : ""} · ${[s.city, s.state].filter(Boolean).join(", ")} ${s.zip}`.trim();
}
