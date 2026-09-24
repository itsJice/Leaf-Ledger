import React, { useEffect, useState } from "react";
import { Loader2, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { apiFetch } from "utils/apiFetch";

// Settings > Users (super admins only -- backend app/apis/users). Shows
// everyone who has signed in, has a role set, or is on the install roster,
// and what each can do. "Automatic" clears a set role so it falls back to the
// roster (Lead -> lead, anyone else on it -> crew) or to office staff.

interface UserRow {
  email: string;
  role: string;
  explicit: string | null;
  locked: boolean;
  rosterName: string | null;
  rosterTitle: string | null;
  lastSignIn: string | null;
}

const ROLE_LABEL: Record<string, string> = {
  crew: "Crew: no pages",
  lead: "Lead: their own shifts only",
  staff: "Office staff: everything except admin",
  admin: "Admin: everything except roles",
  super_admin: "Super admin: everything",
};

export default function UserRolesEditor() {
  const [rows, setRows] = useState<UserRow[] | null>(null);
  const [roles, setRoles] = useState<string[]>([]);
  const [saving, setSaving] = useState<string | null>(null);
  const [newEmail, setNewEmail] = useState("");

  const load = async () => {
    const r = await apiFetch("/api/users");
    if (!r.ok) {
      toast.error("Couldn't load users");
      return;
    }
    const d = await r.json();
    setRows(d.users);
    setRoles(d.roles);
  };

  useEffect(() => {
    void load();
  }, []);

  const setRole = async (email: string, role: string | null) => {
    setSaving(email);
    try {
      const r = await apiFetch("/api/users", {
        method: "PUT",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ email, role }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail || "Couldn't save");
      await load();
      toast.success(`Updated ${email}`);
    } catch (e) {
      toast.error((e as Error).message);
    } finally {
      setSaving(null);
    }
  };

  return (
    <div className="rounded-xl border border-stone-200 bg-white p-5">
      <div className="mb-2 flex items-center gap-2">
        <ShieldCheck size={16} className="text-emerald-700" />
        <h2 className="text-sm font-semibold text-stone-800">Users &amp; Roles</h2>
      </div>
      <p className="mb-4 text-xs text-stone-500">
        Leads on the install schedule roster get their own shifts automatically when their roster email matches the email
        they sign in with. Anyone else who signs in is office staff unless you set a role here.
      </p>

      {!rows ? (
        <Loader2 className="animate-spin text-stone-400" />
      ) : (
        <div className="divide-y divide-stone-100">
          {rows.map((u) => (
            <div key={u.email} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-stone-800">{u.email}</p>
                <p className="text-[11px] text-stone-500">
                  {u.rosterName ? `${u.rosterName} · ${u.rosterTitle} on roster` : "Not on roster"}
                  {" · "}
                  {u.lastSignIn ? `last signed in ${new Date(u.lastSignIn).toLocaleDateString()}` : "never signed in"}
                </p>
              </div>
              {u.locked ? (
                <span className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-semibold text-emerald-800">Owner · super admin</span>
              ) : (
                <select
                  value={u.explicit ?? ""}
                  disabled={saving === u.email}
                  onChange={(e) => void setRole(u.email, e.target.value || null)}
                  className="max-w-full rounded-lg border border-stone-300 bg-white px-2 py-1.5 text-xs"
                  aria-label={`Role for ${u.email}`}
                >
                  <option value="">Automatic ({ROLE_LABEL[u.role]?.split(":")[0] ?? u.role})</option>
                  {roles.map((r) => (
                    <option key={r} value={r}>
                      {ROLE_LABEL[r] ?? r}
                    </option>
                  ))}
                </select>
              )}
            </div>
          ))}
        </div>
      )}

      <form
        className="mt-4 flex flex-wrap gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          if (newEmail.trim()) void setRole(newEmail.trim(), "staff").then(() => setNewEmail(""));
        }}
      >
        <input
          type="email"
          value={newEmail}
          onChange={(e) => setNewEmail(e.target.value)}
          placeholder="Add someone by email"
          className="min-w-0 flex-1 rounded-lg border border-stone-300 px-3 py-1.5 text-sm"
        />
        <button type="submit" className="rounded-lg bg-stone-900 px-3 py-1.5 text-sm font-semibold text-white">
          Add as staff
        </button>
      </form>
      <p className="mt-2 text-[11px] text-stone-500">
        Adding someone here sets their role. They still need a login. Create it in Supabase (Authentication → Users) as you do today.
      </p>
    </div>
  );
}
