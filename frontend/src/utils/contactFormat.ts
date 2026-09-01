/**
 * Phone/email presentation helpers.
 *
 * Phone numbers arrive from every direction -- typed by hand, pasted from a
 * vendor's site, or loaded from rows that predate any formatting (the database
 * has values stored as bare digits, e.g. "9523732020"). Rather than migrate the
 * stored data, format at the edges: display formatted everywhere, and tidy the
 * input on blur so newly-typed numbers get stored tidy too.
 */

/**
 * Format a US/CA phone for display. Anything that isn't a recognizable
 * 10-digit (or 1 + 10) number is returned untouched -- international numbers,
 * extensions and "call the main line" style notes shouldn't be mangled into
 * a shape they don't fit.
 */
export function formatPhone(raw?: string | null): string {
  const value = (raw ?? "").trim();
  if (!value) return "";
  const digits = value.replace(/\D/g, "");
  if (digits.length === 10) {
    return `(${digits.slice(0, 3)}) ${digits.slice(3, 6)}-${digits.slice(6)}`;
  }
  if (digits.length === 11 && digits.startsWith("1")) {
    return `+1 (${digits.slice(1, 4)}) ${digits.slice(4, 7)}-${digits.slice(7)}`;
  }
  return value;
}

/** `tel:` href -- strip formatting so the dialer gets clean digits. */
export function telHref(raw?: string | null): string {
  const digits = (raw ?? "").replace(/[^\d+]/g, "");
  return `tel:${digits}`;
}

/**
 * Open a Gmail compose window with the address pre-filled.
 *
 * Note this is Gmail-web specific by request; a plain `mailto:` would be the
 * portable choice for someone using a desktop mail client instead.
 */
export function gmailComposeHref(email?: string | null, subject?: string): string {
  const to = encodeURIComponent((email ?? "").trim());
  const su = subject ? `&su=${encodeURIComponent(subject)}` : "";
  return `https://mail.google.com/mail/?view=cm&fs=1&to=${to}${su}`;
}

/** Canonical shipping-speed vocabulary. The DB column is free text on purpose --
 *  this list owns the vocabulary so adding a bucket never needs a migration. */
export const SHIPPING_SPEEDS: { value: string; label: string }[] = [
  { value: "next_day", label: "Ships next day" },
  { value: "2_3_days", label: "2–3 days" },
  { value: "about_1_week", label: "About a week" },
  { value: "2_weeks_plus", label: "2+ weeks — needs prompting" },
  { value: "varies", label: "Varies" },
];

export function shippingSpeedLabel(value?: string | null): string {
  if (!value) return "";
  return SHIPPING_SPEEDS.find((s) => s.value === value)?.label ?? value;
}
