/** Window event that tells the sidebar (components/Layout.tsx) to refetch projects. */
export const PROJECTS_CHANGED_EVENT = "leaf-ledger-projects-changed";

/**
 * Broadcast that projects/clients changed. A plain `Event` with no detail,
 * exactly as the copies in Arrangements.tsx, Library.tsx and the inline
 * dispatches in Clients.tsx.
 */
export function notifyProjectsChanged() {
  window.dispatchEvent(new Event(PROJECTS_CHANGED_EVENT));
}
