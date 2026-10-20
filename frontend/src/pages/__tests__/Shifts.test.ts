import { describe, expect, it } from "vitest";
import { dayPackList, formatMinutes, nextStopRow, stopInstallNote, stopStatus } from "utils/shifts";

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

describe("install notes on the morning of", () => {
  const CORDS = "Install requires (8) longer extension cords. Please pack in Kit";
  const s = (row: number, x: Partial<ReturnType<typeof stop>> & { installNote?: string; installNotes?: string }) => ({ ...stop(row), ...x });

  it("uses the card's install notes first, then the spreadsheet's", () => {
    expect(stopInstallNote(s(1, { installNote: CORDS, advice: "old" }))).toBe(CORDS);
    expect(stopInstallNote(s(1, { installNotes: " card ", advice: "old" }))).toBe("card");
    expect(stopInstallNote(s(1, { advice: "sheet note" }))).toBe("sheet note");
    expect(stopInstallNote(s(1, {}))).toBe("");
  });

  it("builds the pack list from the server's, else from the stops in route order", () => {
    const d = day([s(2, { advice: "Side gate" }), s(1, {}), s(3, { installNote: CORDS })]);
    expect(dayPackList(d)).toEqual([
      { row: 2, name: "Stop 2", text: "Side gate" },
      { row: 3, name: "Stop 3", text: CORDS },
    ]);
    expect(dayPackList({ ...d, packList: [{ row: 9, name: "Doe, Jane", text: CORDS }, { row: 4, name: "x", text: " " }] }))
      .toEqual([{ row: 9, name: "Doe, Jane", text: CORDS }]);
    expect(dayPackList(day([s(1, {})]))).toEqual([]);
  });
});
