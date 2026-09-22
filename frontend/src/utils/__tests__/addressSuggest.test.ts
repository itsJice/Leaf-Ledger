import { describe, expect, it } from "vitest";
import { shapeSuggestions, suggestionLabel } from "../addressSuggest";

const street = (name: string, postcode: string) => ({
  properties: { name, city: "Houston", postcode, state: "Texas", country: "United States", type: "street" },
  geometry: { coordinates: [-95.42, 29.75] as [number, number] },
});

describe("shapeSuggestions", () => {
  it("keeps the typed house number on a street-level match and fills city/state/zip", () => {
    const [s] = shapeSuggestions([street("Inwood Drive", "77019")], "3640 Inwood Drive");
    expect(s).toMatchObject({ line1: "3640 Inwood Drive", city: "Houston", state: "TX", zip: "77019", lat: 29.75, lon: -95.42 });
    expect(suggestionLabel(s)).toBe("3640 Inwood Drive · Houston, TX 77019");
  });

  it("uses the match's own house number and shows a named place", () => {
    const [s] = shapeSuggestions([{
      properties: { name: "Four Seasons Hotel", housenumber: "1300", street: "Lamar Street", city: "Houston",
        postcode: "77010", state: "Texas", country: "United States", type: "house" },
      geometry: { coordinates: [-95.36, 29.75] },
    }], "1300 Lamar");
    expect(s.line1).toBe("1300 Lamar Street");
    expect(suggestionLabel(s)).toBe("1300 Lamar Street (Four Seasons Hotel) · Houston, TX 77010");
  });

  it("drops non-US, non-address and zipless results and de-duplicates", () => {
    const out = shapeSuggestions([
      street("Inwood Drive", "77019"),
      street("Inwood Drive", "77019"),
      { properties: { name: "Inwood", country: "United States", type: "city", state: "Texas" } },
      { properties: { name: "Inwood Drive", country: "Canada", type: "street", postcode: "X" } },
      { properties: { name: "Nowhere Road", country: "United States", type: "street", state: "Texas" } },
    ], "3640 Inwood");
    expect(out.map((s) => `${s.line1}|${s.zip}`)).toEqual(["3640 Inwood Drive|77019"]);
  });
});
