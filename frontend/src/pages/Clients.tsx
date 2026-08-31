import React, { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  ArrowRight,
  Briefcase,
  Check,
  ChevronDown,
  FolderOpen,
  Mail,
  MapPin,
  MessageSquare,
  Pencil,
  Phone,
  Plus,
  Trash2,
  TreePine,
  X,
  Users,
} from "lucide-react";
import Layout from "components/Layout";
import { apiClient } from "app";
import { ContentType } from "../apiclient/http-client";
import { formatCurrency } from "utils/format";
import { toast } from "sonner";
import { NewProjectModal } from "./Arrangements";

type ProjectSummary = {
  id: number;
  name: string;
  client_name?: string | null;
  created_at: string;
  updated_at: string;
  total_cost: number;
  container_count: number;
};

type Bucket = {
  id: number;
  label?: string | null;
  bucket_type?: string | null;
  requested_quantity?: number | null;
  scope_notes?: string | null;
  sort_order: number;
  items?: Array<unknown>;
};

type ProjectDetail = ProjectSummary & {
  containers: Bucket[];
};

type ActivityEntry = {
  id: number;
  kind: string;
  season: string;
  summary: string;
  detail?: Record<string, unknown> | null;
  occurred_at?: string | null;
  created_at?: string | null;
};

type SecondaryContact = {
  label: string;
  phone?: string | null;
  email?: string | null;
};

type ClientRecord = {
  id?: number | null;
  name: string;
  email?: string | null;
  phone?: string | null;
  notes?: string | null;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  secondary_contacts?: SecondaryContact[];
  created_at?: string | null;
  updated_at?: string | null;
  project_count: number;
  bucket_count: number;
  selected_cost: number;
  last_project_at?: string | null;
  source: "saved" | "from_projects";
  activity?: ActivityEntry[];
};

type ClientGroup = {
  id?: number | null;
  name: string;
  email?: string | null;
  phone?: string | null;
  notes?: string | null;
  street?: string | null;
  city?: string | null;
  state?: string | null;
  zip?: string | null;
  secondaryContacts: SecondaryContact[];
  activity: ActivityEntry[];
  source: "saved" | "from_projects";
  projects: ProjectSummary[];
  projectCount: number;
  bucketCount: number;
  selectedCost: number;
  updatedAt?: string | null;
};

const LOCAL_CLIENTS_KEY = "leaf-ledger-local-clients-v1";
const CLIENTS_PAGE_CACHE_KEY = "leaf-ledger:clients-page-cache:v1";

type ClientsPageCache = {
  clientRows: ClientRecord[];
  projects: ProjectSummary[];
  cachedAt: number;
};

function readClientsPageCache(): ClientsPageCache | null {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(CLIENTS_PAGE_CACHE_KEY) || "null");
    if (!parsed || !Array.isArray(parsed.clientRows) || !Array.isArray(parsed.projects)) return null;
    return parsed;
  } catch {
    return null;
  }
}

function writeClientsPageCache(clientRows: ClientRecord[], projects: ProjectSummary[]) {
  try {
    window.localStorage.setItem(CLIENTS_PAGE_CACHE_KEY, JSON.stringify({ clientRows, projects, cachedAt: Date.now() }));
  } catch {
    // localStorage is only a speed cache; failures should not block the app.
  }
}

