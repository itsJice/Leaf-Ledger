import React, { useEffect, useRef, useState } from "react";
import { Check, ChevronRight, Loader2, X } from "lucide-react";

/**
 * Cascading Client -> Project -> Group picker used by the standalone "New Design"
 * entry point (route /designs/new).
 *
 * IMPORTANT: this component never touches the network. Choosing "+ Add new..."
 * only records a typed name in local state. The parent is responsible for
 * creating the client / project / group records, and it must only do that when
 * the design is actually saved. That keeps abandoned builds from leaving orphan
 * clients, projects, and rooms behind.
 */

export type DesignHierarchyClient = { id?: number | null; name: string };
export type DesignHierarchyProject = { id: number; name: string; client_name?: string | null };
export type DesignHierarchyGroup = { id: number; name: string; project_id: number };

export type DesignHierarchy = {
  clients: DesignHierarchyClient[];
  projects: DesignHierarchyProject[];
  groups: DesignHierarchyGroup[];
};

export type DesignDestination = {
  clientName: string;
  clientIsNew: boolean;
  projectId: number | null;
  projectName: string;
  projectIsNew: boolean;
  groupId: number | null;
  groupName: string;
  groupIsNew: boolean;
};

export const EMPTY_DESIGN_DESTINATION: DesignDestination = {
  clientName: "",
  clientIsNew: false,
  projectId: null,
  projectName: "",
  projectIsNew: false,
  groupId: null,
  groupName: "",
  groupIsNew: false,
};

export function destinationIsComplete(destination: DesignDestination) {
  const clientOk = Boolean(destination.clientName.trim());
  const projectOk = destination.projectIsNew ? Boolean(destination.projectName.trim()) : destination.projectId !== null;
  const groupOk = destination.groupIsNew ? Boolean(destination.groupName.trim()) : destination.groupId !== null;
  return clientOk && projectOk && groupOk;
}

const ADD_NEW_VALUE = "__add_new__";

type SlotOption = { value: string; label: string };

function DestinationSlot({
  label,
  placeholder,
  newPlaceholder,
  options,
  value,
  displayName,
  isNew,
  disabled,
  disabledHint,
  loading,
  locked,
  onPick,
  onCreate,
  onReset,
}: {
  label: string;
  placeholder: string;
  newPlaceholder: string;
  options: SlotOption[];
  value: string;
  displayName: string;
  isNew: boolean;
  disabled?: boolean;
  disabledHint?: string;
  loading?: boolean;
  locked?: boolean;
  onPick: (value: string) => void;
  onCreate: (name: string) => void;
  onReset: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (adding) window.requestAnimationFrame(() => inputRef.current?.focus());
  }, [adding]);

  useEffect(() => {
    if (disabled && adding) {
      setAdding(false);
      setDraft("");
    }
  }, [disabled, adding]);

  const commit = () => {
    const name = draft.trim();
    if (!name) return;
    onCreate(name);
    setAdding(false);
    setDraft("");
  };

  return (
    <label className="flex min-w-[168px] flex-1 flex-col gap-1">
      <span className="flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        {label}
        {isNew && (
          <span className="rounded-full bg-emerald-50 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wide text-emerald-700">
            new
          </span>
        )}
      </span>

      {isNew || locked ? (
        <div className="flex h-[38px] items-center justify-between gap-2 rounded-xl border border-stone-200 bg-white px-3 text-sm font-semibold text-stone-800">
          <span className="truncate">{displayName || placeholder}</span>
          {!locked && (
            <button
              type="button"
              onClick={onReset}
              aria-label={`Clear ${label.toLowerCase()}`}
              className="flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-stone-300 transition hover:bg-stone-100 hover:text-stone-600"
            >
              <X size={12} />
            </button>
          )}
        </div>
      ) : adding ? (
        <div className="flex h-[38px] items-center gap-1 rounded-xl border border-emerald-300 bg-white px-2 ring-2 ring-emerald-100">
          <input
            ref={inputRef}
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                commit();
              }
              if (event.key === "Escape") {
                event.preventDefault();
                setAdding(false);
                setDraft("");
              }
            }}
            placeholder={newPlaceholder}
            aria-label={newPlaceholder}
            className="min-w-0 flex-1 bg-transparent px-1 text-sm text-stone-900 outline-none placeholder:text-stone-300"
          />
          <button
            type="button"
            onClick={commit}
            disabled={!draft.trim()}
            aria-label={`Save new ${label.toLowerCase()}`}
            className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg bg-emerald-700 text-white transition hover:bg-emerald-800 disabled:opacity-40"
          >
            <Check size={13} />
          </button>
          <button
            type="button"
            onClick={() => {
              setAdding(false);
              setDraft("");
            }}
            aria-label={`Cancel new ${label.toLowerCase()}`}
            className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg text-stone-400 transition hover:bg-stone-100 hover:text-stone-700"
          >
            <X size={13} />
          </button>
        </div>
      ) : (
        <div className="relative">
          <select
            value={value}
            disabled={disabled}
            title={disabled ? disabledHint : undefined}
            onChange={(event) => {
              const next = event.target.value;
              if (next === ADD_NEW_VALUE) {
                setAdding(true);
                return;
              }
              onPick(next);
            }}
            className="h-[38px] w-full appearance-none rounded-xl border border-stone-200 bg-white px-3 pr-8 text-sm font-medium text-stone-800 outline-none transition focus:border-emerald-500 focus:ring-2 focus:ring-emerald-100 disabled:cursor-not-allowed disabled:bg-stone-50 disabled:text-stone-400"
          >
            <option value="">{disabled ? disabledHint || placeholder : placeholder}</option>
            {options.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
            <option value={ADD_NEW_VALUE}>+ Add new…</option>
          </select>
          <span className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-stone-400">
            {loading ? <Loader2 size={13} className="animate-spin" /> : <ChevronRight size={13} className="rotate-90" />}
          </span>
        </div>
      )}
    </label>
  );
}

