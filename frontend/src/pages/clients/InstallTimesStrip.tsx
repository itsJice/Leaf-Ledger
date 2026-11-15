import { useEffect, useState } from "react";
import { Clock } from "components/icons";
import { apiFetch } from "utils/apiFetch";
import { diffLabel, fmtHours } from "utils/installTimes";

/**
 * The client card's "Install times" strip: each past season's real on-site
 * hours against the estimate at the time, from Install Times
 * (backend app/apis/install_actuals, GET /install-times/client/{id}). Office
 * staff only on the server; anyone else (or a client with nothing entered)
 * sees nothing here rather than an error.
 */

interface SeasonSummary {
  season: string;
  kind: "install" | "takedown";
  visits: number;
  actualHours: number | null;
  estHours: number | null;
}

export function InstallTimesStrip({ clientId }: { clientId: number }) {
  const [rows, setRows] = useState<SeasonSummary[] | null>(null);

  useEffect(() => {
    let live = true;
    apiFetch(`/api/install-times/client/${clientId}`)
      .then((r) => (r.ok ? r.json() : { summary: [] }))
      .then((d) => live && setRows(d.summary ?? []))
      .catch(() => live && setRows([]));
    return () => {
      live = false;
    };
  }, [clientId]);

  if (!rows || rows.length === 0) return null;
  return (
    <div className="mt-3 border-t border-stone-100 pt-3" data-testid="install-times-strip">
      <p className="mb-1 flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wide text-stone-400">
        <Clock size={11} /> Install times
      </p>
      <ul className="space-y-0.5 text-xs text-stone-700">
        {rows.map((r) => {
          const diff = diffLabel(r.estHours, r.actualHours);
          return (
            <li key={`${r.season}-${r.kind}`} className="flex flex-wrap items-baseline gap-x-2">
              <span className="w-24 shrink-0 font-semibold text-stone-800">
                {r.season} {r.kind === "takedown" ? "takedown" : "install"}
              </span>
              <span>
                {r.actualHours != null ? `${fmtHours(r.actualHours)} on site` : <span className="italic text-stone-400">not entered</span>}
              </span>
              <span className="text-stone-500">{r.estHours != null ? `est ${fmtHours(r.estHours)}` : "no estimate"}</span>
              {diff && (
                <span className={diff.tone === "over" ? "text-red-700" : diff.tone === "under" ? "text-emerald-700" : "text-stone-500"}>
                  {diff.text}
                </span>
              )}
              {r.visits > 1 && <span className="text-stone-400">({r.visits} visits)</span>}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