function formatCacheStamp(ms?: number | null) {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

function normalizedClientName(name?: string | null) {
  const trimmed = (name || "").trim();
  return trimmed || "Unassigned";
}

function readLocalClients(): ClientRecord[] {
  try {
    const rows = JSON.parse(window.localStorage.getItem(LOCAL_CLIENTS_KEY) || "[]");
    return Array.isArray(rows) ? rows : [];
  } catch {
    return [];
  }
}

function writeLocalClients(rows: ClientRecord[]) {
  window.localStorage.setItem(LOCAL_CLIENTS_KEY, JSON.stringify(rows));
}

function mergeClients(primary: ClientRecord[], secondary: ClientRecord[] = []) {
  const map = new Map<string, ClientRecord>();
  [...secondary, ...primary].forEach((client) => {
    const name = normalizedClientName(client.name);
    map.set(name.toLowerCase(), { ...client, name });
  });
  return Array.from(map.values()).sort((a, b) => normalizedClientName(a.name).localeCompare(normalizedClientName(b.name)));
}

function makeLocalClient(payload: { name: string; email: string; phone: string; notes: string }): ClientRecord {
  const now = new Date().toISOString();
  return {
    id: -Date.now(),
    name: payload.name,
    email: payload.email || null,
    phone: payload.phone || null,
    notes: payload.notes || null,
    street: null,
    city: null,
    state: null,
    zip: null,
    created_at: now,
    updated_at: now,
    project_count: 0,
    bucket_count: 0,
    selected_cost: 0,
    last_project_at: null,
    source: "saved",
    activity: [],
  };
}

function bucketTitle(bucket: Bucket) {
  return bucket.label || bucket.bucket_type || `Scope ${bucket.sort_order + 1}`;
}

function bucketQuantity(bucket: Bucket) {
  return Math.max(1, Number(bucket.requested_quantity || 1));
}

function withClientTimeout<T>(promise: Promise<T>, ms = 8000): Promise<T> {
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

function buildClientGroups(clientRows: ClientRecord[], projects: ProjectSummary[]) {
  const groups = new Map<string, ClientGroup>();
  const projectStats = new Map<string, {
    name: string;
    projects: ProjectSummary[];
    projectCount: number;
    bucketCount: number;
    selectedCost: number;
    updatedAt?: string | null;
  }>();

  projects.forEach((project) => {
    const name = normalizedClientName(project.client_name);
    const key = name.toLowerCase();
    const existing = projectStats.get(key) || {
      name,
      projects: [],
      projectCount: 0,
      bucketCount: 0,
      selectedCost: 0,
      updatedAt: project.updated_at,
    };

    existing.projects.push(project);
    existing.projectCount += 1;
    existing.bucketCount += project.container_count || 0;
    existing.selectedCost += project.total_cost || 0;
    if (!existing.updatedAt || new Date(project.updated_at).getTime() > new Date(existing.updatedAt).getTime()) {
      existing.updatedAt = project.updated_at;
    }
    projectStats.set(key, existing);
  });

  clientRows.forEach((client) => {
    const name = normalizedClientName(client.name);
    const key = name.toLowerCase();
    const stats = projectStats.get(key);
    const updatedAt = stats?.updatedAt || client.updated_at || client.last_project_at;
    groups.set(name.toLowerCase(), {
      id: client.id,
      name,
      email: client.email,
      phone: client.phone,
      notes: client.notes,
      street: client.street,
      city: client.city,
      state: client.state,
      zip: client.zip,
      secondaryContacts: client.secondary_contacts || [],
      activity: client.activity || [],
      source: client.source,
      projects: stats?.projects || [],
      projectCount: stats ? stats.projectCount : client.project_count || 0,
      bucketCount: stats ? stats.bucketCount : client.bucket_count || 0,
      selectedCost: stats ? stats.selectedCost : client.selected_cost || 0,
      updatedAt,
    });
  });

  projectStats.forEach((stats, key) => {
    if (groups.has(key)) return;
    groups.set(key, {
      name: stats.name,
      secondaryContacts: [],
      activity: [],
      source: "from_projects" as const,
      projects: stats.projects,
      projectCount: stats.projectCount,
      bucketCount: stats.bucketCount,
      selectedCost: stats.selectedCost,
      updatedAt: stats.updatedAt,
    });
  });

  return Array.from(groups.values()).sort((a, b) => a.name.localeCompare(b.name));
}

function NewClientModal({ client, onClose, onSaved }: {
  client?: ClientGroup | null;
  onClose: () => void;
  onSaved: (client: ClientRecord) => void;
}) {
  const editing = Boolean(client?.id);
  const [form, setForm] = useState({
    name: client?.name || "", email: client?.email || "", phone: client?.phone || "",
    notes: client?.notes || "", street: client?.street || "", city: client?.city || "",
    state: client?.state || "", zip: client?.zip || "",
  });
  const [secondaryContacts, setSecondaryContacts] = useState<SecondaryContact[]>(
    () => (client?.secondaryContacts || []).map((c) => ({ ...c }))
  );
  const [saving, setSaving] = useState(false);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const phoneRef = useRef<HTMLInputElement>(null);
  const notesRef = useRef<HTMLTextAreaElement>(null);
  const streetRef = useRef<HTMLInputElement>(null);
  const cityRef = useRef<HTMLInputElement>(null);
  const stateRef = useRef<HTMLInputElement>(null);
  const zipRef = useRef<HTMLInputElement>(null);
  const savingRef = useRef(false);

  const set = (key: keyof typeof form, value: string) => setForm((current) => ({ ...current, [key]: value }));

  const saveClient = async () => {
    if (savingRef.current) return;
    const payload = {
      name: (nameRef.current?.value || form.name).trim(),
      email: (emailRef.current?.value || form.email).trim(),
      phone: (phoneRef.current?.value || form.phone).trim(),
      notes: (notesRef.current?.value || form.notes).trim(),
      street: (streetRef.current?.value || form.street).trim(),
      city: (cityRef.current?.value || form.city).trim(),
      state: (stateRef.current?.value || form.state).trim(),
      zip: (zipRef.current?.value || form.zip).trim(),
    };
    if (!payload.name) {
      toast.error("Client name required");
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      if (editing) {
        const res = await withClientTimeout(apiClient.request<ClientRecord>({
          path: `/routes/clients/update/${client!.id}`,
          method: "PUT",
          body: {
            name: payload.name,
            email: payload.email || undefined,
            phone: payload.phone || undefined,
            notes: payload.notes || undefined,
            street: payload.street || undefined,
            city: payload.city || undefined,
            state: payload.state || undefined,
            zip: payload.zip || undefined,
            secondary_contacts: secondaryContacts.filter((c) => c.label.trim() || c.phone?.trim() || c.email?.trim()),
          },
          type: ContentType.Json,
        }), 4000);
        if (!res.ok) throw new Error("Could not save client");
        const updated = await res.json();
        onSaved(updated);
        toast.success("Client updated");
        onClose();
        return;
      }
      const res = await withClientTimeout(apiClient.request<ClientRecord>({
        path: "/routes/clients/create",
        method: "POST",
        body: {
          name: payload.name,
          email: payload.email || undefined,
          phone: payload.phone || undefined,
          notes: payload.notes || undefined,
          street: payload.street || undefined,
          city: payload.city || undefined,
          state: payload.state || undefined,
          zip: payload.zip || undefined,
          secondary_contacts: secondaryContacts.filter((c) => c.label.trim() || c.phone?.trim() || c.email?.trim()),
        },
        type: ContentType.Json,
      }), 4000);
      if (!res.ok) throw new Error("Could not create client");
      const createdClient = await res.json();
      onSaved(createdClient);
      window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
      toast.success("Client created");
      onClose();
    } catch {
      if (editing) {
        toast.error("Couldn't save that change -- try again in a moment.");
        return;
      }
      const localClient = makeLocalClient(payload);
      writeLocalClients(mergeClients([localClient], readLocalClients()));
      onSaved(localClient);
      window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
      toast.success("Client created locally");
      onClose();
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/40">
      <div className="mx-4 w-full max-w-md rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 px-6 py-4">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>{editing ? "Edit Client" : "New Client"}</h2>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600"><X size={18} /></button>
        </div>
        <form onSubmit={(event) => { event.preventDefault(); void saveClient(); }}>
          <div className="space-y-4 px-6 py-5">
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Client name *</span>
              <input ref={nameRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.name} onChange={(e) => set("name", e.target.value)} placeholder="e.g. Joe Smith" />
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-stone-600">Email</span>
                <input ref={emailRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.email} onChange={(e) => set("email", e.target.value)} placeholder="Optional" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-stone-600">Phone</span>
                <input ref={phoneRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.phone} onChange={(e) => set("phone", e.target.value)} placeholder="Optional" />
              </label>
            </div>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Street address</span>
              <input ref={streetRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.street} onChange={(e) => set("street", e.target.value)} placeholder="Optional" />
            </label>
            <div className="grid gap-3 grid-cols-[2fr_1fr_1fr]">
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-stone-600">City</span>
                <input ref={cityRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.city} onChange={(e) => set("city", e.target.value)} placeholder="Optional" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-stone-600">State</span>
                <input ref={stateRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.state} onChange={(e) => set("state", e.target.value)} placeholder="TX" />
              </label>
              <label className="block">
                <span className="mb-1 block text-xs font-medium text-stone-600">ZIP</span>
                <input ref={zipRef} className="w-full rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.zip} onChange={(e) => set("zip", e.target.value)} placeholder="Optional" />
              </label>
            </div>
            <div>
              <span className="mb-1 block text-xs font-medium text-stone-600">
                Additional contacts <span className="font-normal text-stone-400">— spouse, assistant, another number</span>
              </span>
              <div className="grid gap-2">
                {secondaryContacts.map((contact, i) => (
                  <div key={i} className="flex items-center gap-2">
                    <input
                      className="w-28 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
                      value={contact.label}
                      onChange={(e) => setSecondaryContacts((rows) => rows.map((r, j) => j === i ? { ...r, label: e.target.value } : r))}
                      placeholder="Label"
                    />
                    <input
                      className="min-w-0 flex-1 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
                      value={contact.phone || ""}
                      onChange={(e) => setSecondaryContacts((rows) => rows.map((r, j) => j === i ? { ...r, phone: e.target.value } : r))}
                      placeholder="Phone"
                    />
                    <input
                      className="min-w-0 flex-1 rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300"
                      value={contact.email || ""}
                      onChange={(e) => setSecondaryContacts((rows) => rows.map((r, j) => j === i ? { ...r, email: e.target.value } : r))}
                      placeholder="Email"
                    />
                    <button type="button" onClick={() => setSecondaryContacts((rows) => rows.filter((_, j) => j !== i))} className="shrink-0 text-stone-300 hover:text-red-500">
                      <X size={14} />
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => setSecondaryContacts((rows) => [...rows, { label: "", phone: "", email: "" }])}
                className="mt-2 text-xs font-medium text-emerald-700 hover:text-emerald-900"
              >
                + add another contact
              </button>
            </div>
            <label className="block">
              <span className="mb-1 block text-xs font-medium text-stone-600">Notes</span>
              <textarea ref={notesRef} rows={3} className="w-full resize-none rounded-lg border border-stone-200 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-emerald-300" value={form.notes} onChange={(e) => set("notes", e.target.value)} placeholder="Designer, house, preferences, install notes..." />
            </label>
          </div>
          <div className="flex items-center justify-end gap-3 border-t border-stone-100 px-6 py-4">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-stone-500 hover:text-stone-700">Cancel</button>
            <button
              type="button"
              onClick={() => void saveClient()}
              disabled={saving}
              className="rounded-lg px-5 py-2 text-sm font-semibold text-white disabled:opacity-60 hover:opacity-90"
              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
            >
              {saving ? "Saving..." : editing ? "Save changes" : "Create client"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

function DeleteClientDialog({
  client,
  onClose,
  onConfirm,
}: {
  client: ClientGroup;
  onClose: () => void;
  onConfirm: (deleteProjects: boolean) => void;
}) {
  const [deleteProjects, setDeleteProjects] = useState(false);
  const [confirming, setConfirming] = useState(false);

  return (
    <div className="fixed inset-0 z-[10000] flex items-center justify-center bg-black/35">
      <div className="mx-4 w-full max-w-sm rounded-2xl bg-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-stone-100 px-5 py-4">
          <h2 className="font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>Delete client</h2>
          <button type="button" onClick={onClose} className="text-stone-400 hover:text-stone-600"><X size={18} /></button>
        </div>
        <div className="space-y-4 px-5 py-4">
          <p className="text-sm text-stone-600">
            What should happen to <span className="font-semibold text-stone-800">{client.name}</span>?
          </p>
          <div className="space-y-2">
            <button
              type="button"
              onClick={() => setDeleteProjects(false)}
              className={`w-full rounded-xl border px-3 py-3 text-left text-sm ${!deleteProjects ? "border-emerald-300 bg-emerald-50 text-emerald-900" : "border-stone-200 text-stone-600 hover:bg-stone-50"}`}
            >
              Delete client only
              <span className="mt-0.5 block text-xs text-stone-500">Projects stay and become unassigned.</span>
            </button>
            {client.projectCount > 0 && (
              <button
                type="button"
                onClick={() => setDeleteProjects(true)}
                className={`w-full rounded-xl border px-3 py-3 text-left text-sm ${deleteProjects ? "border-amber-300 bg-amber-50 text-amber-900" : "border-stone-200 text-stone-600 hover:bg-stone-50"}`}
              >
                Delete client and projects
                <span className="mt-0.5 block text-xs text-stone-500">Also deletes {client.projectCount} project{client.projectCount === 1 ? "" : "s"}.</span>
              </button>
            )}
          </div>
          {confirming && (
            <div className="rounded-xl border border-stone-200 bg-stone-50 px-3 py-3 text-sm text-stone-700">
              Confirm delete: {deleteProjects ? "client and all projects" : "client only"}?
            </div>
          )}
        </div>
        <div className="flex items-center justify-end gap-3 border-t border-stone-100 px-5 py-4">
          <button type="button" onClick={onClose} className="px-3 py-2 text-sm text-stone-500 hover:text-stone-700">Cancel</button>
          {!confirming ? (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-lg border border-stone-200 px-4 py-2 text-sm font-semibold text-stone-700 hover:bg-stone-50"
            >
              Continue
            </button>
          ) : (
            <button
              type="button"
              onClick={() => onConfirm(deleteProjects)}
              className="rounded-lg bg-stone-800 px-4 py-2 text-sm font-semibold text-white hover:bg-stone-900"
            >
              Confirm delete
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// Filter chip: which line of work touched this client. Ported from
// Designs.tsx's FilterChip (same visual language across the app) --
// there's no shared component to import, it's page-local there too.
// "Christmas" and "Green Products" are what the client mentally means by
// them (2026-08-28): Christmas install history vs. a saved design/
// arrangement project. Product-CATEGORY based tagging was considered and
// rejected -- the catalog is almost entirely holiday decor even in
// "Florals"/"Greenery & Plants" (poinsettia, holly, pine everywhere), so
// category alone can't reliably separate the two the way workflow can.
type ClientTypeTag = "christmas" | "greenery";
type TypeFacet = { value: ClientTypeTag; label: string; count: number };

function clientHasTag(client: ClientGroup, tag: ClientTypeTag): boolean {
  // Comments now live in the same `activity` array (kind: "comment") --
  // a client with only a note on file, no real install history, must not
  // count as a "Christmas" client just because activity.length > 0.
  if (tag === "christmas") return client.activity.some((a) => a.kind !== "comment");
  return client.projectCount > 0;
}

function TypeFilterChip({ options, selected, onToggle, onClear }: {
  options: TypeFacet[];
  selected: ClientTypeTag[];
  onToggle: (value: ClientTypeTag) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const active = selected.length > 0;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-medium transition-colors ${
          active
            ? "border-emerald-600 bg-emerald-700 text-white"
            : "border-stone-300 bg-white text-stone-600 hover:border-stone-400 hover:text-stone-900"
        }`}
        title="Filter by type of work"
      >
        Type
        {active && (
          <span className="rounded-full bg-white/25 px-1.5 text-[10px] leading-4">{selected.length}</span>
        )}
        <ChevronDown size={12} className={open ? "rotate-180 transition-transform" : "transition-transform"} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-30 mt-1.5 w-64 rounded-xl border border-stone-200 bg-white p-1.5 shadow-lg">
          <div className="flex items-center justify-between px-2 py-1">
            <span className="text-[10px] font-semibold uppercase tracking-widest text-stone-400">Type</span>
            {selected.length > 0 && (
              <button onClick={onClear} className="text-[11px] font-medium text-emerald-700 hover:text-emerald-900">Clear</button>
            )}
          </div>
          {options.map((o) => {
            const on = selected.includes(o.value);
            return (
              <button
                key={o.value}
                onClick={() => onToggle(o.value)}
                className="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-sm hover:bg-stone-100"
              >
                <span className={`flex h-4 w-4 shrink-0 items-center justify-center rounded border ${
                  on ? "border-emerald-700 bg-emerald-700 text-white" : "border-stone-300"
                }`}>
                  {on && <Check size={11} strokeWidth={3} />}
                </span>
                <span className={`flex-1 truncate ${on ? "font-medium text-emerald-900" : "text-stone-600"}`}>{o.label}</span>
                <span className="shrink-0 text-xs text-stone-400">{o.count.toLocaleString()}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default function Clients() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const focusedClient = searchParams.get("client") || "";
  const localClientsOnLoad = useMemo(() => readLocalClients(), []);
  const cachedPage = useMemo(() => readClientsPageCache(), []);

  const [clientRows, setClientRows] = useState<ClientRecord[]>(() => cachedPage?.clientRows?.length ? cachedPage.clientRows : localClientsOnLoad);
  const [projects, setProjects] = useState<ProjectSummary[]>(() => cachedPage?.projects || []);
  const [projectDetails, setProjectDetails] = useState<Record<number, ProjectDetail>>({});
  const [expandedClient, setExpandedClient] = useState<string | null>(focusedClient || null);
  const [loading, setLoading] = useState(() => !cachedPage && localClientsOnLoad.length === 0);
  const [initialDataSettled, setInitialDataSettled] = useState(() => Boolean(cachedPage));
  const [refreshingSummary, setRefreshingSummary] = useState(() => Boolean(cachedPage || localClientsOnLoad.length));
  const [summaryCachedAt, setSummaryCachedAt] = useState<number | null>(() => cachedPage?.cachedAt || null);
  const [commentDrafts, setCommentDrafts] = useState<Record<string, string>>({});
  const [postingComment, setPostingComment] = useState<string | null>(null);
  const [detailsLoadingClient, setDetailsLoadingClient] = useState<string | null>(null);
  const [showNewClientModal, setShowNewClientModal] = useState(false);
  const [editingClient, setEditingClient] = useState<ClientGroup | null>(null);
  const [projectClientName, setProjectClientName] = useState<string | null>(null);
  const [deleteClientTarget, setDeleteClientTarget] = useState<ClientGroup | null>(null);

  // Shared by both create and edit: replace by id first (so a rename can
  // never leave a stale duplicate under the old name), THEN merge -- plain
  // name-keyed merging alone would add the renamed client as a second row
  // while the original name's now-stale row stayed put.
  const upsertClientRow = (saved: ClientRecord) => {
    setClientRows((current) => {
      const withoutOld = current.filter((row) => row.id == null || row.id !== saved.id);
      const next = mergeClients([saved], withoutOld);
      writeClientsPageCache(next, projects);
      return next;
    });
    setInitialDataSettled(true);
    setSummaryCachedAt(Date.now());
  };

  const clients = useMemo(() => buildClientGroups(clientRows, projects), [clientRows, projects]);
  const [typeFilter, setTypeFilter] = useState<ClientTypeTag[]>([]);
  const typeFacets = useMemo<TypeFacet[]>(() => [
    { value: "christmas", label: "Christmas", count: clients.filter((c) => clientHasTag(c, "christmas")).length },
    { value: "greenery", label: "Green Products", count: clients.filter((c) => clientHasTag(c, "greenery")).length },
  ], [clients]);
  const toggleTypeFilter = (tag: ClientTypeTag) =>
    setTypeFilter((current) => current.includes(tag) ? current.filter((t) => t !== tag) : [...current, tag]);
  const visibleClients = useMemo(() => {
    let list = focusedClient ? clients.filter((client) => client.name === focusedClient) : clients;
    if (typeFilter.length > 0) list = list.filter((c) => typeFilter.some((tag) => clientHasTag(c, tag)));
    return list;
  }, [clients, focusedClient, typeFilter]);

  useEffect(() => {
    let mounted = true;
    const localClients = readLocalClients();
    if (!cachedPage && localClients.length) {
      setClientRows(localClients);
      setLoading(false);
    }
    setRefreshingSummary(Boolean(cachedPage || localClients.length));

    const loadSummary = async () => {
      const [clientResult, projectResult] = await Promise.allSettled([
        apiClient.request<ClientRecord[]>({ path: "/routes/clients/list", method: "GET" }).then((r) => (r.ok ? r.json() : [])),
        apiClient.list_arrangements().then((r) => (r.ok ? r.json() : [])),
      ]);

      const nextClients = clientResult.status === "fulfilled" && Array.isArray(clientResult.value)
        ? mergeClients(clientResult.value, localClients)
        : (cachedPage?.clientRows?.length ? cachedPage.clientRows : localClients);
      const nextProjects = projectResult.status === "fulfilled" && Array.isArray(projectResult.value)
        ? projectResult.value
        : (cachedPage?.projects || []);

      if (!mounted) return;
      if (projectResult.status === "rejected" && nextProjects.length === 0) {
        toast.error("Projects are still loading. Try again if they do not appear.");
      }
      setClientRows(nextClients);
      setProjects(nextProjects);
      writeClientsPageCache(nextClients, nextProjects);
      setSummaryCachedAt(Date.now());
      setInitialDataSettled(true);
      setLoading(false);
      setRefreshingSummary(false);
    };

    void loadSummary();

    return () => { mounted = false; };
  }, [cachedPage]);

  useEffect(() => {
    if (focusedClient) setExpandedClient(focusedClient);
  }, [focusedClient]);

  const loadDetailsForClient = async (client: ClientGroup) => {
    const missing = client.projects.filter((project) => !projectDetails[project.id]);
    if (missing.length === 0) return;

    setDetailsLoadingClient(client.name);
    try {
      const details = await Promise.all(
        missing.map(async (project) => {
          const detail = await withClientTimeout(apiClient.get_arrangement({ arrangementId: project.id }).then((r) => r.json()));
          return detail as unknown as ProjectDetail;
        })
      );

      setProjectDetails((prev) => {
        const next = { ...prev };
        details.forEach((detail) => {
          next[detail.id] = detail;
        });
        return next;
      });
    } catch {
      toast.error("Failed to load project scopes");
    } finally {
      setDetailsLoadingClient(null);
    }
  };

  const toggleClient = (client: ClientGroup) => {
    const next = expandedClient === client.name ? null : client.name;
    setExpandedClient(next);
    if (next) void loadDetailsForClient(client);
  };

  const showAllClients = () => {
    setSearchParams({});
    setExpandedClient(null);
  };

  const addProjectToClient = (clientName: string) => {
    setProjectClientName(clientName);
    setExpandedClient(clientName);
  };

  const deleteProject = async (project: ProjectSummary) => {
    if (!confirm(`Delete project "${project.name}"? This removes its scopes and saved products.`)) return;
    try {
      await apiClient.delete_arrangement({ arrangementId: project.id });
      setProjects((current) => {
        const next = current.filter((row) => row.id !== project.id);
        writeClientsPageCache(clientRows, next);
        return next;
      });
      setProjectDetails((current) => {
        const next = { ...current };
        delete next[project.id];
        return next;
      });
      window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
      toast.success("Project deleted");
    } catch {
      toast.error("Failed to delete project");
    }
  };

  const deleteClient = async (client: ClientGroup, deleteProjects: boolean) => {
    try {
      await apiClient.request({
        path: `/routes/clients/delete/${encodeURIComponent(client.name)}?delete_projects=${deleteProjects ? "true" : "false"}`,
        method: "DELETE",
      });
      const nextClientRows = clientRows.filter((row) => normalizedClientName(row.name) !== client.name);
      const nextProjects = deleteProjects
        ? projects.filter((project) => normalizedClientName(project.client_name) !== client.name)
        : projects.map((project) => normalizedClientName(project.client_name) === client.name ? { ...project, client_name: null } : project);
      setClientRows(nextClientRows);
      setProjects(nextProjects);
      writeClientsPageCache(nextClientRows, nextProjects);
      if (focusedClient === client.name) showAllClients();
      setDeleteClientTarget(null);
      window.dispatchEvent(new Event("leaf-ledger-projects-changed"));
      toast.success(deleteProjects ? "Client and projects deleted" : "Client deleted; projects kept");
    } catch {
      toast.error("Failed to delete client");
    }
  };

  // Comments share client_activity with the Christmas-install history
  // (kind distinguishes them) -- the same feed the install-schedule tool's
  // client popup reads and writes, so a note added on either side shows up
  // on both without a second store to keep in sync.
  const patchClientActivity = (clientId: number | null | undefined, updater: (activity: ActivityEntry[]) => ActivityEntry[]) => {
    if (clientId == null) return;
    setClientRows((rows) => rows.map((row) =>
      row.id === clientId ? { ...row, activity: updater(row.activity || []) } : row));
  };

  const addComment = async (client: ClientGroup) => {
    if (client.id == null) { toast.error("Save this client before adding comments"); return; }
    const text = (commentDrafts[client.name] || "").trim();
    if (!text) return;
    setPostingComment(client.name);
    try {
      const res = await apiClient.request<ActivityEntry>({
        path: `/routes/clients/${client.id}/comments`,
        method: "POST",
        body: { text },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error("Failed to add comment");
      const entry = await res.json();
      patchClientActivity(client.id, (activity) => [entry, ...activity]);
      setCommentDrafts((d) => ({ ...d, [client.name]: "" }));
    } catch {
      toast.error("Couldn't save that comment — try again.");
    } finally {
      setPostingComment(null);
    }
  };

  const removeComment = async (client: ClientGroup, entry: ActivityEntry) => {
    if (client.id == null) return;
    const prev = client.activity;
    patchClientActivity(client.id, (activity) => activity.filter((a) => a.id !== entry.id));
    try {
      const res = await apiClient.request({
        path: `/routes/clients/${client.id}/comments/${entry.id}`,
        method: "DELETE",
      });
      if (!res.ok) throw new Error("Failed to delete comment");
    } catch {
      patchClientActivity(client.id, () => prev);
      toast.error("Couldn't delete that comment — try again.");
    }
  };

  return (
    <Layout>
      <header className="sticky top-0 z-10 flex items-center justify-between border-b border-stone-200 px-10 py-4" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
        <div>
          <div className="mb-1 flex items-center gap-1 text-xs font-semibold text-emerald-700">
            <button onClick={showAllClients} className="hover:underline">Clients</button>
            {focusedClient && (
              <>
                <span className="text-stone-300">/</span>
                <span className="text-stone-500">{focusedClient}</span>
              </>
            )}
          </div>
          <h1 className="text-xl font-semibold text-stone-800" style={{ fontFamily: "Georgia, serif" }}>
            {focusedClient ? focusedClient : "Clients"}
          </h1>
          <p className="mt-0.5 text-xs text-stone-500">
            {focusedClient
              ? "Projects and scope buckets for this client"
              : initialDataSettled || clients.length > 0
                ? `${clients.length} client${clients.length === 1 ? "" : "s"} with saved projects${refreshingSummary ? " · Refreshing..." : summaryCachedAt ? ` · Updated ${formatCacheStamp(summaryCachedAt)}` : ""}`
                : "Checking clients..."}
          </p>
        </div>
        <button
          onClick={() => setShowNewClientModal(true)}
          className="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90"
          style={{ backgroundColor: "rgb(var(--ll-brand))" }}
        >
          <Plus size={15} strokeWidth={2.2} />
          New Client
        </button>
      </header>

      {!focusedClient && (
        <div className="flex items-center gap-2 border-b border-stone-100 px-10 py-3" style={{ backgroundColor: "rgb(var(--ll-page))" }}>
          <TypeFilterChip
            options={typeFacets}
            selected={typeFilter}
            onToggle={toggleTypeFilter}
            onClear={() => setTypeFilter([])}
          />
          {typeFilter.length > 0 && (
            <button onClick={() => setTypeFilter([])} className="text-xs font-medium text-stone-400 hover:text-stone-600">
              Reset
            </button>
          )}
        </div>
      )}

      <main className="px-10 py-6">
        {loading || (!initialDataSettled && visibleClients.length === 0) ? (
          <div className="flex items-center justify-center py-24">
            <div className="text-center">
              <div className="mx-auto h-6 w-6 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent" />
              <p className="mt-3 text-sm text-stone-400">Checking clients...</p>
            </div>
          </div>
        ) : visibleClients.length === 0 && typeFilter.length > 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
              <Users size={28} className="text-emerald-600" strokeWidth={1.5} />
            </div>
            <p className="mb-1 text-base font-medium text-stone-600">No clients match that filter</p>
            <button onClick={() => setTypeFilter([])} className="rounded-lg border border-stone-200 px-4 py-2 text-sm font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700">
              Clear filter
            </button>
          </div>
        ) : visibleClients.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <div className="mb-4 flex h-16 w-16 items-center justify-center rounded-full" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
              <Users size={28} className="text-emerald-600" strokeWidth={1.5} />
            </div>
            <p className="mb-1 text-base font-medium text-stone-600">No clients yet</p>
            <p className="mb-4 max-w-xs text-sm leading-relaxed text-stone-400">Create a client first, then attach projects and scope buckets to that client.</p>
            <button onClick={() => setShowNewClientModal(true)} className="rounded-lg px-4 py-2 text-sm font-semibold text-white hover:opacity-90" style={{ backgroundColor: "rgb(var(--ll-brand))" }}>
              Create First Client
            </button>
          </div>
        ) : (
          <div className="grid gap-4">
            {visibleClients.map((client) => {
              const expanded = expandedClient === client.name;
              const loadingBuckets = detailsLoadingClient === client.name;

              return (
                <section key={client.name} className="overflow-hidden rounded-xl border border-stone-200 bg-white">
                  <button onClick={() => toggleClient(client)} className="flex w-full items-center gap-4 px-6 py-5 text-left transition-colors hover:bg-stone-50">
                    <div className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-lg" style={{ backgroundColor: "rgb(var(--ll-brand-soft))" }}>
                      <Users size={19} className="text-emerald-700" strokeWidth={1.6} />
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-base font-semibold text-stone-800">{client.name}</p>
                      <p className="mt-0.5 text-xs text-stone-400">
                        {client.projectCount} project{client.projectCount === 1 ? "" : "s"} · {client.bucketCount} scope{client.bucketCount === 1 ? "" : "s"}
                      </p>
                    </div>
                    <div className="hidden text-right sm:block">
                      <p className="text-sm font-semibold text-stone-800">{formatCurrency(client.selectedCost)}</p>
                      <p className="text-xs text-stone-400">selected product cost</p>
                    </div>
                    <div className="hidden text-right md:block">
                      <p className="text-xs text-stone-400">Last updated</p>
                      <p className="text-xs font-medium text-stone-600">{client.updatedAt ? new Date(client.updatedAt).toLocaleDateString() : "No projects yet"}</p>
                    </div>
                    <ChevronDown size={17} className={`text-stone-400 transition-transform ${expanded ? "rotate-180" : ""}`} />
                  </button>

                  {expanded && (
                    <div className="border-t border-stone-100 bg-stone-50/60 px-6 py-5">
                      <div className="mb-4 flex flex-wrap items-center gap-2">
                        <button
                          onClick={() => navigate(`/clients?client=${encodeURIComponent(client.name)}`)}
                          className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700"
                        >
                          <FolderOpen size={14} />
                          View client projects
                        </button>
                        <button
                          onClick={() => addProjectToClient(client.name)}
                          className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700"
                        >
                          <Plus size={14} />
                          Add project for this client
                        </button>
                        <button
                          onClick={() => setEditingClient(client)}
                          className="flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-700 hover:border-emerald-300 hover:text-emerald-700"
                        >
                          <Pencil size={14} />
                          Edit client
                        </button>
                        <button
                          onClick={() => setDeleteClientTarget(client)}
                          className="ml-auto flex items-center gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs font-semibold text-stone-400 hover:border-stone-300 hover:text-stone-600"
                        >
                          <Trash2 size={14} />
                          Delete client
                        </button>
                      </div>

                      {(client.phone || client.email || client.street || client.city || client.secondaryContacts.length > 0) && (
                        <div className="mb-4 flex flex-wrap gap-x-5 gap-y-1.5 rounded-xl border border-stone-200 bg-white px-4 py-3 text-xs text-stone-600">
                          {client.phone && (
                            <span className="flex items-center gap-1.5"><Phone size={12} className="text-stone-400" />{client.phone}</span>
                          )}
                          {client.email && (
                            <span className="flex items-center gap-1.5"><Mail size={12} className="text-stone-400" />{client.email}</span>
                          )}
                          {(client.street || client.city) && (
                            <span className="flex items-center gap-1.5">
                              <MapPin size={12} className="text-stone-400" />
                              {[client.street, [client.city, client.state].filter(Boolean).join(", "), client.zip].filter(Boolean).join(" · ")}
                            </span>
                          )}
                          {client.secondaryContacts.map((contact, i) => (
                            <span key={i} className="flex items-center gap-1.5">
                              <Users size={12} className="text-stone-400" />
                              <span className="font-medium text-stone-500">{contact.label || "Contact"}</span>
                              {[contact.phone, contact.email].filter(Boolean).join(" · ")}
                            </span>
                          ))}
                        </div>
                      )}

                      {client.activity.some((a) => a.kind !== "comment") && (
                        <div className="mb-5">
                          <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-stone-400">
                            <TreePine size={12} />
                            Christmas install history
                          </p>
                          <div className="grid gap-1.5">
                            {client.activity.filter((a) => a.kind !== "comment").map((entry) => (
                              <div key={entry.id} className="flex items-center gap-3 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs">
                                <span className="rounded-full px-2 py-0.5 font-semibold" style={{ backgroundColor: "rgb(var(--ll-brand-soft))", color: "rgb(var(--ll-brand))" }}>
                                  {entry.season}
                                </span>
                                <span className="min-w-0 flex-1 truncate text-stone-700">{entry.summary}</span>
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      <div className="mb-5">
                        <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-stone-400">
                          <MessageSquare size={12} />
                          Comments
                        </p>
                        {/* Same feed the install-schedule tool's client popup reads and
                            writes -- a note added on either side shows up on both. */}
                        <div className="grid gap-1.5">
                          {client.activity.filter((a) => a.kind === "comment").length === 0 && (
                            <p className="text-xs italic text-stone-400">No comments yet.</p>
                          )}
                          {client.activity.filter((a) => a.kind === "comment").map((entry) => (
                            <div key={entry.id} className="flex items-start gap-2 rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs">
                              <span className="min-w-0 flex-1 text-stone-700">{entry.summary}</span>
                              <span className="shrink-0 text-[10px] text-stone-400">
                                {entry.created_at ? new Date(entry.created_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }) : ""}
                              </span>
                              <button
                                onClick={() => removeComment(client, entry)}
                                className="shrink-0 text-stone-300 hover:text-red-500"
                                title="Delete comment"
                              >
                                <X size={12} />
                              </button>
                            </div>
                          ))}
                        </div>
                        <div className="mt-2 flex gap-2">
                          <input
                            type="text"
                            value={commentDrafts[client.name] || ""}
                            onChange={(e) => setCommentDrafts((d) => ({ ...d, [client.name]: e.target.value }))}
                            onKeyDown={(e) => { if (e.key === "Enter") addComment(client); }}
                            placeholder="Add a note…"
                            maxLength={2000}
                            className="min-w-0 flex-1 rounded-lg border border-stone-200 px-3 py-1.5 text-xs outline-none focus:border-emerald-500"
                          />
                          <button
                            onClick={() => addComment(client)}
                            disabled={postingComment === client.name || !(commentDrafts[client.name] || "").trim()}
                            className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
                            style={{ backgroundColor: "rgb(var(--ll-brand))" }}
                          >
                            Add
                          </button>
                        </div>
                      </div>

                      <div className="grid gap-3">
                        {client.projects.map((project) => {
                          const detail = projectDetails[project.id];

                          return (
                            <div key={project.id} className="rounded-xl border border-stone-200 bg-white p-4">
                              <div className="flex items-start gap-3">
                                <div className="mt-0.5 flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-lg bg-stone-100 text-stone-500">
                                  <Briefcase size={16} />
                                </div>
                                <div className="min-w-0 flex-1">
                                  <div className="flex flex-wrap items-center gap-2">
                                    <p className="font-semibold text-stone-800">{project.name}</p>
                                    <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700">
                                      {project.container_count} scope{project.container_count === 1 ? "" : "s"}
                                    </span>
                                  </div>
                                  <p className="mt-0.5 text-xs text-stone-400">Selected cost {formatCurrency(project.total_cost)} · updated {new Date(project.updated_at).toLocaleDateString()}</p>

                                  <div className="mt-3 flex flex-wrap gap-1.5">
                                    {detail?.containers?.length ? detail.containers.map((bucket) => (
                                      <span key={bucket.id} className="rounded-full border border-stone-200 bg-stone-50 px-2 py-1 text-[11px] font-medium text-stone-600">
                                        {bucketQuantity(bucket)}x {bucketTitle(bucket)}
                                      </span>
                                    )) : loadingBuckets ? (
                                      <span className="text-xs text-stone-400">Loading scopes...</span>
                                    ) : (
                                      <span className="text-xs text-stone-400">Open project to view scopes</span>
                                    )}
                                  </div>
                                </div>
                                <button
                                  onClick={() => navigate(`/clients/project?client=${encodeURIComponent(client.name)}&id=${project.id}`)}
                                  className="flex items-center gap-1 rounded-lg px-3 py-2 text-xs font-semibold text-emerald-700 hover:bg-emerald-50"
                                >
                                  Open project
                                  <ArrowRight size={13} />
                                </button>
                                <button
                                  onClick={() => deleteProject(project)}
                                  className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-300 transition-colors hover:bg-red-50 hover:text-red-500"
                                  title="Delete project"
                                  aria-label={`Delete ${project.name}`}
                                >
                                  <Trash2 size={14} />
                                </button>
                              </div>
                            </div>
                          );
                        })}
                        {client.projects.length === 0 && (
                          <div className="rounded-xl border border-dashed border-stone-200 bg-white p-5 text-center">
                            <p className="text-sm font-medium text-stone-600">No projects for this client yet</p>
                            <button
                              onClick={() => addProjectToClient(client.name)}
                              className="mt-3 rounded-lg px-4 py-2 text-xs font-semibold text-white hover:opacity-90"
                              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
                            >
                              Add first project
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </section>
              );
            })}
          </div>
        )}
      </main>
      {showNewClientModal && (
        <NewClientModal
          onClose={() => setShowNewClientModal(false)}
          onSaved={(client) => {
            upsertClientRow(client);
            setSearchParams({ client: client.name });
            setExpandedClient(client.name);
          }}
        />
      )}
      {editingClient && (
        <NewClientModal
          client={editingClient}
          onClose={() => setEditingClient(null)}
          onSaved={(client) => {
            upsertClientRow(client);
            if (focusedClient === editingClient.name || expandedClient === editingClient.name) {
              setSearchParams(focusedClient ? { client: client.name } : {});
              setExpandedClient(client.name);
            }
          }}
        />
      )}
      {projectClientName && (
        <NewProjectModal
          initialClientName={projectClientName}
          onClose={() => setProjectClientName(null)}
          onCreated={(project) => {
            const summary = { ...project, container_count: project.containers?.length || 0 };
            setProjects((current) => {
              const next = [summary, ...current.filter((row) => row.id !== project.id)];
              writeClientsPageCache(clientRows, next);
              return next;
            });
            setInitialDataSettled(true);
            setSummaryCachedAt(Date.now());
            setExpandedClient(projectClientName);
          }}
        />
      )}
      {deleteClientTarget && (
        <DeleteClientDialog
          client={deleteClientTarget}
          onClose={() => setDeleteClientTarget(null)}
          onConfirm={(deleteProjects) => void deleteClient(deleteClientTarget, deleteProjects)}
        />
      )}
    </Layout>
  );
}
