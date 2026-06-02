import React, { useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowLeft,
  CheckCircle2,
  Circle,
  HelpCircle,
  Grid3X3,
  Leaf,
  Minus,
  Redo2,
  Package,
  Pencil,
  Plus,
  Save,
  Search,
  Trash2,
  Undo2,
  Upload,
  X,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency, categoryLabel, unitLabel } from "utils/format";
import { toast } from "sonner";
import { ProductDetailModal, type Product as LibraryProduct } from "./Library";

type ItemStatus = "candidate" | "selected";

type ContainerItem = {
  id: number;
  product_id: number;
  product_name: string;
  product_category: string;
  unit: string;
  current_price?: number;
  supplier_name?: string;
  supplier_sku?: string;
  photo_url?: string;
  quantity: number;
  line_total?: number;
  status?: ItemStatus;
  part_key?: string;
  part_label?: string;
  part_order?: number;
};

type Container = {
  id: number;
  arrangement_id: number;
  container_product_id?: number;
  container_name?: string;
  label?: string;
  room_id?: number | null;
  bucket_type?: string;
  requested_quantity?: number;
  scope_notes?: string;
  sort_order: number;
  items: ContainerItem[];
  subtotal: number;
};

type ProjectRoom = {
  id: number;
  arrangement_id: number;
  name: string;
  notes?: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
};

type Arrangement = {
  id: number;
  name: string;
  client_name?: string;
  notes?: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  rooms?: ProjectRoom[];
  containers: Container[];
  total_cost: number;
  total_with_markup: number;
};

type ArrangementSummary = {
  id: number;
  name: string;
  client_name?: string;
  created_at: string;
  updated_at: string;
  total_cost: number;
  container_count: number;
};

const PROJECTS_LIST_CACHE_KEY = "leaf-ledger:projects-list-cache:v1";

type ProjectsListCache = {
  arrangements: ArrangementSummary[];
  cachedAt: number;
};

function readProjectsListCache(): ProjectsListCache | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(PROJECTS_LIST_CACHE_KEY) || "null");
    if (!parsed || !Array.isArray(parsed.arrangements)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeProjectsListCache(arrangements: ArrangementSummary[]) {
  try {
    window.localStorage.setItem(PROJECTS_LIST_CACHE_KEY, JSON.stringify({ arrangements, cachedAt: Date.now() }));
  } catch {
    // localStorage is only a speed cache; failures should not block the app.
  }
}

function formatProjectsCacheStamp(ms?: number | null) {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function notifyProjectsChanged() {
  window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
}

function arrangementShellFromSummary(summary: ArrangementSummary): Arrangement {
  return {
    id: summary.id,
    name: summary.name,
    client_name: summary.client_name,
    notes: "",
    created_by: "",
    created_at: summary.created_at,
    updated_at: summary.updated_at,
    rooms: [],
    containers: [],
    total_cost: summary.total_cost || 0,
    total_with_markup: summary.total_cost || 0,
  };
}

function arrangementRouteShell(id: number, clientName?: string): Arrangement {
  const now = new Date().toISOString();
  return {
    id,
    name: "Opening project...",
    client_name: clientName,
    notes: "",
    created_by: "",
    created_at: now,
    updated_at: now,
    rooms: [],
    containers: [],
    total_cost: 0,
    total_with_markup: 0,
  };
}

function withTimeout<T>(promise: Promise<T>, ms = 12000): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error("Request timed out")), ms);
    promise.then(
      (value) => {
        window.clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        window.clearTimeout(timer);
        reject(error);
      }
    );
  });
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => window.setTimeout(resolve, ms));
}

function scopeTitle(bucket?: Container | null) {
  if (!bucket) return "Scope";
  return bucket.label || bucket.bucket_type || `Scope ${bucket.sort_order + 1}`;
}

function scopeQuantity(bucket?: Container | null) {
  return Math.max(1, Number(bucket?.requested_quantity || 1));
}

function recipeSections(bucket: Container) {
  const text = `${bucket.bucket_type || ""} ${bucket.label || ""}`.toLowerCase();
  if (text.includes("tree") || text.includes("fig")) return ["Container", "Top Dressing", "Trunks & Branches", "Leaves"];
  if (text.includes("wreath")) return ["Base", "Greenery", "Ribbon", "Decor"];
  if (text.includes("garland")) return ["Base Garland", "Greenery", "Ribbon", "Decor"];
  if (text.includes("arrangement")) return ["Container", "Base", "Focal Product", "Fill"];
  return ["Products", "Notes", "Pricing"];
}

function scopePlaceholders(bucket: Container) {
  const sections = recipeSections(bucket);
  return sections.length >= 4 ? sections.slice(0, 4) : [...sections, "Product", "Product", "Product", "Product"].slice(0, 4);
}

function partKey(label: string, index: number) {
  return `${index}-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "") || "part"}`;
}

function itemsForPart(bucket: Container | null | undefined, label: string, index: number) {
  if (!bucket) return [];
  const key = partKey(label, index);
  return bucket.items.filter((item) => (item.part_key || "") === key || (!item.part_key && index === 0));
}

function primarySelectedForPart(bucket: Container, label: string, index: number) {
  return (
    itemsForPart(bucket, label, index).find((item) => (item.status || "selected") === "selected") ||
    itemsForPart(bucket, label, index)[0] ||
    null
  );
}

function builderProductName(product: LibraryProduct) {
  return String(product.raw_data?.Description || product.description || product.name || "").trim();
}

