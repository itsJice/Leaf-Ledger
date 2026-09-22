import { useRef, useState } from "react";
import { X } from "lucide-react";
import { apiClient } from "app";
import { toast } from "sonner";
import { notifyProjectsChanged } from "utils/projectsChanged";
import type { Arrangement } from "./types";

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
      onCreated(arr as unknown as Arrangement);
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
              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
            >
              {saving ? "Creating..." : "Create project"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
