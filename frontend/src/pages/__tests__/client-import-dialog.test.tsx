/**
 * The Clients import dialog (Comment #11): the template and example CSVs it
 * offers, the row status wording, and the first step's markup. The import
 * never shows how names will be composed (user, 2026-10-12): the example
 * table is just the template columns, starting with First name.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn(() => new Promise(() => undefined)) }));
vi.mock("sonner", () => ({ toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() } }));

import "../../test/setup";
import {
  ClientImportDialog, csvCell, statusLabel, templateCsv, type ImportTemplate,
} from "../clients/ClientImportDialog";

const HEADERS = ["First", "Last", "ADDRESS", "CITY", "ST", "ZIP", "Area", "Zone", "PHONE", "EMAIL"];
const row = (p: Record<string, string>) => HEADERS.map((h) => p[h] || "");
const TEMPLATE: ImportTemplate = {
  headers: HEADERS,
  example_rows: [
    row({ First: "Jamie", Last: "Rivera", ADDRESS: '12 "B" St, Unit 4', Area: "North", Zone: "The Woodlands" }),
    row({ First: "Dana", Last: "Lee", Area: "Central", Zone: "Heights/Near Northside" }),
    row({ First: "Marcus", Last: "Hale", Area: "West", Zone: "Katy/Fulshear" }),
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
    expect(lines[1]).toBe('Jamie,Rivera,"12 ""B"" St, Unit 4",,,,North,The Woodlands,,');
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
