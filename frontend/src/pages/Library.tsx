import React, { useEffect, useState, useRef, useCallback, useMemo } from "react";
import {
  Search,
  Plus,
  Heart,
  Upload,
  Pencil,
  Trash2,
  X,
  ChevronDown,
  Leaf,
  Grid3X3,
  Store,
  ChevronRight,
  Package,
  Check,
  AlertTriangle,
  RefreshCw,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { formatCurrency, formatDate, categoryLabel, unitLabel } from "utils/format";
import { readFavoriteIds, setLocalFavorite } from "utils/favorites";
import { toast } from "sonner";

const CATEGORIES = ["containers", "wood", "greenery", "florals", "trees"];
const UNITS = ["stem", "pot", "flat", "bunch", "each"];
const INITIAL_CARD_RENDER_LIMIT = 96;
const KNOWN_COLOR_WORDS = [
  "aqua", "beige", "black", "blue", "blush", "bronze", "brown", "burgundy", "camel",
  "charcoal", "cinnamon", "clear", "coffee", "copper", "coral", "cream", "crimson",
  "delphinium", "flame", "gold", "gray", "green", "honey", "indigo", "iridescent",
  "ivory", "lavender", "lilac", "lime", "mauve", "mint", "moss", "mustard", "olive",
  "orange", "orchid", "peach", "peacock", "pearl", "pink", "platinum", "purple",
  "red", "rose", "royal", "rubrum", "salmon", "seafoam", "silver", "smoke", "tan",
  "taupe", "teal", "tomato", "turquoise", "violet", "white", "yellow",
];
const ALLSTATE_COLOR_CODE_MAP: Record<string, string[]> = {
  AQ: ["Aqua"],
  BE: ["Beige"],
  BK: ["Black"],
  BL: ["Blue"],
  BR: ["Brown"],
  BU: ["Blue"],
  CL: ["Clear"],
  CP: ["Copper"],
  CR: ["Cream"],
  CW: ["Clear", "White"],
  FS: ["Frost", "Silver"],
  GO: ["Gold"],
  GR: ["Green"],
  GY: ["Gray"],
  IV: ["Ivory"],
  LV: ["Lavender"],
  MO: ["Moss"],
  MX: ["Mixed"],
  OR: ["Orange"],
  PE: ["Pearl"],
  PK: ["Pink"],
  PU: ["Purple"],
  RE: ["Red"],
  RO: ["Rose"],
  SI: ["Silver"],
  TA: ["Tan"],
  TE: ["Teal"],
  WH: ["White"],
  YL: ["Yellow"],
};
const AVAILABILITY_FILTERS = [
  "Available today",
  "Within 1-4 months",
  "Over 4 months",
  "Sold out / unavailable",
  "Future ETA",
] as const;
const LIBRARY_CACHE_KEY = "leaf-ledger:library-cache:v1";
const LIBRARY_CACHE_RAW_KEYS = [
  "Description",
  "ColorGrp",
  "Season",
  "Class",
  "Material Breakdown",
  "Country of Origin",
  "Avail. Qty",
  "Avail. Qty: *",
  "ProdLength",
  "ProdWeight",
  "BoxWeight",
  "CsWeight",
  "Box LxWxH",
  "Case LxWxH",
  "CaseCube",
  "Oversize",
  "SugRetail",
  "UPC",
  "MinQty",
  "BoxQty",
  "CaseQty",
  "CatalogVol",
  "CatPage",
  "P-CatVol",
  "P-CatPage",
  "allstate_subcategory",
  "Item No",
  "detail_status",
  "image_status",
];
const PRODUCT_TYPE_RULES: Array<{ label: string; keywords: string[] }> = [
  { label: "Ribbon", keywords: [" ribbon ", " trim ", " bow "] },
  { label: "Spray", keywords: [" spray "] },
  { label: "Pick", keywords: [" pick "] },
  { label: "Ornament", keywords: [" ornament ", " finial ", " topper "] },
  { label: "Wreath", keywords: [" wreath "] },
  { label: "Garland", keywords: [" garland "] },
  { label: "Tree", keywords: [" tree "] },
  { label: "Stem", keywords: [" stem "] },
  { label: "Bush", keywords: [" bush "] },
  { label: "Bundle", keywords: [" bundle "] },
  { label: "Floral", keywords: [" floral ", " flower ", " bloom "] },
  { label: "Container", keywords: [" vase ", " pot ", " planter ", " container ", " bowl ", " urn "] },
];

export type Product = {
  id: number;
  supplier_sku?: string;
  name: string;
  description?: string;
  category: string;
  unit: string;
  current_price?: number;
  price_updated_at?: string;
  photo_url?: string;
  supplier_id: number;
  supplier_name?: string;
  moq?: number;
  box_qty?: number;
  case_qty?: number;
  availability?: string;
  availability_note?: string;
  upc?: string;
  length_in?: number;
  weight_lb?: number;
  material?: string;
  color?: string;
  country_of_origin?: string;
  raw_data?: Record<string, any>;
  is_favorited: boolean;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

type Supplier = { id: number; name: string; website_url?: string; categories: string[] };
type ProjectSummary = {
  id: number;
  name: string;
  client_name?: string;
  container_count: number;
};
type ProjectBucket = {
  id: number;
  label?: string;
  sort_order: number;
};
type ProjectDetail = {
  id: number;
  name: string;
  client_name?: string;
  containers: ProjectBucket[];
};
type ProductSearchEntry = {
  product: Product;
  category: string;
  categoryLabel: string;
  supplierName: string;
  productTypes: string[];
  colors: string[];
  sizes: string[];
  availability?: string;
  country?: string;
  searchText: string;
  codeText: string;
  sortName: string;
  isFavorited: boolean;
};

function trimRawDataForCache(raw?: Record<string, any> | null) {
  if (!raw) return {};
  const trimmed: Record<string, any> = {};
  for (const key of LIBRARY_CACHE_RAW_KEYS) {
    if (raw[key] !== undefined) trimmed[key] = raw[key];
  }
  return trimmed;
}

function trimProductForCache(product: Product): Product {
  return {
    ...product,
    raw_data: trimRawDataForCache(product.raw_data),
  };
}

function readLibraryCache(): { suppliers: Supplier[]; products: Product[] } | null {
  try {
    const raw = localStorage.getItem(LIBRARY_CACHE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed?.products) || !Array.isArray(parsed?.suppliers)) return null;
    return { suppliers: parsed.suppliers, products: parsed.products };
  } catch {
    return null;
  }
}

function writeLibraryCache(suppliers: Supplier[], products: Product[]) {
  try {
    const payload = {
      suppliers,
      products: products.map(trimProductForCache),
      cachedAt: Date.now(),
    };
    localStorage.setItem(LIBRARY_CACHE_KEY, JSON.stringify(payload));
  } catch {
    // Ignore cache quota/storage issues.
  }
}

function applyLocalFavoriteState(products: Product[]): Product[] {
  const favoriteIds = readFavoriteIds();
  return products.map((product) => ({
    ...product,
    is_favorited: product.is_favorited || favoriteIds.has(product.id),
  }));
}

async function addProductToBucket(containerId: number, productId: number, status: "candidate" | "selected" = "candidate") {
  await apiClient.add_item_to_container(
    { containerId },
    { product_id: productId, quantity: 1, status } as any
  );
}

function notifyProjectsChanged() {
  window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
}

// ─── Product Modal ────────────────────────────────────────────────────────────
function ProductModal({
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
      const res = await fetch("/routes/products/upload-photo-new", { method: "POST", body: fd });
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg mx-4 overflow-hidden">
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
            style={{ backgroundColor: "#2d5a33" }}
          >
            {saving ? "Saving..." : form.id ? "Update" : "Add Product"}
          </button>
        </div>
      </div>
    </div>
  );
}

function AddToProjectModal({
  product,
  onClose,
}: {
  product: Product;
  onClose: () => void;
}) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [selectedBucketId, setSelectedBucketId] = useState<number | null>(null);
  const [newBucketName, setNewBucketName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    apiClient.list_arrangements()
      .then((r) => r.json())
      .then((rows: ProjectSummary[]) => {
        setProjects(rows);
        if (rows[0]) setSelectedProjectId(rows[0].id);
      })
      .catch(() => toast.error("Could not load projects"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!selectedProjectId) {
      setProject(null);
      setSelectedBucketId(null);
      return;
    }
    apiClient.get_arrangement({ arrangementId: selectedProjectId })
      .then((r) => r.json())
      .then((detail: ProjectDetail) => {
        setProject(detail);
        setSelectedBucketId(detail.containers[0]?.id ?? null);
      })
      .catch(() => toast.error("Could not load project buckets"));
  }, [selectedProjectId]);

  const createBucket = async () => {
    if (!selectedProjectId || !newBucketName.trim()) return;
    setSaving(true);
    try {
      const res = await apiClient.add_container(
        { arrangementId: selectedProjectId },
        { label: newBucketName.trim(), items: [] }
      );
      const detail = await res.json();
      setProject(detail);
      const created = detail.containers[detail.containers.length - 1];
      setSelectedBucketId(created?.id ?? null);
      setNewBucketName("");
      notifyProjectsChanged();
      toast.success("Bucket created");
    } catch {
      toast.error("Could not create bucket");
    } finally {
      setSaving(false);
    }
  };

  const addToBucket = async () => {
    if (!selectedBucketId) {
      toast.error("Choose or create a bucket first");
      return;
    }
    setSaving(true);
    try {
      await addProductToBucket(selectedBucketId, product.id, "candidate");
      notifyProjectsChanged();
      toast.success(`Saved ${displayProductName(product)} to project`);
      onClose();
    } catch {
      toast.error("Could not add product to project");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-start justify-between border-b border-stone-100 px-5 py-4">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Add to project</p>
            <h2 className="mt-1 text-sm font-semibold text-stone-800 line-clamp-2">{displayProductName(product)}</h2>
            <p className="text-xs text-stone-400">{product.supplier_sku}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-700">
            <X size={17} />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          {loading ? (
            <div className="flex justify-center py-8">
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
            </div>
          ) : projects.length === 0 ? (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-800">
              Create a project first, then use + to save products into its buckets.
            </div>
          ) : (
            <>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-stone-500">Project</span>
                <select
                  value={selectedProjectId ?? ""}
                  onChange={(e) => setSelectedProjectId(Number(e.target.value))}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.client_name ? `${p.client_name} · ${p.name}` : p.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-stone-500">Bucket</span>
                <select
                  value={selectedBucketId ?? ""}
                  onChange={(e) => setSelectedBucketId(Number(e.target.value))}
                  className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                >
                  {project?.containers.length ? (
                    project.containers.map((bucket) => (
                      <option key={bucket.id} value={bucket.id}>
                        {bucket.label || `Bucket ${bucket.sort_order + 1}`}
                      </option>
                    ))
                  ) : (
                    <option value="">No buckets yet</option>
                  )}
                </select>
              </label>
              <div className="flex gap-2">
                <input
                  value={newBucketName}
                  onChange={(e) => setNewBucketName(e.target.value)}
                  placeholder="New bucket, e.g. Tree 1"
                  className="min-w-0 flex-1 rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                />
                <button
                  onClick={createBucket}
                  disabled={saving || !newBucketName.trim()}
                  className="rounded-lg border border-stone-200 px-3 py-2 text-sm font-semibold text-stone-600 hover:border-emerald-300 hover:text-emerald-700 disabled:opacity-50"
                >
                  Create
                </button>
              </div>
            </>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-stone-100 px-5 py-4">
          <button onClick={onClose} className="rounded-lg px-4 py-2 text-sm font-medium text-stone-500 hover:text-stone-800">
            Cancel
          </button>
          <button
            onClick={addToBucket}
            disabled={saving || projects.length === 0}
            className="rounded-lg px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            style={{ backgroundColor: "#2d5a33" }}
          >
            {saving ? "Saving..." : "Save to bucket"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Category colour dots ─────────────────────────────────────────────────────
const CATEGORY_COLORS: Record<string, string> = {
  containers: "#a16207",
  wood: "#92400e",
  greenery: "#15803d",
  florals: "#be185d",
  trees: "#166534",
};

// ─── Stale price check ───────────────────────────────────────────────────────
const STALE_DAYS = 30;
function isPriceStale(price_updated_at?: string | null): boolean {
  if (!price_updated_at) return true;
  const diffMs = Date.now() - new Date(price_updated_at).getTime();
  return diffMs > STALE_DAYS * 24 * 60 * 60 * 1000;
}

// ─── Inline Price Editor ─────────────────────────────────────────────────────
function InlinePriceEditor({ p, onUpdated }: { p: Product; onUpdated: (price: number, ts: string) => void }) {
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
      const res = await apiClient.sync_prices2({ productId: p.id }, { new_price: price });
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

// ─── Image with proxy fallback ───────────────────────────────────────────────
function ImagePending({ compact = false }: { compact?: boolean }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-stone-100 text-stone-400">
      <Leaf size={compact ? 14 : 28} strokeWidth={1.2} />
      {!compact && <span className="text-[11px] font-medium">Image pending</span>}
    </div>
  );
}

function ProxiedImage({ src, alt }: { src: string; alt: string }) {
  const [usedProxy, setUsedProxy] = useState(false);
  const [failed, setFailed] = useState(false);
  const normalizedSrc = src.startsWith("/routes/")
    ? src.replace(/^\/routes\//, "/api/")
    : src;
  const isInternalProxy = normalizedSrc.startsWith("/api/products/image-proxy?");
  const proxySrc = isInternalProxy ? normalizedSrc : `/api/products/image-proxy?url=${encodeURIComponent(normalizedSrc)}`;
  if (failed) return <ImagePending />;
  return (
    <img
      src={usedProxy && !isInternalProxy ? proxySrc : normalizedSrc}
      alt={alt}
      loading="lazy"
      decoding="async"
      className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"
      onError={() => {
        if (!usedProxy && !isInternalProxy) setUsedProxy(true);
        else setFailed(true);
      }}
    />
  );
}

function formatDetailValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(2);
  return String(value);
}

function sourceValue(product: Product, ...keys: string[]): unknown {
  const raw = product.raw_data || {};
  for (const key of keys) {
    const value = raw[key];
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function displayProductName(product: Product): string {
  const raw = product.raw_data || {};
  const preferred = raw.Description || product.description || product.name;
  return String(preferred || product.name || "").trim();
}

function normalizeSearchText(value: unknown): string {
  return String(value ?? "")
    .toLowerCase()
    .replace(/["'`]/g, "")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function titleCase(value: string): string {
  return value.replace(/\b\w+/g, (part) => part.charAt(0).toUpperCase() + part.slice(1).toLowerCase());
}

function expandSearchAliases(value: unknown): string {
  const normalized = normalizeSearchText(value);
  if (!normalized) return "";

  let expanded = ` ${normalized} `;

  const unitPatterns: Array<[RegExp, string]> = [
    [/\b(\d+(?:\.\d+)?)\s*yd\b/g, "$1 yd $1 yard $1 yards"],
    [/\b(\d+(?:\.\d+)?)\s*in\b/g, "$1 in $1 inch $1 inches"],
    [/\b(\d+(?:\.\d+)?)\s*ft\b/g, "$1 ft $1 foot $1 feet"],
    [/\b(\d+(?:\.\d+)?)\s*ea\b/g, "$1 ea $1 each"],
    [/\b(\d+(?:\.\d+)?)\s*cs\b/g, "$1 cs $1 case"],
    [/\b(\d+(?:\.\d+)?)\s*bx\b/g, "$1 bx $1 box"],
    [/\b(\d+(?:\.\d+)?)\s*st\b/g, "$1 st $1 set"],
  ];

  for (const [pattern, replacement] of unitPatterns) {
    expanded = expanded.replace(pattern, ` ${replacement} `);
  }

  const tokenAliases: Array<[RegExp, string]> = [
    [/\byd\b/g, "yd yard yards"],
    [/\byard\b/g, "yard yd yards"],
    [/\byards\b/g, "yards yd yard"],
    [/\bin\b/g, "in inch inches"],
    [/\binch\b/g, "inch in inches"],
    [/\binches\b/g, "inches in inch"],
    [/\bft\b/g, "ft foot feet"],
    [/\bfoot\b/g, "foot ft feet"],
    [/\bfeet\b/g, "feet ft foot"],
    [/\bea\b/g, "ea each"],
    [/\beach\b/g, "each ea"],
    [/\bcs\b/g, "cs case"],
    [/\bcase\b/g, "case cs"],
    [/\bbx\b/g, "bx box"],
    [/\bbox\b/g, "box bx"],
    [/\bst\b/g, "st set"],
    [/\bset\b/g, "set st"],
    [/\bqty\b/g, "qty quantity"],
    [/\bquantity\b/g, "quantity qty"],
    [/\bw\b/g, "w width"],
    [/\bwidth\b/g, "width w"],
  ];

  for (const [pattern, replacement] of tokenAliases) {
    expanded = expanded.replace(pattern, ` ${replacement} `);
  }

  return expanded.replace(/\s+/g, " ").trim();
}

function looksLikeCodeQuery(query: string): boolean {
  return /[\d/-]/.test(query) || /^[a-z]{1,3}$/.test(query);
}

function matchesSearchTokens(haystack: string, query: string): boolean {
  const tokens = normalizeSearchText(query).split(" ").filter(Boolean);
  if (!tokens.length) return true;
  return matchesNormalizedTokens(haystack, tokens);
}

function matchesNormalizedTokens(haystack: string, tokens: string[]): boolean {
  if (!tokens.length) return true;
  return tokens.every((token) => haystack.includes(token));
}

function supplierKey(product: Product): string {
  return normalizeSearchText(product.supplier_name || "");
}

function uniqStrings(values: Array<string | undefined | null>): string[] {
  return Array.from(new Set(values.map((value) => (value || "").trim()).filter(Boolean)));
}

function looksLikeSupplierColorCode(value: unknown): boolean {
  const raw = String(value ?? "").trim();
  if (!raw) return false;
  return raw
    .split(/[\/,\s-]+/)
    .filter(Boolean)
    .every((token) => /^[A-Z]{1,4}$/.test(token));
}

function extractKnownColorWords(value: unknown): string[] {
  const normalized = normalizeSearchText(value);
  if (!normalized) return [];
  return KNOWN_COLOR_WORDS.filter((word) => normalized.includes(word)).map(titleCase);
}

function decodeAllstateColorGroup(value: unknown): string[] {
  const normalized = normalizeSearchText(value).toUpperCase();
  if (!normalized) return [];
  const tokens = normalized.split(/[^A-Z0-9]+/).filter(Boolean);
  return uniqStrings(tokens.flatMap((token) => ALLSTATE_COLOR_CODE_MAP[token] || []));
}

function productColorLabels(product: Product): string[] {
  const raw = product.raw_data || {};
  const explicitValues = [
    product.color,
    raw.Color,
    raw["Primary Color"],
    raw.ColorGrp,
  ].filter(Boolean);

  const explicitWords = explicitValues.flatMap((value) => {
    if (looksLikeSupplierColorCode(value)) return [];
    const found = extractKnownColorWords(value);
    if (found.length) return found;
    const normalized = normalizeSearchText(value);
    if (!normalized) return [];
    return normalized
      .split(" ")
      .filter((token) => token.length >= 3)
      .map(titleCase);
  });

  const colorCodeLabels =
    supplierKey(product) === "allstate"
      ? decodeAllstateColorGroup(product.color || raw.ColorGrp || raw.Color || raw["Primary Color"])
      : [];

  const descriptionLabels = extractKnownColorWords([
    displayProductName(product),
    raw.Description,
    product.description,
  ].filter(Boolean).join(" "));

  return uniqStrings([...explicitWords, ...colorCodeLabels, ...descriptionLabels]).sort();
}

function productColorSummary(product: Product): string {
  const labels = productColorLabels(product);
  if (labels.length) return labels.join(", ");
  const raw = product.raw_data || {};
  return String(product.color || raw.ColorGrp || raw.Color || "—");
}

function productCountryLabel(product: Product): string | undefined {
  const raw = product.raw_data || {};
  const value = product.country_of_origin || raw["Country of Origin"] || raw.Country;
  return value ? titleCase(String(value)) : undefined;
}

function productAvailabilityLabel(product: Product): string | undefined {
  const raw = product.raw_data || {};
  const note = normalizeSearchText(product.availability_note || raw["Avail. Qty: *"] || raw["Avail. Qty"]);
  if (note.includes("within 1 4 months")) return "Within 1-4 months";
  if (note.includes("available today") || note.includes("today")) return "Available today";
  if (note.includes("sold out") || note.includes("out of stock") || note.includes("unavailable")) {
    return "Sold out / unavailable";
  }
  if (product.availability === "in_stock") return "Available today";
  if (product.availability === "out_of_stock") return "Sold out / unavailable";
  if (product.availability === "eta") return "Future ETA";
  if (/eta|available\s+[a-z]{3,9}\s+\d{4}|expected|future/.test(note)) return "Future ETA";
  if (note.includes("over 4 months")) return "Over 4 months";
  return undefined;
}

function productTypeLabels(product: Product): string[] {
  const raw = product.raw_data || {};
  const haystack = ` ${normalizeSearchText([
    displayProductName(product),
    raw.Description,
    product.description,
    raw.allstate_subcategory,
    categoryLabel(product.category),
  ].filter(Boolean).join(" "))} `;
  return PRODUCT_TYPE_RULES
    .filter((rule) => rule.keywords.some((keyword) => haystack.includes(keyword)))
    .map((rule) => rule.label);
}

function productSizeLabels(product: Product, cachedTypeLabels?: string[]): string[] {
  const raw = product.raw_data || {};
  const sourceText = [
    displayProductName(product),
    raw.Description,
    product.description,
    raw.ProdLength,
    raw["Box LxWxH"],
    raw["Case LxWxH"],
  ].filter(Boolean).join(" ");
  const sourceLower = sourceText.toLowerCase();
  if (!sourceText) return [];

  const labels: string[] = [];
  const add = (label: string) => labels.push(label);
  const normalizedUnit = (unit: string) => {
    const lower = unit.toLowerCase();
    if (lower === "yard" || lower === "yards") return "yd";
    if (lower === "foot" || lower === "feet") return "ft";
    if (lower === "inch" || lower === "inches") return "in";
    return lower;
  };

  const hasRibbonType = (cachedTypeLabels || productTypeLabels(product)).includes("Ribbon");
  if (hasRibbonType) {
    for (const match of sourceText.matchAll(/(\d+(?:\.\d+)?)\s*(?:"|in|inch|inches)?\s*w?\s*x\s*(\d+(?:\.\d+)?)\s*(yd|yard|yards|ft|foot|feet|in|inch|inches)\b/gi)) {
      const width = match[1];
      const length = match[2];
      const unit = normalizedUnit(match[3]);
      add(`${width} in x ${length} ${unit}`);
      add(`${width} in`);
      add(`${length} ${unit}`);
    }
  }

  for (const match of sourceLower.matchAll(/(\d+(?:\.\d+)?)\s*(yd|yard|yards|ft|foot|feet|in|inch|inches)\b/g)) {
    const unit = normalizedUnit(match[2]);
    add(`${match[1]} ${unit}`);
  }

  return uniqStrings(labels).sort((a, b) => {
    const aNum = parseFloat(a);
    const bNum = parseFloat(b);
    if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && aNum !== bNum) return aNum - bNum;
    return a.localeCompare(b, undefined, { numeric: true });
  });
}

function buildProductSearchEntry(product: Product): ProductSearchEntry {
  const raw = product.raw_data || {};
  const displayName = displayProductName(product);
  const productTypes = productTypeLabels(product);
  const colors = productColorLabels(product);
  const sizes = productSizeLabels(product, productTypes);
  const country = productCountryLabel(product);
  const availability = productAvailabilityLabel(product);
  const categoryText = categoryLabel(product.category);
  const supplierName = product.supplier_name || "";
  const searchText = expandSearchAliases([
    displayName,
    product.description,
    product.color,
    product.material,
    product.country_of_origin,
    supplierName,
    categoryText,
    sourceBasePrice(product),
    sourceUom(product),
    raw.Description,
    raw.ColorGrp,
    raw.Season,
    raw.Class,
    raw["Material Breakdown"],
    raw["Country of Origin"],
    raw["Avail. Qty"],
    raw["Avail. Qty: *"],
    raw["ProdLength"],
    raw["ProdWeight"],
    raw["BoxWeight"],
    raw["CsWeight"],
    raw["Box LxWxH"],
    raw["Case LxWxH"],
    raw["CaseCube"],
    raw["Oversize"],
    raw["SugRetail"],
    raw["UPC"],
    raw["MinQty"],
    raw["BoxQty"],
    raw["CaseQty"],
    raw["CatalogVol"],
    raw["CatPage"],
    raw["P-CatVol"],
    raw["P-CatPage"],
    raw["allstate_subcategory"],
    ...productTypes,
    ...colors,
    country,
    availability,
    ...sizes,
  ].filter(Boolean).join(" "));

  return {
    product,
    category: product.category,
    categoryLabel: categoryText,
    supplierName,
    productTypes,
    colors,
    sizes,
    availability,
    country,
    searchText,
    codeText: searchableCodeText(product),
    sortName: displayName || product.name,
    isFavorited: product.is_favorited,
  };
}

function searchableVisibleText(product: Product): string {
  const raw = product.raw_data || {};
  return expandSearchAliases([
    displayProductName(product),
    product.description,
    product.color,
    product.material,
    product.country_of_origin,
    product.supplier_name,
    categoryLabel(product.category),
    sourceBasePrice(product),
    sourceUom(product),
    raw.Description,
    raw.ColorGrp,
    raw.Season,
    raw.Class,
    raw["Material Breakdown"],
    raw["Country of Origin"],
    raw["Avail. Qty"],
    raw["Avail. Qty: *"],
    raw["ProdLength"],
    raw["ProdWeight"],
    raw["BoxWeight"],
    raw["CsWeight"],
    raw["Box LxWxH"],
    raw["Case LxWxH"],
    raw["CaseCube"],
    raw["Oversize"],
    raw["SugRetail"],
    raw["UPC"],
    raw["MinQty"],
    raw["BoxQty"],
    raw["CaseQty"],
    raw["CatalogVol"],
    raw["CatPage"],
    raw["P-CatVol"],
    raw["P-CatPage"],
    raw["ColorGrp"],
    raw["allstate_subcategory"],
    ...productTypeLabels(product),
    ...productColorLabels(product),
    productCountryLabel(product),
    productAvailabilityLabel(product),
    ...productSizeLabels(product),
  ]
    .filter(Boolean)
    .join(" "));
}

function searchableCodeText(product: Product): string {
  const rawCodeText = [
    product.supplier_sku,
    product.upc,
    product.raw_data?.["Item No"],
    product.name,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
  return `${rawCodeText} ${expandSearchAliases(rawCodeText)}`.trim();
}

function sourceBasePrice(product: Product): string {
  const rawPrice = sourceValue(product, "BasePrice");
  if (rawPrice) return String(rawPrice);
  return product.current_price != null ? formatCurrency(product.current_price) : "—";
}

function sourceUom(product: Product): string {
  const rawUom = sourceValue(product, "Uom", "UOM");
  if (rawUom) return String(rawUom);
  return unitLabel(product.unit).toUpperCase();
}

function sourceOrderContext(product: Product): Array<[string, unknown]> {
  return [
    ["MinQty", product.moq ?? sourceValue(product, "MinQty")],
    ["BoxQty", product.box_qty ?? sourceValue(product, "BoxQty")],
    ["CaseQty", product.case_qty ?? sourceValue(product, "CaseQty")],
    ["SugRetail", sourceValue(product, "SugRetail")],
  ].filter(([, value]) => value !== undefined && value !== null && value !== "");
}

function imageStatus(product: Product): "stored" | "visible" | "pending" | "failed" {
  const status = product.raw_data?.image_status;
  if (status === "stored" && product.photo_url) return "stored";
  if (product.photo_url) return "visible";
  if (status === "failed") return "failed";
  return "pending";
}

function detailStatus(product: Product): "stored" | "pending" | "failed" {
  const status = product.raw_data?.detail_status;
  if (status === "failed") return "failed";
  if (status === "stored" || product.raw_data?.detail_url) return "stored";
  return "pending";
}

function ProductDetailSection({ title, rows }: { title: string; rows: Array<[string, unknown]> }) {
  return (
    <section>
      <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">{title}</p>
      <div className="rounded-lg border border-stone-100 bg-white px-3">
        {rows.map(([label, value]) => (
          <ProductDetailRow key={`${title}-${label}`} label={label} value={value} />
        ))}
      </div>
    </section>
  );
}

function ProductDetailRow({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="grid grid-cols-[132px_minmax(0,1fr)] gap-3 border-b border-stone-100 py-2 last:border-b-0">
      <dt className="text-xs font-semibold text-stone-500">{label}</dt>
      <dd className="text-xs text-stone-800 break-words">{formatDetailValue(value)}</dd>
    </div>
  );
}

function MultiSelectFilter({
  label,
  options,
  selected,
  onChange,
}: {
  label: string;
  options: string[];
  selected: string[];
  onChange: (values: string[]) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, []);

  const toggleValue = (value: string) => {
    onChange(
      selected.includes(value)
        ? selected.filter((item) => item !== value)
        : [...selected, value]
    );
  };

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-center justify-between rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm text-stone-700 focus:outline-none focus:ring-2 focus:ring-emerald-300"
      >
        <span className="truncate text-left">
          {selected.length === 0 ? label : `${selected.length} selected`}
        </span>
        <ChevronDown size={15} className={`text-stone-400 transition-transform ${open ? "rotate-180" : ""}`} />
      </button>
      {open && (
        <div className="absolute z-20 mt-2 max-h-64 w-full overflow-auto rounded-xl border border-stone-200 bg-white p-1 shadow-lg">
          {options.map((option) => {
            const active = selected.includes(option);
            return (
              <button
                key={option}
                type="button"
                onClick={() => toggleValue(option)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm text-left ${
                  active ? "bg-emerald-50 text-emerald-700" : "text-stone-700 hover:bg-stone-50"
                }`}
              >
                <span className="truncate">{option}</span>
                {active && <Check size={14} />}
              </button>
            );
          })}
        </div>
      )}
      {selected.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-2">
          {selected.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => toggleValue(value)}
              className="inline-flex items-center gap-1 rounded-full border border-emerald-200 bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700"
            >
              <span>{value}</span>
              <X size={12} />
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

export function ProductDetailModal({ product, onClose }: { product: Product; onClose: () => void }) {
  const raw = product.raw_data || {};
  const displayName = displayProductName(product);
  const detailPending = detailStatus(product) !== "stored";
  const pricingRows: Array<[string, unknown]> = [
    ["Base Price", sourceBasePrice(product)],
    ["UOM", sourceUom(product)],
    ["Minimum Quantity", product.moq ?? raw.MinQty],
    ["Box Quantity", product.box_qty ?? raw.BoxQty],
    ["Case Quantity", product.case_qty ?? raw.CaseQty],
    ["Suggested Retail", raw.SugRetail],
    ["Price Updated", product.price_updated_at ? formatDate(product.price_updated_at) : "—"],
  ];
  const coreRows: Array<[string, unknown]> = [
    ["Item Number", product.supplier_sku || raw["Item No"]],
    ["Name", displayName],
    ["Description", raw.Description || product.description],
    ["Supplier", product.supplier_name],
    ["Category", raw.allstate_subcategory || categoryLabel(product.category)],
    ["UPC", product.upc || raw.UPC],
  ];
  const availabilityRows: Array<[string, unknown]> = [
    ["Availability", product.availability_note || raw["Avail. Qty: *"] || raw["Avail. Qty"] || product.availability],
  ];
  const dimensionRows: Array<[string, unknown]> = [
    ["Product Length", raw.ProdLength || product.length_in],
    ["Product Weight", raw.ProdWeight || product.weight_lb],
    ["Box Weight", raw.BoxWeight],
    ["Case Weight", raw.CsWeight],
    ["Box LxWxH", raw["Box LxWxH"]],
    ["Case LxWxH", raw["Case LxWxH"]],
    ["Case Cube", raw.CaseCube],
  ];
  const supplierRows: Array<[string, unknown]> = [
    ["Class", raw.Class],
    ["Color Group", productColorSummary(product)],
    ["Season", raw.Season],
    ["Oversize", raw.Oversize],
    ["Poly Bag", raw.PolyBag],
    ["Fragile", raw.Fragile],
    ["Catalog Volume", raw.CatalogVol],
    ["Catalog Page", raw.CatPage],
  ];
  const materialRows: Array<[string, unknown]> = [
    ["Country of Origin", product.country_of_origin || raw["Country of Origin"]],
    ["Material Breakdown", product.material || raw["Material Breakdown"]],
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={(e) => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-5xl max-h-[90vh] overflow-hidden rounded-xl bg-white shadow-2xl">
        <div className="flex items-start justify-between gap-4 border-b border-stone-100 px-5 py-4">
          <div>
            <p className="text-xs uppercase tracking-wide text-stone-400">{product.supplier_name}</p>
            <h2 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{displayName}</h2>
            <p className="text-xs text-stone-500">{product.supplier_sku || raw["Item No"]}</p>
          </div>
          <button onClick={onClose} className="rounded-lg p-2 text-stone-400 hover:bg-stone-100 hover:text-stone-700">
            <X size={18} />
          </button>
        </div>
        <div className="grid gap-0 overflow-y-auto md:grid-cols-[340px_minmax(0,1fr)]" style={{ maxHeight: "calc(90vh - 82px)" }}>
          <div className="border-b border-stone-100 bg-stone-50 p-5 md:border-b-0 md:border-r">
            <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-stone-400">Image</p>
            <div className="aspect-square overflow-hidden rounded-lg border border-stone-200 bg-white">
              {product.photo_url ? <ProxiedImage src={product.photo_url} alt={displayName} /> : <ImagePending />}
            </div>
            {imageStatus(product) === "pending" && (
              <div className="mt-3 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Image lookup in progress
              </div>
            )}
            {imageStatus(product) === "failed" && (
              <div className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs font-medium text-red-700">
                Image retry needed
              </div>
            )}
            <div className="mt-4 grid grid-cols-2 gap-2 text-xs">
              <div className="rounded-lg bg-white p-3">
                <p className="text-stone-400">Category</p>
                <p className="font-semibold text-stone-800">{categoryLabel(product.category)}</p>
              </div>
              <div className="rounded-lg bg-white p-3">
                <p className="text-stone-400">Source UOM</p>
                <p className="font-semibold text-stone-800">{sourceUom(product)}</p>
              </div>
            </div>
            <div className="mt-2 rounded-lg bg-white p-3 text-xs">
              <p className="text-stone-400">Source price</p>
              <p className="text-lg font-semibold text-stone-800">{sourceBasePrice(product)} <span className="text-xs font-medium text-stone-400">/ {sourceUom(product)}</span></p>
            </div>
          </div>
          <div className="space-y-5 bg-stone-50/40 p-5">
            {detailPending && (
              <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700">
                Pending detail backfill: source-page fields may be incomplete.
              </div>
            )}
            <ProductDetailSection title="Core Product" rows={coreRows} />
            <ProductDetailSection title="Pricing & Ordering" rows={pricingRows} />
            <ProductDetailSection title="Availability" rows={availabilityRows} />
            <ProductDetailSection title="Dimensions & Weights" rows={dimensionRows} />
            <ProductDetailSection title="Supplier Details" rows={supplierRows} />
            <ProductDetailSection title="Material & Origin" rows={materialRows} />
          </div>
        </div>
      </div>
    </div>
  );
}

// ─── Single product card ──────────────────────────────────────────────────────
function ProductCard({
  p,
  animating,
  onFavorite,
  onProjectAdd,
  onPriceUpdated,
  onOpen,
}: {
  p: Product;
  animating: boolean;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onOpen: (p: Product) => void;
}) {
  const stale = isPriceStale(p.price_updated_at);
  const status = imageStatus(p);
  const orderContext = sourceOrderContext(p);
  const hasSourcePrice = !!sourceValue(p, "BasePrice", "Uom", "UOM");
  const displayName = displayProductName(p);
  return (
    <div
      role="button"
      tabIndex={0}
      onClick={() => onOpen(p)}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") onOpen(p); }}
      className="bg-white rounded-xl border border-stone-200 overflow-hidden group hover:shadow-md transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-emerald-300"
    >
      {/* Image */}
      <div className="relative h-56 bg-stone-100 overflow-hidden">
        {p.photo_url ? (
          <ProxiedImage src={p.photo_url} alt={displayName} />
        ) : (
          <ImagePending />
        )}
        {status === "pending" && (
          <div className="absolute top-2 left-2 rounded-full bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700 shadow-sm ring-1 ring-amber-200">
            Finding image
          </div>
        )}
        {status === "failed" && (
          <div className="absolute top-2 left-2 rounded-full bg-red-50 px-2 py-0.5 text-[10px] font-semibold text-red-700 shadow-sm ring-1 ring-red-200">
            Image retry needed
          </div>
        )}
        {status === "stored" && (
          <div className="absolute top-2 left-2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-medium text-emerald-700 shadow-sm">
            Image stored
          </div>
        )}
        {onProjectAdd && (
          <button
            onClick={(e) => { e.stopPropagation(); onProjectAdd(p); }}
            className="absolute top-2 right-2 flex h-8 w-8 items-center justify-center rounded-full bg-emerald-700 text-white shadow-sm transition-colors hover:bg-emerald-800"
            title="Add to project"
          >
            <Plus size={16} strokeWidth={2.4} />
          </button>
        )}
        {/* Favorite */}
        <button
          onClick={(e) => { e.stopPropagation(); onFavorite(p.id); }}
          className={`absolute right-2 w-8 h-8 flex items-center justify-center rounded-full bg-white/80 backdrop-blur-sm hover:bg-white transition-colors ${onProjectAdd ? "top-12" : "top-2"}`}
          style={{ transform: animating ? "scale(1.4)" : "scale(1)", transition: "transform 0.2s cubic-bezier(0.34,1.56,0.64,1)" }}
        >
          <Heart
            size={15}
            className="transition-colors"
            style={{ color: p.is_favorited ? "#c2410c" : "#a8a29e" }}
            fill={p.is_favorited ? "#c2410c" : "none"}
          />
        </button>
        {/* Category badge */}
        <div className="absolute bottom-2 left-2">
          <span
            className="text-xs font-medium px-2 py-0.5 rounded-full bg-white/80 backdrop-blur-sm"
            style={{ color: CATEGORY_COLORS[p.category] || "#57534e" }}
          >
            {categoryLabel(p.category)}
          </span>
        </div>
      </div>
      {/* Info */}
      <div className="p-4">
        <p className="font-semibold text-stone-800 text-sm leading-tight truncate mb-1">{displayName}</p>
        <p className="text-xs text-stone-400 mb-2 truncate">{p.supplier_sku || p.supplier_name}</p>
        <div>
          {hasSourcePrice ? (
            <>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-stone-400">Base price</p>
              <p className="text-base font-bold text-stone-800">
                {sourceBasePrice(p)} <span className="text-xs font-semibold text-stone-400">/ {sourceUom(p)}</span>
              </p>
            </>
          ) : (
            <>
              <InlinePriceEditor
                p={p}
                onUpdated={(price, ts) => onPriceUpdated?.(p.id, price, ts)}
              />
              <p className="text-xs text-stone-400">per {unitLabel(p.unit)}</p>
            </>
          )}
          {orderContext.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {orderContext.map(([label, value]) => (
                <span key={label} className="rounded-full bg-stone-100 px-2 py-0.5 text-[10px] font-medium text-stone-600">
                  {label} {formatDetailValue(value)}
                </span>
              ))}
            </div>
          )}
        </div>
        {/* Stale price warning */}
        {stale && (
          <div className="flex items-center gap-1 mt-1.5">
            <AlertTriangle size={10} className="text-amber-400 flex-shrink-0" />
            <p className="text-[10px] text-amber-600">Supplier price may be outdated</p>
          </div>
        )}
        {!stale && p.price_updated_at && (
          <p className="text-[10px] text-stone-300 mt-1">Supplier price updated {formatDate(p.price_updated_at)}</p>
        )}
      </div>
    </div>
  );
}

// ─── Category pill config ────────────────────────────────────────────────────
const CAT_PILL: Record<string, { bg: string; text: string; label: string }> = {
  greenery:   { bg: "#dcfce7", text: "#15803d", label: "Greenery" },
  florals:    { bg: "#fce7f3", text: "#be185d", label: "Florals" },
  trees:      { bg: "#d1fae5", text: "#065f46", label: "Trees" },
  wood:       { bg: "#fef3c7", text: "#92400e", label: "Wood" },
  containers: { bg: "#fef9c3", text: "#a16207", label: "Containers" },
  other:      { bg: "#f1f5f9", text: "#475569", label: "Other" },
};

// ─── Vendor View ─────────────────────────────────────────────────────────────
function VendorView({
  suppliers,
  products,
  animatingIds,
  onFavorite,
  onProjectAdd,
  onAddProduct,
  onPriceUpdated,
  onOpenProduct,
}: {
  suppliers: Supplier[];
  products: Product[];
  animatingIds: Set<number>;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onAddProduct: (supplierId: number) => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onOpenProduct: (p: Product) => void;
}) {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [filterCat, setFilterCat] = useState("");
  const [visibleBySupplier, setVisibleBySupplier] = useState<Record<number, number>>({});

  const allCats = Array.from(new Set(suppliers.flatMap((s) => s.categories || []))).sort();
  const visibleSuppliers = filterCat
    ? suppliers.filter((s) => (s.categories || []).includes(filterCat))
    : suppliers;

  return (
    <div>
      {/* Category filter pills */}
      {allCats.length > 0 && (
        <div className="flex items-center gap-2 mb-5 flex-wrap">
          <span className="text-xs text-stone-400 font-medium mr-1">Filter by type:</span>
          <button
            onClick={() => setFilterCat("")}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              filterCat === ""
                ? "bg-emerald-700 text-white border-emerald-700"
                : "border-stone-200 text-stone-500 hover:border-stone-300 bg-white"
            }`}
          >
            All vendors
          </button>
          {allCats.map((cat) => {
            const cfg = CAT_PILL[cat] || CAT_PILL.other;
            const active = filterCat === cat;
            return (
              <button
                key={cat}
                onClick={() => setFilterCat(active ? "" : cat)}
                className="px-3 py-1 rounded-full text-xs font-medium border transition-all"
                style={active
                  ? { backgroundColor: cfg.text, color: "#fff", borderColor: cfg.text }
                  : { backgroundColor: cfg.bg, color: cfg.text, borderColor: "transparent" }
                }
              >
                {cfg.label}
              </button>
            );
          })}
        </div>
      )}
      <div className="space-y-4">
      {visibleSuppliers.length === 0 && (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "#e8f0e8" }}>
            <Store size={28} className="text-emerald-600" strokeWidth={1.5} />
          </div>
          <p className="text-base font-medium text-stone-600 mb-1">No suppliers yet</p>
          <p className="text-sm text-stone-400 max-w-xs leading-relaxed">Add suppliers from the Suppliers page to get started.</p>
        </div>
      )}
      {visibleSuppliers.map((s) => {
        const vendorProducts = products
          .filter((p) => p.supplier_id === s.id)
          .sort((a, b) => {
            if (a.is_favorited && !b.is_favorited) return -1;
            if (!a.is_favorited && b.is_favorited) return 1;
            return a.name.localeCompare(b.name);
          });
        const isExpanded = expandedId === s.id;
        const favCount = vendorProducts.filter((p) => p.is_favorited).length;
        const visibleCount = visibleBySupplier[s.id] ?? INITIAL_CARD_RENDER_LIMIT;
        const visibleVendorProducts = vendorProducts.slice(0, visibleCount);

        return (
          <div key={s.id} className="bg-white rounded-2xl border border-stone-200 overflow-hidden">
            {/* Supplier header */}
            <button
              className="w-full flex items-center justify-between px-6 py-4 hover:bg-stone-50 transition-colors text-left"
              onClick={() => setExpandedId(isExpanded ? null : s.id)}
            >
              <div className="flex items-center gap-3">
                <div
                  className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
                  style={{ backgroundColor: "#e8f0e8" }}
                >
                  <Store size={18} className="text-emerald-700" strokeWidth={1.5} />
                </div>
                <div>
                  <p className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{s.name}</p>
                  <div className="flex items-center gap-1.5 flex-wrap mt-0.5">
                    {(s.categories || []).map((cat) => {
                      const cfg = CAT_PILL[cat] || CAT_PILL.other;
                      return (
                        <span
                          key={cat}
                          className="text-xs font-medium px-2 py-0.5 rounded-full"
                          style={{ backgroundColor: cfg.bg, color: cfg.text }}
                        >
                          {cfg.label}
                        </span>
                      );
                    })}
                    <span className="text-xs text-stone-400">
                      · {vendorProducts.length} product{vendorProducts.length !== 1 ? "s" : ""}
                      {favCount > 0 && <span className="text-orange-500"> · {favCount} ♥</span>}
                    </span>
                  </div>
                </div>
              </div>
              <div className="flex items-center gap-3">
                {vendorProducts.length > 0 && (
                  <div className="flex -space-x-1">
                    {vendorProducts.slice(0, 4).map((p) => (
                      <div key={p.id} className="w-7 h-7 rounded-full border-2 border-white bg-stone-100 overflow-hidden flex-shrink-0">
                        {p.photo_url ? (
                          <img src={p.photo_url} alt={p.name} className="w-full h-full object-cover" />
                        ) : (
                          <div className="w-full h-full flex items-center justify-center">
                            <Leaf size={10} className="text-stone-300" />
                          </div>
                        )}
                      </div>
                    ))}
                    {vendorProducts.length > 4 && (
                      <div className="w-7 h-7 rounded-full border-2 border-white bg-stone-200 flex items-center justify-center">
                        <span className="text-xs text-stone-500">+{vendorProducts.length - 4}</span>
                      </div>
                    )}
                  </div>
                )}
                <ChevronRight
                  size={16}
                  className="text-stone-400 transition-transform duration-200"
                  style={{ transform: isExpanded ? "rotate(90deg)" : "rotate(0deg)" }}
                />
              </div>
            </button>

            {/* Products panel */}
            {isExpanded && (
              <div className="border-t border-stone-100 px-6 py-5">
                {vendorProducts.length === 0 ? (
                  <div className="flex flex-col items-center py-8 text-center">
                    <Package size={24} className="text-stone-300 mb-2" strokeWidth={1.5} />
                    <p className="text-sm text-stone-400 mb-3">No products from this supplier yet</p>
                    <button
                      onClick={() => onAddProduct(s.id)}
                      className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                    >
                      <Plus size={13} /> Add first product
                    </button>
                  </div>
                ) : (
                  <>
                    <div className="grid grid-cols-2 gap-4 xl:grid-cols-3 2xl:grid-cols-4">
                      {visibleVendorProducts.map((p) => (
                        <ProductCard
                          key={p.id}
                          p={p}
                          animating={animatingIds.has(p.id)}
                          onFavorite={onFavorite}
                          onProjectAdd={onProjectAdd}
                          onPriceUpdated={onPriceUpdated}
                          onOpen={onOpenProduct}
                        />
                      ))}
                    </div>
                    {visibleCount < vendorProducts.length && (
                      <div className="mt-4 flex justify-center">
                        <button
                          onClick={() =>
                            setVisibleBySupplier((prev) => ({
                              ...prev,
                              [s.id]: (prev[s.id] ?? INITIAL_CARD_RENDER_LIMIT) + INITIAL_CARD_RENDER_LIMIT,
                            }))
                          }
                          className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-600 hover:border-emerald-300 hover:text-emerald-700"
                        >
                          Show more products ({Math.min(visibleCount, vendorProducts.length)} of {vendorProducts.length})
                        </button>
                      </div>
                    )}
                    <div className="mt-4 pt-4 border-t border-stone-100 flex justify-between items-center">
                      <p className="text-xs text-stone-400">
                        Avg price: {formatCurrency(
                          vendorProducts.reduce((s, p) => s + (p.current_price || 0), 0) / (vendorProducts.filter(p => p.current_price).length || 1)
                        )}
                      </p>
                      <button
                        onClick={() => onAddProduct(s.id)}
                        className="text-xs font-semibold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                      >
                        <Plus size={13} /> Add product
                      </button>
                    </div>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
      </div>
    </div>
  );
}

// ─── Product View ────────────────────────────────────────────────────────────
export function ProductView({
  products,
  animatingIds,
  onFavorite,
  onProjectAdd,
  onAddProduct,
  onPriceUpdated,
  onSyncAll,
  onOpenProduct,
  hideSyncAll = false,
  hideFavoritesToggle = false,
  emptyTitle = "No products found",
  emptyDescription,
}: {
  products: Product[];
  animatingIds: Set<number>;
  onFavorite: (id: number) => void;
  onProjectAdd?: (product: Product) => void;
  onAddProduct?: () => void;
  onPriceUpdated?: (id: number, price: number, ts: string) => void;
  onSyncAll?: () => Promise<void>;
  onOpenProduct: (p: Product) => void;
  hideSyncAll?: boolean;
  hideFavoritesToggle?: boolean;
  emptyTitle?: string;
  emptyDescription?: string;
}) {
  const [syncing, setSyncing] = useState(false);

  const handleSyncAll = async () => {
    if (!onSyncAll) return;
    setSyncing(true);
    try {
      await onSyncAll();
    } finally {
      setSyncing(false);
    }
  };
  const [activeCategory, setActiveCategory] = useState("");
  const [searchInput, setSearchInput] = useState("");
  const [activeSearch, setActiveSearch] = useState("");
  const [favoritesOnly, setFavoritesOnly] = useState(false);
  const [categoryFilter, setCategoryFilter] = useState<string[]>([]);
  const [productTypeFilter, setProductTypeFilter] = useState<string[]>([]);
  const [supplierFilter, setSupplierFilter] = useState<string[]>([]);
  const [colorFilter, setColorFilter] = useState<string[]>([]);
  const [sizeFilter, setSizeFilter] = useState<string[]>([]);
  const [availabilityFilter, setAvailabilityFilter] = useState<string[]>([]);
  const [countryFilter, setCountryFilter] = useState<string[]>([]);
  const [visibleLimit, setVisibleLimit] = useState(INITIAL_CARD_RENDER_LIMIT);

  useEffect(() => {
    const timer = window.setTimeout(() => setActiveSearch(searchInput), 200);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  const productIndex = useMemo(() => products.map(buildProductSearchEntry), [products]);

  const categoryCounts = useMemo(() => {
    const counts = new Map<string, number>();
    for (const entry of productIndex) {
      counts.set(entry.category, (counts.get(entry.category) || 0) + 1);
    }
    return counts;
  }, [productIndex]);

  const dynamicCategories = useMemo(
    () => Array.from(categoryCounts.keys()).sort((a, b) => (categoryCounts.get(b) || 0) - (categoryCounts.get(a) || 0)),
    [categoryCounts]
  );

  const normalizedSearch = useMemo(() => normalizeSearchText(activeSearch), [activeSearch]);
  const searchTokens = useMemo(() => normalizedSearch.split(" ").filter(Boolean), [normalizedSearch]);
  const rawSearch = activeSearch.trim().toLowerCase();
  const shouldSearchCodes = rawSearch.length >= 4 || looksLikeCodeQuery(rawSearch);

  const baseFiltered = useMemo(() => productIndex.filter((entry) => {
    if (favoritesOnly && !entry.isFavorited) return false;
    if (activeCategory && entry.category !== activeCategory) return false;
    return true;
  }), [productIndex, favoritesOnly, activeCategory]);

  const matchesTextFilters = useCallback((entry: ProductSearchEntry) => {
    if (!normalizedSearch) return true;
    const matchesVisibleText = matchesNormalizedTokens(entry.searchText, searchTokens);
    const matchesCodeText =
      shouldSearchCodes &&
      (entry.codeText.includes(rawSearch) || matchesNormalizedTokens(entry.codeText, searchTokens));
    return matchesVisibleText || matchesCodeText;
  }, [normalizedSearch, rawSearch, searchTokens, shouldSearchCodes]);

  const matchesStructuredFilters = useCallback((entry: ProductSearchEntry, exclude?: {
    category?: boolean;
    productType?: boolean;
    supplier?: boolean;
    color?: boolean;
    size?: boolean;
    availability?: boolean;
    country?: boolean;
  }) => {
    if (!exclude?.category && categoryFilter.length > 0 && !categoryFilter.includes(entry.categoryLabel)) return false;
    if (!exclude?.productType && productTypeFilter.length > 0 && !productTypeFilter.some((type) => entry.productTypes.includes(type))) return false;
    if (!exclude?.supplier && supplierFilter.length > 0 && !supplierFilter.includes(entry.supplierName)) return false;
    if (!exclude?.color && colorFilter.length > 0 && !colorFilter.some((color) => entry.colors.includes(color))) return false;
    if (!exclude?.size && sizeFilter.length > 0 && !sizeFilter.some((size) => entry.sizes.includes(size))) return false;
    if (!exclude?.availability && availabilityFilter.length > 0 && !availabilityFilter.includes(entry.availability || "")) return false;
    if (!exclude?.country && countryFilter.length > 0 && !countryFilter.includes(entry.country || "")) return false;
    return true;
  }, [categoryFilter, productTypeFilter, supplierFilter, colorFilter, sizeFilter, availabilityFilter, countryFilter]);

  const optionBase = useMemo(
    () => baseFiltered.filter((entry) => matchesTextFilters(entry)),
    [baseFiltered, matchesTextFilters]
  );

  const supplierOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { supplier: true }))
      .map((entry) => entry.supplierName)
      .filter(Boolean))).sort(),
    [optionBase, matchesStructuredFilters]
  );
  const categoryOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { category: true }))
      .map((entry) => entry.categoryLabel))).sort(),
    [optionBase, matchesStructuredFilters]
  );
  const productTypeOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { productType: true }))
      .flatMap((entry) => entry.productTypes))).sort(),
    [optionBase, matchesStructuredFilters]
  );
  const colorOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { color: true }))
      .flatMap((entry) => entry.colors))).sort(),
    [optionBase, matchesStructuredFilters]
  );
  const sizeOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { size: true }))
      .flatMap((entry) => entry.sizes))).sort((a, b) => {
      const aNum = parseFloat(a);
      const bNum = parseFloat(b);
      if (!Number.isNaN(aNum) && !Number.isNaN(bNum) && aNum !== bNum) return aNum - bNum;
      return a.localeCompare(b, undefined, { numeric: true });
    }),
    [optionBase, matchesStructuredFilters]
  );
  const countryOptions = useMemo(
    () => Array.from(new Set(optionBase
      .filter((entry) => matchesStructuredFilters(entry, { country: true }))
      .map((entry) => entry.country)
      .filter(Boolean))).sort(),
    [optionBase, matchesStructuredFilters]
  );
  const availabilityOptions = useMemo(
    () => AVAILABILITY_FILTERS.filter((label) =>
      optionBase
        .filter((entry) => matchesStructuredFilters(entry, { availability: true }))
        .some((entry) => entry.availability === label)
    ),
    [optionBase, matchesStructuredFilters]
  );

  const filtered = useMemo(() => baseFiltered.filter((entry) => {
    if (!matchesStructuredFilters(entry)) return false;
    return matchesTextFilters(entry);
  }), [baseFiltered, matchesStructuredFilters, matchesTextFilters]);

  const sortedEntries = useMemo(() => [...filtered].sort((a, b) => {
    if (a.isFavorited && !b.isFavorited) return -1;
    if (!a.isFavorited && b.isFavorited) return 1;
    return a.sortName.localeCompare(b.sortName);
  }), [filtered]);
  const sorted = useMemo(() => sortedEntries.map((entry) => entry.product), [sortedEntries]);
  const visibleProducts = sorted.slice(0, visibleLimit);

  useEffect(() => {
    setVisibleLimit(INITIAL_CARD_RENDER_LIMIT);
  }, [activeCategory, activeSearch, favoritesOnly, categoryFilter, productTypeFilter, supplierFilter, colorFilter, sizeFilter, availabilityFilter, countryFilter]);

  return (
    <div>
      {/* Category tabs */}
      <div className="flex items-center gap-1 mb-5 border-b border-stone-200 pb-0 overflow-x-auto">
        <button
          onClick={() => setActiveCategory("")}
          className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
            activeCategory === ""
              ? "border-emerald-600 text-emerald-700"
              : "border-transparent text-stone-500 hover:text-stone-700"
          }`}
        >
          All <span className="text-xs text-stone-400 ml-1">({products.length})</span>
        </button>
        {dynamicCategories.map((cat) => (
          <button
            key={cat}
            onClick={() => setActiveCategory(activeCategory === cat ? "" : cat)}
            className={`flex-shrink-0 px-4 py-2.5 text-sm font-medium border-b-2 transition-colors -mb-px ${
              activeCategory === cat
                ? "border-emerald-600 text-emerald-700"
                : "border-transparent text-stone-500 hover:text-stone-700"
            }`}
          >
            {categoryLabel(cat)}
            <span className="text-xs text-stone-400 ml-1">({categoryCounts.get(cat) || 0})</span>
          </button>
        ))}
      </div>

      {/* Search + favorites row */}
      <div className="flex items-center gap-3 mb-5 flex-wrap">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            className="w-full pl-9 pr-3 py-2 text-sm border border-stone-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-emerald-300"
            placeholder="Search products..."
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
          />
        </div>
        <div className="text-sm font-medium text-stone-500 tabular-nums">
          {sorted.length.toLocaleString()} {sorted.length === 1 ? "result" : "results"}
        </div>
        {!hideFavoritesToggle && (
          <button
            onClick={() => setFavoritesOnly((v) => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border transition-all ${
              favoritesOnly
                ? "border-orange-300 bg-orange-50 text-orange-700"
                : "border-stone-200 bg-white text-stone-500 hover:text-stone-700"
            }`}
          >
            <Heart
              size={13}
              fill={favoritesOnly ? "#c2410c" : "none"}
              style={{ color: favoritesOnly ? "#c2410c" : "#a8a29e" }}
            />
            Favorites
          </button>
        )}
        {(searchInput || activeSearch || favoritesOnly || activeCategory || categoryFilter.length > 0 || productTypeFilter.length > 0 || supplierFilter.length > 0 || colorFilter.length > 0 || sizeFilter.length > 0 || availabilityFilter.length > 0 || countryFilter.length > 0) && (
          <button
            onClick={() => {
              setSearchInput("");
              setActiveSearch("");
              setFavoritesOnly(false);
              setActiveCategory("");
              setCategoryFilter([]);
              setProductTypeFilter([]);
              setSupplierFilter([]);
              setColorFilter([]);
              setSizeFilter([]);
              setAvailabilityFilter([]);
              setCountryFilter([]);
            }}
            className="text-xs text-stone-500 hover:text-stone-700 flex items-center gap-1"
          >
            <X size={12} /> Clear
          </button>
        )}
        {!hideSyncAll && (
          <div className="ml-auto">
            <button
              onClick={handleSyncAll}
              disabled={syncing || products.length === 0}
              className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm border border-stone-200 bg-white text-stone-600 hover:text-emerald-700 hover:border-emerald-300 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <RefreshCw size={13} className={syncing ? "animate-spin" : ""} />
              {syncing ? "Syncing…" : "Sync Prices"}
            </button>
          </div>
        )}
      </div>

      <div className="mb-5 grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-7">
        <MultiSelectFilter
          label="All categories"
          options={categoryOptions}
          selected={categoryFilter}
          onChange={setCategoryFilter}
        />
        <MultiSelectFilter
          label="All product types"
          options={productTypeOptions}
          selected={productTypeFilter}
          onChange={setProductTypeFilter}
        />
        <MultiSelectFilter
          label="All suppliers"
          options={supplierOptions}
          selected={supplierFilter}
          onChange={setSupplierFilter}
        />
        <MultiSelectFilter
          label="All colors"
          options={colorOptions}
          selected={colorFilter}
          onChange={setColorFilter}
        />
        <MultiSelectFilter
          label="All sizes"
          options={sizeOptions}
          selected={sizeFilter}
          onChange={setSizeFilter}
        />
        <MultiSelectFilter
          label="All availability"
          options={availabilityOptions}
          selected={availabilityFilter}
          onChange={setAvailabilityFilter}
        />
        <MultiSelectFilter
          label="All countries"
          options={countryOptions}
          selected={countryFilter}
          onChange={setCountryFilter}
        />
      </div>

      {/* Grid */}
      {sorted.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-24 text-center">
          <div className="w-16 h-16 rounded-full flex items-center justify-center mb-4" style={{ backgroundColor: "#e8f0e8" }}>
            <Leaf size={28} className="text-emerald-600" strokeWidth={1.5} />
          </div>
          <p className="text-base font-medium text-stone-600 mb-1">{emptyTitle}</p>
          <p className="text-sm text-stone-400 max-w-xs leading-relaxed mb-4">
            {emptyDescription || (products.length === 0
              ? "Add your first plant, container, or accent to start building projects."
              : "Try adjusting your filters.")}
          </p>
          {products.length === 0 && onAddProduct && (
            <button
              onClick={onAddProduct}
              className="px-4 py-2 text-sm font-semibold text-white rounded-lg hover:opacity-90"
              style={{ backgroundColor: "#2d5a33" }}
            >
              Add First Product
            </button>
          )}
        </div>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 xl:grid-cols-3 2xl:grid-cols-4">
            {visibleProducts.map((p) => (
              <ProductCard
                key={p.id}
                p={p}
                animating={animatingIds.has(p.id)}
                onFavorite={onFavorite}
                onProjectAdd={onProjectAdd}
                onPriceUpdated={onPriceUpdated}
                onOpen={onOpenProduct}
              />
            ))}
          </div>
          {visibleLimit < sorted.length && (
            <div className="mt-5 flex justify-center">
              <button
                onClick={() => setVisibleLimit((limit) => limit + INITIAL_CARD_RENDER_LIMIT)}
                className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-sm font-semibold text-stone-600 hover:border-emerald-300 hover:text-emerald-700"
              >
                Show more products ({Math.min(visibleLimit, sorted.length)} of {sorted.length})
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function Library() {
  const cachedLibrary = useMemo(() => readLibraryCache(), []);
  const [products, setProducts] = useState<Product[]>(applyLocalFavoriteState(cachedLibrary?.products || []));
  const [suppliers, setSuppliers] = useState<Supplier[]>(cachedLibrary?.suppliers || []);
  const [loading, setLoading] = useState(!cachedLibrary);
  const [refreshing, setRefreshing] = useState(false);
  const [view, setView] = useState<"vendor" | "product">("product");
  const [showModal, setShowModal] = useState(false);
  const [editProduct, setEditProduct] = useState<Partial<Product> | null>(null);
  const [detailProduct, setDetailProduct] = useState<Product | null>(null);
  const [projectAddProduct, setProjectAddProduct] = useState<Product | null>(null);
  const [animatingIds, setAnimatingIds] = useState<Set<number>>(new Set());
  const [presetSupplierId, setPresetSupplierId] = useState<number | null>(null);

  const load = async () => {
    if (products.length === 0 && suppliers.length === 0) setLoading(true);
    else setRefreshing(true);
    try {
      const [ssRes, psRes] = await Promise.allSettled([
        apiClient.list_suppliers().then((r) => r.json()),
        apiClient.list_products({ favorites_only: false }).then((r) => r.json()),
      ]);
      let nextSuppliers = suppliers;
      let nextProducts = products;
      if (ssRes.status === "fulfilled") {
        nextSuppliers = ssRes.value;
        setSuppliers(ssRes.value);
      }
      if (psRes.status === "fulfilled") {
        nextProducts = applyLocalFavoriteState(psRes.value);
        setProducts(nextProducts);
      }
      if (ssRes.status === "fulfilled" || psRes.status === "fulfilled") {
        writeLibraryCache(nextSuppliers, nextProducts);
      } else {
        console.error("Products load failed:", (psRes as PromiseRejectedResult).reason);
        toast.error("Failed to load products — please sign in");
      }
    } catch {
      toast.error("Failed to load library");
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { load(); }, []);

  const toggleFavorite = async (id: number) => {
    setAnimatingIds((prev) => new Set(prev).add(id));
    setTimeout(() => {
      setAnimatingIds((prev) => { const next = new Set(prev); next.delete(id); return next; });
    }, 350);
    const target = products.find((p) => p.id === id);
    const nextFavorited = !target?.is_favorited;
    setLocalFavorite(id, nextFavorited);
    setProducts((prev) => {
      const next = prev.map((p) => p.id === id ? { ...p, is_favorited: nextFavorited } : p);
      writeLibraryCache(suppliers, next);
      return next;
    });
    try {
      await apiClient.toggle_favorite({ productId: id });
    } catch {
      toast.info("Saved locally. Favorites will stay on this device.");
    }
  };

  const deleteProduct = async (id: number) => {
    if (!confirm("Delete this product?")) return;
    try {
      await apiClient.delete_product({ productId: id });
      setProducts((prev) => prev.filter((p) => p.id !== id));
      toast.success("Product deleted");
    } catch {
      toast.error("Failed to delete");
    }
  };

  const updateProductPrice = (id: number, price: number, ts: string) => {
    setProducts((prev) =>
      prev.map((p) => p.id === id ? { ...p, current_price: price, price_updated_at: ts } : p)
    );
  };

  const syncAllPrices = async () => {
    // Collect unique supplier IDs from all products
    const supplierIds = [...new Set(products.map((p) => p.supplier_id))];
    if (supplierIds.length === 0) return;
    try {
      await apiClient.sync_prices_bulk({ supplier_ids: supplierIds });
      toast.success("Prices synced");
      // Reload products to pick up fresh prices
      const res = await apiClient.list_products({ favorites_only: false });
      const updated = await res.json();
      setProducts(updated);
    } catch {
      toast.error("Price sync failed");
    }
  };

  const openAddProduct = (supplierId?: number) => {
    setPresetSupplierId(supplierId ?? null);
    setEditProduct(supplierId ? { supplier_id: supplierId } : null);
    setShowModal(true);
  };

  return (
    <Layout>
      {/* Header */}
      <header className="sticky top-0 z-10 flex items-center justify-between px-10 py-4 border-b border-stone-200" style={{ backgroundColor: "#f7f4ef" }}>
        <div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Product Library</h1>
          <p className="text-xs text-stone-500 mt-0.5">
            {products.length} products across {suppliers.length} suppliers
            {refreshing && <span className="ml-2 text-emerald-700">Refreshing…</span>}
          </p>
        </div>
        <div className="flex items-center gap-3">
          {/* View toggle */}
          <div className="flex items-center rounded-lg border border-stone-200 bg-white overflow-hidden">
            <button
              onClick={() => setView("vendor")}
              className={`flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium transition-colors ${
                view === "vendor" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-700 hover:bg-stone-50"
              }`}
            >
              <Store size={14} />
              Vendor View
            </button>
            <button
              onClick={() => setView("product")}
              className={`flex items-center gap-1.5 px-3.5 py-2 text-sm font-medium transition-colors ${
                view === "product" ? "bg-emerald-700 text-white" : "text-stone-500 hover:text-stone-700 hover:bg-stone-50"
              }`}
            >
              <Grid3X3 size={14} />
              Product View
            </button>
          </div>
        </div>
      </header>

      <div className="px-10 py-6">
        {loading ? (
          <div className="flex items-center justify-center py-24">
            <div className="w-6 h-6 border-2 border-emerald-600 border-t-transparent rounded-full animate-spin" />
          </div>
        ) : view === "vendor" ? (
          <VendorView
            suppliers={suppliers}
            products={products}
            animatingIds={animatingIds}
            onFavorite={toggleFavorite}
            onProjectAdd={setProjectAddProduct}
            onAddProduct={(sid) => openAddProduct(sid)}
            onPriceUpdated={updateProductPrice}
            onOpenProduct={setDetailProduct}
          />
        ) : (
          <ProductView
            products={products}
            animatingIds={animatingIds}
            onFavorite={toggleFavorite}
            onProjectAdd={setProjectAddProduct}
            onAddProduct={() => openAddProduct()}
            onPriceUpdated={updateProductPrice}
            onSyncAll={syncAllPrices}
            onOpenProduct={setDetailProduct}
          />
        )}
      </div>

      {detailProduct && (
        <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />
      )}

      {projectAddProduct && (
        <AddToProjectModal product={projectAddProduct} onClose={() => setProjectAddProduct(null)} />
      )}

      {showModal && (
        <ProductModal
          product={editProduct}
          suppliers={suppliers}
          onClose={() => { setShowModal(false); setEditProduct(null); setPresetSupplierId(null); }}
          onSave={(p) => {
            setProducts((prev) =>
              prev.some((x) => x.id === p.id)
                ? prev.map((x) => (x.id === p.id ? p : x))
                : [p, ...prev]
            );
          }}
        />
      )}
    </Layout>
  );
}