function builderProductSearchText(product: LibraryProduct) {
  const raw = product.raw_data || {};
  return [
    builderProductName(product),
    product.name,
    product.description,
    product.supplier_sku,
    product.supplier_name,
    product.category,
    product.unit,
    product.material,
    product.color,
    product.country_of_origin,
    product.availability,
    raw.ColorGrp,
    raw.Class,
    raw.Season,
    raw.UPC,
    raw["Material Breakdown"],
    raw.Material_Breakdown,
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

function BuilderProductPicker({
  products,
  loadingCatalog = false,
  activePartLabel,
  selectedProductIds,
  selectedProductItemIds,
  onAdd,
  onRemove,
  onOpenProduct,
  onContinue,
}: {
  products: LibraryProduct[];
  loadingCatalog?: boolean;
  activePartLabel: string;
  selectedProductIds: Set<number>;
  selectedProductItemIds: Map<number, number>;
  onAdd: (product: LibraryProduct) => void;
  onRemove: (itemId: number) => void;
  onOpenProduct: (product: LibraryProduct) => void;
  onContinue: () => void;
}) {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [category, setCategory] = useState("All");
  const [page, setPage] = useState(1);
  const [perPage, setPerPage] = useState(25);

  useEffect(() => {
    const handle = window.setTimeout(() => setActiveQuery(query), 180);
    return () => window.clearTimeout(handle);
  }, [query]);

  const indexed = useMemo(
    () =>
      products.map((product) => ({
        product,
        name: builderProductName(product),
        search: builderProductSearchText(product),
      })),
    [products]
  );

  const categories = useMemo(() => {
    const values = Array.from(new Set(products.map((product) => product.category).filter(Boolean)));
    return ["All", ...values.sort((a, b) => categoryLabel(a).localeCompare(categoryLabel(b)))].slice(0, 12);
  }, [products]);

  const filtered = useMemo(() => {
    const terms = activeQuery.toLowerCase().trim().split(/\s+/).filter(Boolean);
    return indexed
      .filter(({ product, search }) => {
        if (category !== "All" && product.category !== category) return false;
        return terms.every((term) => search.includes(term));
      });
  }, [indexed, activeQuery, category]);

  const totalPages = Math.max(1, Math.ceil(filtered.length / perPage));
  const currentPage = Math.min(page, totalPages);
  const visible = useMemo(
    () => filtered.slice((currentPage - 1) * perPage, currentPage * perPage),
    [filtered, currentPage, perPage]
  );

  useEffect(() => {
    setPage(1);
  }, [activeQuery, category, perPage]);

  return (
    <div className="flex h-full flex-col">
      <div className="space-y-3 border-b border-stone-100 p-5">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" size={16} />
          <input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search for ${activePartLabel.toLowerCase()}`}
            className="w-full rounded-xl border border-stone-200 py-2.5 pl-9 pr-9 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery("")}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-stone-400 hover:text-stone-700"
            >
              <X size={15} />
            </button>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {categories.map((value) => (
            <button
              key={value}
              type="button"
              onClick={() => setCategory(value)}
              className={`rounded-full px-3 py-1.5 text-xs font-medium ${
                category === value ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-600 hover:bg-stone-200"
              }`}
            >
              {value === "All" ? "All" : categoryLabel(value)}
            </button>
          ))}
        </div>
        <p className="text-xs text-stone-400">
          Showing {visible.length} of {filtered.length.toLocaleString()} matches from {products.length.toLocaleString()} catalog products. Add keeps you in this builder.
        </p>
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-xs text-stone-500">
            <span>View</span>
            <select
              value={perPage}
              onChange={(event) => setPerPage(Number(event.target.value))}
              className="rounded-lg border border-stone-200 bg-white px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
            >
              {[25, 50, 100].map((value) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
            <span>per page</span>
          </div>
          <div className="text-xs text-stone-500">
            Page {currentPage} of {totalPages}
          </div>
        </div>
        <button
          type="button"
          onClick={onContinue}
          className="w-full rounded-xl bg-stone-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-40"
          disabled={selectedProductIds.size === 0}
        >
          Continue to mockup →
        </button>
      </div>

      <div className="min-h-0 flex-1 overflow-auto p-5">
        {loadingCatalog && products.length === 0 ? (
          <div className="flex min-h-[360px] items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-stone-50 text-center">
            <div>
              <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-emerald-700 border-t-transparent" />
              <p className="mt-4 font-semibold text-stone-800">Loading catalog</p>
              <p className="mt-1 text-sm text-stone-400">This only loads inside the product picker.</p>
            </div>
          </div>
        ) : visible.length === 0 ? (
          <div className="rounded-2xl border border-dashed border-stone-300 p-8 text-center">
            <p className="font-semibold text-stone-800">No matching products</p>
            <p className="mt-1 text-sm text-stone-400">Try a broader word, SKU, color, or category.</p>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            {visible.map(({ product, name }) => {
              const selectedItemId = selectedProductItemIds.get(product.id);
              const added = selectedItemId != null;
              const price = product.current_price != null ? formatCurrency(product.current_price) : "No price";
              return (
                <div
                  key={product.id}
                  className={`rounded-2xl border bg-white p-3 shadow-sm transition-all ${
                    added ? "border-emerald-700 ring-1 ring-emerald-100" : "border-stone-200 hover:border-stone-300"
                  }`}
                >
                  <button type="button" onClick={() => onOpenProduct(product)} className="block w-full text-left">
                    <div className="mb-3 flex h-32 items-center justify-center rounded-xl bg-stone-50">
                      {product.photo_url ? (
                        <img src={product.photo_url} alt={name} className="h-full w-full object-contain" />
                      ) : (
                        <span className="text-xs font-semibold text-stone-400">Image pending</span>
                      )}
                    </div>
                    <p className="line-clamp-2 min-h-[40px] text-sm font-semibold leading-snug text-stone-900">{name || product.name}</p>
                    <p className="mt-1 truncate text-xs text-stone-400">{product.supplier_sku || product.supplier_name}</p>
                    <p className="mt-2 text-sm font-bold text-stone-900">
                      {price} <span className="text-xs font-medium text-stone-400">/ {unitLabel(product.unit)}</span>
                    </p>
                  </button>
                  <button
                    type="button"
                    onClick={(event) => {
                      event.preventDefault();
                      event.stopPropagation();
                      if (added && selectedItemId != null) {
                        onRemove(selectedItemId);
                      } else {
                        onAdd(product);
                      }
                    }}
                    className={`mt-3 flex w-full items-center justify-center gap-2 rounded-xl px-3 py-2 text-sm font-semibold ${
                      added ? "bg-emerald-900 text-white" : "border border-stone-200 bg-white text-stone-800 hover:bg-stone-50"
                    }`}
                  >
                    {added ? <CheckCircle2 size={15} /> : <Plus size={15} />}
                    {added ? "Added" : "Add"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-stone-100 bg-white px-5 py-4">
        <div className="flex items-center gap-4 text-xs text-stone-500">
          <span>{categories.length - 1} filter groups</span>
          <span className="flex items-center gap-1 font-semibold text-emerald-800">
            <CheckCircle2 size={14} />
            {selectedProductIds.size} saved to this part
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setPage((value) => Math.max(1, value - 1))}
            disabled={currentPage <= 1}
            className="rounded-lg border border-stone-200 px-3 py-2 text-xs font-semibold text-stone-700 disabled:opacity-40"
          >
            Prev
          </button>
          <span className="min-w-16 text-center text-xs text-stone-500">{currentPage} / {totalPages}</span>
          <button
            type="button"
            onClick={() => setPage((value) => Math.min(totalPages, value + 1))}
            disabled={currentPage >= totalPages}
            className="rounded-lg border border-stone-200 px-3 py-2 text-xs font-semibold text-stone-700 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}

export function NewProjectModal({
  onClose,
  onCreated,
  initialClientName = "",
}: {
  onClose: () => void;
  onCreated: (a: Arrangement) => void;
  initialClientName?: string;
}) {
  const [form, setForm] = useState({ name: "", client_name: initialClientName, notes: "" });
  const [saving, setSaving] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const clientRef = useRef<HTMLInputElement>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const savingRef = useRef(false);
  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  const handleCreate = async () => {
    if (savingRef.current) return;
    const payload = {
      name: (nameRef.current?.value || form.name).trim(),
      client_name: (clientRef.current?.value || form.client_name).trim(),
      notes: (notesRef.current?.value || form.notes).trim(),
    };
    if (!payload.name) {
      toast.error("Project name required");
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      const res = await apiClient.create_arrangement({
        name: payload.name,
        client_name: payload.client_name || undefined,
        notes: payload.notes || undefined,
      });
      const arr = await res.json();
      onCreated(arr);
      notifyProjectsChanged();
      onClose();
      toast.success("Project created");
    } catch {
      toast.error("Failed to create project");
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40">
      <div className="mx-4 w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 px-6 py-4">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>New Project</h2>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600"><X size={18} /></button>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); void handleCreate(); }}>
          <div className="space-y-4 px-6 py-5">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Project/job name *</span>
              <input ref={nameRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Bookshelf" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Person / client</span>
              <input ref={clientRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.client_name} onChange={(e) => set("client_name", e.target.value)} placeholder="e.g. Joe Smith" />
            </label>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Notes</span>
              <textarea ref={notesRef} rows={3} className="w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Design goals, dimensions, preferences..." />
            </label>
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-stone-100 px-6 py-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-stone-500 hover:text-stone-700">Cancel</button>
            <button
              type="button"
              onClick={() => void handleCreate()}
              disabled={saving}
              className="rounded-lg px-5 py-2 text-sm font-semibold text-white disabled:opacity-60 hover:opacity-90"
              style={{ backgroundColor: "#2d5a33" }}
            >
              {saving ? "Creating..." : "Create project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

export default function Arrangements() {
  const navigate = useNavigate();
  const location = useLocation();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedId = searchParams.get("id") ? Number(searchParams.get("id")) : null;
  const clientFilter = searchParams.get("client") || "";
  const isClientPath = location.pathname.includes("/clients/project");
  const cachedProjectsList = useMemo(() => readProjectsListCache(), []);

  const [arrangements, setArrangements] = useState<ArrangementSummary[]>(() => cachedProjectsList?.arrangements || []);
  const [arrangement, setArrangement] = useState<Arrangement | null>(null);
  const [products, setProducts] = useState<LibraryProduct[]>([]);
  const [detailProduct, setDetailProduct] = useState<LibraryProduct | null>(null);
  const [activeRoomId, setActiveRoomId] = useState<number | null>(null);
  const [newRoomName, setNewRoomName] = useState("");
  const [newRoomNotes, setNewRoomNotes] = useState("");
  const [activeBucketId, setActiveBucketId] = useState<number | null>(null);
  const [creatingBuiltProduct, setCreatingBuiltProduct] = useState(false);
  const [newScopeName, setNewScopeName] = useState("Tree");
  const [newScopeQuantity, setNewScopeQuantity] = useState("1");
  const [newScopeNotes, setNewScopeNotes] = useState("");
  const [selectedScopeType, setSelectedScopeType] = useState("Tree");
  const [loading, setLoading] = useState(() => !cachedProjectsList);
  const [listSettled, setListSettled] = useState(() => Boolean(cachedProjectsList));
  const [listRefreshing, setListRefreshing] = useState(() => Boolean(cachedProjectsList));
  const [listCachedAt, setListCachedAt] = useState<number | null>(() => cachedProjectsList?.cachedAt || null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [projectHydrating, setProjectHydrating] = useState(false);
  const [productsLoading, setProductsLoading] = useState(false);
  const [productsLoaded, setProductsLoaded] = useState(false);
  const [savingBucket, setSavingBucket] = useState(false);
  const [showNewModal, setShowNewModal] = useState(false);
  const [editingName, setEditingName] = useState(false);
  const [nameEdit, setNameEdit] = useState("");
  const [builderStep, setBuilderStep] = useState<"type" | "products" | "mockup" | "review" | "po">("type");
  const [activePart, setActivePart] = useState<{ label: string; index: number } | null>(null);
  const [treeHeight, setTreeHeight] = useState("");
  const [treeCanopySize, setTreeCanopySize] = useState("");
  const [treeDensity, setTreeDensity] = useState("");
  const builderTopRef = useRef<HTMLDivElement>(null);
  const catalogRef = useRef<HTMLDivElement>(null);
  const scopeNameRef = useRef<HTMLInputElement>(null);
  const scopeQuantityRef = useRef<HTMLInputElement>(null);
  const scopeNotesRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (searchParams.get("new") !== "1") return;
    setShowNewModal(true);
    const next = new URLSearchParams(searchParams);
    next.delete("new");
    setSearchParams(next);
  }, [searchParams, setSearchParams]);

  const filteredArrangements = useMemo(() => {
    if (!clientFilter) return arrangements;
    return arrangements.filter((a) => (a.client_name || "Unassigned") === clientFilter);
  }, [arrangements, clientFilter]);

  const projectRooms = arrangement?.rooms || [];
  const roomContainers = activeRoomId ? (arrangement?.containers || []).filter((c) => c.room_id === activeRoomId) : [];
  const activeRoom = projectRooms.find((room) => room.id === activeRoomId) || null;
  const projectRoomsLoading = Boolean(
    selectedId && projectRooms.length === 0 && (projectHydrating || arrangement?.name === "Opening project...")
  );
  const activeBucket = roomContainers.find((c) => c.id === activeBucketId) || null;
  const orderItems = activeBucket?.items || [];
  const orderSubtotal = orderItems.reduce((sum, item) => {
    const quantity = Number(item.quantity) || 1;
    const price = Number(item.current_price) || 0;
    return sum + quantity * price;
  }, 0);
  const activeParts = activeBucket ? scopePlaceholders(activeBucket) : [];
  const partsComplete = activeBucket
    ? activeParts.filter((label, index) => itemsForPart(activeBucket, label, index).some((item) => (item.status || "selected") === "selected")).length
    : 0;
  const builderSteps = ["type", "products", "mockup", "review", "po"] as const;
  const productTypeOptions = [
    { label: "Tree", icon: Leaf },
    { label: "Sit around", icon: Circle },
    { label: "Garland", icon: Leaf },
    { label: "Spray", icon: Package },
    { label: "Swag", icon: Leaf },
    { label: "Christmas tree", icon: Leaf },
    { label: "Drop in", icon: Package },
    { label: "Planter", icon: Grid3X3 },
    { label: "Custom", icon: Plus },
  ];
  const isTreeScopeType = selectedScopeType === "Tree" || selectedScopeType === "Christmas tree";
  const goToBuilderStep = (step: typeof builderSteps[number]) => {
    setBuilderStep(step);
    window.requestAnimationFrame(() => {
      const target = builderTopRef.current;
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        return;
      }
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  };

  const loadList = async () => {
    if (arrangements.length === 0) setLoading(true);
    else setListRefreshing(true);
    try {
      const response = await apiClient.list_arrangements();
      if (!response.ok) throw new Error("Failed to load projects");
      const data = await response.json();
      const rows = Array.isArray(data) ? data : [];
      setArrangements(rows);
      writeProjectsListCache(rows);
      setListCachedAt(Date.now());
      setListSettled(true);
    } catch {
      if (arrangements.length === 0) toast.error("Failed to load projects");
    } finally {
      setLoading(false);
      setListRefreshing(false);
    }
  };

  const loadProducts = async () => {
    if (productsLoaded || productsLoading) return;
    setProductsLoading(true);
    try {
      const response = await apiClient.list_products({ favorites_only: false });
      if (!response.ok) throw new Error("Failed to load product library");
      const data = await response.json();
      setProducts(Array.isArray(data) ? data : []);
      setProductsLoaded(true);
    } catch {
      toast.error("Failed to load product library");
    } finally {
      setProductsLoading(false);
    }
  };

  const loadDetail = async (id: number, options?: { silent?: boolean }) => {
    setProjectHydrating(true);
    if (!options?.silent) setDetailLoading(true);
    try {
      let data: Arrangement | null = null;
      let lastError: unknown = null;
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          data = await withTimeout(
            apiClient.get_arrangement({ arrangementId: id }).then((r) => {
              if (!r.ok) throw new Error("Failed to load project");
              return r.json();
            }),
            25000
          );
          break;
        } catch (error) {
          lastError = error;
          if (attempt < 2) await delay(600);
        }
      }
      if (!data) throw lastError || new Error("Failed to load project");
      setArrangement(data);
      setActiveBucketId((current) => {
        if (!activeRoomId) return null;
        const roomBuckets = data.containers.filter((c: Container) => c.room_id === activeRoomId);
        if (current && roomBuckets.some((c: Container) => c.id === current)) return current;
        return null;
      });
    } catch {
      const summary = arrangements.find((a) => a.id === id);
      if (arrangement?.id === id) {
        if (!options?.silent) toast.error("Project is still loading. Keeping the current view.");
        return;
      }
      if (summary && !arrangement) {
        setArrangement({
          id: summary.id,
          name: summary.name,
          client_name: summary.client_name,
          notes: "",
          created_by: "",
          created_at: summary.created_at,
          updated_at: summary.updated_at,
          rooms: [],
          containers: [],
          total_cost: summary.total_cost || 0,
          total_with_markup: summary.total_cost || 0,
        });
      }
      if (!options?.silent) toast.error("Project is taking too long to load. Try again.");
    } finally {
      setProjectHydrating(false);
      if (!options?.silent) setDetailLoading(false);
    }
  };

  useEffect(() => { loadList(); }, []);
  useEffect(() => {
    if (selectedId) {
      const summary = arrangements.find((a) => a.id === selectedId);
      setArrangement((current) => {
        if (current?.id === selectedId) return current;
        return summary ? arrangementShellFromSummary(summary) : arrangementRouteShell(selectedId, clientFilter);
      });
      void loadDetail(selectedId, { silent: true });
    } else {
      setArrangement(null);
      setActiveRoomId(null);
      setActiveBucketId(null);
    }
  }, [selectedId]);

  useEffect(() => {
    if (selectedId && arrangement?.id === selectedId && arrangement.name === "Opening project..." && arrangements.length > 0) {
      const summary = arrangements.find((a) => a.id === selectedId);
      if (summary) setArrangement(arrangementShellFromSummary(summary));
    }
    if (selectedId && !arrangement && arrangements.length > 0 && !detailLoading) {
      void loadDetail(selectedId, { silent: true });
    }
  }, [arrangements.length, selectedId, arrangement?.id, arrangement?.name, detailLoading]);

  useEffect(() => {
    if (!activeBucket) {
      setActivePart(null);
      return;
    }
    setActivePart((current) => current || { label: scopePlaceholders(activeBucket)[0] || "Products", index: 0 });
  }, [activeBucket?.id]);

  const enterProductPicker = () => {
    void loadProducts();
    goToBuilderStep("products");
  };

  const selectProject = (id: number) => setSearchParams(clientFilter ? { client: clientFilter, id: String(id) } : { id: String(id) });
  const clearSelection = () => {
    if (isClientPath) {
      navigate(clientFilter ? `/clients?client=${encodeURIComponent(clientFilter)}` : "/clients");
      return;
    }
    setSearchParams(clientFilter ? { client: clientFilter } : {});
  };
  const showAllProjects = () => setSearchParams({});
  const showClientProjects = () => setSearchParams({ client: clientFilter });
  const openRoom = (roomId: number) => {
    setActiveRoomId(roomId);
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };
  const closeRoom = () => {
    setActiveRoomId(null);
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };
  const openBucketCatalog = (bucketId: number, part?: { label: string; index: number }) => {
    setActiveBucketId(bucketId);
    setCreatingBuiltProduct(false);
    setActivePart(part || null);
    enterProductPicker();
  };
  const openBuiltProduct = (bucket: Container) => {
    setActiveBucketId(bucket.id);
    setCreatingBuiltProduct(false);
    setActivePart({ label: scopePlaceholders(bucket)[0] || "Products", index: 0 });
    enterProductPicker();
  };
  const startNewBuiltProduct = () => {
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(true);
    goToBuilderStep("type");
  };
  const goBackBuilderStep = () => {
    const currentIndex = builderSteps.indexOf(builderStep);
    if (currentIndex > 0) {
      goToBuilderStep(builderSteps[currentIndex - 1]);
      return;
    }
    backToBuiltProducts();
  };
  const backToBuiltProducts = () => {
    setActiveBucketId(null);
    setActivePart(null);
    setCreatingBuiltProduct(false);
    goToBuilderStep("type");
  };

  const addRoom = async () => {
    const name = newRoomName.trim();
    if (!arrangement || !name) return;
    try {
      const res = await apiClient.request<Arrangement>({
        path: `/routes/arrangements/room/add/${arrangement.id}`,
        method: "POST",
        body: { name, notes: newRoomNotes.trim() || undefined },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error(await res.text().catch(() => "Failed to add room"));
      const updated = await res.json();
      setArrangement(updated);
      setNewRoomName("");
      setNewRoomNotes("");
      notifyProjectsChanged();
      toast.success("Room/design package added");
    } catch {
      toast.error("Failed to add room/design package");
    }
  };

  const removeRoom = async (roomId: number) => {
    if (!arrangement || !confirm("Delete this room/design package? Existing scopes will stay with the project but will no longer be assigned to this room.")) return;
    try {
      const res = await apiClient.request({ path: `/routes/arrangements/room/delete/${roomId}`, method: "DELETE" });
      if (!res.ok) throw new Error("Failed");
      if (activeRoomId === roomId) closeRoom();
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success("Room/design package deleted");
    } catch {
      toast.error("Failed to delete room/design package");
    }
  };

  const deleteProject = async (id: number) => {
    if (!confirm("Delete this project?")) return;
    try {
      await apiClient.delete_arrangement({ arrangementId: id });
      setArrangements((prev) => {
        const next = prev.filter((a) => a.id !== id);
        writeProjectsListCache(next);
        return next;
      });
      if (selectedId === id) clearSelection();
      notifyProjectsChanged();
      toast.success("Project deleted");
    } catch {
      toast.error("Failed to delete project");
    }
  };

  const addBucket = async () => {
    const scopeName = (scopeNameRef.current?.value || newScopeName).trim();
    const quantityValue = scopeQuantityRef.current?.value || newScopeQuantity;
    const notesValue = scopeNotesRef.current?.value || newScopeNotes;
    const setupNotes = [
      notesValue.trim(),
      isTreeScopeType && treeHeight.trim() ? `Height: ${treeHeight.trim()}` : "",
      isTreeScopeType && treeCanopySize.trim() ? `Canopy size: ${treeCanopySize.trim()}` : "",
      isTreeScopeType && treeDensity.trim() ? `Density: ${treeDensity.trim()}` : "",
    ].filter(Boolean).join("\n");
    if (!arrangement || !scopeName) return;
    setSavingBucket(true);
    try {
      const res = await apiClient.add_container(
        { arrangementId: arrangement.id },
        {
          label: scopeName,
          room_id: activeRoomId,
          bucket_type: selectedScopeType === "Custom" ? scopeName : selectedScopeType,
          requested_quantity: Math.max(1, Number(quantityValue) || 1),
          scope_notes: setupNotes || undefined,
          items: [],
        } as any
      );
      if (!res.ok) {
        const message = await res.text().catch(() => "");
        throw new Error(message || "Failed to add scope");
      }
      const updated = await res.json();
      if (!updated?.containers || !Array.isArray(updated.containers)) {
        throw new Error("Scope response was incomplete");
      }
      setArrangement(updated);
      const createdBucket = updated.containers[updated.containers.length - 1] || null;
      setCreatingBuiltProduct(false);
      setActiveBucketId(createdBucket?.id ?? null);
      if (createdBucket) {
        setActivePart({ label: scopePlaceholders(createdBucket)[0] || "Products", index: 0 });
        enterProductPicker();
      }
      setNewScopeName(selectedScopeType === "Custom" ? "" : selectedScopeType);
      setNewScopeQuantity("1");
      setNewScopeNotes("");
      setTreeHeight("");
      setTreeCanopySize("");
      setTreeDensity("");
      if (scopeNameRef.current) scopeNameRef.current.value = selectedScopeType === "Custom" ? "" : selectedScopeType;
      if (scopeQuantityRef.current) scopeQuantityRef.current.value = "1";
      if (scopeNotesRef.current) scopeNotesRef.current.value = "";
      notifyProjectsChanged();
      toast.success("Scope added");
    } catch (error) {
      console.error("Failed to add scope", error);
      toast.error("Failed to add scope");
    } finally {
      setSavingBucket(false);
    }
  };

  const goToProductParts = async () => {
    if (activeBucket) {
      setActivePart((current) => current || { label: scopePlaceholders(activeBucket)[0] || "Products", index: 0 });
      enterProductPicker();
      return;
    }
    await addBucket();
  };

  const removeBucket = async (containerId: number) => {
    if (!arrangement) return;
    try {
      await apiClient.remove_container({ containerId });
      if (activeBucketId === containerId) backToBuiltProducts();
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success("Scope removed");
    } catch {
      toast.error("Failed to remove scope");
    }
  };

  const addProductToActiveBucket = async (product: LibraryProduct) => {
    if (!arrangement || !activeBucket) {
      toast.error("Choose a scope first");
      return;
    }
    const bucketId = activeBucket.id;
    const bucketLabel = scopeTitle(activeBucket);
    const part = activePart || { label: scopePlaceholders(activeBucket)[0] || "Products", index: 0 };
    const key = partKey(part.label, part.index);
    const optimisticId = -Date.now();
    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => {
          if (bucket.id !== bucketId) return bucket;
          const existing = bucket.items.find((item) => {
            const existingKey = item.part_key || partKey(item.part_label || "", item.part_order || 0);
            return item.product_id === product.id && existingKey === key;
          });
          if (existing) {
            return {
              ...bucket,
              items: bucket.items.map((item) =>
                item.id === existing.id
                  ? {
                      ...item,
                      quantity: item.quantity + 1,
                      line_total: (Number(item.current_price) || 0) * (item.quantity + 1),
                      status: "selected",
                    }
                  : item
              ),
              subtotal: (bucket.subtotal || 0) + (Number(product.current_price) || 0),
            };
          }
          const unitPrice = Number(product.current_price) || 0;
          return {
            ...bucket,
            items: [
              ...bucket.items,
              {
                id: optimisticId,
                product_id: product.id,
                product_name: product.name,
                product_category: product.category,
                unit: product.unit,
                current_price: product.current_price,
                supplier_name: product.supplier_name,
                supplier_sku: product.supplier_sku,
                photo_url: product.photo_url,
                quantity: 1,
                line_total: unitPrice,
                status: "selected",
                part_key: key,
                part_label: part.label,
                part_order: part.index,
              },
            ],
            subtotal: (bucket.subtotal || 0) + unitPrice,
          };
        }),
      };
    });
    try {
      await apiClient.add_item_to_container(
        { containerId: bucketId },
        { product_id: product.id, quantity: 1, status: "selected", part_key: key, part_label: part.label, part_order: part.index } as any
      );
      void loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
      toast.success(`Saved ${product.name} to ${bucketLabel} · ${part.label}`);
    } catch {
      void loadDetail(arrangement.id, { silent: true });
      toast.error("Could not add product to scope");
    }
  };

  const removeItem = async (itemId: number) => {
    if (!arrangement) return;
    const itemToRemove = arrangement.containers.flatMap((bucket) => bucket.items).find((item) => item.id === itemId);
    if (!itemToRemove) return;

    setArrangement((current) => {
      if (!current) return current;
      return {
        ...current,
        containers: current.containers.map((bucket) => {
          const existsInBucket = bucket.items.some((item) => item.id === itemId);
          if (!existsInBucket) return bucket;
          const removedLineTotal = Number(itemToRemove.line_total) || (Number(itemToRemove.current_price) || 0) * (Number(itemToRemove.quantity) || 1);
          return {
            ...bucket,
            items: bucket.items.filter((item) => item.id !== itemId),
            subtotal: Math.max(0, (Number(bucket.subtotal) || 0) - removedLineTotal),
          };
        }),
      };
    });

    if (itemId < 0) return;

    try {
      await apiClient.remove_item({ itemId });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      await loadDetail(arrangement.id, { silent: true });
      toast.error("Failed to remove item");
    }
  };

  const updateQty = async (itemId: number, qty: number) => {
    if (!arrangement) return;
    try {
      await apiClient.update_item_quantity({ itemId, quantity: qty });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      toast.error("Failed to update quantity");
    }
  };

  const updateStatus = async (itemId: number, status: ItemStatus) => {
    if (!arrangement) return;
    try {
      await apiClient.request({
        path: `/routes/arrangements/item/status/${itemId}`,
        method: "PUT",
        body: { status },
        type: ContentType.Json,
      });
      await loadDetail(arrangement.id, { silent: true });
      notifyProjectsChanged();
    } catch {
      toast.error("Failed to update product status");
    }
  };

  const saveName = async () => {
    if (!arrangement || !nameEdit.trim()) return;
    try {
      await apiClient.update_arrangement({ arrangementId: arrangement.id }, { name: nameEdit.trim() });
      setArrangement((a) => a ? { ...a, name: nameEdit.trim() } : a);
      setArrangements((prev) => {
        const next = prev.map((a) => a.id === arrangement.id ? { ...a, name: nameEdit.trim() } : a);
        writeProjectsListCache(next);
        return next;
      });
      setEditingName(false);
      notifyProjectsChanged();
      toast.success("Project renamed");
    } catch {
      toast.error("Failed to rename project");
    }
  };

  return (
    <Layout>
      {!selectedId ? (
        <>
          <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4" style={{ backgroundColor: "#f7f4ef" }}>
            <div>
              <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                <button onClick={showAllProjects} className="hover:underline">All Projects</button>
                {clientFilter && (
                  <>
                    <span className="text-stone-300">/</span>
                    <span className="text-stone-500">{clientFilter}</span>
                  </>
                )}
              </div>
              <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
                {clientFilter ? `${clientFilter} Projects` : "Projects"}
              </h1>
              <p className="mt-0.5 text-xs text-stone-500">
                {!listSettled && filteredArrangements.length === 0
                  ? "Checking projects..."
                  : `${filteredArrangements.length} project${filteredArrangements.length !== 1 ? "s" : ""} · clients, jobs, and scopes${listRefreshing ? " · Refreshing..." : listCachedAt ? ` · Updated ${formatProjectsCacheStamp(listCachedAt)}` : ""}`}
              </p>
            </div>
            <button onClick={() => setShowNewModal(true)} className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
              <Plus size={15} strokeWidth={2.2} /> New Project
            </button>
          </header>
          <div className="px-10 py-6">
            {loading && filteredArrangements.length === 0 ? (
              <div className="flex items-center justify-center py-24">
                <div className="h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              </div>
            ) : listSettled && filteredArrangements.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-24 text-center">
                <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "#e8f0e8" }}>
                  <Package size={28} className="text-emerald-600" strokeWidth={1.5} />
                </div>
                <p className="mb-1 text-base font-medium text-stone-600">No projects yet</p>
                <p className="mb-4 max-w-xs text-sm leading-relaxed text-stone-400">Create a client project, then add scopes like Tree, Garland, or Bookshelf.</p>
                <button onClick={() => setShowNewModal(true)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>Create First Project</button>
              </div>
            ) : (
              <div className="grid gap-3">
                {filteredArrangements.map((a) => (
                  <div key={a.id} onClick={() => selectProject(a.id)} className="group flex cursor-pointer items-center gap-4 rounded-xl border border-stone-200 bg-white px-6 py-4 transition-all hover:shadow-sm">
                    <div className="flex h-10 w-10 flex-shrink-0 items-center justify-center rounded-lg" style={{ backgroundColor: "#e8f0e8" }}>
                      <Package size={18} className="text-emerald-700" strokeWidth={1.5} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm font-semibold text-stone-800">{a.name}</p>
                      <p className="mt-0.5 text-xs text-stone-400">{a.client_name || "No client"} · {a.container_count} scope{a.container_count !== 1 ? "s" : ""}</p>
                    </div>
                    <div className="mr-4 text-right">
                      <p className="text-sm font-semibold text-stone-800">{formatCurrency(a.total_cost)}</p>
                      <p className="text-xs text-stone-400">selected cost</p>
                    </div>
                    <p className="text-xs text-stone-300">{new Date(a.updated_at).toLocaleDateString()}</p>
                    <button onClick={(e) => { e.stopPropagation(); deleteProject(a.id); }} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-300 opacity-0 transition-colors hover:bg-red-50 hover:text-red-500 group-hover:opacity-100">
                      <Trash2 size={14} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      ) : arrangement ? (
        <>
          <header className="sticky top-0 z-10 flex items-center gap-4 border-b border-stone-200 px-10 py-4" style={{ backgroundColor: "#f7f4ef" }}>
            <button onClick={activeRoomId ? (activeBucket || creatingBuiltProduct ? backToBuiltProducts : closeRoom) : clearSelection} className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 transition-colors hover:bg-stone-200">
              <ArrowLeft size={16} />
            </button>
            <div className="flex-1">
              {isClientPath && (
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <button onClick={() => navigate("/clients")} className="hover:underline">Clients</button>
                  <span className="text-stone-300">/</span>
                  <button onClick={clearSelection} className="hover:underline">{arrangement.client_name || clientFilter || "Client"}</button>
                  <span className="text-stone-300">/</span>
                  <span className="text-stone-500">{arrangement.name}</span>
                  {activeRoom && (
                    <>
                      <span className="text-stone-300">/</span>
                      <span className="text-stone-500">{activeRoom.name}</span>
                    </>
                  )}
                </div>
              )}
              {!isClientPath && (
                <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
                  <button onClick={showAllProjects} className="hover:underline">All Projects</button>
                  {clientFilter && (
                    <>
                      <span className="text-stone-300">/</span>
                      <button onClick={showClientProjects} className="hover:underline">{clientFilter}</button>
                    </>
                  )}
                  <span className="text-stone-300">/</span>
                  <span className="text-stone-500">{arrangement.name}</span>
                  {activeRoom && (
                    <>
                      <span className="text-stone-300">/</span>
                      <span className="text-stone-500">{activeRoom.name}</span>
                    </>
                  )}
                </div>
              )}
              {editingName ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    className="rounded-lg border border-emerald-300 px-2 py-1 text-sm font-semibold text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300"
                    value={nameEdit}
                    onChange={(e) => setNameEdit(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") saveName(); if (e.key === "Escape") setEditingName(false); }}
                  />
                  <button onClick={saveName} className="p-1 text-emerald-600 hover:text-emerald-800"><Save size={14} /></button>
                  <button onClick={() => setEditingName(false)} className="p-1 text-stone-400 hover:text-stone-600"><X size={14} /></button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <h1 className="text-lg font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{arrangement.name}</h1>
                  <button onClick={() => { setNameEdit(arrangement.name); setEditingName(true); }} className="text-stone-300 transition-colors hover:text-stone-500"><Pencil size={13} /></button>
                </div>
              )}
              <p className="text-xs text-stone-400">{arrangement.client_name || "No client"} · saved ideas do not affect pricing until selected</p>
            </div>
            <div className="text-right">
              <p className="text-sm font-bold text-stone-800">{formatCurrency(arrangement.total_with_markup)}</p>
              <p className="text-xs text-stone-400">quote estimate · selected base {formatCurrency(arrangement.total_cost)}</p>
            </div>
            <button onClick={() => navigate(`/invoice?arrangement_id=${arrangement.id}`)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "#2d5a33" }}>
              View Invoice
            </button>
          </header>

          {!activeRoomId ? (
            <div className="px-10 py-6">
              <div className="mb-6 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                <div className="mb-4">
                  <h2 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>Rooms & design packages</h2>
                  <p className="mt-1 text-sm text-stone-500">Add a room, area, or design package first. Then build individual products inside it.</p>
                </div>
                <div className="grid gap-3 md:grid-cols-[1fr_1fr_auto]">
                  <input
                    value={newRoomName}
                    onChange={(e) => setNewRoomName(e.target.value)}
                    placeholder="Living Room, Dining Room, Front Porch..."
                    className="rounded-xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                  <input
                    value={newRoomNotes}
                    onChange={(e) => setNewRoomNotes(e.target.value)}
                    placeholder="Optional notes"
                    className="rounded-xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                  />
                  <button
                    onClick={addRoom}
                    disabled={!newRoomName.trim()}
                    className="rounded-xl px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
                    style={{ backgroundColor: "#2d5a33" }}
                  >
                    Add package
                  </button>
                </div>
              </div>

              {projectRoomsLoading ? (
                <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3" aria-live="polite" aria-label="Loading design packages">
                  {[0, 1, 2].map((index) => (
                    <div key={index} className="rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                      <div className="mb-4 h-3 w-28 animate-pulse rounded bg-stone-100" />
                      <div className="h-6 w-44 animate-pulse rounded bg-stone-100" />
                      <div className="mt-2 h-4 w-60 max-w-full animate-pulse rounded bg-stone-100" />
                      <div className="mt-5 grid grid-cols-3 gap-2">
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                        <div className="h-16 animate-pulse rounded-xl bg-stone-50" />
                      </div>
                      <div className="mt-4 h-10 animate-pulse rounded-xl bg-stone-100" />
                    </div>
                  ))}
                  <p className="sr-only">Loading design packages</p>
                </div>
              ) : projectRooms.length === 0 ? (
                <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white px-6 py-16 text-center">
                  <Grid3X3 className="mb-3 text-emerald-700" size={28} />
                  <p className="font-semibold text-stone-800">No rooms or design packages yet</p>
                  <p className="mt-1 max-w-md text-sm text-stone-500">For a whole house, create packages like Living Room, Dining Room, Entry, Patio, or Christmas Install.</p>
                </div>
              ) : (
                <div className="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
                  {projectRooms.map((room) => {
                    const scopes = (arrangement.containers || []).filter((bucket) => bucket.room_id === room.id);
                    const selectedTotal = scopes.reduce((sum, bucket) => sum + (bucket.subtotal || 0), 0);
                    const savedCount = scopes.reduce((sum, bucket) => sum + bucket.items.length, 0);
                    return (
                      <div key={room.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition-all hover:border-emerald-200 hover:shadow-md">
                        <div className="mb-4 flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Design package</p>
                            <h3 className="mt-1 text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{room.name}</h3>
                            {room.notes && <p className="mt-1 line-clamp-2 text-sm text-stone-500">{room.notes}</p>}
                          </div>
                          <button onClick={() => removeRoom(room.id)} className="rounded-lg p-1 text-stone-300 opacity-0 transition-colors hover:bg-stone-100 hover:text-stone-600 group-hover:opacity-100">
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="mb-4 grid grid-cols-3 gap-2">
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Products</p>
                            <p className="mt-1 font-semibold text-stone-900">{scopes.length}</p>
                          </div>
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Saved</p>
                            <p className="mt-1 font-semibold text-stone-900">{savedCount}</p>
                          </div>
                          <div className="rounded-xl bg-emerald-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-emerald-700">Selected</p>
                            <p className="mt-1 font-semibold text-emerald-900">{formatCurrency(selectedTotal)}</p>
                          </div>
                        </div>
                        <button onClick={() => openRoom(room.id)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "#2d5a33" }}>
                          Open package
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          ) : !activeBucket && !creatingBuiltProduct ? (
            <div className="px-10 py-6">
              <div className="mb-6 flex flex-wrap items-start justify-between gap-4 rounded-2xl border border-stone-200 bg-white p-5 shadow-sm">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wide text-emerald-700">Design package</p>
                  <h2 className="mt-1 text-xl font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{activeRoom?.name || "Package"}</h2>
                  <p className="mt-1 max-w-2xl text-sm text-stone-500">Create the individual things that need to be built for this room or package. Each one opens its own product builder.</p>
                </div>
              </div>

              {roomContainers.length === 0 ? (
                <button onClick={startNewBuiltProduct} className="flex min-h-[260px] w-full flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white text-center transition-colors hover:border-emerald-300 hover:bg-emerald-50/40">
                  <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900">+</span>
                  <span className="font-semibold text-stone-900">Create the first built product</span>
                  <span className="mt-1 text-sm text-stone-500">Examples: 2 Fiddle Fig trees, 1 wreath, 1 sit around.</span>
                </button>
              ) : (
                <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                  {roomContainers.map((bucket) => {
                    const selected = bucket.items.filter((item) => (item.status || "selected") === "selected");
                    const candidates = bucket.items.filter((item) => (item.status || "selected") === "candidate");
                    return (
                      <div key={bucket.id} className="group rounded-2xl border border-stone-200 bg-white p-5 shadow-sm transition-all hover:border-emerald-200 hover:shadow-md">
                        <div className="mb-4 flex items-start justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">{bucket.bucket_type || "Built product"}</p>
                            <h3 className="mt-1 text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{scopeQuantity(bucket)}x {scopeTitle(bucket)}</h3>
                            {bucket.scope_notes && <p className="mt-1 line-clamp-2 text-sm text-stone-500">{bucket.scope_notes}</p>}
                          </div>
                          <button onClick={() => removeBucket(bucket.id)} className="rounded-lg p-1 text-stone-300 opacity-0 transition-colors hover:bg-stone-100 hover:text-stone-600 group-hover:opacity-100">
                            <Trash2 size={14} />
                          </button>
                        </div>
                        <div className="mb-4 grid grid-cols-3 gap-2">
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Ideas</p>
                            <p className="mt-1 font-semibold text-stone-900">{candidates.length}</p>
                          </div>
                          <div className="rounded-xl bg-emerald-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-emerald-700">Selected</p>
                            <p className="mt-1 font-semibold text-emerald-900">{selected.length}</p>
                          </div>
                          <div className="rounded-xl bg-stone-50 p-3">
                            <p className="text-[11px] font-semibold uppercase text-stone-400">Cost</p>
                            <p className="mt-1 font-semibold text-stone-900">{formatCurrency(bucket.subtotal)}</p>
                          </div>
                        </div>
                        <div className="mb-4 space-y-2">
                          {scopePlaceholders(bucket).map((label, index) => {
                            const partItems = itemsForPart(bucket, label, index);
                            return (
                              <div key={`${bucket.id}-${label}-${index}`} className="flex items-center justify-between rounded-xl border border-dashed border-stone-200 px-3 py-2 text-sm">
                                <span className="text-stone-600">{label}</span>
                                <span className={partItems.length ? "font-semibold text-emerald-700" : "text-stone-300"}>{partItems.length || "+"}</span>
                              </div>
                            );
                          })}
                        </div>
                        <button onClick={() => openBuiltProduct(bucket)} className="w-full rounded-xl px-4 py-2 text-sm font-semibold text-white" style={{ backgroundColor: "#2d5a33" }}>
                          Open builder
                        </button>
                      </div>
                    );
                  })}
                  <button onClick={startNewBuiltProduct} className="flex min-h-[320px] flex-col items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-white text-center transition-colors hover:border-emerald-300 hover:bg-emerald-50/40">
                    <span className="mb-3 flex h-14 w-14 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900">+</span>
                    <span className="font-semibold text-stone-900">New built product</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
          <div ref={builderTopRef} className="px-6 py-5">
            <div className="mb-4 overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
              <div className="flex flex-wrap items-center justify-between gap-3 border-b border-stone-100 px-5 py-3">
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full border border-stone-200 text-emerald-800">
                    <Leaf size={16} />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-stone-900">Leaf & Ledger</p>
                    <p className="text-xs text-stone-400">{activeBucket ? scopeTitle(activeBucket) : "Product Builder"}</p>
                  </div>
                </div>
                <div className="flex items-center gap-2 text-stone-400">
                  {[Undo2, Redo2, Upload, HelpCircle].map((Icon, index) => (
                    <button key={index} type="button" className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-stone-50 hover:text-stone-700">
                      <Icon size={15} strokeWidth={1.8} />
                    </button>
                  ))}
                  <span className="flex h-8 w-8 items-center justify-center rounded-full bg-stone-100 text-xs font-semibold text-stone-600">A</span>
                </div>
              </div>
              <div className="flex flex-wrap items-center justify-between gap-3 px-5 py-4">
                <div className="flex flex-wrap items-center gap-4 text-sm">
                  <span className="flex items-center gap-2 text-stone-500"><span className="h-2 w-2 rounded-full bg-emerald-700" /> Type: <strong className="text-stone-900">{activeBucket ? activeBucket.bucket_type || scopeTitle(activeBucket) : "No scope"}</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Parts: <strong className="text-stone-900">{partsComplete}/{activeParts.length || 0} selected</strong></span>
                  <span className="text-stone-300">|</span>
                  <span className="text-stone-500">Order: <strong className="text-emerald-800">{orderItems.length ? "ready" : "draft"}</strong></span>
                </div>
                <div className="flex items-center gap-2">
                  {builderStep !== "type" && (
                    <button
                      type="button"
                      onClick={goBackBuilderStep}
                      className="flex items-center gap-1 rounded-full border border-stone-200 bg-white px-3 py-1.5 text-xs font-semibold text-stone-700 transition-colors hover:bg-stone-50"
                    >
                      <ArrowLeft size={13} />
                      Back
                    </button>
                  )}
                  {builderSteps.map((step, index) => (
                    <button
                      key={step}
                      onClick={() => goToBuilderStep(step)}
                      className={`rounded-full px-3 py-1.5 text-xs font-semibold transition-colors ${builderStep === step ? "bg-stone-900 text-white" : "bg-stone-100 text-stone-500 hover:bg-stone-200"}`}
                    >
                      {index + 1}. {step === "type" ? "Select type" : step === "products" ? "Choose parts" : step === "mockup" ? "Mockup" : step === "review" ? "Review" : "Order"}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            <div className="grid min-h-[720px] overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm lg:grid-cols-[minmax(0,1fr)_520px]">
              <section className="relative border-r border-stone-100 bg-[radial-gradient(circle_at_1px_1px,#e7e5e4_1px,transparent_0)] [background-size:22px_22px] p-8 pl-24">
                {builderStep === "type" ? (
                  <div className="h-full" aria-label="Empty builder canvas" />
                ) : !activeBucket ? (
                  <div className="flex h-full items-center justify-center text-center">
                    <div>
                      <Package className="mx-auto mb-3 text-emerald-700" size={32} />
                      <p className="font-semibold text-stone-800">Create a scope to start building</p>
                      <p className="mt-1 text-sm text-stone-400">Examples: Fiddle Fig, Wreath, Sitting Arrangement.</p>
                    </div>
                  </div>
                ) : (
                  <div className="mx-auto flex max-w-3xl flex-col gap-5">
                    <div className="mb-1 flex items-center justify-between">
                      <div>
                        <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">Active scope</p>
                        <h2 className="text-xl font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>{scopeQuantity(activeBucket)}x {scopeTitle(activeBucket)}</h2>
                      </div>
                      <button onClick={() => removeBucket(activeBucket.id)} className="rounded-lg px-2 py-1 text-xs text-stone-400 hover:bg-red-50 hover:text-red-500">Delete scope</button>
                    </div>
                    {scopePlaceholders(activeBucket).map((label, index) => {
                      const partItems = itemsForPart(activeBucket, label, index);
                      const selectedPart = activePart?.index === index;
                      const primary = partItems[0];
                      const primaryStatus = primary?.status || "selected";
                      return (
                        <button
                          key={`${label}-${index}`}
                          type="button"
                          onClick={() => openBucketCatalog(activeBucket.id, { label, index })}
                          className={`group relative flex min-h-[128px] items-center gap-4 rounded-2xl border bg-white/95 px-6 py-5 text-left shadow-sm transition-all hover:border-stone-900 hover:shadow-md ${selectedPart ? "border-stone-900 ring-2 ring-stone-100" : "border-dashed border-stone-300"}`}
                        >
                          <span className="absolute -top-3 left-5 rounded-full border border-stone-200 bg-white px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                            {label}
                          </span>
                          {index < scopePlaceholders(activeBucket).length - 1 && <span className="absolute left-[47px] top-[88px] h-10 border-l border-dashed border-stone-300" />}
                          <div className="flex h-12 w-12 flex-shrink-0 items-center justify-center rounded-full bg-stone-100 text-2xl text-stone-900 group-hover:bg-emerald-50 group-hover:text-emerald-800">+</div>
                          <div className="min-w-0 flex-1">
                            {primary ? (
                              <>
                                <p className="line-clamp-2 text-sm font-semibold text-stone-900">{primary.product_name}</p>
                                <p className="mt-1 text-xs text-stone-400">{primary.supplier_sku || primary.supplier_name} · {partItems.length} saved</p>
                                <div className="mt-2 flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      updateStatus(primary.id, primaryStatus === "selected" ? "candidate" : "selected");
                                    }}
                                    className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
                                      primaryStatus === "selected" ? "bg-emerald-50 text-emerald-800 ring-1 ring-emerald-200" : "bg-stone-50 text-stone-500 ring-1 ring-stone-200"
                                    }`}
                                  >
                                    {primaryStatus === "selected" ? "Selected" : "Idea"}
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      openBucketCatalog(activeBucket.id, { label, index });
                                    }}
                                    className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-500 ring-1 ring-stone-200 hover:text-stone-800"
                                  >
                                    Change
                                  </button>
                                  <button
                                    type="button"
                                    onClick={(event) => {
                                      event.preventDefault();
                                      event.stopPropagation();
                                      removeItem(primary.id);
                                    }}
                                    className="rounded-full bg-stone-50 px-2.5 py-1 text-[11px] font-semibold text-stone-400 ring-1 ring-stone-200 hover:text-red-500"
                                  >
                                    Remove
                                  </button>
                                </div>
                              </>
                            ) : (
                              <>
                                <p className="font-semibold text-stone-900">{label}</p>
                                <p className="text-sm text-stone-400">Select product</p>
                              </>
                            )}
                          </div>
                          <span className="rounded-lg border border-stone-200 bg-white px-4 py-2 text-xs font-semibold text-stone-700 shadow-sm">{primary ? "Add more" : "Select product"}</span>
                          {primary?.photo_url && (
                            <img src={primary.photo_url} alt={primary.product_name} className="h-16 w-16 flex-shrink-0 rounded-xl object-contain" />
                          )}
                        </button>
                      );
                    })}
                  </div>
                )}
                <div className="absolute bottom-6 left-6 flex items-center gap-2 rounded-2xl border border-stone-200 bg-white/90 px-3 py-2 text-sm text-stone-600 shadow-sm">
                  <button type="button" className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-stone-100"><Minus size={14} /></button>
                  <span className="min-w-12 text-center text-xs font-semibold">100%</span>
                  <button type="button" className="flex h-7 w-7 items-center justify-center rounded-lg hover:bg-stone-100"><Plus size={14} /></button>
                </div>
              </section>

              <aside className="flex min-h-[720px] flex-col bg-white">
                <div className="border-b border-stone-100 px-5 py-4">
                  <div className="mb-3 flex items-center justify-between">
                    <div>
                      <p className="text-xs text-stone-400">Project / Builder</p>
                      <h3 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>
                        {builderStep === "type" && "Select type"}
                        {builderStep === "products" && (activePart ? `Select ${activePart.label}` : "Choose products")}
                        {builderStep === "mockup" && "Mockup setup"}
                        {builderStep === "review" && "Review selections"}
                        {builderStep === "po" && "Purchase Order Review"}
                      </h3>
                    </div>
                    <button onClick={() => setShowNewModal(false)} className="hidden text-stone-300"><X size={18} /></button>
                  </div>
                </div>

                {builderStep === "type" && (
                  <div className="space-y-4 p-5">
                    <div>
                      <p className="mb-3 text-xs font-semibold text-stone-500">Select a product type</p>
                      <div className="space-y-3">
                        {productTypeOptions.map(({ label, icon: Icon }) => {
                          const selected = selectedScopeType === label;
                          return (
                            <button
                              key={label}
                              type="button"
                              onClick={() => {
                                setSelectedScopeType(label);
                                if (label === "Custom") {
                                  setNewScopeName("");
                                  window.requestAnimationFrame(() => scopeNameRef.current?.focus());
                                  return;
                                }
                                if (!newScopeName.trim() || productTypeOptions.some((option) => option.label.toLowerCase() === newScopeName.trim().toLowerCase())) {
                                  setNewScopeName(label);
                                  if (scopeNameRef.current) scopeNameRef.current.value = label;
                                }
                              }}
                              className={`flex w-full items-center justify-between rounded-xl border px-4 py-3 text-left transition-colors ${selected ? "border-stone-900 bg-white shadow-sm" : "border-stone-200 bg-white hover:border-stone-300"}`}
                            >
                              <span className="flex items-center gap-3 text-sm font-semibold text-stone-800">
                                <Icon size={17} strokeWidth={1.7} />
                                {label}
                              </span>
                              {selected && <CheckCircle2 size={18} className="text-stone-900" />}
                            </button>
                          );
                        })}
                      </div>
                      {selectedScopeType === "Custom" && (
                        <div className="mt-4">
                          <label className="mb-2 block text-xs font-semibold text-stone-500">Custom product type</label>
                          <input ref={scopeNameRef} value={newScopeName} onChange={(e) => setNewScopeName(e.target.value)} placeholder="Type what you are building" className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" />
                        </div>
                      )}
                      <div className="mt-4 grid grid-cols-[90px_1fr] gap-3">
                        <input ref={scopeQuantityRef} value={newScopeQuantity} onChange={(e) => setNewScopeQuantity(e.target.value)} type="number" min="1" aria-label="Quantity" className="rounded-lg border border-stone-200 px-3 py-2 text-sm" />
                        <input ref={scopeNotesRef} value={newScopeNotes} onChange={(e) => setNewScopeNotes(e.target.value)} placeholder="Optional notes" className="rounded-lg border border-stone-200 px-3 py-2 text-sm" />
                      </div>
                      {isTreeScopeType && (
                        <div className="mt-5 rounded-2xl border border-stone-200 bg-stone-50/70 p-4">
                          <p className="text-xs font-semibold uppercase tracking-wide text-stone-500">Tree setup</p>
                          <p className="mt-1 text-xs text-stone-400">These guide the build before products are chosen.</p>
                          <div className="mt-4 grid gap-3">
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Height</span>
                              <input
                                value={treeHeight}
                                onChange={(event) => setTreeHeight(event.target.value)}
                                placeholder="e.g. 8 ft"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Canopy size</span>
                              <input
                                value={treeCanopySize}
                                onChange={(event) => setTreeCanopySize(event.target.value)}
                                placeholder="e.g. full, narrow, 48 in"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                            <label className="block">
                              <span className="mb-1 block text-xs font-semibold text-stone-500">Density</span>
                              <input
                                value={treeDensity}
                                onChange={(event) => setTreeDensity(event.target.value)}
                                placeholder="e.g. light, medium, dense"
                                className="w-full rounded-lg border border-stone-200 bg-white px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                              />
                            </label>
                          </div>
                        </div>
                      )}
                      <button onClick={() => void goToProductParts()} disabled={savingBucket || (!activeBucket && !newScopeName.trim())} className="mt-5 w-full rounded-lg bg-stone-950 px-4 py-3 text-sm font-semibold text-white disabled:opacity-50">Next step →</button>
                    </div>
                  </div>
                )}

                {builderStep === "products" && activeBucket && (
                  <div ref={catalogRef} className="min-h-0 flex-1">
                    <BuilderProductPicker
                      products={products}
                      loadingCatalog={productsLoading}
                      activePartLabel={activePart ? activePart.label : "Products"}
                      selectedProductIds={new Set(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => item.product_id))}
                      selectedProductItemIds={new Map(itemsForPart(activeBucket, activePart?.label || "Products", activePart?.index || 0).map((item) => [item.product_id, item.id]))}
                      onAdd={addProductToActiveBucket}
                      onRemove={removeItem}
                      onOpenProduct={setDetailProduct}
                      onContinue={() => goToBuilderStep("mockup")}
                    />
                  </div>
                )}

                {builderStep === "mockup" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="rounded-2xl border border-stone-200 bg-white p-4">
                      <p className="text-sm font-semibold text-stone-900">AI mockup</p>
                      <p className="mt-1 text-xs text-stone-500">Mockup generation comes later. This page reserves the workflow for standalone product renders and room placement.</p>
                    </div>
                    <div className="grid grid-cols-3 gap-2">
                      {["Standalone product", "Place in a space", "Both"].map((label, index) => (
                        <button
                          key={label}
                          type="button"
                          className={`rounded-2xl border p-4 text-left text-xs transition-colors ${
                            index === 2 ? "border-emerald-300 bg-emerald-50/50 ring-1 ring-emerald-100" : "border-stone-200 bg-white hover:bg-stone-50"
                          }`}
                        >
                          <p className="font-semibold text-stone-900">{label}</p>
                          <p className="mt-2 text-stone-500">
                            {index === 0 ? "Clean product image." : index === 1 ? "Use a room photo later." : "Product and room view."}
                          </p>
                        </button>
                      ))}
                    </div>
                    <div className="grid gap-3 sm:grid-cols-2">
                      <div className="flex min-h-32 items-center justify-center rounded-2xl border border-dashed border-stone-300 bg-stone-50 text-center">
                        <div>
                          <Upload className="mx-auto text-stone-400" size={22} />
                          <p className="mt-2 text-sm font-semibold text-stone-700">Room photo placeholder</p>
                          <p className="mt-1 text-xs text-stone-400">Upload comes later.</p>
                        </div>
                      </div>
                      <label className="block">
                        <span className="mb-2 block text-xs font-semibold text-stone-500">Placement note</span>
                        <textarea
                          rows={5}
                          placeholder="Example: place near window, centered beside lounge chair."
                          className="w-full resize-none rounded-2xl border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300"
                        />
                      </label>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Skip mockup</button>
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Continue to review</button>
                    </div>
                  </div>
                )}

                {builderStep === "review" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="rounded-2xl border border-stone-200 bg-white p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <p className="font-semibold text-stone-900">Review {scopeTitle(activeBucket)}</p>
                          <p className="mt-1 text-xs text-stone-400">Saved ideas stay as candidates. Selected products count toward cost and purchase order.</p>
                        </div>
                        <div className="rounded-xl bg-emerald-50 px-3 py-2 text-right">
                          <p className="text-[11px] font-semibold uppercase tracking-wide text-emerald-700">Selected cost</p>
                          <p className="font-semibold text-emerald-900">{formatCurrency(activeBucket.subtotal)}</p>
                        </div>
                      </div>
                    </div>
                    {scopePlaceholders(activeBucket).map((label, index) => (
                      <div key={`${label}-review`} className="rounded-2xl border border-stone-200 bg-white p-3">
                        <div className="mb-2 flex items-center justify-between">
                          <p className="text-xs font-semibold uppercase tracking-wide text-stone-400">{label}</p>
                          <button
                            type="button"
                            onClick={() => { setActivePart({ label, index }); enterProductPicker(); }}
                            className="text-xs font-semibold text-emerald-800 hover:text-emerald-900"
                          >
                            Edit product
                          </button>
                        </div>
                        {itemsForPart(activeBucket, label, index).length === 0 ? (
                          <button
                            type="button"
                            onClick={() => { setActivePart({ label, index }); enterProductPicker(); }}
                            className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-stone-300 py-4 text-sm font-semibold text-stone-500 hover:border-emerald-300 hover:bg-emerald-50/40"
                          >
                            <Plus size={16} />
                            Add product
                          </button>
                        ) : itemsForPart(activeBucket, label, index).map((item) => {
                          const status = item.status || "selected";
                          return (
                            <div key={item.id} className={`mb-2 flex items-center gap-3 rounded-xl border p-2 last:mb-0 ${status === "selected" ? "border-emerald-200 bg-emerald-50/40" : "border-stone-100 bg-stone-50"}`}>
                              {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-12 w-12 rounded-lg object-contain" /> : <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-white text-[10px] font-semibold text-stone-400">No image</div>}
                              <div className="min-w-0 flex-1">
                                <p className="truncate text-sm font-medium text-stone-800">{item.product_name}</p>
                                <p className="text-xs text-stone-400">{item.supplier_sku || item.supplier_name} · {formatCurrency(item.current_price)} / {unitLabel(item.unit)}</p>
                              </div>
                              <button onClick={() => updateStatus(item.id, status === "selected" ? "candidate" : "selected")} className={`rounded-full px-3 py-1 text-[11px] font-semibold ${status === "selected" ? "bg-emerald-800 text-white" : "bg-white text-stone-500 ring-1 ring-stone-200"}`}>{status === "selected" ? "Selected" : "Candidate"}</button>
                            </div>
                          );
                        })}
                      </div>
                    ))}
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("mockup")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Back to mockup</button>
                      <button onClick={() => goToBuilderStep("po")} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Purchase order review</button>
                    </div>
                  </div>
                )}

                {builderStep === "po" && activeBucket && (
                  <div className="space-y-4 p-5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-lg font-semibold text-stone-900" style={{ fontFamily: "Georgia, serif" }}>Purchase Order Review</h3>
                        <p className="text-xs text-stone-400">Drafted from selected products only.</p>
                      </div>
                    </div>
                    <div className="overflow-hidden rounded-2xl border border-stone-200">
                      {orderItems.length > 0 && (
                        <div className="grid grid-cols-[1.3fr_1fr_52px_82px_86px] gap-3 border-b border-stone-100 bg-stone-50 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-stone-400">
                          <span>Part</span>
                          <span>Vendor</span>
                          <span className="text-right">Qty</span>
                          <span className="text-right">Unit price</span>
                          <span className="text-right">Line total</span>
                        </div>
                      )}
                      {orderItems.length === 0 ? (
                        <p className="p-4 text-sm text-stone-400">No products selected for this built product yet.</p>
                      ) : orderItems.map((item) => (
                        <div key={item.id} className="grid grid-cols-[1.3fr_1fr_52px_82px_86px] gap-3 border-b border-stone-100 p-3 text-sm last:border-b-0">
                          <div className="flex min-w-0 items-center gap-3">
                            {item.photo_url ? <img src={item.photo_url} alt={item.product_name} className="h-11 w-11 rounded-lg object-contain" /> : <div className="h-11 w-11 rounded-lg bg-stone-100" />}
                            <div className="min-w-0">
                              <p className="truncate font-medium text-stone-800">{item.part_label || "Product"}</p>
                              <p className="truncate text-xs text-stone-500">{item.product_name}</p>
                              <p className="text-[11px] text-stone-400">{item.supplier_sku || ""}</p>
                            </div>
                          </div>
                          <div className="min-w-0 self-center">
                            <p className="truncate text-stone-700">{item.supplier_name || "Supplier"}</p>
                            <p className="text-xs text-stone-400">Source price</p>
                          </div>
                          <p className="self-center text-right text-stone-500">{Number(item.quantity) || 1}</p>
                          <p className="self-center text-right text-stone-700">{formatCurrency(item.current_price)}</p>
                          <p className="self-center text-right font-semibold text-stone-900">{formatCurrency((Number(item.current_price) || 0) * (Number(item.quantity) || 1))}</p>
                        </div>
                      ))}
                    </div>
                    <div className="rounded-2xl border border-stone-200 p-4">
                      <div className="flex justify-between text-sm"><span>Product subtotal</span><strong>{formatCurrency(orderSubtotal)}</strong></div>
                      <div className="mt-2 flex justify-between text-sm text-stone-500"><span>Estimated freight</span><span>Set later</span></div>
                      <div className="mt-2 flex justify-between text-sm text-stone-500"><span>Tax estimate</span><span>Set later</span></div>
                      <div className="mt-3 flex justify-between border-t border-stone-100 pt-3 text-base"><span>Total</span><strong>{formatCurrency(orderSubtotal)}</strong></div>
                    </div>
                    <div className="grid grid-cols-2 gap-3">
                      <button onClick={() => goToBuilderStep("review")} className="rounded-lg border border-stone-200 px-4 py-2.5 text-sm font-semibold text-stone-700">Back to mockups</button>
                      <button onClick={() => navigate(`/invoice?arrangement_id=${arrangement.id}`)} className="rounded-lg bg-emerald-800 px-4 py-2.5 text-sm font-semibold text-white">Create purchase order</button>
                    </div>
                  </div>
                )}
              </aside>
            </div>
          </div>
          )}
        </>
      ) : (
        <div className="flex flex-col items-center justify-center px-10 py-40 text-center">
          <p className="text-base font-medium text-stone-700">Project could not load</p>
          <p className="mt-1 max-w-sm text-sm leading-relaxed text-stone-400">
            Go back to All Projects and open it again. The catalog add button will stay on the page when the project is loaded.
          </p>
          <button
            onClick={clearSelection}
            className="mt-4 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
            style={{ backgroundColor: "#2d5a33" }}
          >
            Back to projects
          </button>
        </div>
      )}

      {showNewModal && (
        <NewProjectModal
          initialClientName={clientFilter === "Unassigned" ? "" : clientFilter}
          onClose={() => setShowNewModal(false)}
          onCreated={(arr) => {
            setArrangements((prev) => {
              const next = [{ ...arr, container_count: 0 }, ...prev];
              writeProjectsListCache(next);
              return next;
            });
            setListSettled(true);
            setListCachedAt(Date.now());
            notifyProjectsChanged();
          }}
        />
      )}
      {detailProduct && <ProductDetailModal product={detailProduct} onClose={() => setDetailProduct(null)} />}
    </Layout>
  );
}
