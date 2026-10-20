/**
 * How-to videos: the single list behind Help > How-to videos (/help).
 *
 * README
 * ------
 * Every video the app shows is one entry here. The page reads nothing else.
 *
 * YouTube (preferred): upload the video to YouTube as Unlisted and set
 * `youtubeId`. The player then shows a privacy-enhanced embed
 * (youtube-nocookie.com) and the card uses YouTube's thumbnail unless a
 * local `poster` is set. Paste the share link into `parseYouTubeId` (in
 * utils/howto.ts) to get the id: youtu.be/ID, youtube.com/watch?v=ID,
 * /shorts/ID and /embed/ID links all work. Once an entry has a `youtubeId`,
 * drop its `file` (and `poster`, unless you want a custom one) and delete
 * the local files.
 *
 * Local files (fallback, used when `youtubeId` is empty): each video and its
 * poster live in `frontend/public/howto/` and are
 * served as static files from the same origin (Vite copies public/ into
 * dist/, and backend main.py serves any real file under dist/). Put a
 * version in the file name (`-v2`) and bump it when a video is remade, so a
 * phone that cached the old one fetches the new one. Keep each file small
 * (H.264, `-movflags +faststart`, CRF 26-28, under about 8 MB).
 *
 * The videos are Remotion compositions in /Users/justice/Projects/
 * leaf-and-ledger/demo-video (`composition` names the one to re-render).
 *
 * Staleness (planned, not built yet): a check will compare each entry with
 * what changed in the app since `updatedAt`:
 *   - `sourceFiles`: repo paths whose changes could make the video wrong.
 *     A `#section` suffix narrows it to one part of a big file, e.g.
 *     `scheduler/review_template.html#install-notes`.
 *   - `labels`: on-screen strings the video relies on. If one disappears
 *     from the source files, the video no longer matches the app.
 *   - `screens`: the UI areas shown, for a person reading the report.
 * When a video is out of date, set `needsRemake: true`: the card shows an
 * amber "Being updated" badge and the video still plays. Set it back to
 * false (and update `updatedAt`, `durationSec` and the file names) once the
 * remake ships.
 */

export const HOWTO_CATEGORIES = ["Install Schedule"] as const;
export type HowToCategory = (typeof HOWTO_CATEGORIES)[number];

export interface HowToVideo {
  /** Stable id, also the `?v=` link to open it straight away. */
  id: string;
  title: string;
  /** One line under the title. */
  description: string;
  category: HowToCategory;
  /**
   * YouTube video id (the 11 characters after `v=` or `youtu.be/`). When set,
   * the player embeds YouTube instead of playing `file`. Empty = not on
   * YouTube yet.
   */
  youtubeId?: string;
  /** Public path of the .mp4, under /howto/. Needed when there's no `youtubeId`. */
  file?: string;
  /** Public path of the poster image, under /howto/. Optional with a `youtubeId` (its thumbnail is used). */
  poster?: string;
  durationSec: number;
  /** YYYY-MM-DD the video was last made. */
  updatedAt: string;
  /** UI areas the video shows. */
  screens: string[];
  /** App files whose changes could make it stale (optional `#section`). */
  sourceFiles: string[];
  /** On-screen strings the video relies on. */
  labels: string[];
  /** Out of date: shows "Being updated" but still plays. */
  needsRemake: boolean;
  /** Remotion composition id in demo-video/. */
  composition: string;
}

export const HOWTO_VIDEOS: HowToVideo[] = [
  {
    id: "add-install-note",
    title: "Add an install note",
    description:
      "Put what the crew needs to bring on the client's card so it shows in the lead's Pack list on install morning and on the printed crew sheet.",
    category: "Install Schedule",
    // Unlisted: https://youtu.be/hmeqv11SMYg
    youtubeId: "hmeqv11SMYg",
    durationSec: 55,
    updatedAt: "2026-10-19",
    screens: [
      "Install Schedule: Days view, stop card",
      "Install Schedule: stop card editor (This season)",
      "Crew Shifts (lead's phone): Pack list for today",
      "Printed crew sheet: pack list",
    ],
    sourceFiles: [
      "scheduler/review_template.html#install-notes",
      "scheduler/review_template.html#stop-card-editor",
      "scheduler/review_template.html#crew-sheet-print",
      "frontend/src/pages/Shifts.tsx",
      "frontend/src/utils/shifts.ts",
      "backend/app/apis/lead/__init__.py",
    ],
    labels: [
      "Install notes 2026",
      "Pack list for today",
      "notes",
      "Save changes",
      "Edit",
      "stops have install notes",
    ],
    needsRemake: false,
    composition: "HowToInstallNotes",
  },
];
