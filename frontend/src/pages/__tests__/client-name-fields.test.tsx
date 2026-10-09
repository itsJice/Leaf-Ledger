/**
 * The client dialog types a name as parts -- First name, Last name, Business
 * name, Location, whichever apply -- and shows the one display name they
 * make. The composing rules must match backend/app/libs/client_names.py.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import "../../test/setup";
import {
  ClientNameFields, composeClientName, contactPersonName, duplicateNameMessage, initialNameParts,
  namePartsBody, namePartsProblem, type NameParts,
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
    [{ company: "The Club at Carlton Woods", site: "Nicklaus Clubhouse" }, "The Club at Carlton Woods - Nicklaus Clubhouse"],
    [{ company: "A Hug Away", site: "Daycare" }, "A Hug Away - Daycare"],
    [{ company: "Capital Bank - Baytown" }, "Capital Bank - Baytown"],
    // businesses go by their business name; the person is the contact
    [{ company: "A Hug Away", first_name: "Marissa", last_name: "Frazier" }, "A Hug Away"],
    [{ company: "Serenity Retreat", first_name: "Tiffany", last_name: "Pardue" }, "Serenity Retreat"],
    [{ company: "A Hug Away", first_name: "Marissa", last_name: "Frazier", site: "Residence" }, "A Hug Away - Residence"],
    [{ company: " A  Hug Away ", last_name: "Frazier", site: " Office " }, "A Hug Away - Office"],
    [{ site: "Daycare" }, ""],
  ] as [Partial<NameParts>, string][])("%o -> %s", (p, expected) => {
    expect(composeClientName(parts(p))).toBe(expected);
  });
});

describe("contactPersonName", () => {
  it("names the contact person only when a business is set", () => {
    expect(contactPersonName(parts({ company: "Serenity Retreat", first_name: "Tiffany", last_name: "Pardue" }))).toBe("Tiffany Pardue");
    expect(contactPersonName(parts({ company: "A Hug Away", first_name: " Takisha " }))).toBe("Takisha");
    expect(contactPersonName(parts({ company: "A Hug Away" }))).toBe("");
    expect(contactPersonName(parts({ first_name: "Kerri", last_name: "Byler" }))).toBe("");
  });
});

describe("duplicateNameMessage", () => {
  it("tells two cards for one business to add a Location", () => {
    const msg = duplicateNameMessage(parts({ company: "A Hug Away", first_name: "Takisha" }));
    expect(msg).toContain("“A Hug Away”");
    expect(msg).toContain("add a Location");
  });
  it("keeps the plain message for people and unknown parts", () => {
    expect(duplicateNameMessage(parts({ first_name: "Kerri", last_name: "Byler" }))).toMatch(/already has that name/);
    expect(duplicateNameMessage(null)).toMatch(/already has that name/);
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
  it("loads an old \"Business | Last, First\" card's parts into the right boxes", () => {
    const p = initialNameParts({ name: "A Hug Away | Frazier, Marissa", first_name: "Marissa", last_name: "Frazier", company: "A Hug Away" });
    expect(p).toEqual(parts({ first_name: "Marissa", last_name: "Frazier", company: "A Hug Away" }));
    expect(composeClientName(p)).toBe("A Hug Away");
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

  it("shows a business by its business name, with the person as the contact", () => {
    const html = render(parts({ first_name: "Tiffany", last_name: "Pardue", company: "Serenity Retreat" }));
    expect(html).toMatch(/Shows as: <span[^>]*>Serenity Retreat<\/span>/);
    expect(html).toContain("Contact person:");
    expect(html).toContain("Tiffany Pardue");
    expect(html).not.toContain("Pardue, Tiffany");
  });

  it("adds the location with a dash", () => {
    const html = render(parts({ company: "The Club at Carlton Woods", site: "Nicklaus Clubhouse" }));
    expect(html).toContain("The Club at Carlton Woods - Nicklaus Clubhouse");
    expect(html).not.toContain("Contact person");
  });

  it("no contact line for a person on their own", () => {
    expect(render(parts({ first_name: "Kerri", last_name: "Byler" }))).not.toContain("Contact person");
  });

  it("warns that an old \"Business | Last, First\" name will be renamed", () => {
    const html = render(parts({ first_name: "Marissa", last_name: "Frazier", company: "A Hug Away" }), "A Hug Away | Frazier, Marissa");
    expect(html).toContain("Renames");
  });

  it("warns when a save will rename the client everywhere", () => {
    expect(render(parts({ first_name: "Natalia", last_name: "Scheib" }), "Scheib, Nataliya")).toContain("Renames");
    expect(render(parts({ first_name: "Nataliya", last_name: "Scheib" }), "Scheib, Nataliya")).not.toContain("Renames");
  });
});
