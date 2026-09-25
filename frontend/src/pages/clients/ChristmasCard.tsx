import React, { useMemo, useState } from "react";
import { Check, Pencil, Plus, Trash2, X } from "components/icons";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../../apiclient/http-client";
import { formatCurrency } from "utils/format";
import type { ActivityEntry } from "./SeasonHistory";
import {
  INVENTORY_TYPES, ROLE_LABELS, discountLabel, missingLabel,
  type InventoryLine, type InventoryType, type PricingView, type RoleNeed,
} from "./pricing";

/**
 * A client's Christmas card for one season: what they own (trees, wreaths,
 * garlands, sprays, swags -- each a type, a size and a count), how many
 * boxes it lives in and whether we store them, and what the job takes
 * (crew leads / specialty / designers / generals, install hours, the drive
 * each way from the warehouse).
 *
 * The card is what the ideal price is computed FROM (backend
 * app.libs.pricing, off that season's rate card): install labour, the same
 * again for takedown, storage per box, and pickup & delivery from the box
 * count and the drive. Next to the card: that ideal, what was charged, and
 * the discount between them. Nothing here computes a price -- the numbers
 * come back on the season row from the API.
 *
 * Every key saved here lives on the season's client_activity.detail, stamped
 * as an app edit so the spreadsheet sync leaves it alone. A blank current
 * season pre-fills from the previous one -- the client's stuff rarely
 * changes -- and nothing is written until the first Save.
 */

type Props = {
  clientId: number;
  season: string;
  detail: Record<string, unknown>;
  previousDetail: Record<string, unknown> | null;
  pricing: PricingView | null;
  onSaved: (entry: ActivityEntry) => void;
};

type LineDraft = { type: InventoryType; size: string; qty: string; note: string };
type Draft = {
  inventory: LineDraft[];
  role: Record<keyof RoleNeed, string>;
  est_hours: string;
  boxes: string;
  storing: "yes" | "no" | "unknown";
  drive_min_out: string;
  drive_min_back: string;
};

const TYPE_LABEL: Record<InventoryType, string> = {
  tree: "Tree", wreath: "Wreath", garland: "Garland", spray: "Spray", swag: "Swag", other: "Other",
};

function str(v: unknown): string {
  return v === null || v === undefined ? "" : String(v);
}

function linesOf(d: Record<string, unknown>): InventoryLine[] {
  const raw = d.inventory;
  if (!Array.isArray(raw)) return [];
  return raw.filter((l) => l && typeof l === "object" && (INVENTORY_TYPES as readonly string[]).includes(String((l as InventoryLine).type))) as InventoryLine[];
}

function roleOf(d: Record<string, unknown>): RoleNeed {
  const raw = d.role_need;
  return raw && typeof raw === "object" ? (raw as RoleNeed) : {};
}

/** Does this season's card have anything on it yet? */
function hasCard(d: Record<string, unknown>): boolean {
  return linesOf(d).length > 0 || Object.values(roleOf(d)).some((v) => v) || d.est_hours != null || d.boxes != null;
}

function draftFrom(d: Record<string, unknown>): Draft {
  const role = roleOf(d);
  return {
    inventory: linesOf(d).map((l) => ({ type: l.type, size: str(l.size), qty: str(l.qty), note: str(l.note) })),
    role: { leads: str(role.leads), specialty: str(role.specialty), designer: str(role.designer), general: str(role.general) },
    est_hours: str(d.est_hours),
    boxes: str(d.boxes),
    storing: d.storing === true ? "yes" : d.storing === false ? "no" : "unknown",
    drive_min_out: str(d.drive_min_out),
    drive_min_back: str(d.drive_min_back),
  };
}

function linesToFields(lines: LineDraft[]): InventoryLine[] {
  return lines
    .filter((l) => l.type)
    .map((l) => {
      const out: InventoryLine = { type: l.type, qty: Math.max(1, Number(l.qty) || 1) };
      if (l.size.trim()) out.size = l.size.trim();
      if (l.note.trim()) out.note = l.note.trim();
      return out;
    });
}

