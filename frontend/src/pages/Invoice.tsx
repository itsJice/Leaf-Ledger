import React, { useEffect, useState, useRef } from "react";
import { useSearchParams } from "react-router-dom";
import { Printer, ChevronDown, FileText } from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { formatCurrency } from "utils/format";
import { toast } from "sonner";

type ArrangementSummary = { id: number; name: string; client_name?: string };
type ContainerItem = {
  id: number; product_name: string; product_category: string;
  unit: string; current_price?: number; supplier_name?: string;
  quantity: number; line_total?: number;
};
type Container = { id: number; label?: string; container_name?: string; items: ContainerItem[]; subtotal: number };
type Arrangement = {
  id: number; name: string; client_name?: string; notes?: string;
  containers: Container[]; total_cost: number; total_with_markup: number;
};
type MarkupSettings = { global_markup: number };

export default function Invoice() {
  const [searchParams, setSearchParams] = useSearchParams();
  const arrangementId = searchParams.get("arrangement_id") ? Number(searchParams.get("arrangement_id")) : null;

  const [arrangements, setArrangements] = useState<ArrangementSummary[]>([]);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [markup, setMarkup] = useState(30);
  const [loading, setLoading] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);

  // Auto-sync prices in background when invoice page opens
  useEffect(() => {
    apiClient.list_arrangements().then((r) => r.json()).then(setArrangements).catch(() => {});
    apiClient.get_markup_settings().then((r) => r.json()).then((d: MarkupSettings) => setMarkup(d.global_markup)).catch(() => {});
    // Silently sync prices for suppliers not refreshed in 23+ hours
    apiClient.sync_prices_bulk({ supplier_ids: null })
      .then((r) => r.json())
      .then((d: { message: string }) => {
        if (!d.message.includes("0 supplier")) {
          toast.info("🔄 Refreshing prices in background…", { duration: 3000 });
        }
      })
      .catch(() => {}); // Silent fail — never block the UI
  }, []);

  useEffect(() => {
    if (!arrangementId) { setArrangement(null); return; }
    setLoading(true);
    apiClient.get_arrangement({ arrangementId })
      .then((r) => r.json())
      .then(setArrangement)
      .catch(() => toast.error("Failed to load arrangement"))
      .finally(() => setLoading(false));
  }, [arrangementId]);

  const handlePrint = () => window.print();

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200 print:hidden" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Invoice</h1>
          <p className="text-xs text-stone-500 mt-0.5">Generate print-ready invoice from any arrangement</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="relative">
            <select
              className="appearance-none border border-stone-200 rounded-lg pl-3 pr-8 py-2 text-sm bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
              value={arrangementId || ""}
              onChange={(e) => setSearchParams(e.target.value ? { arrangement_id: e.target.value } : {})}
            >
              <option value="">Select arrangement...</option>
              {arrangements.map((a) => (
                <option key={a.id} value={a.id}>{a.name}{a.client_name ? ` — ${a.client_name}` : ""}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-2 top-1/2 -translate-y-1/2 text-stone-400 pointer-events-none" />
          </div>
          {arrangement && (
            <button
              onClick={handlePrint}
              className="flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-semibold text-white hover:opacity-90 transition-colors"
              style={{ backgroundColor: "#2d5a33" }}
            >
              <Printer size={14} /> Print / Export
            </button>
          )}
        </div>
      </header>

      <div className="px-10 py-8">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : !arrangement ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "#e8f0e8" }}>
              <FileText size={28} className="text-emerald-600" strokeWidth={1.5} />
            </div>
            <p className="text-base font-medium text-stone-600 mb-1">No arrangement selected</p>
            <p className="text-sm text-stone-400 max-w-xs leading-relaxed">Select an arrangement from the dropdown above to preview and print an invoice.</p>
          </div>
        ) : (
          <>
            {/* Stale price warning banner */}
            {hasStale && (
              <div className="flex items-start gap-3 max-w-3xl mx-auto mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 print:hidden">
                <AlertTriangle size={15} className="text-amber-500 mt-0.5 flex-shrink-0" />
                <div>
                  <p className="text-sm font-medium text-amber-800">Prices may be outdated</p>
                  <p className="text-xs text-amber-700 mt-0.5">
                    {staleItems.length} item{staleItems.length !== 1 ? "s" : ""} have prices that haven't been updated in {STALE_DAYS}+ days.
                    Consider syncing your supplier catalogs before sending this invoice.
                  </p>
                </div>
              </div>
            )}

            <div ref={printRef} className="bg-white rounded-2xl border border-stone-200 max-w-3xl mx-auto p-10 print:shadow-none print:border-0 print:rounded-none print:max-w-none">
            {/* Invoice header */}
            <div className="flex items-start justify-between mb-8 pb-6 border-b border-stone-200">
              <div>
                <h2 className="text-2xl font-bold text-stone-800 mb-1" style={{ fontFamily: "Georgia, serif" }}>Invoice</h2>
                <p className="text-sm text-stone-500">The Branch Design Group</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-stone-700">{arrangement.name}</p>
                {arrangement.client_name && <p className="text-sm text-stone-500">Client: {arrangement.client_name}</p>}
                <p className="text-xs text-stone-400 mt-1">{new Date().toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric" })}</p>
              </div>
            </div>

            {/* Containers */}
            {arrangement.containers.map((container) => (
              <div key={container.id} className="mb-8">
                <h3 className="text-sm font-semibold text-stone-700 mb-3" style={{ fontFamily: "Georgia, serif" }}>
                  {container.label || "Container"}{container.container_name ? ` — ${container.container_name}` : ""}
                </h3>
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-stone-200">
                      <th className="text-left pb-2 text-xs font-semibold text-stone-500 uppercase tracking-wider">Product</th>
                      <th className="text-left pb-2 text-xs font-semibold text-stone-500 uppercase tracking-wider">Supplier</th>
                      <th className="text-center pb-2 text-xs font-semibold text-stone-500 uppercase tracking-wider">Qty</th>
                      <th className="text-right pb-2 text-xs font-semibold text-stone-500 uppercase tracking-wider">Unit</th>
                      <th className="text-right pb-2 text-xs font-semibold text-stone-500 uppercase tracking-wider">Total</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-stone-50">
                    {container.items.map((item) => (
                      <tr key={item.id}>
                        <td className="py-2.5 font-medium text-stone-800">{item.product_name}</td>
                        <td className="py-2.5 text-stone-500">{item.supplier_name || "—"}</td>
                        <td className="py-2.5 text-center text-stone-600">{item.quantity}</td>
                        <td className="py-2.5 text-right text-stone-500">{formatCurrency(item.current_price)}</td>
                        <td className="py-2.5 text-right font-semibold text-stone-800">{formatCurrency(item.line_total)}</td>
                      </tr>
                    ))}
                  </tbody>
                  <tfoot>
                    <tr className="border-t border-stone-200">
                      <td colSpan={4} className="pt-2 text-xs text-stone-400 text-right">Container subtotal</td>
                      <td className="pt-2 text-right font-semibold text-stone-700">{formatCurrency(container.subtotal)}</td>
                    </tr>
                  </tfoot>
                </table>
              </div>
            ))}

            {/* Totals */}
            <div className="border-t-2 border-stone-800 pt-4 mt-4">
              <div className="flex items-center justify-between text-sm mb-1.5">
                <span className="text-stone-500">Subtotal (base cost)</span>
                <span className="font-medium text-stone-700">{formatCurrency(arrangement.total_cost)}</span>
              </div>
              <div className="flex items-center justify-between text-sm mb-3">
                <span className="text-stone-500">Markup ({markup}%)</span>
                <span className="font-medium text-stone-700">{formatCurrency(arrangement.total_with_markup - arrangement.total_cost)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-base font-bold text-stone-800">Total</span>
                <span className="text-xl font-bold text-stone-800">{formatCurrency(arrangement.total_with_markup)}</span>
              </div>
            </div>

            {arrangement.notes && (
              <div className="mt-6 pt-4 border-t border-stone-100">
                <p className="text-xs font-semibold text-stone-500 uppercase tracking-wider mb-1">Notes</p>
                <p className="text-sm text-stone-600 leading-relaxed">{arrangement.notes}</p>
              </div>
            )}
          </div>
          </>
        )}
      </div>
    </Layout>
  );
}
