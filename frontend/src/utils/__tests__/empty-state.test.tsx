import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ClipboardList, ShoppingCart } from "lucide-react";
import EmptyState from "../../components/EmptyState";
import { EmptyOrders, EmptySourcing } from "./inline-copies-3a-jsx";
import { readSrc, snippet } from "./source-text";

describe("EmptyState", () => {
  it("the oracle copies are verbatim page source", () => {
    const oracle = readSrc("utils/__tests__/inline-copies-3a-jsx.tsx");
    const sourcing = snippet(readSrc("pages/Sourcing.tsx"), "function Empty()", "\n}\n");
    const orders = snippet(readSrc("pages/Orders.tsx"), "function Empty()", "\n}\n");
    expect(oracle).toContain(sourcing.replace("function Empty()", "function EmptySourcing()"));
    expect(oracle).toContain(orders.replace("function Empty()", "function EmptyOrders()"));
  });

  it("renders the same markup as Sourcing.tsx Empty()", () => {
    expect(
      renderToStaticMarkup(
        <EmptyState icon={ClipboardList} title="No worksheet selected" description="Pick one on the left, or start a new one from the purple sheet." />,
      ),
    ).toBe(renderToStaticMarkup(<EmptySourcing />));
  });

  it("renders the same markup as Orders.tsx Empty()", () => {
    expect(
      renderToStaticMarkup(
        <EmptyState icon={ShoppingCart} title="No order selected" description="Open a product in Catalog Search and use “Add to order”, or start a new one." />,
      ),
    ).toBe(renderToStaticMarkup(<EmptyOrders />));
  });

  it("className overrides the wrapper only", () => {
    const html = renderToStaticMarkup(<EmptyState icon={ShoppingCart} title="t" description="d" className="py-8" />);
    expect(html.startsWith('<div class="py-8"><div class="mb-4 flex h-16 w-16')).toBe(true);
  });
});