function roleToFields(role: Draft["role"]): RoleNeed {
  const out: RoleNeed = {};
  (Object.keys(role) as (keyof RoleNeed)[]).forEach((k) => {
    const s = role[k].trim();
    if (s !== "") out[k] = Number(s);
  });
  return out;
}

/** Only what changed, in the shape PUT /clients/{id}/seasons/{season} takes.
 *  `original` is the row as stored -- when the draft was seeded from the
 *  previous season, everything on it counts as changed. */
function diff(original: Record<string, unknown>, draft: Draft): Record<string, unknown> {
  const fields: Record<string, unknown> = {};
  const inv = linesToFields(draft.inventory);
  if (JSON.stringify(inv) !== JSON.stringify(linesOf(original))) fields.inventory = inv.length ? inv : null;
  const role = roleToFields(draft.role);
  if (JSON.stringify(role) !== JSON.stringify(roleOf(original))) fields.role_need = Object.keys(role).length ? role : null;
  (["est_hours", "boxes", "drive_min_out", "drive_min_back"] as const).forEach((k) => {
    const after = draft[k].trim();
    if (after !== str(original[k])) fields[k] = after === "" ? null : after;
  });
  const storingBefore = original.storing === true ? "yes" : original.storing === false ? "no" : "unknown";
  if (draft.storing !== storingBefore) fields.storing = draft.storing === "unknown" ? null : draft.storing === "yes";
  return fields;
}

const inputClass = "w-full rounded-lg border border-stone-200 px-2.5 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-emerald-300";
const smallInput = "w-16 rounded-lg border border-stone-200 px-2 py-1 text-xs text-right focus:outline-none focus:ring-2 focus:ring-emerald-300";

function Money({ v }: { v: number | null | undefined }) {
  return <>{v === null || v === undefined ? "–" : formatCurrency(v)}</>;
}

function Summary({ d, pricing, season }: { d: Record<string, unknown>; pricing: PricingView | null; season: string }) {
  const lines = linesOf(d);
  const role = roleOf(d);
  const crew = ROLE_LABELS.filter(({ key }) => role[key]).map(({ key, label }) => `${role[key]} ${label.toLowerCase()}`).join(", ");
  const ideal = pricing?.ideal;
  const missing = missingLabel(ideal?.missing);
  return (
    <div className="grid gap-x-6 gap-y-2 text-xs text-stone-700 sm:grid-cols-[1fr_auto]">
      <div>
        {lines.length > 0 ? (
          <ul className="flex flex-wrap gap-1.5">
            {lines.map((l, i) => (
              <li key={i} className="rounded-full border border-stone-200 bg-stone-50 px-2 py-0.5" title={l.note || ""}>
                {l.qty} × {TYPE_LABEL[l.type]}{l.size ? ` ${l.size}` : ""}
              </li>
            ))}
          </ul>
        ) : (
          <p className="italic text-stone-400">No inventory recorded yet — what trees, wreaths, garlands, sprays and swags does this client have?</p>
        )}
        <p className="mt-1.5 text-stone-500">
          {[
            d.boxes != null ? `${String(d.boxes)} boxes` : null,
            d.storing === true ? "stored with us" : d.storing === false ? "kept at the client" : null,
            crew || null,
            d.est_hours != null ? `${String(d.est_hours)}h install` : null,
            d.drive_min_out != null || d.drive_min_back != null ? `drive ${str(d.drive_min_out) || "?"} / ${str(d.drive_min_back) || "?"} min` : null,
          ].filter(Boolean).join(" · ") || "No crew, hours or boxes on the card yet"}
        </p>
      </div>
      <div className="min-w-[220px] rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
        <div className="flex items-baseline justify-between gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Ideal {season}</span>
          <span className="font-semibold text-stone-800"><Money v={ideal?.total} /></span>
        </div>
        {ideal?.total != null ? (
          <p className="mt-0.5 text-[10px] text-stone-400">
            install <Money v={ideal.install} /> · takedown <Money v={ideal.takedown} /> · storage <Money v={ideal.storage} /> · pickup &amp; delivery <Money v={ideal.pickup_delivery} />
          </p>
        ) : (
          <p className="mt-0.5 text-[10px] text-amber-700">{missing ? `Needs ${missing}` : "Not enough on the card to price"}</p>
        )}
        <div className="mt-1.5 flex items-baseline justify-between gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">
            {pricing?.charged_source === "invoice" ? "Invoiced" : "Charged"}
          </span>
          <span className="font-semibold text-stone-800"><Money v={pricing?.charged} /></span>
        </div>
        <div className="mt-0.5 flex items-baseline justify-between gap-3">
          <span className="text-[10px] font-semibold uppercase tracking-wide text-stone-400">Discount</span>
          <span className={pricing?.discount_pct != null && pricing.discount_pct > 0.05 ? "font-medium text-amber-700" : pricing?.discount_pct != null && pricing.discount_pct < -0.05 ? "font-medium text-emerald-700" : "text-stone-600"}>
            {discountLabel(pricing?.discount_pct) || "–"}
          </span>
        </div>
        {pricing?.basis && <p className="mt-1 text-[10px] text-stone-400" title={pricing.basis}>{pricing.basis}</p>}
      </div>
    </div>
  );
}

