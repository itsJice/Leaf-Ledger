import { useEffect, useRef } from "react";
import { Play, RefreshCw, Search, X } from "components/icons";
import type { HowToVideo } from "../../data/howtoVideos";
import {
  categoriesWithVideos,
  filterVideos,
  formatDuration,
  formatUpdated,
  posterOf,
  youtubeEmbedUrl,
  youtubeIdOf,
} from "utils/howto";
import type { CategoryFilter } from "utils/howto";

const SORA = { fontFamily: "'Sora', system-ui, sans-serif" };

/** Amber "Being updated" badge for a video flagged `needsRemake`. */
export function RemakeBadge({ className = "" }: { className?: string }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[11px] font-semibold text-amber-800 ${className}`}
      title="This video is being remade to match the app. It still plays."
    >
      <RefreshCw size={11} /> Being updated
    </span>
  );
}

export function VideoCard({ video, onOpen }: { video: HowToVideo; onOpen: (id: string) => void }) {
  const poster = posterOf(video);
  return (
    <li className="overflow-hidden rounded-xl border border-stone-200 bg-white shadow-sm transition-shadow hover:shadow-md">
      <button
        type="button"
        onClick={() => onOpen(video.id)}
        className="group block w-full text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500"
        aria-label={`Play ${video.title} (${formatDuration(video.durationSec)})`}
        data-video-card={video.id}
      >
        <div className="relative aspect-video w-full overflow-hidden bg-stone-100">
          {poster && (
            <img
              src={poster}
              alt=""
              loading="lazy"
              decoding="async"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            />
          )}
          <span className="absolute inset-0 flex items-center justify-center">
            <span className="flex h-12 w-12 items-center justify-center rounded-full bg-[#1f3d2b]/85 text-white shadow-lg transition-transform duration-200 group-hover:scale-105">
              <Play size={20} className="translate-x-[1px]" />
            </span>
          </span>
          <span className="absolute bottom-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-xs font-semibold tabular-nums text-white">
            {formatDuration(video.durationSec)}
          </span>
          {video.needsRemake && <RemakeBadge className="absolute left-2 top-2 shadow-sm" />}
        </div>
        <div className="p-3 sm:p-4">
          <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">{video.category}</p>
          <h2 className="mt-0.5 text-base font-semibold text-stone-800" style={SORA}>
            {video.title}
          </h2>
          <p className="mt-1 line-clamp-2 text-sm text-stone-600">{video.description}</p>
          <p className="mt-2 text-xs text-stone-500">
            {formatDuration(video.durationSec)} · Last updated {formatUpdated(video.updatedAt)}
          </p>
        </div>
      </button>
    </li>
  );
}

/**
 * The video itself in a 16:9 box: a YouTube embed when the entry has a
 * `youtubeId`, else the local file with the native controls.
 */
function PlayerMedia({ video, autoplay }: { video: HowToVideo; autoplay: boolean }) {
  const yt = youtubeIdOf(video);
  if (yt) {
    return (
      <div className="relative aspect-video w-full bg-black" data-youtube-embed={yt}>
        <iframe
          key={yt}
          src={youtubeEmbedUrl(yt, { autoplay })}
          title={video.title}
          loading="lazy"
          allow="autoplay; encrypted-media; picture-in-picture; fullscreen"
          allowFullScreen
          referrerPolicy="strict-origin-when-cross-origin"
          className="absolute inset-0 h-full w-full border-0"
        />
      </div>
    );
  }
  return (
    <video
      key={video.file}
      src={video.file}
      poster={video.poster}
      controls
      playsInline
      autoPlay
      preload="metadata"
      className="block aspect-video w-full bg-black"
    >
      Your browser can't play this video.
    </video>
  );
}

/**
 * The inline player: a dialog over the page. `autoplay` is true when the
 * viewer clicked a card (YouTube only starts on its own after a click); a
 * `?v=` link opens it ready to play.
 */
export function VideoPlayer({
  video,
  onClose,
  autoplay = false,
}: {
  video: HowToVideo;
  onClose: () => void;
  autoplay?: boolean;
}) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    closeRef.current?.focus({ preventScroll: true });
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const titleId = `howto-title-${video.id}`;
  return (
    <div
      className="fixed inset-0 z-[60] flex items-end justify-center bg-black/70 sm:items-center sm:p-6"
      onClick={onClose}
      data-video-player={video.id}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-5xl overflow-hidden rounded-t-2xl bg-white shadow-2xl sm:rounded-2xl"
      >
        <PlayerMedia video={video} autoplay={autoplay} />
        <div className="flex items-start gap-3 p-4 pb-[max(1rem,env(safe-area-inset-bottom))]">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <p className="text-[11px] font-bold uppercase tracking-wide text-emerald-700">{video.category}</p>
              {video.needsRemake && <RemakeBadge />}
            </div>
            <h2 id={titleId} className="mt-0.5 text-lg font-semibold text-stone-800" style={SORA}>
              {video.title}
            </h2>
            <p className="mt-1 text-sm text-stone-600">{video.description}</p>
            <p className="mt-2 text-xs text-stone-500">
              {formatDuration(video.durationSec)} · Last updated {formatUpdated(video.updatedAt)}
            </p>
          </div>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            aria-label="Close video"
            className="flex h-10 w-10 flex-none items-center justify-center rounded-full bg-stone-100 text-stone-600 hover:bg-stone-200 hover:text-stone-800"
          >
            <X size={18} />
          </button>
        </div>
      </div>
    </div>
  );
}

export interface HowToVideosViewProps {
  videos: HowToVideo[];
  query: string;
  category: CategoryFilter;
  /** The video playing, or null. */
  openId: string | null;
  /** The player was opened by a click (so a YouTube embed may autoplay). */
  autoplay?: boolean;
  onQuery: (q: string) => void;
  onCategory: (c: CategoryFilter) => void;
  onOpen: (id: string) => void;
  onClose: () => void;
}

/** Everything under the page header: search, category filter, cards, player. */
export function HowToVideosView({
  videos,
  query,
  category,
  openId,
  autoplay = false,
  onQuery,
  onCategory,
  onOpen,
  onClose,
}: HowToVideosViewProps) {
  const shown = filterVideos(videos, query, category);
  const categories = categoriesWithVideos(videos);
  const open = openId ? videos.find((v) => v.id === openId) ?? null : null;
  const filters: { value: CategoryFilter; label: string }[] = [
    { value: "all", label: "All" },
    ...categories.map((c) => ({ value: c, label: c })),
  ];

  return (
    <div className="mx-auto max-w-5xl px-4 pb-24 pt-3 sm:px-6 sm:pt-5">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <label className="relative min-w-0 flex-1">
          <span className="sr-only">Search how-to videos</span>
          <Search size={15} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-stone-400" />
          <input
            type="search"
            value={query}
            onChange={(e) => onQuery(e.target.value)}
            placeholder="Search videos"
            className="h-10 w-full rounded-lg border border-stone-200 bg-white pl-9 pr-3 text-base text-stone-800 placeholder:text-stone-400 focus:border-emerald-500 focus:outline-none sm:text-sm"
          />
        </label>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Category">
          {filters.map(({ value, label }) => {
            const on = category === value;
            return (
              <button
                key={value}
                type="button"
                onClick={() => onCategory(value)}
                aria-pressed={on}
                className={`min-h-10 rounded-full border px-3 text-xs font-medium transition-colors sm:min-h-9 ${
                  on
                    ? "border-emerald-600 bg-emerald-50 text-emerald-800"
                    : "border-stone-200 bg-white text-stone-600 hover:border-stone-300"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>

      {shown.length ? (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {shown.map((v) => (
            <VideoCard key={v.id} video={v} onOpen={onOpen} />
          ))}
        </ul>
      ) : (
        <div className="rounded-xl border border-dashed border-stone-300 px-4 py-10 text-center">
          <p className="text-sm text-stone-600">No videos match that search.</p>
          <button
            type="button"
            onClick={() => {
              onQuery("");
              onCategory("all");
            }}
            className="mt-2 min-h-10 text-sm font-semibold text-emerald-700 hover:text-emerald-800"
          >
            Show all videos
          </button>
        </div>
      )}

      {open && <VideoPlayer video={open} onClose={onClose} autoplay={autoplay} />}
    </div>
  );
}
