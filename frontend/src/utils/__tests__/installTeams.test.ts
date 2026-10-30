import { describe, expect, it } from "vitest";
import { TEAMS_PATH, canEditTeams, teamsFromSearch, viewForPath } from "utils/installViews";

// The Teams button on every install page opens the Roster with the Teams
// builder open (user, 2026-10-30).
describe("Teams button link", () => {
  it("goes to the Roster view with ?teams=1", () => {
    const [path, search] = TEAMS_PATH.split("?");
    expect(viewForPath(path)).toBe("roster");
    expect(teamsFromSearch(`?${search}`)).toBe(true);
  });

  it("only opens the builder when asked", () => {
    expect(teamsFromSearch("")).toBe(false);
    expect(teamsFromSearch("?teams=0")).toBe(false);
    expect(teamsFromSearch("?date=2026-11-02&teams=true")).toBe(true);
  });

  it("shows for staff and up, never for leads, crew or view-only logins", () => {
    expect(canEditTeams({ role: "super_admin" })).toBe(true);
    expect(canEditTeams({ role: "admin" })).toBe(true);
    expect(canEditTeams({ role: "staff" })).toBe(true);
    for (const role of ["lead", "crew", "viewer", "production"]) expect(canEditTeams({ role })).toBe(false);
    expect(canEditTeams({ role: "admin", viewOnly: true })).toBe(false);
    expect(canEditTeams(null)).toBe(false);
  });
});
