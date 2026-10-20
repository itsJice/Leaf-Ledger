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
  parseYouTubeId,
  posterOf,
  registryProblems,
  youtubeEmbedUrl,
  youtubeIdOf,
  youtubeThumbnailUrl,
} from "utils/howto";
import type { CategoryFilter } from "utils/howto";
import { userRoutes } from "../../user-routes";
import { NAV_GROUPS } from "components/sidebarNav";
import { HOME_TILES, visibleTiles } from "utils/homeTiles";

const PUBLIC = path.resolve(__dirname, "../../../public");
const noop = () => undefined;

const video = (p: Partial<HowToVideo> = {}): HowToVideo => ({ ...HOWTO_VIDEOS[0], ...p });

const YT = "dQw4w9WgXcQ";
/** A local-file entry: the fallback path for videos not on YouTube. */
const LOCAL = { youtubeId: "", file: "/howto/sample-v1.mp4", poster: "/howto/sample-v1.jpg" };
const localVideo = (p: Partial<HowToVideo> = {}): HowToVideo => video({ id: "local", ...LOCAL, ...p });
const ytVideo = (p: Partial<HowToVideo> = {}): HowToVideo =>
  video({ id: "on-youtube", youtubeId: YT, file: undefined, poster: undefined, ...p });

function view(
  p: { videos?: HowToVideo[]; query?: string; category?: CategoryFilter; openId?: string | null; autoplay?: boolean } = {},
) {
  return renderToStaticMarkup(
    <HowToVideosView
      videos={p.videos ?? HOWTO_VIDEOS}
      query={p.query ?? ""}
      category={p.category ?? "all"}
      openId={p.openId ?? null}
      autoplay={p.autoplay}
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
        if (f) expect(fs.existsSync(path.join(PUBLIC, f)), f).toBe(true);
      }
      // Small enough to stream on a phone (and to keep in git).
      if (v.file) expect(fs.statSync(path.join(PUBLIC, v.file)).size).toBeLessThan(8 * 1024 * 1024);
    }
  });

  it("lists the first video as approved, on YouTube", () => {
    const v = HOWTO_VIDEOS.find((x) => x.id === "add-install-note")!;
    expect(v.title).toBe("Add an install note");
    expect(youtubeIdOf(v)).toBe("hmeqv11SMYg");
    expect(parseYouTubeId("https://youtu.be/hmeqv11SMYg")).toBe(v.youtubeId);
    // Its local copy is gone; the card uses the YouTube thumbnail.
    expect(v.file).toBeUndefined();
    expect(v.poster).toBeUndefined();
    expect(posterOf(v)).toBe("https://i.ytimg.com/vi/hmeqv11SMYg/hqdefault.jpg");
    expect(fs.existsSync(path.join(PUBLIC, "howto/add-install-note-v2.mp4"))).toBe(false);
    expect(v.category).toBe("Install Schedule");
    expect(v.updatedAt).toBe("2026-10-19");
    expect(v.composition).toBe("HowToInstallNotes");
    expect(v.labels).toEqual(expect.arrayContaining(["Install notes 2026", "Pack list for today", "notes"]));
    expect(v.sourceFiles).toEqual(expect.arrayContaining(["frontend/src/pages/Shifts.tsx"]));
  });

  it("catches a bad entry", () => {
    const bad = localVideo({ id: "Bad Id", file: "video.mp4", durationSec: 0, updatedAt: "10/19/2026", labels: [] });
    const problems = registryProblems([bad, localVideo(), localVideo()]);
    expect(problems.join("\n")).toMatch(/kebab-case/);
    expect(problems.join("\n")).toMatch(/file must be/);
    expect(problems.join("\n")).toMatch(/durationSec/);
    expect(problems.join("\n")).toMatch(/updatedAt/);
    expect(problems.join("\n")).toMatch(/labels/);
    expect(problems.join("\n")).toMatch(/duplicate id/);
  });

  it("accepts a YouTube-only entry and catches a bad id or a missing source", () => {
    expect(registryProblems([ytVideo()])).toEqual([]);
    expect(registryProblems([localVideo()])).toEqual([]);
    expect(registryProblems([ytVideo({ poster: "/howto/custom.jpg" })])).toEqual([]);
    expect(registryProblems([ytVideo({ youtubeId: "https://youtu.be/dQw4w9WgXcQ" })]).join("\n")).toMatch(/youtubeId must be/);
    const none = registryProblems([video({ youtubeId: "", file: undefined, poster: undefined })]).join("\n");
    expect(none).toMatch(/needs a youtubeId or a file/);
    expect(none).toMatch(/needs a poster/);
  });
});

