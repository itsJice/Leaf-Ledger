import { describe, expect, it } from "vitest";
import { buildTypeIcon } from "../buildTypeIcon";
import { buildTypeIcon as designsCopy, buildTypeIconApp as appCopy } from "./inline-copies-3a";
import { readSrc, snippet } from "./source-text";

const INPUTS: Array<string | null | undefined> = [
  undefined, null, "", "   ", "Christmas Tree", "holiday tree", "Wreath", "Garland", "Horizontal Swag",
  "Vertical Spray", "Teardrop", "Door Drop", "Planter", "Container Garden", "Ornament", "Branch", "Stem",
  "Tree", "Fiddle Fig", "Centerpiece", "Orchid Arrangement", "Succulent", "Plant & Bush", "Bush", "Rug",
  "  WREATH  ", "Christmas Wreath",
];

describe("buildTypeIcon", () => {
  it("the oracle copies are verbatim page source", () => {
    const oracle = readSrc("utils/__tests__/inline-copies-3a.ts");
    const designs = readSrc("pages/Designs.tsx");
    expect(oracle).toContain(snippet(designs, "type IconComponent", "\n];\n"));
    expect(oracle).toContain(snippet(designs, "export function buildTypeIcon", "\n}\n"));
    const app = snippet(readSrc("pages/App.tsx"), "function buildTypeIcon", "\n}\n");
    expect(oracle).toContain(app.replace("function buildTypeIcon(", "function buildTypeIconApp("));
  });

  it("matches the Designs.tsx copy on every input", () => {
    expect(INPUTS.map(buildTypeIcon)).toEqual(INPUTS.map(designsCopy));
  });

  it("App.tsx's copy differs (older 3-rule mapping, Package fallback)", () => {
    const differing = INPUTS.filter((i) => buildTypeIcon(i) !== appCopy(i));
    expect(differing.length).toBeGreaterThan(0);
    expect(differing).toContain("Rug"); // Shapes vs Package
    expect(differing).toContain("Garland"); // Spline vs Package
    expect(buildTypeIcon("Christmas Tree")).toBe(appCopy("Christmas Tree")); // both TreePine
  });
});
