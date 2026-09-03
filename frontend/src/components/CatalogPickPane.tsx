import React, { useEffect, useRef, useState } from "react";
import { Package, Search, X } from "lucide-react";
import { apiFetch } from "utils/apiFetch";

// Catalog Search as a side pane: the buyer types what a need line says
// ("cream hydrangea"), sees catalog matches with picture, vendor, SKU and
// price, and picks one. Same endpoint as the Catalog Search page, so results
// and typo correction match what the team already trusts.

export interface CatalogPick {
  id: number;
  name: string;
  supplier_name?: string | null;
  supplier_sku?: string | null;
  current_price?: number | null;
  image_urls?: string[];
}

interface Props {
  title?: string;
  initialQuery?: string;
  onPick: (p: CatalogPick) => void;
  onClose: () => void;
  pickLabel?: string;
}

const proxied = (url?: string | null) =>
  url ? `/api/products/image-proxy?url=${encodeURIComponent(url)}` : undefined;
const money = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

export default function CatalogPickPane({ title, initialQuery, onPick, onClose, pickLabel }: Props) {
  const [q, setQ] = useState(initialQuery || "");
  const [items, setItems] = useState<CatalogPick[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [corrected, setCorrected] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const seq = useRef(0);

  useEffect(() => {
    if (timer.current) window.clearTimeout(timer.current);
    const term = q.trim();
    if (!term) { setItems([]); setTotal(0); return; }
    timer.current = window.setTimeout(async () => {
      const my = ++seq.current;
      setLoading(true);
      try {
        const r = await apiFetch(`/api/products/search?search=${encodeURIComponent(term)}&limit=30`);
        const data = r.ok ? await r.json() : { items: [], total: 0 };
        if (my !== seq.current) return;
        setItems(data.items || []);
        setTotal(data.total || 0);
        setCorrected(data.corrected ? data.searched_for : null);
      } finally {
        if (my === seq.current) setLoading(false);
      }
    }, 250);
    return () => { if (timer.current) window.clearTimeout(timer.current); };
  }, [q]);

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center justify-between border-b border-stone-200 px-4 py-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-stone-500">Catalog search</p>
          {title && <p className="text-sm font-medium text-stone-800">{title}</p>}
        </div>
        <button onClick={onClose} className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700" aria-label="Close">
          <X size={16} />
        </button>
      </div>
      <div className="px-4 py-3">
        <div className="flex items-center gap-2 rounded-lg border border-stone-300 bg-white px-2.5 py-1.5 focus-within:border-emerald-500">
          <Search size={14} className="text-stone-400" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="cream hydrangea, sage velvet ribbon, sugar pine cone…"
            className="w-full bg-transparent text-sm outline-none"
          />
        </div>
        <p className="mt-1.5 text-[11px] text-stone-400">
          {loading ? "Searching…" : q.trim() ? `${total.toLocaleString()} match${total === 1 ? "" : "es"}` : "Type what the need line says."}
          {corrected && <> · showing results for <b>{corrected}</b></>}
        </p>
      </div>
      <div className="flex-1 overflow-y-auto px-4 pb-4">
        <div className="flex flex-col gap-2">
          {items.map((p) => {
            const img = proxied(p.image_urls?.[0]);
            return (
              <div key={p.id} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-white p-2">
                <div className="flex h-16 w-16 shrink-0 items-center justify-center overflow-hidden rounded-md bg-stone-50">
                  {img ? <img src={img} alt="" className="h-full w-full object-contain" loading="lazy" /> : <Package size={20} className="text-stone-300" />}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-stone-800" title={p.name}>{p.name}</p>
                  <p className="truncate text-[11px] text-stone-500">
                    {p.supplier_name || "Unknown vendor"}{p.supplier_sku ? ` · ${p.supplier_sku}` : ""}
                  </p>
                  <p className="text-xs font-semibold text-emerald-800">{money(p.current_price)}</p>
                </div>
                <button
                  onClick={() => onPick(p)}
                  className="shrink-0 rounded-md bg-emerald-700 px-2.5 py-1.5 text-xs font-medium text-white hover:bg-emerald-800"
                >
                  {pickLabel || "Use this"}
                </button>
              </div>
            );
          })}
          {!loading && q.trim() && items.length === 0 && (
            <p className="py-8 text-center text-sm text-stone-400">Nothing matched. Try fewer words, or the vendor's wording.</p>
          )}
        </div>
      </div>
    </div>
  );
}
