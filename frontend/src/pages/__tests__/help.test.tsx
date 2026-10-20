/**
 * Help > How-to videos: the registry (data/howtoVideos.ts), the page's
 * cards, the player and the "Being updated" badge, plus the ways in (route,
 * sidebar, home tile).
 */
import fs from "node:fs";
import path from "node:path";
import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { matchRoutes } from "react-router-dom";

vi.mock("app", () => ({ apiClient: {}, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));

import "../../test/setup";
import { HOWTO_CATEGORIES, HOWTO_VIDEOS } from "../../data/howtoVideos";
import type { HowToVideo } from "../../data/howtoVideos";
import { HowToVideosView, VideoCard, VideoPlayer } from "../help/HowToVideosView";
import {
  HELP_PATH,
  categoriesWithVideos,
  filterVideos,
  formatDuration,
  formatUpdated,
  isHelpPath,
  registryProblems,
} from "utils/howto";
import type { CategoryFilter } from "utils/howto";
import { userRoutes } from "../../user-routes";
import { NAV_GROUPS } from "components/sidebarNav";
import { HOME_TILES, visibleTiles } from "utils/homeTiles";

const PUBLIC = path.resolve(__dirname, "../../../public");
const noop = () => undefined;

const video = (p: Partial<HowToVideo> = {}): HowToVideo => ({ ...HOWTO_VIDEOS[0], ...p });

function view(p: { videos?: HowToVideo[]; query?: string; category?: CategoryFilter; openId?: string | null } = {}) {
  return renderToStaticMarkup(
    <HowToVideosView
      videos={p.videos ?? HOWTO_VIDEOS}
      query={p.query ?? ""}
      category={p.category ?? "all"}
      openId={p.openId ?? null}
      onQuery={noop}
      onCategory={noop}
      onOpen={noop}
      onClose={noop}
    />,
  );
}

describe("the video registry", () => {
  it("has the right shape", () => {
    expect(registryProblems(HOWTO_VIDEOS)).toEqual([]);
    expect(HOWTO_VIDEOS.length).toBeGreaterThan(0);
  });

  it("points at files that exist in public/howto", () => {
    for (const v of HOWTO_VIDEOS) {
      for (const f of [v.file, v.poster]) {
        expect(fs.existsSync(path.join(PUBLIC, f)), f).toBe(true);
      }
      // Small enough to stream on a phone (and to keep in git).
      expect(fs.statSync(path.join(PUBLIC, v.file)).size).toBeLessThan(8 * 1024 * 1024);
    }
  });

  it("lists the first video as approved", () => {
    const v = HOWTO_VIDEOS.find((x) => x.id === "add-install-note")!;
    expect(v.title).toBe("Add an install note");
    expect(v.category).toBe("Install Schedule");
    expect(v.updatedAt).toBe("2026-10-19");
    expect(v.composition).toBe("HowToInstallNotes");
    expect(v.labels).toEqual(expect.arrayContaining(["Install notes 2026", "Pack list for today", "notes"]));
    expect(v.sourceFiles).toEqual(expect.arrayContaining(["frontend/src/pages/Shifts.tsx"]));
  });

  it("catches a bad entry", () => {
    const bad = video({ id: "Bad Id", file: "video.mp4", durationSec: 0, updatedAt: "10/19/2026", labels: [] });
    const problems = registryProblems([bad, HOWTO_VIDEOS[0], HOWTO_VIDEOS[0]]);
    expect(problems.join("\n")).toMatch(/kebab-case/);
    expect(problems.join("\n")).toMatch(/file must be/);
    expect(problems.join("\n")).toMatch(/durationSec/);
    expect(problems.join("\n")).toMatch(/updatedAt/);
    expect(problems.join("\n")).toMatch(/labels/);
    expect(problems.join("\n")).toMatch(/duplicate id/);
  });
});

describe("helpers", () => {
  it("formats length and date", () => {
    expect(formatDuration(55)).toBe("0:55");
    expect(formatDuration(75)).toBe("1:15");
    expect(formatUpdated("2026-10-19")).toBe("Oct 19, 2026");
  });

  it("searches and filters by category", () => {
    const other = video({ id: "other", title: "Move a client", description: "Drag it to a new day.", updatedAt: "2026-10-01" });
    const all = [other, HOWTO_VIDEOS[0]];
    expect(filterVideos(all, "", "all").map((v) => v.id)).toEqual(["add-install-note", "other"]);
    expect(filterVideos(all, "pack list", "all").map((v) => v.id)).toEqual(["add-install-note"]);
    expect(filterVideos(all, "MOVE", "Install Schedule").map((v) => v.id)).toEqual(["other"]);
    expect(filterVideos(all, "nothing like this", "all")).toEqual([]);
    expect(categoriesWithVideos(all)).toEqual(["Install Schedule"]);
    expect(HOWTO_CATEGORIES).toContain("Install Schedule");
  });
});

describe("the page", () => {
  it("renders a card per video with title, description, length, date, poster and category", () => {
    const html = view();
    const v = HOWTO_VIDEOS[0];
    expect(html).toContain(`data-video-card="${v.id}"`);
    expect(html).toContain("Add an install note");
    expect(html).toContain("Pack list on install morning");
    expect(html).toContain("0:55");
    expect(html).toContain("Last updated Oct 19, 2026");
    expect(html).toContain(`src="${v.poster}"`);
    expect(html).toContain("Install Schedule");
    // Search box and category filter.
    expect(html).toContain('type="search"');
    expect(html).toMatch(/aria-pressed="true"[^>]*>All</);
    // No player until a card is clicked.
    expect(html).not.toContain("<video");
  });

  it("shows the empty state when nothing matches", () => {
    const html = view({ query: "zzz" });
    expect(html).toContain("No videos match");
    expect(html).not.toContain("data-video-card");
  });

  it("opens the player with the native controls and the poster", () => {
    const v = HOWTO_VIDEOS[0];
    const html = view({ openId: v.id });
    expect(html).toContain(`data-video-player="${v.id}"`);
    expect(html).toContain('role="dialog"');
    const tag = /<video[^>]*>/.exec(html)![0];
    expect(tag).toContain(`src="${v.file}"`);
    expect(tag).toContain(`poster="${v.poster}"`);
    expect(tag).toContain('preload="metadata"');
    expect(tag).toContain("controls");
    expect(tag).toContain("playsinline");
    expect(html).toContain('aria-label="Close video"');
  });

  it("ignores an unknown ?v= id", () => {
    expect(view({ openId: "nope" })).not.toContain("<video");
  });

  it("badges a video that needs a remake, and it still plays", () => {
    const stale = video({ needsRemake: true });
    expect(renderToStaticMarkup(<VideoCard video={stale} onOpen={noop} />)).toContain("Being updated");
    expect(renderToStaticMarkup(<VideoCard video={video({ needsRemake: false })} onOpen={noop} />)).not.toContain("Being updated");
    const player = renderToStaticMarkup(<VideoPlayer video={stale} onClose={noop} />);
    expect(player).toContain("Being updated");
    expect(player).toContain(`src="${stale.file}"`);
  });
});

describe("ways in", () => {
  it("has a route", () => {
    expect(HELP_PATH).toBe("/help");
    expect(isHelpPath("/help")).toBe(true);
    expect(isHelpPath("/helpers")).toBe(false);
    const m = matchRoutes(userRoutes, "/help");
    expect(m?.[m.length - 1].route.path).toBe("/help");
  });

  it("is in the sidebar under Help", () => {
    const g = NAV_GROUPS.find((x) => x.id === "help")!;
    expect(g.label).toBe("Help");
    expect(g.items.map((i) => i.path)).toEqual(["/help"]);
    expect(g.items[0].adminOnly).toBeFalsy();
  });

  it("is a home tile for everyone", () => {
    const t = HOME_TILES.find((x) => x.path === "/help")!;
    expect(t.group).toBe("more");
    expect(t.adminOnly).toBeFalsy();
    expect(visibleTiles({ isAdmin: false, pages: null }).map((x) => x.id)).toContain(t.id);
    expect(visibleTiles({ isAdmin: false, pages: ["/search", "/help"] }).map((x) => x.id)).toContain(t.id);
  });
});
