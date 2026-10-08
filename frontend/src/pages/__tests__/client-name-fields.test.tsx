/**
 * The client dialog types a name as parts -- Person (first + last) or
 * Business (company + optional site) -- and shows the one display name they
 * make. The composing rules must match backend/app/libs/client_names.py.
 */
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import "../../test/setup";
import {
  ClientNameFields, composeClientName, initialNameParts, namePartsBody, namePartsProblem,
  type NameParts,
} from "../clients/ClientNameFields";

const person = (first: string, last: string): NameParts =>
  ({ client_type: "person", first_name: first, last_name: last, company: "", site: "" });
const business = (company: string, site = ""): NameParts =>
  ({ client_type: "business", first_name: "", last_name: "", company, site });

describe("composeClientName", () => {
  it("writes a person as Last, First", () => {
    expect(composeClientName(person("Nataliya", "Scheib"))).toBe("Scheib, Nataliya");
    expect(composeClientName(person("  Nataliya ", " Scheib  "))).toBe("Scheib, Nataliya");
    expect(composeClientName(person("", "Hellums"))).toBe("Hellums");
  });
  it("writes a business as Company | Site, or just Company", () => {
    expect(composeClientName(business("The Club at Carlton Woods", "Nicklaus Clubhouse")))
      .toBe("The Club at Carlton Woods | Nicklaus Clubhouse");
    expect(composeClientName(business("A Hug Away", "Daycare"))).toBe("A Hug Away | Daycare");
    expect(composeClientName(business("Capital Bank - Baytown"))).toBe("Capital Bank - Baytown");
  });
});

describe("initialNameParts", () => {
  it("starts a new client as an empty person", () => {
    expect(initialNameParts(null)).toEqual(person("", ""));
  });
  it("uses the parts the server sends", () => {
    expect(initialNameParts({ name: "Scheib, Nataliya", client_type: "person", first_name: "Nataliya", last_name: "Scheib" }))
      .toEqual(person("Nataliya", "Scheib"));
    expect(initialNameParts({ name: "A Hug Away | Daycare", client_type: "business", company: "A Hug Away", site: "Daycare" }))
      .toEqual(business("A Hug Away", "Daycare"));
  });
  it("falls back to the whole name as a company when there are no parts", () => {
    expect(initialNameParts({ name: "Capital Bank - Baytown" })).toEqual(business("Capital Bank - Baytown"));
  });
});

describe("validation and request body", () => {
  it("needs a name for a person and a company for a business", () => {
    expect(namePartsProblem(person("", " "))).toMatch(/first or last/);
    expect(namePartsProblem(person("A, B", "C"))).toMatch(/comma/);
    expect(namePartsProblem(business("", "Daycare"))).toMatch(/company/);
    expect(namePartsProblem(business("A | B"))).toMatch(/\|/);
    expect(namePartsProblem(person("Nataliya", "Scheib"))).toBeNull();
  });
  it("sends only the type's own fields", () => {
    expect(namePartsBody({ ...person("Nataliya", "Scheib"), company: "stale" }))
      .toEqual({ client_type: "person", first_name: "Nataliya", last_name: "Scheib", company: "", site: "" });
    expect(namePartsBody({ ...business("A Hug Away", " Daycare "), first_name: "stale" }))
      .toEqual({ client_type: "business", first_name: "", last_name: "", company: "A Hug Away", site: "Daycare" });
  });
});

describe("ClientNameFields", () => {
  const render = (value: NameParts, currentName?: string) =>
    renderToStaticMarkup(<ClientNameFields value={value} onChange={() => undefined} currentName={currentName} />);

  it("shows First and Last name boxes and the live preview for a person", () => {
    const html = render(person("Nataliya", "Scheib"));
    expect(html).toContain("First name");
    expect(html).toContain("Last name");
    expect(html).not.toContain("Company");
    expect(html).toContain("Shows as: <span");
    expect(html).toContain("Scheib, Nataliya");
    expect(html).toMatch(/role="radio" aria-checked="true"[^>]*>.*Person/);
  });

  it("shows Company and an optional site for a business", () => {
    const html = render(business("The Club at Carlton Woods", "Nicklaus Clubhouse"));
    expect(html).toContain("Company");
    expect(html).toContain("Location / site");
    expect(html).not.toContain("First name");
    expect(html).toContain("The Club at Carlton Woods | Nicklaus Clubhouse");
  });

  it("uses 16px text and 40px-tall controls (no iPhone zoom, easy taps)", () => {
    const html = render(person("", ""));
    const inputs = html.match(/<input[^>]*>/g) || [];
    expect(inputs).toHaveLength(2);
    inputs.forEach((i) => { expect(i).toContain("text-base"); expect(i).toContain("h-10"); });
    const radios = html.match(/<button[^>]*role="radio"[^>]*>/g) || [];
    expect(radios).toHaveLength(2);
    radios.forEach((b) => expect(b).toContain("h-10"));
  });

  it("warns when a save will rename the client everywhere", () => {
    expect(render(person("Natalia", "Scheib"), "Scheib, Nataliya")).toContain("Renames");
    expect(render(person("Nataliya", "Scheib"), "Scheib, Nataliya")).not.toContain("Renames");
  });
});
