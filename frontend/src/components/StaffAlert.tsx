import React, { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { toast } from "sonner";
import { AlertTriangle } from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { currentMe, isReadOnly } from "utils/me";

/**
 * The staff alert: one short warning about a client ("dog in the yard --
 * call before opening the gate"), shown as an amber icon next to the
 * client's name wherever the name appears. Hover (or tap) shows it, signed
 * and dated; clicking opens a small editor for office staff and up.
 *
 * Stored on the client (clients.staff_alert); written by
 * PUT /api/clients/{id}/staff-alert. The popover renders in a portal, so the
 * icon can sit inside a clickable row or a button without the editor's
 * clicks and keystrokes reaching it.
 */

export interface StaffAlertValue {
  text: string;
  by?: string | null;
  at?: string | null;
}

export const STAFF_ALERT_MAX = 500;

const EDIT_ROLES = new Set(["staff", "admin", "super_admin"]);

/** May the signed-in account set or clear a staff alert? */
export function canEditStaffAlert(): boolean {
  const me = currentMe();
  return Boolean(me && EDIT_ROLES.has(me.role) && !isReadOnly());
}

/** The alert in a client row from /api/clients/list, or null. */
export function staffAlertOf(row: {
  staff_alert?: string | null;
  staff_alert_by?: string | null;
  staff_alert_at?: string | null;
} | null | undefined): StaffAlertValue | null {
  if (!row?.staff_alert) return null;
  return { text: row.staff_alert, by: row.staff_alert_by ?? null, at: row.staff_alert_at ?? null };
}

export interface StaffAlertSaved {
  id: number;
  staff_alert: string | null;
  staff_alert_by: string | null;
  staff_alert_at: string | null;
}

export async function saveStaffAlert(clientId: number, text: string): Promise<StaffAlertSaved> {
  const res = await apiFetch(`/api/clients/${clientId}/staff-alert`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  if (!res.ok) {
    let why = "Couldn't save the staff alert";
    try {
      const j = await res.json();
      if (j?.detail) why = String(j.detail);
    } catch { /* no body */ }
    throw new Error(why);
  }
  return res.json();
}

function signature(alert: StaffAlertValue): string {
  const when = alert.at ? new Date(alert.at) : null;
  const date = when && !Number.isNaN(when.getTime())
    ? when.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" })
    : "";
  return [alert.by, date].filter(Boolean).join(", ");
}

type Mode = "closed" | "card" | "edit";

export function StaffAlert({
  clientId,
  alert,
  onSaved,
  editable,
  addLabel = "+ alert",
  showAdd = "hover",
  size = 15,
  className = "",
}: {
  clientId?: number | null;
  alert: StaffAlertValue | null;
  onSaved?: (saved: StaffAlertSaved) => void;
  /** Defaults to the signed-in role (staff and up, not the view-only login). */
  editable?: boolean;
  addLabel?: string;
  /** With no alert: "hover" shows a faint add link when a parent `group` is
   *  hovered, "always" shows it, "never" shows nothing. */
  showAdd?: "hover" | "always" | "never";
  size?: number;
  className?: string;
}) {
  const canEdit = (editable ?? canEditStaffAlert()) && clientId != null;
  const [mode, setMode] = useState<Mode>("closed");
  const [draft, setDraft] = useState("");
  const [saving, setSaving] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  const anchor = useRef<HTMLSpanElement>(null);
  const pop = useRef<HTMLDivElement>(null);
  const lastPointer = useRef<string>("mouse");
  const hoverTimer = useRef<number | null>(null);

  const place = () => {
    const r = anchor.current?.getBoundingClientRect();
    if (!r) return;
    const width = 288;
    const left = Math.max(8, Math.min(r.left, window.innerWidth - width - 8));
    setPos({ top: r.bottom + 6, left });
  };

  useLayoutEffect(() => {
    if (mode !== "closed") place();
  }, [mode]);

  useEffect(() => {
    if (mode === "closed") return;
    const onDown = (e: PointerEvent) => {
      const t = e.target as Node;
      if (pop.current?.contains(t) || anchor.current?.contains(t)) return;
      setMode("closed");
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setMode("closed");
    const onMove = () => place();
    document.addEventListener("pointerdown", onDown);
    document.addEventListener("keydown", onKey);
    window.addEventListener("scroll", onMove, true);
    window.addEventListener("resize", onMove);
    return () => {
      document.removeEventListener("pointerdown", onDown);
      document.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", onMove, true);
      window.removeEventListener("resize", onMove);
    };
  }, [mode]);

  if (!alert && (!canEdit || showAdd === "never")) return null;

  const openEditor = () => {
    setDraft(alert?.text || "");
    setMode("edit");
  };

  const activate = (e: React.SyntheticEvent) => {
    e.stopPropagation();
    e.preventDefault();
    if (!alert) {
      openEditor();
      return;
    }
    // Touch has no hover: a tap shows the card (with an Edit button for staff).
    if (lastPointer.current === "touch" || !canEdit) {
      setMode((m) => (m === "card" ? "closed" : "card"));
      return;
    }
    openEditor();
  };

  const save = async (text: string) => {
    if (clientId == null) return;
    setSaving(true);
    try {
      const saved = await saveStaffAlert(clientId, text);
      onSaved?.(saved);
      toast.success(saved.staff_alert ? "Staff alert saved" : "Staff alert cleared");
      setMode("closed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Couldn't save the staff alert");
    } finally {
      setSaving(false);
    }
  };

  const stop = (e: React.SyntheticEvent) => e.stopPropagation();

  const trigger = alert ? (
    <span
      ref={anchor}
      role="button"
      tabIndex={0}
      aria-label={`Staff alert: ${alert.text}`}
      onPointerDown={(e) => { lastPointer.current = e.pointerType; e.stopPropagation(); }}
      onPointerEnter={(e) => {
        if (e.pointerType !== "mouse") return;
        if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
        setMode((m) => (m === "closed" ? "card" : m));
      }}
      onPointerLeave={(e) => {
        if (e.pointerType !== "mouse") return;
        hoverTimer.current = window.setTimeout(() => setMode((m) => (m === "card" ? "closed" : m)), 150);
      }}
      onClick={activate}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") activate(e); }}
      className={`inline-flex shrink-0 cursor-pointer items-center rounded text-amber-500 hover:text-amber-600 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 ${className}`}
    >
      <AlertTriangle size={size} strokeWidth={2.2} />
    </span>
  ) : (
    <span
      ref={anchor}
      role="button"
      tabIndex={0}
      data-edit
      onPointerDown={stop}
      onClick={activate}
      onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") activate(e); }}
      className={`inline-flex shrink-0 cursor-pointer items-center whitespace-nowrap rounded px-1 text-[11px] font-medium text-amber-700/80 hover:text-amber-700 focus:opacity-100 focus:outline-none focus-visible:ring-2 focus-visible:ring-amber-300 ${
        showAdd === "hover" ? "opacity-0 group-hover:opacity-100" : ""
      } ${className}`}
      title="Add a staff alert -- shown next to this client's name everywhere"
    >
      {addLabel}
    </span>
  );

  const popover = mode !== "closed" && pos && createPortal(
    <div
      ref={pop}
      onClick={stop}
      onPointerDown={stop}
      onKeyDown={stop}
      onPointerEnter={() => { if (hoverTimer.current) window.clearTimeout(hoverTimer.current); }}
      onPointerLeave={(e) => {
        if (e.pointerType === "mouse" && mode === "card") {
          hoverTimer.current = window.setTimeout(() => setMode((m) => (m === "card" ? "closed" : m)), 150);
        }
      }}
      role="dialog"
      aria-label="Staff alert"
      className="fixed z-[10050] w-72 rounded-xl border border-amber-200 bg-white p-3 text-left shadow-xl"
      style={{ top: pos.top, left: pos.left }}
    >
      {mode === "card" && alert && (
        <>
          <p className="mb-1 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
            <AlertTriangle size={12} /> Staff alert
          </p>
          <p className="whitespace-pre-wrap text-sm text-stone-800">{alert.text}</p>
          {signature(alert) && <p className="mt-1.5 text-xs text-stone-500">— {signature(alert)}</p>}
          {canEdit && (
            <button
              type="button"
              data-edit
              onClick={openEditor}
              className="mt-2 text-xs font-semibold text-emerald-700 hover:text-emerald-900"
            >
              Edit
            </button>
          )}
        </>
      )}
      {mode === "edit" && (
        <form onSubmit={(e) => { e.preventDefault(); void save(draft); }}>
          <p className="mb-1.5 flex items-center gap-1.5 text-[10px] font-semibold uppercase tracking-wide text-amber-700">
            <AlertTriangle size={12} /> Staff alert
          </p>
          <textarea
            autoFocus
            rows={3}
            maxLength={STAFF_ALERT_MAX}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); void save(draft); }
            }}
            placeholder="What should the team know before going out? e.g. Dog in the yard — call first"
            className="w-full resize-none rounded-lg border border-stone-200 px-2.5 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-amber-300"
          />
          <div className="mt-1 flex items-center justify-between gap-2">
            <span className="text-[10px] text-stone-400">{draft.trim().length}/{STAFF_ALERT_MAX}</span>
            <div className="flex items-center gap-1.5">
              <button type="button" onClick={() => setMode("closed")} className="px-2 py-1 text-xs text-stone-500 hover:text-stone-700">
                Cancel
              </button>
              {alert && (
                <button
                  type="button"
                  data-edit
                  disabled={saving}
                  onClick={() => void save("")}
                  className="rounded-md px-2 py-1 text-xs font-medium text-red-600 hover:bg-red-50 disabled:opacity-50"
                >
                  Clear
                </button>
              )}
              <button
                type="submit"
                data-edit
                disabled={saving || (!draft.trim() && !alert)}
                className="rounded-md bg-amber-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
              >
                {saving ? "Saving…" : "Save"}
              </button>
            </div>
          </div>
        </form>
      )}
    </div>,
    document.body,
  );

  return (
    <>
      {trigger}
      {popover}
    </>
  );
}
