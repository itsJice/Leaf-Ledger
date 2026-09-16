import React, { useMemo, useState } from "react";
import { Check, Pencil, Plus, TreePine, X } from "lucide-react";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../../apiclient/http-client";
import { formatCurrency } from "utils/format";
import { currentSeasonLabel, seasonSpanLabel } from "utils/season";

/**
 * One client's Christmas history, season by season, with an inline editor.
 *
 * Every value here lives in that season's client_activity.detail. The keys
 * are the ones backend/app/libs/client_season.py names, whether they came
 * from the spreadsheet sync or from a person: a value saved here is stamped
 * in detail.app_edits and the next sync leaves it alone, so the app is the
 * record. Older seasons show whatever the sheets tracked; from 2026 on the
 * sync captures the whole row.
 */

export type ActivityEntry = {
  id: number;
  kind: string;
  season: string;
  summary: string;
  detail?: Record<string, unknown> | null;
  occurred_at?: string | null;
  created_at?: string | null;
};

type Status = "installing" | "hold" | "not_installing";

/** The editable subset -- mirrors client_season.SEASON_FIELDS. */
const EDITABLE = {
  install_date: "date",
  takedown_date: "date",
  storing: "bool",
  boxes: "int",
  crew: "text",
  crew_size: "int",
  est_hours: "number",
  real_hours: "number",
  install_fee: "money",
  takedown_fee: "money",
  storage_fee: "money",
  total: "money",
  ideal_total: "money",
  invoice_total: "money",
  notes: "text",
  production_notes: "text",
  confirmation_notes: "text",
} as const;
type EditableKey = keyof typeof EDITABLE;

const MONEY_KEYS: EditableKey[] = ["install_fee", "takedown_fee", "storage_fee", "total", "ideal_total", "invoice_total"];

function str(v: unknown): string {
  if (v === null || v === undefined) return "";
  return String(v);
}

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === "") return null;
  const n = typeof v === "number" ? v : Number(String(v).replace(/[$,]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function statusOf(d: Record<string, unknown>): Status {
  if (d.not_installing) return "not_installing";
  if (d.hold) return "hold";
  return "installing";
}

function seasonTotal(d: Record<string, unknown>): number | null {
  const t = num(d.total);
  if (t !== null) return t;
  const fees = [num(d.install_fee), num(d.takedown_fee), num(d.storage_fee)];
  if (fees.every((f) => f === null)) return null;
  return fees.reduce<number>((a, f) => a + (f || 0), 0);
}

function mdy(iso: unknown): string {
  const s = str(iso);
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s);
  return m ? `${m[2]}/${m[3]}/${m[1]}` : s;
}

function editedOn(d: Record<string, unknown>, key: string): string | null {
  const edits = d.app_edits;
  if (!edits || typeof edits !== "object") return null;
  const when = (edits as Record<string, unknown>)[key];
  return when ? String(when) : null;
}

function EditedDot({ d, k }: { d: Record<string, unknown>; k: string }) {
  const when = editedOn(d, k);
  if (!when) return null;
  const date = new Date(when);
  const label = Number.isNaN(date.getTime()) ? when : date.toLocaleDateString();
  return (
    <span
      className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-emerald-500 align-middle"
      title={`Set in Leaf & Ledger ${label} — the spreadsheet sync won't overwrite it`}
    />
  );
}

const STATUS_LABEL: Record<Status, string> = {
  installing: "Installing",
  hold: "On hold",
  not_installing: "Not installing",
};

const STATUS_CLASS: Record<Status, string> = {
  installing: "bg-emerald-50 text-emerald-800 border-emerald-200",
  hold: "bg-amber-50 text-amber-800 border-amber-200",
  not_installing: "bg-stone-100 text-stone-600 border-stone-200",
};

function Seg<T extends string>({ value, options, onChange }: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="inline-flex overflow-hidden rounded-lg border border-stone-200 bg-white text-xs">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => onChange(o.value)}
          className={`px-2.5 py-1.5 font-medium ${value === o.value ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-50"}`}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

type Draft = Record<EditableKey, string> & { status: Status; storing: "yes" | "no" | "unknown" };

function draftFrom(d: Record<string, unknown>): Draft {
  const out = {} as Draft;
  (Object.keys(EDITABLE) as EditableKey[]).forEach((k) => {
    if (k === "storing") return; // three-way below, not free text
    out[k] = str(d[k]);
  });
  out.status = statusOf(d);
  out.storing = d.storing === true ? "yes" : d.storing === false ? "no" : "unknown";
  return out;
}

/** Only what changed, in the shape PUT /clients/{id}/seasons/{season} takes. */
function diffDraft(original: Record<string, unknown>, draft: Draft): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  (Object.keys(EDITABLE) as EditableKey[]).forEach((k) => {
    if (k === "storing") return;
    const before = str(original[k]);
    const after = draft[k].trim();
    if (before === after) return;
    fields[k] = after === "" ? null : after;
  });
  const storingBefore = original.storing === true ? "yes" : original.storing === false ? "no" : "unknown";
  if (draft.storing !== storingBefore) fields.storing = draft.storing === "unknown" ? null : draft.storing === "yes";
  const statusBefore = statusOf(original);
  if (draft.status !== statusBefore) {
    if (draft.status === "installing") {
      fields.hold = false;
      fields.not_installing = false;
    } else if (draft.status === "hold") fields.hold = true;
    else fields.not_installing = true;
  }
  return fields;
}

