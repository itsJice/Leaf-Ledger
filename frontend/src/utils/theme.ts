import { useCallback, useEffect, useSyncExternalStore } from "react";
import { type ThemePrefs, usePreferences } from "utils/preferences";

/**
 * Appearance: dark/light mode and the accent colour.
 *
 * Applying a theme is two DOM writes on `<html>` and nothing else:
 *
 *   - `.dark` toggles the mode. `tailwind.config.js` is `darkMode: ["class"]`,
 *     and `src/index.css` swaps the CSS variables that the whole `stone-*` /
 *     `emerald-*` surface of the app is built on.
 *   - `data-accent="<key>"` selects the accent palette. Because every accent
 *     usage — solid buttons, active nav, focus rings, tinted panels, hairlines
 *     — resolves through the same `--p-*` ramp, one attribute recolours all of
 *     them together.
 *
 * Preferences are the single source of truth (`utils/preferences`); this module
 * only reflects them into the DOM. First paint is handled earlier still, by the
 * inline snippet in `index.html` that reads the same localStorage cache — see
 * `PREFERENCES_CACHE_KEY`. Keep the two in sync: the snippet is deliberately a
 * duplicate of `applyTheme`'s essential three lines, because it has to run
 * before any module loads.
 */

export interface ThemeAccent {
	key: string;
	label: string;
	/** A representative colour for a picker swatch, as a CSS colour string. */
	swatch: string;
}

/**
 * The curated accents. Order matters: the first entry is the default.
 *
 * Every one of these has to survive two hard constraints — it sits next to a
 * permanently dark-green sidebar, and it has to work as both a solid button
 * fill (with white text) and as bright ink on a near-black page. That rules out
 * anything pale or acid; these are all jewel/earth tones taken from Tailwind
 * ramps, so their internal steps are already balanced.
 *
 * `key` must match the `data-accent` blocks in `src/index.css`. The backend
 * cannot validate accent keys (the vocabulary only exists here), so an unknown
 * key round-trips intact and is normalised away by `normalizeAccent`.
 */
export const THEME_ACCENTS: ThemeAccent[] = [
	{ key: "emerald", label: "Emerald", swatch: "#059669" },
	{ key: "teal", label: "Teal", swatch: "#0d9488" },
	{ key: "sky", label: "Sky", swatch: "#0284c7" },
	{ key: "indigo", label: "Indigo", swatch: "#4f46e5" },
	{ key: "rose", label: "Rose", swatch: "#be123c" },
	{ key: "amber", label: "Amber", swatch: "#b45309" },
];

/**
 * The brand accent. Must stay `"emerald"` — `DEFAULT_PREFERENCES` in
 * `utils/preferences` and the server-side default both hardcode that string,
 * and a mismatch would make every stored default disagree with the resolved one.
 */
export const DEFAULT_ACCENT = "emerald";

const DARK_QUERY = "(prefers-color-scheme: dark)";
const THEME_MODES: ThemePrefs["mode"][] = ["system", "light", "dark"];

/** An accent key that `index.css` actually styles, or the default. */
function normalizeAccent(accent: unknown): string {
	const key = typeof accent === "string" ? accent.trim() : "";
	return THEME_ACCENTS.some((a) => a.key === key) ? key : DEFAULT_ACCENT;
}

function normalizeMode(mode: unknown): ThemePrefs["mode"] {
	const value = typeof mode === "string" ? mode.trim().toLowerCase() : "";
	return (THEME_MODES as string[]).includes(value)
		? (value as ThemePrefs["mode"])
		: "system";
}

function prefersDark(): boolean {
	try {
		return window.matchMedia(DARK_QUERY).matches;
	} catch {
		// Ancient or headless environment — assume light.
		return false;
	}
}

// ─── Module-scoped state ─────────────────────────────────────────────────────
// One theme per document, so this lives at module scope rather than per-hook.
// Seeded from whatever the pre-paint snippet already put on <html>, so the very
// first `useTheme()` render agrees with what the user is looking at.

let currentMode: ThemePrefs["mode"] = "system";
let currentAccent = DEFAULT_ACCENT;
let resolvedMode: "light" | "dark" = "light";

const listeners = new Set<() => void>();

