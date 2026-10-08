/**
 * A client's name as parts (backend migrations/021). Every client card offers
 * the same four boxes -- First name, Last name, Business name, Location --
 * and people fill whichever apply. They compose the one display name every
 * other screen matches on, with the same rules as
 * backend/app/libs/client_names.py:
 *
 *   Last, First                        Scheib, Nataliya
 *   Last, First - Location             Byler, Kerri - House
 *   Business                           Hilton Garden Inn
 *   Business | Location                The Club at Carlton Woods | Nicklaus Clubhouse
 *   Business | Last, First [- Loc.]    A Hug Away | Frazier, Marissa
 */
import React from "react";

export type NameParts = {
  first_name: string;
  last_name: string;
  company: string;
  site: string;
};

/** What the API returns for a client (parts may be derived, not saved). */
export type NamePartsIn = {
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  site?: string | null;
};

const squash = (s: string | null | undefined) => (s || "").trim().replace(/\s+/g, " ");

/** The display name the server will save for these parts. */
export function composeClientName(p: NameParts): string {
  const last = squash(p.last_name);
  const first = squash(p.first_name);
  const business = squash(p.company);
  const where = squash(p.site);
  let person = last && first ? `${last}, ${first}` : last || first;
  if (person) {
    if (where) person = `${person} - ${where}`;
    return business ? `${business} | ${person}` : person;
  }
  if (business) return where ? `${business} | ${where}` : business;
  return "";
}

/** Form state from a client record: its parts (the server derives them when
 *  none are saved), or the whole name as the business name if it has none. */
export function initialNameParts(client?: (NamePartsIn & { name?: string | null }) | null): NameParts {
  const has = Boolean(client?.first_name || client?.last_name || client?.company || client?.site);
  return {
    first_name: client?.first_name || "",
    last_name: client?.last_name || "",
    company: client?.company || (!has ? client?.name || "" : ""),
    site: client?.site || "",
  };
}

/** Why these parts can't be saved yet, or null when they can. */
export function namePartsProblem(p: NameParts): string | null {
  if (!squash(p.first_name) && !squash(p.last_name) && !squash(p.company)) {
    return "Enter a first or last name, or a business name";
  }
  if (/\|/.test(p.first_name + p.last_name + p.company + p.site)) return "Names can't contain |";
  if (/,/.test(p.first_name + p.last_name)) return "First and last names can't contain a comma";
  return null;
}

/** The request body fields for these parts ("" clears a box). */
export function namePartsBody(p: NameParts) {
  return {
    first_name: squash(p.first_name),
    last_name: squash(p.last_name),
    company: squash(p.company),
    site: squash(p.site),
  };
}

const inputClass =
  "h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-base text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300";

function Field({ label, value, onChange, placeholder, autoFocus }: {
  label: string; value: string; onChange: (v: string) => void; placeholder: string; autoFocus?: boolean;
}) {
  return (
    <label className="block min-w-0">
      <span className="mb-1 block text-xs font-medium text-stone-600">{label}</span>
      <input className={inputClass} value={value} autoFocus={autoFocus} autoComplete="off"
        onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
    </label>
  );
}

export function ClientNameFields({ value, onChange, currentName, autoFocus }: {
  value: NameParts;
  onChange: (next: NameParts) => void;
  /** The saved name when editing, to say when a save will rename. */
  currentName?: string | null;
  autoFocus?: boolean;
}) {
  const set = (key: keyof NameParts) => (v: string) => onChange({ ...value, [key]: v });
  const shown = composeClientName(value);
  const renaming = Boolean(currentName) && shown !== "" && shown !== currentName;
  return (
    <div className="space-y-3" data-testid="client-name-fields">
      <p className="text-xs text-stone-500">Client name <span className="text-stone-400">— fill whichever apply</span></p>
      <div className="grid grid-cols-2 gap-3">
        <Field label="First name" value={value.first_name} onChange={set("first_name")} placeholder="e.g. Kerri" autoFocus={autoFocus} />
        <Field label="Last name" value={value.last_name} onChange={set("last_name")} placeholder="e.g. Byler" />
      </div>
      {/* Business names run long ("The Club at Carlton Woods"): full width. */}
      <Field label="Business name" value={value.company} onChange={set("company")} placeholder="e.g. A Hug Away" />
      <Field label="Location" value={value.site} onChange={set("site")} placeholder="e.g. House, Daycare, Nicklaus Clubhouse" />
      <p className="text-xs text-stone-500" aria-live="polite">
        Shows as: <span className="font-semibold text-stone-800">{shown || "—"}</span>
        {renaming && (
          <span className="mt-0.5 block text-amber-700">
            Renames “{currentName}” everywhere: projects, jobs, the Install Schedule and the sheet sync.
          </span>
        )}
      </p>
    </div>
  );
}