function Field({ label, children, wide }: { label: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <label className={`block ${wide ? "sm:col-span-2" : ""}`}>
      <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-stone-400">{label}</span>
      {children}
    </label>
  );
}

const inputClass = "w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300";

function SeasonEditor({ clientId, season, detail, onSaved, onClose }: {
  clientId: number;
  season: string;
  detail: Record<string, unknown>;
  onSaved: (entry: ActivityEntry) => void;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<Draft>(() => draftFrom(detail));
  const [saving, setSaving] = useState(false);
  const set = (k: keyof Draft, v: string) => setDraft((d) => ({ ...d, [k]: v }));

  const save = async () => {
    const fields = diffDraft(detail, draft);
    if (Object.keys(fields).length === 0) {
      onClose();
      return;
    }
    setSaving(true);
    try {
      const res = await apiClient.request<ActivityEntry>({
        path: `/routes/clients/${clientId}/seasons/${season}`,
        method: "PUT",
        body: { fields },
        type: ContentType.Json,
      });
      if (!res.ok) {
        let why = "Couldn't save that season";
        try {
          const j = await res.json();
          if (j?.detail) why = String(j.detail);
        } catch { /* no body */ }
        throw new Error(why);
      }
      onSaved(await res.json());
      toast.success(`${season} season saved`);
      onClose();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save that season");
    } finally {
      setSaving(false);
    }
  };

  const extras: [string, unknown][] = [
    ["Specialty", detail.specialty],
    ["People needed", detail.people_needed],
    ["Crew roles", detail.role_need && typeof detail.role_need === "object"
      ? Object.entries(detail.role_need as Record<string, unknown>).filter(([, v]) => v).map(([k, v]) => `${v} ${k}`).join(", ")
      : null],
    ["Install start / end", [detail.real_start, detail.real_end].filter(Boolean).join(" – ")],
    ["Takedown order", detail.takedown_order],
    ["Takedown start / end", [detail.takedown_real_start, detail.takedown_real_end].filter(Boolean).join(" – ")],
    ["Takedown hours", detail.takedown_real_hours ?? detail.takedown_real_note ?? detail.takedown_est_hours ?? detail.takedown_est_note],
    ["Storage note", detail.storage_note],
    ["Was scheduled", detail.was_scheduled ? mdy(detail.was_scheduled) : null],
  ].filter(([, v]) => v !== null && v !== undefined && v !== "") as [string, unknown][];

  return (
    <div className="rounded-xl border border-emerald-200 bg-white p-4">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="text-xs font-semibold text-stone-700">{season} season · {seasonSpanLabel(season)}</span>
        <Seg<Status>
          value={draft.status}
          options={[{ value: "installing", label: "Installing" }, { value: "hold", label: "Hold" }, { value: "not_installing", label: "Not installing" }]}
          onChange={(v) => set("status", v)}
        />
        <span className="flex items-center gap-2 text-xs text-stone-500">
          Storing with us
          <Seg<"yes" | "no" | "unknown">
            value={draft.storing}
            options={[{ value: "yes", label: "Yes" }, { value: "no", label: "No" }, { value: "unknown", label: "?" }]}
            onChange={(v) => set("storing", v)}
          />
        </span>
      </div>
      <div className="grid gap-2.5 sm:grid-cols-4">
        <Field label="Install date"><input type="date" className={inputClass} value={draft.install_date.slice(0, 10)} onChange={(e) => set("install_date", e.target.value)} /></Field>
        <Field label="Takedown date"><input type="date" className={inputClass} value={draft.takedown_date.slice(0, 10)} onChange={(e) => set("takedown_date", e.target.value)} /></Field>
        <Field label="Boxes"><input inputMode="numeric" className={inputClass} value={draft.boxes} onChange={(e) => set("boxes", e.target.value)} /></Field>
        <Field label="Crew size"><input inputMode="numeric" className={inputClass} value={draft.crew_size} onChange={(e) => set("crew_size", e.target.value)} /></Field>
        <Field label="Crew" wide><input className={inputClass} value={draft.crew} onChange={(e) => set("crew", e.target.value)} placeholder="Crew B (6)" /></Field>
        <Field label="Est. hours"><input inputMode="decimal" className={inputClass} value={draft.est_hours} onChange={(e) => set("est_hours", e.target.value)} /></Field>
        <Field label="Real hours"><input inputMode="decimal" className={inputClass} value={draft.real_hours} onChange={(e) => set("real_hours", e.target.value)} /></Field>
        {MONEY_KEYS.map((k) => (
          <Field key={k} label={k.replace(/_/g, " ")}>
            <input inputMode="decimal" className={inputClass} value={draft[k]} onChange={(e) => set(k, e.target.value)} placeholder="$" />
          </Field>
        ))}
        <Field label="Confirmation notes" wide><input className={inputClass} value={draft.confirmation_notes} onChange={(e) => set("confirmation_notes", e.target.value)} /></Field>
        <Field label="Production notes" wide><input className={inputClass} value={draft.production_notes} onChange={(e) => set("production_notes", e.target.value)} placeholder="relight, replace, repair…" /></Field>
        <Field label="Notes" wide><input className={inputClass} value={draft.notes} onChange={(e) => set("notes", e.target.value)} /></Field>
      </div>
      {extras.length > 0 && (
        <p className="mt-3 text-[11px] text-stone-500">
          <span className="font-semibold text-stone-400">Also on file: </span>
          {extras.map(([k, v]) => `${k} ${String(v)}`).join(" · ")}
        </p>
      )}
      <div className="mt-3 flex items-center justify-end gap-2">
        <button type="button" onClick={onClose} className="px-3 py-1.5 text-xs text-stone-500 hover:text-stone-700">Cancel</button>
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
          style={{ backgroundColor: "rgb(var(--ll-brand))" }}
        >
          <Check size={12} strokeWidth={3} />
          {saving ? "Saving…" : "Save season"}
        </button>
      </div>
    </div>
  );
}

const COLS = ["Season", "Status", "Install", "Takedown", "Storing", "Boxes", "Crew", "Hours", "Fees I / T / S", "Total", "Invoiced", ""];

export function SeasonHistory({ clientId, activity, onSaved }: {
  clientId: number | null | undefined;
  activity: ActivityEntry[];
  onSaved: (entry: ActivityEntry) => void;
}) {
  const [editing, setEditing] = useState<string | null>(null);
  const current = currentSeasonLabel();

  const rows = useMemo(() => {
    const seasons = activity
      .filter((a) => a.kind === "christmas_install")
      .map((a) => ({ season: a.season, entry: a, detail: (a.detail && typeof a.detail === "object" ? a.detail : {}) as Record<string, unknown> }));
    if (!seasons.some((s) => s.season === current)) {
      seasons.push({ season: current, entry: null as unknown as ActivityEntry, detail: {} });
    }
    return seasons.sort((a, b) => b.season.localeCompare(a.season));
  }, [activity, current]);

  if (clientId == null) return null;

  return (
    <div className="mb-5">
      <p className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-stone-400">
        <TreePine size={12} />
        Christmas history
        <span className="ml-1 font-normal normal-case tracking-normal text-stone-400">· a green dot marks a value set here, which the spreadsheet sync keeps</span>
      </p>
      <div className="overflow-x-auto rounded-xl border border-stone-200 bg-white">
        <table className="w-full min-w-[820px] text-xs">
          <thead>
            <tr className="border-b border-stone-100 text-left text-[10px] uppercase tracking-wide text-stone-400">
              {COLS.map((c, i) => <th key={i} className="px-3 py-2 font-semibold">{c}</th>)}
            </tr>
          </thead>
          <tbody>
            {rows.map(({ season, entry, detail: d }) => {
              const isCurrent = season === current;
              const empty = !entry;
              const status = statusOf(d);
              const total = seasonTotal(d);
              const fees = [d.install_fee, d.takedown_fee, d.storage_fee].map((v) => (num(v) === null ? "–" : formatCurrency(num(v)))).join(" / ");
              return (
                <React.Fragment key={season}>
                  <tr className={`border-b border-stone-100 last:border-b-0 ${empty ? "text-stone-400" : "text-stone-700"}`}>
                    <td className="px-3 py-2">
                      <span className="rounded-full px-2 py-0.5 font-semibold" style={{ backgroundColor: "rgb(var(--ll-brand-soft))", color: "rgb(var(--ll-brand))" }}>{season}</span>
                      {isCurrent && <span className="ml-1.5 text-[10px] text-stone-400">this season</span>}
                    </td>
                    <td className="px-3 py-2">
                      {empty ? <span className="italic">Nothing recorded yet</span> : (
                        <span className={`rounded-full border px-2 py-0.5 text-[11px] font-medium ${STATUS_CLASS[status]}`}>
                          {STATUS_LABEL[status]}<EditedDot d={d} k={status === "hold" ? "hold" : "not_installing"} />
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{d.install_date ? mdy(d.install_date) : status === "not_installing" && d.was_scheduled ? <s>{mdy(d.was_scheduled)}</s> : "–"}<EditedDot d={d} k="install_date" /></td>
                    <td className="px-3 py-2 whitespace-nowrap">{d.takedown_date ? mdy(d.takedown_date) : "–"}<EditedDot d={d} k="takedown_date" /></td>
                    <td className="px-3 py-2">{d.storing === true ? "Yes" : d.storing === false ? "No" : "–"}{d.storage_note ? <span className="ml-1 text-stone-400" title={String(d.storage_note)}>*</span> : null}<EditedDot d={d} k="storing" /></td>
                    <td className="px-3 py-2">{str(d.boxes) || "–"}<EditedDot d={d} k="boxes" /></td>
                    <td className="max-w-[140px] truncate px-3 py-2" title={str(d.crew)}>{str(d.crew) || "–"}<EditedDot d={d} k="crew" /></td>
                    <td className="px-3 py-2 whitespace-nowrap">{num(d.real_hours) !== null ? `${d.real_hours}h` : num(d.est_hours) !== null ? <span className="text-stone-400">est {String(d.est_hours)}h</span> : "–"}<EditedDot d={d} k="real_hours" /></td>
                    <td className="px-3 py-2 whitespace-nowrap">{fees}</td>
                    <td className="px-3 py-2 whitespace-nowrap font-medium">{total !== null ? formatCurrency(total) : "–"}<EditedDot d={d} k="total" /></td>
                    <td className="px-3 py-2 whitespace-nowrap">{num(d.invoice_total) !== null ? formatCurrency(num(d.invoice_total)) : "–"}<EditedDot d={d} k="invoice_total" /></td>
                    <td className="px-2 py-2 text-right">
                      <button
                        type="button"
                        onClick={() => setEditing(editing === season ? null : season)}
                        className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-emerald-700"
                        title={empty ? `Record the ${season} season` : `Edit the ${season} season`}
                      >
                        {editing === season ? <X size={13} /> : empty ? <Plus size={13} /> : <Pencil size={13} />}
                      </button>
                    </td>
                  </tr>
                  {editing === season && (
                    <tr>
                      <td colSpan={COLS.length} className="bg-stone-50/60 px-3 py-3">
                        <SeasonEditor
                          clientId={clientId}
                          season={season}
                          detail={d}
                          onSaved={onSaved}
                          onClose={() => setEditing(null)}
                        />
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
