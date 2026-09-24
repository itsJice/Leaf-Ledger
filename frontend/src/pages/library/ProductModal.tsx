// Add/edit product form modal (manual products, not supplier-synced ones).
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useRef, useState } from "react";
import { Upload, X } from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { apiClient } from "app";
import { toast } from "sonner";
import { categoryLabel, unitLabel } from "utils/format";
import { CATEGORIES, UNITS } from "./constants";
import type { Product, Supplier } from "./types";

// ─── Product Modal ────────────────────────────────────────────────────────────
export function ProductModal({
  product,
  suppliers,
  onClose,
  onSave,
}: {
  product: Partial<Product> | null;
  suppliers: Supplier[];
  onClose: () => void;
  onSave: (p: Product) => void;
}) {
  const [form, setForm] = useState<any>(
    product || { name: "", category: "greenery", unit: "stem", supplier_id: suppliers[0]?.id }
  );
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const set = (k: string, v: any) => setForm((f: any) => ({ ...f, [k]: v }));

  const uploadPhoto = async (file: File) => {
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      // Fix: the old path had no /api prefix and no auth header, so it always
      // 404'd/401'd. apiFetch adds the Bearer token and never sets a
      // Content-Type itself, so the browser still generates the multipart
      // boundary for this FormData body.
      const res = await apiFetch("/api/products/upload-photo-new", { method: "POST", body: fd });
      const data = await res.json();
      set("photo_url", data.photo_url);
    } catch {
      toast.error("Photo upload failed");
    } finally {
      setUploading(false);
    }
  };

  const handleSave = async () => {
    if (!form.name || !form.supplier_id) {
      toast.error("Name and supplier are required");
      return;
    }
    setSaving(true);
    try {
      let res;
      if (form.id) {
        res = await apiClient.update_product({ productId: form.id }, form);
      } else {
        res = await apiClient.create_product(form);
      }
      const saved = await res.json();
      onSave(saved);
      onClose();
      toast.success(form.id ? "Product updated" : "Product added");
    } catch {
      toast.error("Failed to save product");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 ll-overlay">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden ll-modal">
        <div className="flex items-center justify-between px-6 py-4 border-b border-stone-100">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            {form.id ? "Edit Product" : "Add Product"}
          </h2>
          <button onClick={onClose} className="text-stone-400 hover:text-stone-600">
            <X size={18} />
          </button>
        </div>
        <div className="px-6 py-5 space-y-4 max-h-[70vh] overflow-y-auto">
          {/* Photo */}
          <div className="flex items-center gap-4">
            <div
              className="w-20 h-20 rounded-xl border-2 border-dashed border-stone-200 flex items-center justify-center overflow-hidden flex-shrink-0 cursor-pointer hover:border-emerald-400 transition-colors"
              onClick={() => fileRef.current?.click()}
            >
              {form.photo_url ? (
                <img src={form.photo_url} alt="product" className="w-full h-full object-cover" />
              ) : uploading ? (
                <div className="w-4 h-4 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
              ) : (
                <Upload size={18} className="text-stone-300" />
              )}
            </div>
            <div className="text-xs text-stone-500 leading-relaxed">
              <p className="font-medium text-stone-600 mb-1">Product photo</p>
              <p>Click the box to upload an image</p>
            </div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={(e) => e.target.files?.[0] && uploadPhoto(e.target.files[0])} />
          </div>
          {/* Name */}
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Product name *</label>
            <input
              className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
              value={form.name || ""}
              onChange={(e) => set("name", e.target.value)}
              placeholder="e.g. Monstera Deliciosa"
            />
          </div>
          {/* Supplier */}
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Supplier *</label>
            <select
              className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
              value={form.supplier_id || ""}
              onChange={(e) => set("supplier_id", Number(e.target.value))}
            >
              <option value="">Select supplier</option>
              {suppliers.map((s) => (
                <option key={s.id} value={s.id}>{s.name}</option>
              ))}
            </select>
          </div>
          {/* Category + Unit */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1">Category</label>
              <select
                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                value={form.category || "greenery"}
                onChange={(e) => set("category", e.target.value)}
              >
                {CATEGORIES.map((c) => <option key={c} value={c}>{categoryLabel(c)}</option>)}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-stone-600 mb-1">Unit</label>
              <select
                className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                value={form.unit || "stem"}
                onChange={(e) => set("unit", e.target.value)}
              >
                {UNITS.map((u) => <option key={u} value={u}>{unitLabel(u)}</option>)}
              </select>
            </div>
          </div>
          {/* Price */}
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Current price ($)</label>
            <input
              type="number"
              step="0.01"
              min="0"
              className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
              value={form.current_price || ""}
              onChange={(e) => set("current_price", parseFloat(e.target.value))}
              placeholder="0.00"
            />
          </div>
          {/* Description */}
          <div>
            <label className="block text-xs font-medium text-stone-600 mb-1">Description</label>
            <textarea
              rows={3}
              className="w-full border border-stone-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300 resize-none"
              value={form.description || ""}
              onChange={(e) => set("description", e.target.value)}
              placeholder="Optional notes about this product"
            />
          </div>
        </div>
        <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-stone-100">
          <button onClick={onClose} className="text-sm text-stone-500 hover:text-stone-700 px-4 py-2">Cancel</button>
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2 text-sm font-semibold text-white rounded-lg disabled:opacity-60 transition-colors hover:opacity-90"
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
          >
            {saving ? "Saving..." : form.id ? "Update" : "Add Product"}
          </button>
        </div>
      </div>
    </div>
  );
}
