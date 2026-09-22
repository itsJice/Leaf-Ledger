import { describe, expect, it } from "vitest";
import { formatMinutes, nextStopRow, stopStatus } from "utils/shifts";

const entry = (row: number, endedAt: string | null) => ({
  id: row * 10 + (endedAt ? 1 : 0),
  row,
  personId: "p1",
  personName: "Ana",
  startedAt: "2026-11-14T15:00:00Z",
  endedAt,
});
const stop = (row: number, entries: ReturnType<typeof entry>[] = []) => ({
  row, name: `Stop ${row}`, street: "", city: "", st: "", zip: "", phone: "", mapsUrl: "",
  advice: "", repairNotes: "", hours: null, timeEntries: entries, notes: [],
});
const day = (stops: ReturnType<typeof stop>[]) => ({
  id: "2026-11-14|Crew 1|0", date: "2026-11-14", crewLabel: "Crew 1", note: "", lead: null, crew: [], stops,
});

describe("lead shift helpers", () => {
  it("reads a stop's status from its clocks", () => {
    expect(stopStatus(stop(1))).toBe("todo");
    expect(stopStatus(stop(1, [entry(1, null)]))).toBe("active");
    expect(stopStatus(stop(1, [entry(1, "2026-11-14T16:00:00Z")]))).toBe("done");
  });

  it("points at the stop the crew is at, else the first not started", () => {
    const finished = stop(1, [entry(1, "2026-11-14T16:00:00Z")]);
    expect(nextStopRow(day([finished, stop(2), stop(3)]))).toBe(2);
    expect(nextStopRow(day([finished, stop(2), stop(3, [entry(3, null)])]))).toBe(3);
    expect(nextStopRow(day([finished]))).toBeNull();
  });

  it("formats minutes as hours and minutes", () => {
    expect(formatMinutes(7)).toBe("7m");
    expect(formatMinutes(125.4)).toBe("2h 05m");
  });
});
