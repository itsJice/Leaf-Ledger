// Oracle copies of the inline `Empty()` panels (verbatim apart from the name;
// empty-state.test.tsx checks them against the page source).
import { ClipboardList, ShoppingCart } from "lucide-react";

// pages/Sourcing.tsx
export function EmptySourcing() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
        <ClipboardList size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">No worksheet selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">Pick one on the left, or start a new one from the purple sheet.</p>
    </div>
  );
}

// pages/Orders.tsx
export function EmptyOrders() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
        <ShoppingCart size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">No order selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">
        Open a product in Catalog Search and use “Add to order”, or start a new one.
      </p>
    </div>
  );
}
