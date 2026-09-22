import { describe, expect, it } from "vitest";
import { proxiedImageUrl } from "../images";
import { proxiedCatalogPick, proxiedOrders, proxiedOrnament, proxiedSourcing } from "./inline-copies";

const PROXY_INPUTS: unknown[] = [
  "",
  "https://x.com/a.jpg",
  "http://x.com/a.jpg?b=1",
  "/relative/a.png",
  "data:image/png;base64,AAA",
  "https://x.com/a b#c&d=é",
  null,
  undefined,
];

describe("proxiedImageUrl", () => {
  for (const [name, copy] of Object.entries({ proxiedCatalogPick, proxiedSourcing, proxiedOrders, proxiedOrnament })) {
    it(`matches ${name} on every input`, () => {
      expect(PROXY_INPUTS.map((i) => proxiedImageUrl(i as string))).toEqual(PROXY_INPUTS.map((i) => copy(i as string)));
    });
  }

  it("pins falsy input to undefined and encodes the URL", () => {
    expect(proxiedImageUrl("")).toBeUndefined();
    expect(proxiedImageUrl(null)).toBeUndefined();
    expect(proxiedImageUrl("https://x.com/a.jpg")).toBe("/api/products/image-proxy?url=https%3A%2F%2Fx.com%2Fa.jpg");
  });
});
