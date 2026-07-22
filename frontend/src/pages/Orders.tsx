import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  ShoppingCart, Plus, Minus, Trash2, ExternalLink, Package, LogIn,
  FileText, FileSpreadsheet, FileType, Printer,
} from "lucide-react";
import Layout from "components/Layout";
import { ProductDetailModal } from "./Library";
import {
  listOrders, getOrder, createOrder, deleteOrder, updateItemQty, removeItem,
  setActiveOrderId, getActiveOrderId, defaultOrderName,
  type OrderSummary, type OrderDetail,
} from "utils/orders";
import { toast } from "sonner";

function proxied(url?: string | null): string | undefined {
  if (!url) return undefined;
  return `/api/products/image-proxy?url=${encodeURIComponent(url)}`;
}
const money = (n?: number | null) => (n == null ? "—" : `$${Number(n).toFixed(2)}`);

export default function Orders() {
  const [orders, setOrders] = useState<OrderSummary[]>([]);
  const [activeId, setActiveId] = useState<number | null>(getActiveOrderId());
  const [order, setOrder] = useState<OrderDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [detailId, setDetailId] = useState<number | null>(null);
  const [detailProduct, setDetailProduct] = useState<any | null>(null);

  const refreshList = useCallback(async () => {
    const list = await listOrders();
    setOrders(list);
    setActiveId((cur) => (cur && list.some((o) => o.id === cur) ? cur : list[0]?.id ?? null));
  }, []);

  useEffect(() => { refreshList(); }, [refreshList]);

  const loadOrder = useCallback(async (id: number) => {
    setLoading(true);
    try { setOrder(await getOrder(id)); }
    catch { setOrder(null); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    if (activeId) { setActiveOrderId(activeId); loadOrder(activeId); }
    else setOrder(null);
  }, [activeId, loadOrder]);

  const openProduct = useCallback((id: number) => {
    setDetailId(id);
    fetch(`/api/products/detail/${id}`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setDetailProduct).catch(() => {});
  }, []);

  const newOrder = async () => {
    const created = await createOrder(defaultOrderName());
    await refreshList();
    setActiveId(created.id);
    toast.success(`Created “${created.name}”`);
  };

  const removeOrder = async (id: number) => {
    await deleteOrder(id);
    if (activeId === id) setActiveId(null);
    await refreshList();
    toast.success("Order deleted");
  };

  const changeQty = async (itemId: number, qty: number) => {
    // optimistic
    setOrder((o) => o && applyQty(o, itemId, qty));
    await updateItemQty(itemId, qty);
    if (activeId) { loadOrder(activeId); refreshList(); }
  };
  const dropItem = async (itemId: number) => {
    setOrder((o) => o && dropLine(o, itemId));
    await removeItem(itemId);
    if (activeId) { loadOrder(activeId); refreshList(); }
  };

  const exportUrl = (format: string, supplierId?: number | null) => {
    const q = new URLSearchParams({ format });
    if (supplierId != null) q.set("supplier_id", String(supplierId));
    return `/api/orders/${activeId}/export?${q.toString()}`;
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-8 py-4" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            <ShoppingCart size={18} className="text-emerald-700" /> Purchase Orders
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            Grouped by vendor — ready to order or export as a PO.
          </p>
        </div>
        <button onClick={newOrder} className="inline-flex items-center gap-1.5 rounded-lg bg-emerald-700 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-800">
          <Plus size={15} /> New order
        </button>
      </header>

      <div className="flex">
        {/* Orders rail */}
        <aside className="w-64 flex-shrink-0 border-r border-stone-200 px-3 py-4" style={{ minHeight: "calc(100vh - 65px)" }}>
          <p className="mb-2 px-2 text-xs font-semibold uppercase tracking-widest text-stone-500">Orders ({orders.length})</p>
          {orders.length === 0 ? (
            <p className="px-2 text-sm text-stone-400">No orders yet. Add products from the catalog, or start one.</p>
          ) : (
            <div className="flex flex-col gap-1">
              {orders.map((o) => {
                const active = o.id === activeId;
                return (
                  <button key={o.id} onClick={() => setActiveId(o.id)}
                    className={`group flex flex-col rounded-lg px-3 py-2 text-left ${active ? "bg-emerald-50 ring-1 ring-emerald-200" : "hover:bg-stone-100"}`}>
                    <span className={`truncate text-sm font-medium ${active ? "text-emerald-900" : "text-stone-700"}`}>{o.name}</span>
                    <span className="mt-0.5 text-xs text-stone-400">
                      {o.total_qty} item{o.total_qty === 1 ? "" : "s"} · {o.vendor_count} vendor{o.vendor_count === 1 ? "" : "s"} · {money(o.total_cost)}
                    </span>
                  </button>
                );
              })}
            </div>
          )}
        </aside>

        {/* Order detail */}
        <main className="flex-1 px-8 py-6">
          {!activeId ? (
            <Empty />
          ) : loading && !order ? (
            <p className="py-20 text-center text-sm text-stone-400">Loading order…</p>
          ) : !order ? (
            <Empty />
          ) : order.vendors.length === 0 ? (
            <div className="py-20 text-center">
              <Package className="mx-auto mb-3 text-stone-300" size={32} />
              <p className="text-sm text-stone-500">“{order.name}” is empty.</p>
              <p className="mt-1 text-xs text-stone-400">Open a product in the catalog and use “Add to order”.</p>
              <button onClick={() => removeOrder(order.id)} className="mt-4 inline-flex items-center gap-1.5 text-xs font-medium text-rose-600 hover:text-rose-800">
                <Trash2 size={12} /> Delete this order
              </button>
            </div>
          ) : (
            <>
              {/* Order toolbar */}
              <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h2 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{order.name}</h2>
                  <p className="text-xs text-stone-500">
                    {order.total_qty} items · {order.vendor_count} vendors · <span className="font-semibold text-emerald-800">{money(order.total_cost)}</span> total
                  </p>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  <a href={exportUrl("pdf")} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700"><FileText size={13} /> PDF</a>
                  <a href={exportUrl("docx")} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700"><FileType size={13} /> Word</a>
                  <a href={exportUrl("xlsx")} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700"><FileSpreadsheet size={13} /> Excel</a>
                  <button onClick={() => window.print()} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-300 px-2.5 py-1.5 text-xs font-medium text-stone-600 hover:border-emerald-400 hover:text-emerald-700"><Printer size={13} /> Print</button>
                  <button onClick={() => removeOrder(order.id)} className="inline-flex items-center gap-1.5 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs font-medium text-rose-600 hover:border-rose-300"><Trash2 size={13} /> Delete</button>
                </div>
              </div>

              {/* Vendor groups */}
              <div className="flex flex-col gap-6">
                {order.vendors.map((v) => (
                  <div key={v.supplier_id ?? v.supplier_name} className="overflow-hidden rounded-xl border border-stone-200 bg-white">
                    <div className="flex items-center justify-between gap-3 border-b border-stone-100 bg-stone-50 px-4 py-2.5">
                      <div className="flex items-center gap-3">
                        <span className="font-semibold text-stone-800">{v.supplier_name}</span>
                        <span className="text-xs text-stone-400">{v.subtotal_qty} item{v.subtotal_qty === 1 ? "" : "s"}</span>
                        {v.supplier_login_url && (
                          <a href={v.supplier_login_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 hover:underline"><LogIn size={11} /> Log in</a>
                        )}
                        <a href={exportUrl("pdf", v.supplier_id)} className="text-xs text-stone-400 hover:text-emerald-700" title="Export this vendor's PO as PDF">PO ↓</a>
                      </div>
                      <span className="text-sm font-semibold text-emerald-800">{money(v.subtotal)}</span>
                    </div>
                    <div className="overflow-x-auto">
                    <table className="w-full min-w-[640px] text-sm">
                      <thead>
                        <tr className="text-left text-[11px] uppercase tracking-wide text-stone-400">
                          <th className="px-4 py-2 font-medium">Product</th>
                          <th className="px-2 py-2 font-medium">SKU</th>
                          <th className="px-2 py-2 font-medium">Size</th>
                          <th className="px-2 py-2 text-center font-medium">Qty</th>
                          <th className="px-2 py-2 text-right font-medium">Unit</th>
                          <th className="px-2 py-2 text-right font-medium">Total</th>
                          <th className="px-2 py-2"></th>
                        </tr>
                      </thead>
                      <tbody>
                        {v.items.map((it) => {
                          const img = proxied(it.image_url);
                          return (
                            <tr key={it.item_id} className="border-t border-stone-100 align-middle">
                              <td className="px-4 py-2">
                                <div className="flex items-center gap-3">
                                  <button onClick={() => openProduct(it.product_id)} className="flex h-11 w-11 shrink-0 items-center justify-center overflow-hidden rounded-md border border-stone-200 bg-stone-50">
                                    {img ? <img src={img} alt="" className="h-full w-full object-contain" /> : <Package size={16} className="text-stone-300" />}
                                  </button>
                                  <div className="min-w-0">
                                    <button onClick={() => openProduct(it.product_id)} className="block max-w-[22rem] truncate text-left font-medium text-stone-800 hover:text-emerald-700" title={it.name}>{it.name}</button>
                                    {it.product_url && (
                                      <a href={it.product_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 text-[11px] text-stone-400 hover:text-emerald-700"><ExternalLink size={10} /> View on site</a>
                                    )}
                                  </div>
                                </div>
                              </td>
                              <td className="px-2 py-2 font-mono text-[11px] text-stone-500">{it.sku || "—"}</td>
                              <td className="px-2 py-2 text-stone-500">{it.size || "—"}</td>
                              <td className="px-2 py-2">
                                <div className="mx-auto flex w-fit items-center rounded-md border border-stone-300">
                                  <button onClick={() => changeQty(it.item_id, Math.max(1, it.quantity - 1))} className="px-1.5 py-1 text-stone-500 hover:text-stone-800" aria-label="Decrease"><Minus size={12} /></button>
                                  <input type="number" min={1} value={it.quantity}
                                    onChange={(e) => changeQty(it.item_id, Math.max(1, Number(e.target.value) || 1))}
                                    className="w-11 border-x border-stone-200 py-1 text-center text-sm outline-none" />
                                  <button onClick={() => changeQty(it.item_id, it.quantity + 1)} className="px-1.5 py-1 text-stone-500 hover:text-stone-800" aria-label="Increase"><Plus size={12} /></button>
                                </div>
                              </td>
                              <td className="px-2 py-2 text-right text-stone-600">{money(it.unit_price)}</td>
                              <td className="px-2 py-2 text-right font-medium text-stone-800">{money(it.line_total)}</td>
                              <td className="px-2 py-2 text-right">
                                <button onClick={() => dropItem(it.item_id)} className="text-stone-300 hover:text-rose-600" aria-label="Remove"><Trash2 size={15} /></button>
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                    </div>
                  </div>
                ))}
              </div>

              <div className="mt-6 flex justify-end border-t border-stone-200 pt-4">
                <div className="text-right">
                  <p className="text-xs uppercase tracking-wide text-stone-400">Order total</p>
                  <p className="text-2xl font-semibold text-emerald-800">{money(order.total_cost)}</p>
                </div>
              </div>
            </>
          )}
        </main>
      </div>

      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={() => { setDetailProduct(null); setDetailId(null); if (activeId) loadOrder(activeId); }} />
      )}
    </Layout>
  );
}

function Empty() {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "#eef6ef" }}>
        <ShoppingCart size={28} className="text-emerald-600" strokeWidth={1.5} />
      </div>
      <p className="mb-1 text-base font-medium text-stone-600">No order selected</p>
      <p className="max-w-xs text-sm leading-relaxed text-stone-400">
        Open a product in Catalog Search or the Library and use “Add to order”, or start a new one.
      </p>
    </div>
  );
}

function applyQty(o: OrderDetail, itemId: number, qty: number): OrderDetail {
  return {
    ...o,
    vendors: o.vendors.map((v) => ({
      ...v,
      items: v.items.map((it) => (it.item_id === itemId
        ? { ...it, quantity: qty, line_total: it.unit_price != null ? it.unit_price * qty : null }
        : it)),
    })),
  };
}
function dropLine(o: OrderDetail, itemId: number): OrderDetail {
  return {
    ...o,
    vendors: o.vendors
      .map((v) => ({ ...v, items: v.items.filter((it) => it.item_id !== itemId) }))
      .filter((v) => v.items.length > 0),
  };
}
