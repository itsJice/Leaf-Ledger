import React, { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { CalendarDays, Check, Copy, ExternalLink } from "components/icons";
import { apiFetch } from "utils/apiFetch";

/**
 * A small corner button on the Install Schedule that subscribes the viewer's
 * own calendar to the office feed (backend app/apis/install_calendar).
 *
 * The link comes from /api/install-schedule/calendar-link, which only office
 * staff and up can read -- the link carries the feed's secret. Anyone else
 * (leads, the warehouse display, production) gets a 403 and the button never
 * renders, as it doesn't while the feed isn't configured (404).
 *
 * Google: calendar.google.com/calendar/r?cid=<webcal url> opens Google
 * Calendar on its own "Add calendar?" prompt, so nobody pastes anything.
 * Apple: a webcal:// link opens the Calendar app's subscribe sheet.
 */
export function CalendarSubscribe() {
  const [path, setPath] = useState<string | null>(null);
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await apiFetch("/api/install-schedule/calendar-link");
        if (!res.ok) return;
        const body = await res.json();
        if (!cancelled && typeof body?.path === "string") setPath(body.path);
      } catch {
        /* no button */
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!boxRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (!path) return null;

  const https = `${window.location.origin}${path}`;
  const webcal = `webcal://${window.location.host}${path}`;
  const google = `https://calendar.google.com/calendar/r?cid=${encodeURIComponent(webcal)}`;

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(https);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      toast.error("Couldn't copy -- your browser blocked the clipboard.");
    }
  };

  const item =
    "flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-left text-sm text-[#1f3d2b] hover:bg-stone-100";

  return (
    // Stacked just above the FeedbackWidget's button, which owns the corner.
    <div ref={boxRef} className="absolute bottom-[84px] right-[30px] z-10">
      {open && (
        <div
          role="menu"
          className="absolute bottom-11 right-0 w-64 rounded-xl border border-stone-200 bg-white p-1.5 shadow-lg"
        >
          <p className="px-3 pb-1.5 pt-1 text-xs text-stone-500">
            Add the install schedule to your calendar. Office only: it shows client addresses and phone numbers.
          </p>
          <a role="menuitem" href={google} target="_blank" rel="noopener noreferrer" className={item} onClick={() => setOpen(false)}>
            <ExternalLink className="h-4 w-4 text-stone-400" />
            Add to Google Calendar
          </a>
          <a role="menuitem" href={webcal} className={item} onClick={() => setOpen(false)}>
            <CalendarDays className="h-4 w-4 text-stone-400" />
            Add to Apple Calendar
          </a>
          <button role="menuitem" type="button" className={item} onClick={copy}>
            {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4 text-stone-400" />}
            {copied ? "Copied" : "Copy link"}
          </button>
        </div>
      )}
      <button
        type="button"
        aria-label="Subscribe to the install calendar"
        title="Subscribe to the install calendar"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex h-9 w-9 items-center justify-center rounded-full border border-stone-200 bg-white/90 text-stone-500 shadow-sm backdrop-blur hover:text-[#1f3d2b]"
      >
        <CalendarDays className="h-4 w-4" />
      </button>
    </div>
  );
}