export function ChristmasCard({ clientId, season, detail, previousDetail, pricing, onSaved }: Props) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const seeded = !hasCard(detail) && !!previousDetail && hasCard(previousDetail);
  const [draft, setDraft] = useState<Draft>(() => draftFrom(seeded && previousDetail ? previousDetail : detail));

  // A save (or a sync) replaces the row under us; re-seed the draft when the
  // editor is closed so the next open starts from what is stored.
  const stored = useMemo(() => JSON.stringify(detail), [detail]);
  const [seenStored, setSeenStored] = useState(stored);
  if (!editing && stored !== seenStored) {
    setSeenStored(stored);
    setDraft(draftFrom(seeded && previousDetail ? previousDetail : detail));
  }

  const setLine = (i: number, patch: Partial<LineDraft>) =>
    setDraft((d) => ({ ...d, inventory: d.inventory.map((l, j) => (j === i ? { ...l, ...patch } : l)) }));
  const addLine = (type: InventoryType) =>
    setDraft((d) => ({ ...d, inventory: [...d.inventory, { type, size: "", qty: "1", note: "" }] }));
  const removeLine = (i: number) =>
    setDraft((d) => ({ ...d, inventory: d.inventory.filter((_, j) => j !== i) }));

  const save = async () => {
    const fields = diff(detail, draft);
    if (Object.keys(fields).length === 0) {
      setEditing(false);
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
        let why = "Couldn't save the Christmas card";
        try {
          const j = await res.json();
          if (j?.detail) why = String(j.detail);
        } catch { /* no body */ }
        throw new Error(why);
      }
      onSaved(await res.json());
      toast.success(`${season} Christmas card saved`);
      setEditing(false);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save the Christmas card");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mb-4 rounded-xl border border-stone-200 bg-white p-4">
      <div className="mb-2 flex items-center justify-between gap-3">
        <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-stone-400">
          Christmas card · {season}
          {seeded && !editing && <span className="font-normal normal-case tracking-normal text-amber-700">· copied from last season, not saved yet</span>}
        </p>
        <button
          type="button"
          onClick={() => setEditing((v) => !v)}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs text-stone-500 hover:bg-stone-100 hover:text-emerald-700"
        >
          {editing ? <><X size={12} /> Close</> : <><Pencil size={12} /> Edit card</>}
        </button>
      </div>

      {!editing ? (
        <Summary d={seeded && previousDetail ? previousDetail : detail} pricing={pricing} season={season} />
      ) : (
        <div className="space-y-3">
          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">Inventory</p>
            {draft.inventory.length === 0 && <p className="mb-1.5 text-xs italic text-stone-400">Nothing yet — add a line per item type and size.</p>}
            <div className="space-y-1.5">
              {draft.inventory.map((l, i) => (
                <div key={i} className="grid grid-cols-[92px_60px_1fr_1fr_28px] items-center gap-1.5">
                  <select className={inputClass} value={l.type} onChange={(e) => setLine(i, { type: e.target.value as InventoryType })}>
                    {INVENTORY_TYPES.map((t) => <option key={t} value={t}>{TYPE_LABEL[t]}</option>)}
                  </select>
                  <input inputMode="numeric" className={`${inputClass} text-right`} value={l.qty} onChange={(e) => setLine(i, { qty: e.target.value })} placeholder="qty" title="How many" />
                  <input className={inputClass} value={l.size} onChange={(e) => setLine(i, { size: e.target.value })} placeholder="size (12 ft, 36 in, 9 ft…)" />
                  <input className={inputClass} value={l.note} onChange={(e) => setLine(i, { note: e.target.value })} placeholder="note (flocked, pre-lit, front door…)" />
                  <button type="button" onClick={() => removeLine(i)} className="rounded-md p-1 text-stone-400 hover:bg-stone-100 hover:text-red-600" title="Remove line"><Trash2 size={13} /></button>
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex flex-wrap gap-1.5">
              {INVENTORY_TYPES.map((t) => (
                <button key={t} type="button" onClick={() => addLine(t)} className="flex items-center gap-1 rounded-full border border-stone-200 bg-white px-2 py-0.5 text-[11px] text-stone-600 hover:bg-stone-50">
                  <Plus size={10} /> {TYPE_LABEL[t]}
                </button>
              ))}
            </div>
          </div>

          <div className="grid gap-2.5 sm:grid-cols-4">
            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-stone-400">Boxes</span>
              <input inputMode="numeric" className={inputClass} value={draft.boxes} onChange={(e) => setDraft((d) => ({ ...d, boxes: e.target.value }))} />
            </label>
            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-stone-400">Stored with us</span>
              <select className={inputClass} value={draft.storing} onChange={(e) => setDraft((d) => ({ ...d, storing: e.target.value as Draft["storing"] }))}>
                <option value="yes">Yes</option>
                <option value="no">No — kept at the client</option>
                <option value="unknown">Unknown</option>
              </select>
            </label>
            <label className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-stone-400">Install hours</span>
              <input inputMode="decimal" className={inputClass} value={draft.est_hours} onChange={(e) => setDraft((d) => ({ ...d, est_hours: e.target.value }))} />
            </label>
            <div className="block">
              <span className="mb-0.5 block text-[10px] font-semibold uppercase tracking-wide text-stone-400">Drive out / back (min)</span>
              <div className="flex items-center gap-1.5">
                <input inputMode="decimal" className={smallInput} value={draft.drive_min_out} onChange={(e) => setDraft((d) => ({ ...d, drive_min_out: e.target.value }))} placeholder="out" title="Warehouse → client, minutes" />
                <span className="text-stone-400">/</span>
                <input inputMode="decimal" className={smallInput} value={draft.drive_min_back} onChange={(e) => setDraft((d) => ({ ...d, drive_min_back: e.target.value }))} placeholder="back" title="Client → warehouse, minutes" />
              </div>
            </div>
          </div>

          <div>
            <p className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">Crew for the install</p>
            <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
              {ROLE_LABELS.map(({ key, label }) => (
                <label key={key} className="block">
                  <span className="mb-0.5 block text-[11px] text-stone-500">{label}</span>
                  <input inputMode="numeric" className={inputClass} value={draft.role[key]} onChange={(e) => setDraft((d) => ({ ...d, role: { ...d.role, [key]: e.target.value } }))} placeholder="0" />
                </label>
              ))}
            </div>
          </div>

          <div className="flex items-center justify-end gap-2">
            <button type="button" onClick={() => setEditing(false)} className="px-3 py-1.5 text-xs text-stone-500 hover:text-stone-700">Cancel</button>
            <button
              type="button"
              onClick={() => void save()}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-60"
              style={{ backgroundColor: "rgb(var(--ll-brand))" }}
            >
              <Check size={12} strokeWidth={3} />
              {saving ? "Saving…" : "Save card"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
