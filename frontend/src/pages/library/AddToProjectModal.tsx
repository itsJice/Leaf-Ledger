// Modal to save a product into a project's bucket (candidate item).
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useEffect, useState } from "react";
import { X } from "components/icons";
import { apiClient } from "app";
import { toast } from "sonner";
import { notifyProjectsChanged } from "utils/projectsChanged";
import { displayProductName } from "./display";
import type { Product, ProjectSummary, ProjectBucket, ProjectDetail } from "./types";

async function addProductToBucket(containerId: number, productId: number, status: "candidate" | "selected" = "candidate") {
  await apiClient.add_item_to_container(
    { containerId },
    { product_id: productId, quantity: 1, status } as any
  );
}

export function AddToProjectModal({
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
      .then((value) => {
        const rows = value as unknown as ProjectSummary[];
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
      .then((value) => {
        const detail = value as unknown as ProjectDetail;
        setProject(detail);
        setSelectedBucketId(detail.containers?.[0]?.id ?? null);
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
      const detail = await res.json() as unknown as ProjectDetail;
      setProject(detail);
      const buckets = detail.containers || [];
      const created = buckets[buckets.length - 1];
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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 ll-overlay">
      <div className="w-full max-w-md rounded-2xl bg-white shadow-2xl ll-modal">
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
            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
          >
            {saving ? "Saving..." : "Save to bucket"}
          </button>
        </div>
      </div>
    </div>
  );
}
