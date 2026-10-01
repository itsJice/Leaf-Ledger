import { describe, expect, it } from "vitest";
import {
  carryOver, countBy, filterResponses, fmtDate, isUrl, REQUIRED_MESSAGE, shortOption, validateAnswers,
  EMPTY_FILTER, type FormQuestion, type FormResponse,
} from "../forms";

const q = (key: string, section_id: number, required: boolean, type: FormQuestion["type"] = "short_text",
  options: string[] | null = null): FormQuestion => ({
  id: 0, section_id, position: 0, key, label: key, helper_text: null, type, required, options, export_position: null,
});
const QS = [
  q("requestor", 1, true, "dropdown", ["Reyna", "Laura"]), q("client_name", 1, true), q("project_name", 1, true),
  q("location_item", 1, true, "long_text"), q("preferred_vendor", 2, false), q("install_date", 2, true, "date"),
  q("samples_pictures", 2, true, "checkboxes", ["A", "B"]),
];

describe("validateAnswers", () => {
  it("checks only the current section on Next", () => {
    const a = { requestor: "Reyna", client_name: "  ", project_name: "Ballroom", location_item: "Mantel" };
    expect(validateAnswers(QS, a, 1)).toEqual({ client_name: REQUIRED_MESSAGE });
    expect(validateAnswers(QS, a, 2)).toEqual({ install_date: REQUIRED_MESSAGE, samples_pictures: REQUIRED_MESSAGE });
  });
  it("lets optional fields stay blank and needs a real date and a checkbox pick", () => {
    const a = { requestor: "Reyna", client_name: "Sims, Darcy", project_name: "Home", location_item: "Trees",
      install_date: "2026-11-30", samples_pictures: ["A"] };
    expect(validateAnswers(QS, a)).toEqual({});
    expect(validateAnswers(QS, { ...a, samples_pictures: [] })).toEqual({ samples_pictures: REQUIRED_MESSAGE });
    expect(validateAnswers(QS, { ...a, install_date: "soon" })).toEqual({ install_date: "Enter a date" });
  });
});

describe("submit another for the same project", () => {
  it("keeps requestor, client, project and location, drops the item details", () => {
    expect(carryOver({ requestor: "Laura", client_name: "The Woodlands", project_name: "Ballroom Foyer",
      location_item: "Mantel", product_description: "garland", samples_pictures: ["A"] }))
      .toEqual({ requestor: "Laura", client_name: "The Woodlands", project_name: "Ballroom Foyer", location_item: "Mantel" });
  });
});

const r = (id: number, answers: FormResponse["answers"], status: FormResponse["status"] = "New"): FormResponse => ({
  id, submitted_at: "2026-09-14T00:00:00Z", status, buyer_notes: null, submitted_by: null, source: "app",
  updated_at: null, updated_by: null, answers,
});

describe("summary and filters", () => {
  const rs = [
    r(1, { client_name: "Sims, Darcy", samples_pictures: ["A", "B"], install_date: "2026-09-18", preferred_vendor: "Vickerman" }),
    r(2, { client_name: "sims, darcy", samples_pictures: ["A"], install_date: "2026-11-30", preferred_vendor: "vickerman" }, "Ordered"),
    r(3, { client_name: "The Woodlands", samples_pictures: ["B"], install_date: "2026-11-30", preferred_vendor: "Home Depot" }),
  ];
  it("counts checkbox picks separately and groups free-text spellings", () => {
    expect(countBy(rs, q("samples_pictures", 2, true, "checkboxes", ["A", "B"]))).toEqual([
      { value: "A", count: 2 }, { value: "B", count: 2 }]);
    expect(countBy(rs, q("preferred_vendor", 2, false))[0]).toEqual({ value: "Vickerman", count: 2 });
  });
  it("filters by client (any spelling), status, install date range and text", () => {
    expect(filterResponses(rs, { ...EMPTY_FILTER, client: "SIMS, DARCY" }).map((x) => x.id)).toEqual([1, 2]);
    expect(filterResponses(rs, { ...EMPTY_FILTER, status: "Ordered" }).map((x) => x.id)).toEqual([2]);
    expect(filterResponses(rs, { ...EMPTY_FILTER, from: "2026-11-01" }).map((x) => x.id)).toEqual([2, 3]);
    expect(filterResponses(rs, { ...EMPTY_FILTER, text: "home depot" }).map((x) => x.id)).toEqual([3]);
  });
});

describe("display helpers", () => {
  it("formats dates like the sheet and spots links", () => {
    expect(fmtDate("2026-11-30")).toBe("11/30/2026");
    expect(isUrl("https://www.vickerman.com/p/g1255g?opt=9%27")).toBe(true);
    expect(isUrl("p. 42")).toBe(false);
    expect(shortOption("Yes, need more of the EXACT same product. Sí, necesitamos más.")).toBe("Yes, need more of the EXACT same product.");
  });
});
