// Image with fallback/proxy retries, plus the shared "image pending"
// placeholder. Moved verbatim out of pages/Library.tsx (WP 4.2 library-extract).
import React, { useEffect, useMemo, useState } from "react";
import { Leaf } from "lucide-react";

// ─── Image with proxy fallback ───────────────────────────────────────────────
export function ImagePending({ compact = false, label = "Image pending" }: { compact?: boolean; label?: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-1 bg-stone-100 text-stone-400">
      <Leaf size={compact ? 14 : 28} strokeWidth={1.2} />
      {!compact && <span className="text-[11px] font-medium">{label}</span>}
    </div>
  );
}

export function ProxiedImage({ src, fallbacks = [], alt, className, ...rest }: {
  src: string; fallbacks?: string[]; alt: string; className?: string;
} & Omit<React.ImgHTMLAttributes<HTMLImageElement>, "src" | "alt" | "className" | "onError">) {
  // Build an ordered list of URLs to attempt. Internal stored-image proxy keys
  // are tried as-is (they resolve in production); external URLs are tried
  // directly, then via the image proxy (supplier hotlink guard). When the
  // stored image is unavailable (e.g. blob not present), we fall through to the
  // external source_photo_url / gallery URLs so the image still renders.
  const attempts = useMemo(() => {
    const out: string[] = [];
    const push = (u: string) => { if (u && !out.includes(u)) out.push(u); };
    for (const rawSrc of [src, ...fallbacks]) {
      const s = (rawSrc || "").startsWith("/routes/") ? rawSrc.replace(/^\/routes\//, "/api/") : (rawSrc || "");
      if (!s) continue;
      if (s.startsWith("/api/products/image-proxy?")) push(s);
      else if (/^https?:/i.test(s)) { push(s); push(`/api/products/image-proxy?url=${encodeURIComponent(s)}`); }
      else push(s);
    }
    return out;
  }, [src, fallbacks.join("|")]);
  const [idx, setIdx] = useState(0);
  useEffect(() => { setIdx(0); }, [attempts]);
  if (idx >= attempts.length) return <ImagePending />;
  return (
    <img
      {...rest}
      src={attempts[idx]}
      alt={alt}
      loading="lazy"
      decoding="async"
      className={className ?? "w-full h-full object-cover group-hover:scale-105 transition-transform duration-500"}
      onError={() => setIdx((i) => i + 1)}
    />
  );
}
