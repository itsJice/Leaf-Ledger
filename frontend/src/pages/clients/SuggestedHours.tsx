import { useEffect, useState } from "react";
import { Check, Sparkle } from "components/icons";
import { toast } from "sonner";
import { apiClient } from "app";
import { ContentType } from "../../apiclient/http-client";
import { apiFetch } from "utils/apiFetch";
import type { ActivityEntry } from "./SeasonHistory";

/**
 * "Suggested 2027: X h (basis)" on the client card, from
 * backend app.libs.install_estimate (GET /install-estimate/client/{id}).
 * Accept writes est_hours on that season through the normal season save,
 * stamped as an app edit; nothing changes until someone presses it. A
 * suggestion that needs rates or sizes says NEEDS INPUT and offers no
 * Accept. Office only on the server; anyone else sees nothing here.
 */

interface Suggestion {
  season: string;
  hours: number | null;
  basis: string;
  basisText: string;
  confidence: "high" | "medium" | "low" | null;
  needsInput: string[];
  currentEst: number | null;
}

const CONFIDENCE: Record<string, string> = { high: "high confidence", medium: "medium confidence", low: "low confidence" };

export function SuggestedHours({ clientId, season, onSaved }: { clientId: number; season: string; onSaved: (e: ActivityEntry) => void }) {
  const [s, setS] = useState<Suggestion | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let live = true;
    apiFetch(`/api/install-estimate/client/${clientId}?season=${encodeURIComponent(season)}`)
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => live && setS(d))
      .catch(() => live && setS(null));
    return () => {
      live = false;
    };
  }, [clientId, season]);

  if (!s) return null;

  const accept = async () => {
    if (s.hours == null) return;
    setSaving(true);
    try {
      const res = await apiClient.request<ActivityEntry>({
        path: `/routes/clients/${clientId}/seasons/${season}`,
        method: "PUT",
        body: { fields: { est_hours: s.hours } },
        type: ContentType.Json,
      });
      if (!res.ok) throw new Error("Couldn't save the suggested hours");
      onSaved(await res.json());
      setS({ ...s, currentEst: s.hours });
      toast.success(`${season} install hours set to ${s.hours} h`);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Couldn't save the suggested hours");
    } finally {
      setSaving(false);
    }
  };

  const accepted = s.hours != null && s.currentEst === s.hours;
  return (
    <div className="mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg bg-stone-50 px-3 py-2 text-xs text-stone-700" data-testid="suggested-hours">
      <Sparkle size={13} className="text-emerald-700" />
      <span className="font-semibold text-stone-800">
        Suggested {season}: {s.hours != null ? `${s.hours} h` : <span className="text-amber-700">NEEDS INPUT</span>}
      </span>
      <span className="text-stone-500">
        ({s.hours != null ? s.basisText : s.needsInput.join(", ")}
        {s.confidence ? `, ${CONFIDENCE[s.confidence]}` : ""})
      </span>
      {s.currentEst != null && !accepted && <span className="text-stone-500">· card says {s.currentEst} h</span>}
      {s.hours != null &&
        (accepted ? (
          <span className="ml-auto inline-flex items-center gap-1 font-semibold text-emerald-700">
            <Check size={12} strokeWidth={3} /> On the {season} card
          </span>
        ) : (
          <button
            type="button"
            data-edit
            onClick={() => void accept()}
            disabled={saving}
            className="ml-auto min-h-9 rounded-md border border-emerald-700 px-3 font-semibold text-emerald-700 hover:bg-emerald-50 disabled:opacity-60"
          >
            {saving ? "Saving" : "Accept"}
          </button>
        ))}
    </div>
  );
}
