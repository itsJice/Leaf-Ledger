import { Link } from "react-router-dom";
import { Users } from "components/icons";
import { currentMe } from "utils/me";
import { TEAMS_PATH, canEditTeams } from "utils/installViews";

/**
 * "Teams" on every install page that isn't the schedule itself (Crew Shifts,
 * Install Changes, Install & Takedown Profit): opens the Install Roster with
 * the drag-and-drop Teams builder already open. Hidden for leads, crew and
 * view-only logins, who can't edit teams.
 */
export function TeamsButton({ className = "" }: { className?: string }) {
  if (!canEditTeams(currentMe())) return null;
  return (
    <Link
      to={TEAMS_PATH}
      title="Build and edit teams (drag and drop)"
      className={`inline-flex min-h-10 flex-none items-center gap-1.5 rounded-lg border border-stone-300 bg-white px-3 text-xs font-semibold text-stone-700 hover:border-emerald-600 hover:text-emerald-800 sm:min-h-9 ${className}`}
    >
      <Users size={14} /> Teams
    </Link>
  );
}

export default TeamsButton;