if (typeof document !== "undefined") {
	const root = document.documentElement;
	resolvedMode = root.classList.contains("dark") ? "dark" : "light";
	currentAccent = normalizeAccent(root.getAttribute("data-accent"));
}

function subscribe(listener: () => void): () => void {
	listeners.add(listener);
	return () => {
		listeners.delete(listener);
	};
}

/**
 * OS-level listener, attached once and never removed — the theme is global.
 *
 * `osMedia` must be a module-level reference, not a local inside `watchOS`. A
 * `MediaQueryList` whose only reference is a dead local is eligible for garbage
 * collection, and browsers drop its listeners with it — so "system" mode would
 * silently stop following the OS after the first GC.
 */
let osMedia: MediaQueryList | null = null;

function watchOS(): void {
	if (osMedia || typeof window === "undefined") return;
	try {
		osMedia = window.matchMedia(DARK_QUERY);
	} catch {
		return;
	}
	const onChange = () => {
		// Only "system" cares, but re-applying is idempotent and cheap.
		if (currentMode === "system") applyTheme(currentMode, currentAccent);
	};
	if (typeof osMedia.addEventListener === "function") {
		osMedia.addEventListener("change", onChange);
	} else if (typeof (osMedia as any).addListener === "function") {
		// Safari < 14.
		(osMedia as any).addListener(onChange);
	}
}

/**
 * Reflect `mode` + `accent` onto `<html>`.
 *
 * `"system"` is resolved against `prefers-color-scheme` here and re-resolved
 * automatically whenever the OS setting changes. An accent key that no palette
 * exists for falls back to `DEFAULT_ACCENT` rather than leaving the document in
 * a state nothing is styled for.
 *
 * Safe to call repeatedly; it writes only when something actually differs.
 */
export function applyTheme(mode: ThemePrefs["mode"], accent: string): void {
	const nextMode = normalizeMode(mode);
	const nextAccent = normalizeAccent(accent);
	const nextResolved: "light" | "dark" =
		nextMode === "system" ? (prefersDark() ? "dark" : "light") : nextMode;

	currentMode = nextMode;
	currentAccent = nextAccent;

	if (typeof document !== "undefined") {
		const root = document.documentElement;
		root.classList.toggle("dark", nextResolved === "dark");
		if (root.getAttribute("data-accent") !== nextAccent) {
			root.setAttribute("data-accent", nextAccent);
		}
	}

	watchOS();

	if (nextResolved !== resolvedMode) {
		resolvedMode = nextResolved;
		listeners.forEach((listener) => listener());
	}
}

function getResolved(): "light" | "dark" {
	return resolvedMode;
}

/**
 * The resolved appearance plus writers.
 *
 * `mode` is the stored preference (`"system"` stays `"system"`); `resolved` is
 * what is actually on screen and follows the OS live while `mode` is
 * `"system"`. Writers apply immediately and persist through
 * `usePreferences().save()`, which is debounced — so a burst of clicks in the
 * appearance picker is one request, and the UI never waits for it.
 */
export function useTheme(): {
	mode: ThemePrefs["mode"];
	accent: string;
	resolved: "light" | "dark";
	setMode: (m: ThemePrefs["mode"]) => void;
	setAccent: (a: string) => void;
} {
	const { prefs, save } = usePreferences();
	const mode = normalizeMode(prefs.theme.mode);
	const accent = normalizeAccent(prefs.theme.accent);
	const resolved = useSyncExternalStore(subscribe, getResolved, getResolved);

	// Preferences are authoritative: whenever they settle (cache first, then the
	// server's answer, then any later edit) the DOM is brought in line.
	useEffect(() => {
		applyTheme(mode, accent);
	}, [mode, accent]);

	const setMode = useCallback(
		(next: ThemePrefs["mode"]) => {
			const value = normalizeMode(next);
			applyTheme(value, currentAccent);
			save({ theme: { mode: value } });
		},
		[save],
	);

	const setAccent = useCallback(
		(next: string) => {
			const value = normalizeAccent(next);
			applyTheme(currentMode, value);
			save({ theme: { accent: value } });
		},
		[save],
	);

	return { mode, accent, resolved, setMode, setAccent };
}
