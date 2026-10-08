/**
 * The client dialog types a name as parts -- First name, Last name, Business
 * name, Location, whichever apply -- and shows the one display name they
 * make. The composing rules must match backend/app/libs/client_names.py.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import "../../test/setup";
import {
  ClientNameFields, composeClientName, initialNameParts, namePartsBody, namePartsProblem,
  type NameParts,
} from "../clients/ClientNameFields";

const parts = (p: Partial<NameParts>): NameParts =>
  ({ first_name: "", last_name: "", company: "", site: "", ...p });

describe("composeClientName", () => {
  it.each([
    [{ first_name: "Nataliya", last_name: "Scheib" }, "Scheib, Nataliya"],
    [{ first_name: "  Nataliya ", last_name: " Scheib  " }, "Scheib, Nataliya"],
    [{ last_name: "Hellums" }, "Hellums"],
    [{ first_name: "Kerri", last_name: "Byler", site: "House" }, "Byler, Kerri - House"],
    [{ company: "Hilton Garden Inn" }, "Hilton Garden Inn"],
    [{ company: "The Club at Carlton Woods", site: "Nicklaus Clubhouse" }, "The Club at Carlton Woods | Nicklaus Clubhouse"],
    [{ company: "A Hug Away", site: "Daycare" }, "A Hug Away | Daycare"],
    [{ company: "Capital Bank - Baytown" }, "Capital Bank - Baytown"],
    [{ company: "A Hug Away", first_name: "Marissa", last_name: "Frazier" }, "A Hug Away | Frazier, Marissa"],
    [{ company: "A Hug Away", first_name: "Marissa", last_name: "Frazier", site: "Residence" }, "A Hug Away | Frazier, Marissa - Residence"],
    [{ site: "Daycare" }, ""],
  ] as [Partial<NameParts>, string][])("%o -> %s", (p, expected) => {
    expect(composeClientName(parts(p))).toBe(expected);
  });
});

describe("initialNameParts", () => {
  it("starts a new client empty", () => {
    expect(initialNameParts(null)).toEqual(parts({}));
  });
  it("uses the parts the server sends", () => {
    expect(initialNameParts({ name: "Byler, Kerri - House", first_name: "Kerri", last_name: "Byler", site: "House" }))
      .toEqual(parts({ first_name: "Kerri", last_name: "Byler", site: "House" }));
  });
  it("falls back to the whole name as the business name when there are no parts", () => {
    expect(initialNameParts({ name: "Capital Bank - Baytown" })).toEqual(parts({ company: "Capital Bank - Baytown" }));
  });
});

describe("validation and request body", () => {
  it("needs a person's name or a business name", () => {
    expect(namePartsProblem(parts({ site: "House" }))).toMatch(/business name/);
    expect(namePartsProblem(parts({ first_name: "A, B" }))).toMatch(/comma/);
    expect(namePartsProblem(parts({ company: "A | B" }))).toMatch(/\|/);
    expect(namePartsProblem(parts({ first_name: "Nataliya", last_name: "Scheib" }))).toBeNull();
    expect(namePartsProblem(parts({ company: "A Hug Away" }))).toBeNull();
  });
  it("sends all four boxes, trimmed", () => {
    expect(namePartsBody(parts({ first_name: " Kerri ", last_name: "Byler", site: " House " })))
      .toEqual({ first_name: "Kerri", last_name: "Byler", company: "", site: "House" });
  });
});

describe("ClientNameFields", () => {
  const render = (value: NameParts, currentName?: string) =>
    renderToStaticMarkup(<ClientNameFields value={value} onChange={() => undefined} currentName={currentName} />);

  it("always offers First name, Last name, Business name and Location, with no type switch", () => {
    const html = render(parts({ first_name: "Kerri", last_name: "Byler", site: "House" }));
    for (const label of ["First name", "Last name", "Business name", "Location"]) expect(html).toContain(label);
    expect(html).not.toContain('role="radio"');
    expect(html).toContain("Shows as: <span");
    expect(html).toContain("Byler, Kerri - House");
  });

  it("uses 16px text and 40px-tall boxes (no iPhone zoom, easy taps)", () => {
    const inputs = render(parts({})).match(/<input[^>]*>/g) || [];
    expect(inputs).toHaveLength(4);
    inputs.forEach((i) => { expect(i).toContain("text-base"); expect(i).toContain("h-10"); });
  });

  it("warns when a save will rename the client everywhere", () => {
    expect(render(parts({ first_name: "Natalia", last_name: "Scheib" }), "Scheib, Nataliya")).toContain("Renames");
    expect(render(parts({ first_name: "Nataliya", last_name: "Scheib" }), "Scheib, Nataliya")).not.toContain("Renames");
  });
});
