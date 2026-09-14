// Click-to-edit current price control shown on a product card when the
// supplier hasn't given us a source price.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import React, { useRef, useState } from "react";
import { Pencil, Check, X } from "lucide-react";
import { apiClient } from "app";
import { toast } from "sonner";
import type { Product } from "./types";

// ─── Inline Price Editor ─────────────────────────────────────────────────────
export function InlinePriceEditor({ p, onUpdated }: { p: Product; onUpdated: (price: number, ts: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [val, setVal] = useState(p.current_price?.toString() ?? "");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const open = (e: React.MouseEvent) => {
    e.stopPropagation();
    setVal(p.current_price?.toString() ?? "");
    setEditing(true);
    setTimeout(() => inputRef.current?.select(), 30);
  };

  const save = async (e: React.MouseEvent | React.KeyboardEvent) => {
    e.stopPropagation();
    const price = parseFloat(val);
    if (isNaN(price) || price < 0) { setEditing(false); return; }
    setSaving(true);
    try {
      const res = await apiClient.sync_prices2({ productId: p.id }, { current_price: price });
      const data = await res.json();
      onUpdated(price, data.updated_at || new Date().toISOString());
      setEditing(false);
      toast.success("Price updated");
    } catch {
      toast.error("Failed to update price");
    } finally {
      setSaving(false);
    }
  };

  if (editing) {
    return (
      <div className="flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
        <span className="text-stone-400 text-sm">$</span>
        <input
          ref={inputRef}
          type="number"
          step="0.01"
          min="0"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") save(e); if (e.key === "Escape") setEditing(false); }}
          className="w-16 text-sm font-bold text-stone-800 border-b border-emerald-400 bg-transparent outline-none"
        />
        <button onClick={save} disabled={saving} className="text-emerald-600 hover:text-emerald-700">
          <Check size={13} />
        </button>
        <button onClick={(e) => { e.stopPropagation(); setEditing(false); }} className="text-stone-400 hover:text-stone-600">
          <X size={13} />
        </button>
      </div>
    );
  }

  return (
    <button
      onClick={open}
      className="text-left group/price flex items-baseline gap-1 hover:opacity-80 transition-opacity"
      title="Click to edit price"
    >
      <span className="text-base font-bold text-stone-800">{p.current_price != null ? `$${p.current_price.toFixed(2)}` : "—"}</span>
      <Pencil size={10} className="text-stone-300 group-hover/price:text-emerald-500 transition-colors mb-0.5" />
    </button>
  );
}
