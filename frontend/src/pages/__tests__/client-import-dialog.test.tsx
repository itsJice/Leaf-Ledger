/**
 * The Clients import dialog (Comment #11): the template and example CSVs it
 * offers, the "Shows as" names for the example rows (same rule as the New
 * Client form), the row status wording, and the first step's markup.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn(() => new Promise(() => undefined)) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import "../../test/setup";
import {
  ClientImportDialog, csvCell, exampleShowsAs, statusLabel, templateCsv, type ImportTemplate,
} from "../clients/ClientImportDialog";

const HEADERS = [
  "First name", "Last name", "Business name", "Location", "Email", "Phone", "Street address", "City",
  "State", "ZIP", "Install time preference", "Additional contact label", "Additional contact phone",
  "Additional contact email", "General notes",
];
const row = (p: Record<string, string>) => HEADERS.map((h) => p[h] || "");
const TEMPLATE: ImportTemplate = {
  headers: HEADERS,
  example_rows: [
    row({ "First name": "Jamie", "Last name": "Rivera", "General notes": 'Gate "B", side door' }),
    row({ "First name": "Dana", "Last name": "Lee", "Business name": "Pine Hollow Dental" }),
    row({ "Business name": "Lakeside Country Club", Location: "North Clubhouse" }),
  ],
  odoo_aliases: [["Street2", "added to Street address"]],
  max_rows: 2000,
};

describe("template CSVs", () => {
  it("quotes only cells that need it", () => {
    expect(csvCell("plain")).toBe("plain");
    expect(csvCell("a, b")).toBe('"a, b"');
    expect(csvCell('say "hi"')).toBe('"say ""hi"""');
    expect(csvCell("two\nlines")).toBe('"two\nlines"');
  });

  it("the template is the headers only, with a BOM for Excel", () => {
    expect(templateCsv(TEMPLATE, false)).toBe("\ufeff" + HEADERS.join(",") + "\r\n");
  });

  it("the example adds the three example rows", () => {
    const lines = templateCsv(TEMPLATE, true).replace(/^\ufeff/, "").trimEnd().split("\r\n");
    expect(lines).toHaveLength(4);
    expect(lines[1].startsWith("Jamie,Rivera,,,")).toBe(true);
    expect(lines[1].endsWith(',"Gate ""B"", side door"')).toBe(true);
  });
});

describe("example rows show as", () => {
  it("a person, a business (contact not in the name) and a business with a location", () => {
    expect(TEMPLATE.example_rows.map((r) => exampleShowsAs(TEMPLATE, r))).toEqual([
      "Rivera, Jamie", "Pine Hollow Dental", "Lakeside Country Club | North Clubhouse",
    ]);
  });
});

describe("statusLabel", () => {
  it("reads the same words the preview promises", () => {
    expect(statusLabel({ status: "create", message: null })).toBe("Will create");
    expect(statusLabel({ status: "duplicate", message: "x" })).toBe("Duplicate (skip)");
    expect(statusLabel({ status: "error", message: "phone looks wrong" })).toBe("Error: phone looks wrong");
    expect(statusLabel({ status: "create", message: null }, true)).toBe("Created");
    expect(statusLabel({ status: "duplicate", message: null }, true)).toBe("Duplicate (skipped)");
  });
  it("no em dashes in what the user reads", () => {
    for (const s of ["create", "duplicate", "error"] as const) {
      expect(statusLabel({ status: s, message: "m" })).not.toContain("—");
    }
  });
});

describe("the dialog's first step", () => {
  it("offers both downloads and a file picker for CSV or Excel", () => {
    const html = renderToStaticMarkup(<ClientImportDialog onClose={() => undefined} onImported={() => undefined} />);
    expect(html).toContain("Import clients");
    expect(html).toContain("Download template");
    expect(html).toContain("Download example");
    expect(html).toContain('accept=".csv,.xlsx');
    expect(html).toContain("Nothing is saved until you confirm");
    expect(html).not.toContain("—");
  });
});
