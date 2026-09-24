import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ClipboardList, ShoppingCart } from "components/icons";
import EmptyState from "../../components/EmptyState";
import { EmptyOrders, EmptySourcing } from "./inline-copies-3a-jsx";

// pages/Sourcing.tsx and pages/Orders.tsx now render their "nothing selected"
// panel through EmptyState directly (see their local `Empty` wrappers), so
// there's no page source left to diff against. These oracle copies (verbatim
// snapshots of what the inline markup used to be) still pin the exact props
// each page must pass to reproduce that markup byte-for-byte.
describe("EmptyState", () => {
  it("renders the same markup as Sourcing.tsx's Empty", () => {
    expect(
      renderToStaticMarkup(
        <EmptyState icon={ClipboardList} title="No worksheet selected" description="Pick one on the left, or start a new one from the purple sheet." />,
      ),
    ).toBe(renderToStaticMarkup(<EmptySourcing />));
  });

  it("renders the same markup as Orders.tsx's Empty", () => {
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
