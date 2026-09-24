// Fullscreen image lightbox with zoom/pan and prev/next navigation.
// Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import { useCallback, useEffect, useRef, useState } from "react";
import { X, ChevronLeft, ChevronRight, ZoomIn } from "components/icons";
import { ProxiedImage } from "./ProxiedImage";

export function ImageLightbox({ images, index, onIndex, onClose }: {
  images: string[];
  index: number;
  onIndex: (i: number) => void;
  onClose: () => void;
}) {
  const [zoom, setZoom] = useState(false);
  const [origin, setOrigin] = useState("center");
  const touchStart = useRef<number | null>(null);
  const go = useCallback((delta: number) => {
    setZoom(false);
    onIndex((index + delta + images.length) % images.length);
  }, [index, images.length, onIndex]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      else if (e.key === "ArrowLeft") go(-1);
      else if (e.key === "ArrowRight") go(1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [go, onClose]);

  const rawUrl = images[index] || "";

  return (
    <div className="fixed inset-0 z-[70] flex select-none items-center justify-center bg-black/90 ll-overlay" onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <button onClick={onClose} title="Close (Esc)" className="absolute right-4 top-4 rounded-full bg-white/10 p-2 text-white/80 hover:bg-white/20 hover:text-white">
        <X size={20} />
      </button>
      {images.length > 1 && (
        <span className="absolute left-1/2 top-5 -translate-x-1/2 text-sm font-medium text-white/70">{index + 1} / {images.length}</span>
      )}
      {images.length > 1 && (
        <>
          <button onClick={(e) => { e.stopPropagation(); go(-1); }} title="Previous (←)" className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white/80 hover:bg-white/20 hover:text-white">
            <ChevronLeft size={26} />
          </button>
          <button onClick={(e) => { e.stopPropagation(); go(1); }} title="Next (→)" className="absolute right-3 top-1/2 -translate-y-1/2 rounded-full bg-white/10 p-3 text-white/80 hover:bg-white/20 hover:text-white">
            <ChevronRight size={26} />
          </button>
        </>
      )}
      {/* ProxiedImage, not a bare <img>: the plain element this replaced had no
          retry at all, so a proxy hiccup on this one URL showed a blank black
          screen with nothing recoverable - "Expand does nothing" - even though
          the very same image renders fine as the thumbnail via this same
          component's direct-URL-then-proxy retry chain. */}
      <ProxiedImage
        key={rawUrl}
        src={rawUrl}
        alt=""
        draggable={false}
        onClick={(e) => { e.stopPropagation(); setZoom((z) => !z); }}
        onMouseMove={(e) => {
          if (!zoom) return;
          const r = e.currentTarget.getBoundingClientRect();
          setOrigin(`${((e.clientX - r.left) / r.width) * 100}% ${((e.clientY - r.top) / r.height) * 100}%`);
        }}
        onTouchStart={(e) => { touchStart.current = e.touches[0].clientX; }}
        onTouchEnd={(e) => {
          if (touchStart.current == null) return;
          const dx = e.changedTouches[0].clientX - touchStart.current;
          if (Math.abs(dx) > 50) go(dx < 0 ? 1 : -1);
          touchStart.current = null;
        }}
        style={{ transformOrigin: origin, transform: zoom ? "scale(2.5)" : "scale(1)" }}
        className={`max-h-[92vh] max-w-[92vw] object-contain transition-transform duration-200 ${zoom ? "cursor-zoom-out" : "cursor-zoom-in"}`}
      />
      <span className="absolute bottom-5 left-1/2 flex -translate-x-1/2 items-center gap-1.5 text-xs text-white/50">
        <ZoomIn size={13} /> Click image to zoom{images.length > 1 ? " · swipe or ←/→ to browse" : ""}
      </span>
    </div>
  );
}