export default function DesignDestinationPicker({
  hierarchy,
  destination,
  onChange,
  loading,
  locked,
  className,
}: {
  hierarchy: DesignHierarchy;
  destination: DesignDestination;
  onChange: (next: DesignDestination) => void;
  loading?: boolean;
  /** After the design has been saved the destination can no longer be changed. */
  locked?: boolean;
  className?: string;
}) {
  const clientOptions: SlotOption[] = hierarchy.clients
    .map((client) => client.name)
    .filter((name, index, list) => Boolean(name && name.trim()) && list.indexOf(name) === index)
    .sort((a, b) => a.localeCompare(b))
    .map((name) => ({ value: name, label: name }));

  const projectOptions: SlotOption[] = hierarchy.projects
    .filter((project) => (project.client_name || "").trim() === destination.clientName.trim())
    .map((project) => ({ value: String(project.id), label: project.name }));

  const groupOptions: SlotOption[] = hierarchy.groups
    .filter((group) => destination.projectId !== null && group.project_id === destination.projectId)
    .map((group) => ({ value: String(group.id), label: group.name }));

  const setDestination = (patch: Partial<DesignDestination>) => onChange({ ...destination, ...patch });

  const resetProject = {
    projectId: null,
    projectName: "",
    projectIsNew: false,
  };
  const resetGroup = {
    groupId: null,
    groupName: "",
    groupIsNew: false,
  };

  return (
    <div className={`flex flex-wrap items-end gap-2 ${className || ""}`}>
      <DestinationSlot
        label="Client"
        placeholder="Select client"
        newPlaceholder="New client name"
        options={clientOptions}
        value={destination.clientIsNew ? "" : destination.clientName}
        displayName={destination.clientName}
        isNew={destination.clientIsNew}
        loading={loading}
        locked={locked}
        onPick={(value) => setDestination({ clientName: value, clientIsNew: false, ...resetProject, ...resetGroup })}
        onCreate={(name) => setDestination({ clientName: name, clientIsNew: true, ...resetProject, ...resetGroup })}
        onReset={() => setDestination({ clientName: "", clientIsNew: false, ...resetProject, ...resetGroup })}
      />

      <span className="mb-2.5 hidden text-stone-300 sm:block">
        <ChevronRight size={14} />
      </span>

      <DestinationSlot
        label="Project"
        placeholder="Select project"
        newPlaceholder="New project name"
        options={projectOptions}
        value={destination.projectIsNew || destination.projectId === null ? "" : String(destination.projectId)}
        displayName={destination.projectName}
        isNew={destination.projectIsNew}
        disabled={!destination.clientName.trim()}
        disabledHint="Select a client first"
        loading={loading}
        locked={locked}
        onPick={(value) => {
          const id = Number(value);
          const match = hierarchy.projects.find((project) => project.id === id);
          setDestination({
            projectId: Number.isFinite(id) && value ? id : null,
            projectName: match?.name || "",
            projectIsNew: false,
            ...resetGroup,
          });
        }}
        onCreate={(name) => setDestination({ projectId: null, projectName: name, projectIsNew: true, ...resetGroup })}
        onReset={() => setDestination({ ...resetProject, ...resetGroup })}
      />

      <span className="mb-2.5 hidden text-stone-300 sm:block">
        <ChevronRight size={14} />
      </span>

      <DestinationSlot
        label="Project group"
        placeholder="Select project group"
        newPlaceholder="New group name"
        options={groupOptions}
        value={destination.groupIsNew || destination.groupId === null ? "" : String(destination.groupId)}
        displayName={destination.groupName}
        isNew={destination.groupIsNew}
        disabled={!destination.projectIsNew && destination.projectId === null}
        disabledHint="Select a project first"
        loading={loading}
        locked={locked}
        onPick={(value) => {
          const id = Number(value);
          const match = hierarchy.groups.find((group) => group.id === id);
          setDestination({
            groupId: Number.isFinite(id) && value ? id : null,
            groupName: match?.name || "",
            groupIsNew: false,
          });
        }}
        onCreate={(name) => setDestination({ groupId: null, groupName: name, groupIsNew: true })}
        onReset={() => setDestination({ ...resetGroup })}
      />
    </div>
  );
}
