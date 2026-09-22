// Projects-list cache and arrangement shells.
import { readJsonCache, writeTimestampedJsonCache } from "utils/jsonCache";
import { PROJECTS_LIST_CACHE_KEY } from "../../constants";
import type { Arrangement, ArrangementSummary, ProjectsListCache } from "./types";

export function readProjectsListCache(): ProjectsListCache | null {
  const parsed = readJsonCache<ProjectsListCache | null>(PROJECTS_LIST_CACHE_KEY, null);
  if (!parsed || !Array.isArray(parsed.arrangements)) return null;
  return parsed;
}

export function writeProjectsListCache(arrangements: ArrangementSummary[]) {
  // localStorage is only a speed cache; failures should not block the app.
  writeTimestampedJsonCache(PROJECTS_LIST_CACHE_KEY, { arrangements });
}

export function formatProjectsCacheStamp(ms?: number | null) {
  if (!ms) return "";
  return new Date(ms).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
}

export function arrangementShellFromSummary(summary: ArrangementSummary): Arrangement {
  return {
    id: summary.id,
    name: summary.name,
    client_name: summary.client_name,
    notes: "",
    created_by: "",
    created_at: summary.created_at,
    updated_at: summary.updated_at,
    rooms: [],
    containers: [],
    total_cost: summary.total_cost || 0,
    total_with_markup: summary.total_cost || 0,
  };
}

export function arrangementRouteShell(id: number, clientName?: string): Arrangement {
  const now = new Date().toISOString();
  return {
    id,
    name: "Opening project...",
    client_name: clientName,
    notes: "",
    created_by: "",
    created_at: now,
    updated_at: now,
    rooms: [],
    containers: [],
    total_cost: 0,
    total_with_markup: 0,
  };
}
