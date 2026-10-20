/**
 * Helpers for Help > How-to videos (pages/Help.tsx). Pure, so tests can
 * import them. The videos themselves are listed in data/howtoVideos.ts.
 */
import { HOWTO_CATEGORIES } from "../data/howtoVideos";
import type { HowToCategory, HowToVideo } from "../data/howtoVideos";

/** The page's route. Every signed-in role may open it (app/auth/RoleGate.tsx). */
export const HELP_PATH = "/help";

export function isHelpPath(path: string): boolean {
  return path === HELP_PATH || path === `${HELP_PATH}/`;
}

/** 55 -> "0:55", 75 -> "1:15". */
export function formatDuration(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/** "2026-10-19" -> "Oct 19, 2026", read as a calendar date (no timezone shift). */
export function formatUpdated(ymd: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(ymd);
  if (!m) return ymd;
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]));
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** A YouTube video id: 11 characters of letters, digits, `-` and `_`. */
const YT_ID = /^[A-Za-z0-9_-]{11}$/;

/**
 * The video id from a pasted YouTube link, or null when it isn't one.
 * Handles youtu.be/ID, youtube.com/watch?v=ID, /shorts/ID, /embed/ID and
 * /live/ID (www., m., music. and youtube-nocookie.com too), with or without
 * https:// and extra parameters like `?si=` or `&t=30s`. A bare id is
 * accepted as is.
 */
export function parseYouTubeId(input: string): string | null {
  const raw = (input ?? "").trim();
  if (!raw) return null;
  if (YT_ID.test(raw)) return raw;
  let url: URL;
  try {
    url = new URL(/^[a-z][a-z0-9+.-]*:\/\//i.test(raw) ? raw : `https://${raw}`);
  } catch {
    return null;
  }
  const host = url.hostname.toLowerCase().replace(/^(www|m|music)\./, "");
  const parts = url.pathname.split("/").filter(Boolean);
  let id: string | null = null;
  if (host === "youtu.be") {
    id = parts[0] ?? null;
  } else if (host === "youtube.com" || host === "youtube-nocookie.com") {
    if (parts[0] === "watch") id = url.searchParams.get("v");
    else if (["shorts", "embed", "live", "v"].includes(parts[0] ?? "")) id = parts[1] ?? null;
  }
  return id && YT_ID.test(id) ? id : null;
}

/** The entry's YouTube id when it has a valid one, else null (play the local file). */
export function youtubeIdOf(v: Pick<HowToVideo, "youtubeId">): string | null {
  const id = v.youtubeId?.trim() ?? "";
  return YT_ID.test(id) ? id : null;
}

/** Privacy-enhanced embed URL; `autoplay` when the viewer clicked to open it. */
export function youtubeEmbedUrl(id: string, opts: { autoplay?: boolean } = {}): string {
  const base = `https://www.youtube-nocookie.com/embed/${encodeURIComponent(id)}?rel=0&modestbranding=1&playsinline=1`;
  return opts.autoplay ? `${base}&autoplay=1` : base;
}

export function youtubeThumbnailUrl(id: string): string {
  return `https://i.ytimg.com/vi/${encodeURIComponent(id)}/hqdefault.jpg`;
}

/** The card's poster: a local poster if set, else the YouTube thumbnail. */
export function posterOf(v: Pick<HowToVideo, "poster" | "youtubeId">): string | undefined {
  if (v.poster) return v.poster;
  const id = youtubeIdOf(v);
  return id ? youtubeThumbnailUrl(id) : undefined;
}

export type CategoryFilter = HowToCategory | "all";

/** Search (title, description, category) and category filter; newest first. */
export function filterVideos(videos: HowToVideo[], query: string, category: CategoryFilter): HowToVideo[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  return videos
    .filter((v) => category === "all" || v.category === category)
    .filter((v) => {
      if (!words.length) return true;
      const hay = `${v.title} ${v.description} ${v.category}`.toLowerCase();
      return words.every((w) => hay.includes(w));
    })
    .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : a.updatedAt > b.updatedAt ? -1 : a.title.localeCompare(b.title)));
}

/** Categories that have at least one video, in the registry's order. */
export function categoriesWithVideos(videos: HowToVideo[]): HowToCategory[] {
  return HOWTO_CATEGORIES.filter((c) => videos.some((v) => v.category === c));
}

/** What's wrong with the registry (empty when it's fine). Run by the tests. */
export function registryProblems(videos: HowToVideo[]): string[] {
  const out: string[] = [];
  const ids = new Set<string>();
  for (const v of videos) {
    const at = v.id || "(no id)";
    if (!/^[a-z0-9]+(-[a-z0-9]+)*$/.test(v.id)) out.push(`${at}: id must be kebab-case`);
    if (ids.has(v.id)) out.push(`${at}: duplicate id`);
    ids.add(v.id);
    if (!v.title.trim()) out.push(`${at}: no title`);
    if (!v.description.trim()) out.push(`${at}: no description`);
    if (!(HOWTO_CATEGORIES as readonly string[]).includes(v.category)) out.push(`${at}: unknown category`);
    const yt = v.youtubeId?.trim() ?? "";
    if (yt && !YT_ID.test(yt)) out.push(`${at}: youtubeId must be the 11-character id (use parseYouTubeId on the link)`);
    if (yt || v.file !== undefined) {
      if (v.file !== undefined && !/^\/howto\/[\w.-]+\.mp4$/.test(v.file)) out.push(`${at}: file must be /howto/<name>.mp4`);
    } else {
      out.push(`${at}: needs a youtubeId or a file`);
    }
    if (!yt && v.poster === undefined) out.push(`${at}: a local video needs a poster`);
    if (v.poster !== undefined && !/^\/howto\/[\w.-]+\.(jpg|jpeg|png|webp)$/.test(v.poster)) {
      out.push(`${at}: poster must be /howto/<name>.jpg`);
    }
    if (!(Number.isFinite(v.durationSec) && v.durationSec > 0)) out.push(`${at}: durationSec must be > 0`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(v.updatedAt) || Number.isNaN(Date.parse(v.updatedAt))) {
      out.push(`${at}: updatedAt must be YYYY-MM-DD`);
    }
    if (!v.screens.length) out.push(`${at}: list the screens it shows`);
    if (!v.sourceFiles.length) out.push(`${at}: list its source files`);
    if (!v.labels.length) out.push(`${at}: list the labels it relies on`);
    if (typeof v.needsRemake !== "boolean") out.push(`${at}: needsRemake must be true/false`);
    if (!v.composition.trim()) out.push(`${at}: no composition`);
  }
  return out;
}
