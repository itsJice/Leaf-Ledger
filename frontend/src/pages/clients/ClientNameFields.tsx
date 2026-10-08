/**
 * A client's name as parts (backend migrations/021): Person (first + last)
 * or Business (company + optional location/site). The parts compose the one
 * display name every other screen matches on -- "Last, First" for a person,
 * "Company | Site" (or just "Company") for a business -- the same rules as
 * backend/app/libs/client_names.py.
 */
import React from "react";
import { Building2, Users } from "components/icons";

export type ClientType = "person" | "business";

export type NameParts = {
  client_type: ClientType;
  first_name: string;
  last_name: string;
  company: string;
  site: string;
};

/** What the API returns for a client (parts may be derived, not saved). */
export type NamePartsIn = {
  client_type?: string | null;
  first_name?: string | null;
  last_name?: string | null;
  company?: string | null;
  site?: string | null;
};

const squash = (s: string | null | undefined) => (s || "").trim().replace(/\s+/g, " ");

/** The display name the server will save for these parts. */
export function composeClientName(p: NameParts): string {
  if (p.client_type === "person") {
    const last = squash(p.last_name);
    const first = squash(p.first_name);
    return last && first ? `${last}, ${first}` : last || first;
  }
  const company = squash(p.company);
  const site = squash(p.site);
  return company && site ? `${company} | ${site}` : company || site;
}

/** Form state from a client record. A new client starts as an empty Person;
 *  an existing one uses its parts (the server derives them when none are
 *  saved), or the whole name as a company if it has none at all. */
export function initialNameParts(client?: (NamePartsIn & { name?: string | null }) | null): NameParts {
  const type: ClientType = client?.client_type === "business" ? "business"
    : client?.client_type === "person" ? "person"
    : client?.name ? "business" : "person";
  return {
    client_type: type,
    first_name: client?.first_name || "",
    last_name: client?.last_name || "",
    company: client?.company || (type === "business" && !client?.client_type ? client?.name || "" : ""),
    site: client?.site || "",
  };
}

/** Why these parts can't be saved yet, or null when they can. */
export function namePartsProblem(p: NameParts): string | null {
  if (p.client_type === "person") {
    if (!squash(p.first_name) && !squash(p.last_name)) return "Enter a first or last name";
    if (/[,|]/.test(p.first_name + p.last_name)) return "Names can't contain a comma or |";
    return null;
  }
  if (!squash(p.company)) return "Enter the company name";
  if (/\|/.test(p.company + p.site)) return "Company and site can't contain |";
  return null;
}

/** The request body fields for these parts (only the type's own fields). */
export function namePartsBody(p: NameParts) {
  return p.client_type === "person"
    ? { client_type: "person", first_name: squash(p.first_name), last_name: squash(p.last_name), company: "", site: "" }
    : { client_type: "business", first_name: "", last_name: "", company: squash(p.company), site: squash(p.site) };
}

const inputClass =
  "h-10 w-full rounded-lg border border-stone-200 bg-white px-3 text-base text-stone-800 focus:outline-none focus:ring-2 focus:ring-emerald-300";

export function ClientNameFields({ value, onChange, currentName, autoFocus }: {
  value: NameParts;
  onChange: (next: NameParts) => void;
  /** The saved name when editing, to say when a save will rename. */
  currentName?: string | null;
  autoFocus?: boolean;
}) {
  const set = (key: keyof NameParts, v: string) => onChange({ ...value, [key]: v });
  const shown = composeClientName(value);
  const renaming = Boolean(currentName) && shown !== "" && shown !== currentName;
  const types: { key: ClientType; label: string; Icon: typeof Users }[] = [
    { key: "person", label: "Person", Icon: Users },
    { key: "business", label: "Business", Icon: Building2 },
  ];
  return (
    <div className="space-y-3" data-testid="client-name-fields">
      <div role="radiogroup" aria-label="Client type" className="grid grid-cols-2 overflow-hidden rounded-lg border border-stone-200 text-sm">
        {types.map(({ key, label, Icon }) => {
          const on = value.client_type === key;
          return (
            <button
              key={key}
              type="button"
              role="radio"
              aria-checked={on}
              onClick={() => onChange({ ...value, client_type: key })}
              className={`flex h-10 items-center justify-center gap-2 font-medium transition-colors ${
                on ? "bg-emerald-700 text-white" : "text-stone-600 hover:bg-stone-50"
              }`}
            >
              <Icon size={16} aria-hidden="true" />
              {label}
            </button>
          );
        })}
      </div>
      {value.client_type === "person" ? (
        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-stone-600">First name</span>
            <input className={inputClass} value={value.first_name} autoFocus={autoFocus}
              autoComplete="off" onChange={(e) => set("first_name", e.target.value)} placeholder="Nataliya" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-stone-600">Last name</span>
            <input className={inputClass} value={value.last_name}
              autoComplete="off" onChange={(e) => set("last_name", e.target.value)} placeholder="Scheib" />
          </label>
        </div>
      ) : (
        <div className="grid gap-3">
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-stone-600">Company</span>
            <input className={inputClass} value={value.company} autoFocus={autoFocus}
              autoComplete="off" onChange={(e) => set("company", e.target.value)} placeholder="The Club at Carlton Woods" />
          </label>
          <label className="block">
            <span className="mb-1 block text-xs font-medium text-stone-600">
              Location / site <span className="font-normal text-stone-400">(optional)</span>
            </span>
            <input className={inputClass} value={value.site}
              autoComplete="off" onChange={(e) => set("site", e.target.value)} placeholder="Nicklaus Clubhouse" />
          </label>
        </div>
      )}
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
