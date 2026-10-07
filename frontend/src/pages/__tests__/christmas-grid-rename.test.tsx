/**
 * The Christmas grid shows a client's name split into Client + Site. Those two
 * cells are how a name is changed from the grid: they open the Clients page's
 * Edit client dialog (the one rename path, which renames the client
 * everywhere). Without the callback they stay plain text.
 */
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));

import "../../test/setup";
import { ChristmasGridView, splitName } from "../ChristmasGrid";
import { currentSeasonLabel } from "utils/season";

const season = currentSeasonLabel();
const clients = [{
  id: 7,
  name: "Byler, Kerri | Store",
  activity: [{ id: 1, kind: "christmas_install", season, summary: "", detail: { install_date: `${season}-11-13` }, occurred_at: null, created_at: null }],
}] as unknown as Parameters<typeof ChristmasGridView>[0]["clients"];

describe("Christmas grid name cells", () => {
  it("offer a rename when the page passes onEditName", () => {
    const html = renderToStaticMarkup(
      <ChristmasGridView clients={clients} loading={false} onSaved={() => undefined} onEditName={() => undefined} />,
    );
    const offers = html.match(/title="Byler, Kerri \| Store: click to edit or rename this client"/g) || [];
    expect(offers).toHaveLength(2); // Client and Site
    expect(splitName("Byler, Kerri | Store")).toEqual(["Byler, Kerri", "Store"]);
  });

  it("stay plain text without it", () => {
    const html = renderToStaticMarkup(<ChristmasGridView clients={clients} loading={false} onSaved={() => undefined} />);
    expect(html).not.toContain("click to edit or rename");
    expect(html).toContain("Byler, Kerri");
  });
});