describe("YouTube links", () => {
  it.each([
    ["https://youtu.be/dQw4w9WgXcQ", YT],
    ["https://youtu.be/dQw4w9WgXcQ?si=AbC123xyz", YT],
    ["youtu.be/dQw4w9WgXcQ", YT],
    ["https://www.youtube.com/watch?v=dQw4w9WgXcQ", YT],
    ["https://youtube.com/watch?feature=share&v=dQw4w9WgXcQ&t=30s", YT],
    ["https://m.youtube.com/watch?v=dQw4w9WgXcQ", YT],
    ["www.youtube.com/watch?v=dQw4w9WgXcQ", YT],
    ["https://www.youtube.com/shorts/dQw4w9WgXcQ", YT],
    ["https://youtube.com/shorts/dQw4w9WgXcQ?feature=share", YT],
    ["https://www.youtube.com/embed/dQw4w9WgXcQ?rel=0", YT],
    ["https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", YT],
    ["https://www.youtube.com/live/dQw4w9WgXcQ", YT],
    ["  dQw4w9WgXcQ  ", YT],
    ["https://youtu.be/a_b-C1d2E3f", "a_b-C1d2E3f"],
  ])("reads %s", (link, id) => {
    expect(parseYouTubeId(link)).toBe(id);
  });

  it.each([
    "",
    "   ",
    "not a link",
    "https://example.com/watch?v=dQw4w9WgXcQ",
    "https://youtube.com/watch",
    "https://www.youtube.com/watch?v=short",
    "https://www.youtube.com/channel/UC1234567890",
    "https://youtu.be/",
    "https://evilyoutube.com/watch?v=dQw4w9WgXcQ",
  ])("rejects %j", (link) => {
    expect(parseYouTubeId(link)).toBeNull();
  });

  it("builds the embed and thumbnail URLs", () => {
    expect(youtubeEmbedUrl(YT)).toBe(
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1&playsinline=1",
    );
    expect(youtubeEmbedUrl(YT, { autoplay: true })).toBe(
      "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0&modestbranding=1&playsinline=1&autoplay=1",
    );
    expect(youtubeThumbnailUrl(YT)).toBe("https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg");
  });

  it("uses a local poster first, then the YouTube thumbnail", () => {
    expect(posterOf(ytVideo())).toBe("https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg");
    expect(posterOf(ytVideo({ poster: "/howto/custom.jpg" }))).toBe("/howto/custom.jpg");
    expect(posterOf(localVideo())).toBe(LOCAL.poster);
    expect(youtubeIdOf({ youtubeId: "  " })).toBeNull();
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
    expect(html).toContain('src="https://i.ytimg.com/vi/hmeqv11SMYg/hqdefault.jpg"');
    expect(html).toContain("Install Schedule");
    // Search box and category filter.
    expect(html).toContain('type="search"');
    expect(html).toMatch(/aria-pressed="true"[^>]*>All</);
    // No player until a card is clicked.
    expect(html).not.toContain("<video");
    expect(html).not.toContain("<iframe");
  });

  it("shows the empty state when nothing matches", () => {
    const html = view({ query: "zzz" });
    expect(html).toContain("No videos match");
    expect(html).not.toContain("data-video-card");
  });

  it("opens a local video with the native controls and the poster", () => {
    const v = localVideo();
    const html = view({ videos: [v], openId: v.id });
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

  it("embeds YouTube when the entry has a youtubeId", () => {
    const v = ytVideo();
    const html = view({ videos: [v], openId: v.id });
    expect(html).not.toContain("<video");
    expect(html).toContain(`data-youtube-embed="${YT}"`);
    const tag = /<iframe[^>]*>/.exec(html)![0];
    expect(tag).toContain(
      'src="https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0&amp;modestbranding=1&amp;playsinline=1"',
    );
    expect(tag).toContain('allow="autoplay; encrypted-media; picture-in-picture; fullscreen"');
    expect(tag).toContain("allowfullscreen");
    expect(tag).toContain('title="Add an install note"');
    expect(tag).toContain('loading="lazy"');
    // 16:9 responsive box around it.
    expect(html).toMatch(/class="relative aspect-video w-full[^"]*" data-youtube-embed/);
  });

  it("plays Add an install note from YouTube", () => {
    const html = view({ openId: "add-install-note", autoplay: true });
    expect(html).toContain('src="https://www.youtube-nocookie.com/embed/hmeqv11SMYg?rel=0&amp;modestbranding=1&amp;playsinline=1&amp;autoplay=1"');
    expect(html).not.toContain("<video");
  });

  it("autoplays the embed only when opened by a click", () => {
    const v = ytVideo();
    expect(view({ videos: [v], openId: v.id, autoplay: true })).toContain("playsinline=1&amp;autoplay=1");
    expect(view({ videos: [v], openId: v.id })).not.toContain("autoplay=1");
  });

  it("shows the YouTube thumbnail on the card, unless a local poster is set", () => {
    const thumb = 'src="https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"';
    expect(renderToStaticMarkup(<VideoCard video={ytVideo()} onOpen={noop} />)).toContain(thumb);
    const custom = renderToStaticMarkup(<VideoCard video={ytVideo({ poster: "/howto/custom.jpg" })} onOpen={noop} />);
    expect(custom).toContain('src="/howto/custom.jpg"');
    expect(custom).not.toContain("i.ytimg.com");
  });

  it("falls back to the local video when youtubeId is empty", () => {
    const v = localVideo();
    const html = view({ videos: [v], openId: v.id, autoplay: true });
    expect(html).not.toContain("<iframe");
    expect(/<video[^>]*>/.exec(html)![0]).toContain(`src="${v.file}"`);
  });

  it("ignores an unknown ?v= id", () => {
    const html = view({ openId: "nope" });
    expect(html).not.toContain("<video");
    expect(html).not.toContain("<iframe");
  });

  it("badges a video that needs a remake, and it still plays", () => {
    const stale = localVideo({ needsRemake: true });
    expect(renderToStaticMarkup(<VideoCard video={stale} onOpen={noop} />)).toContain("Being updated");
    expect(renderToStaticMarkup(<VideoCard video={localVideo({ needsRemake: false })} onOpen={noop} />)).not.toContain("Being updated");
    const player = renderToStaticMarkup(<VideoPlayer video={stale} onClose={noop} />);
    expect(player).toContain("Being updated");
    expect(player).toContain(`src="${stale.file}"`);
    // Same on a YouTube video.
    const ytStale = ytVideo({ needsRemake: true });
    expect(renderToStaticMarkup(<VideoCard video={ytStale} onOpen={noop} />)).toContain("Being updated");
    const ytPlayer = renderToStaticMarkup(<VideoPlayer video={ytStale} onClose={noop} />);
    expect(ytPlayer).toContain("Being updated");
    expect(ytPlayer).toContain("<iframe");
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
