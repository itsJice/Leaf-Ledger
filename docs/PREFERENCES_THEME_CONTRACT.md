# Per-account preferences + theming — shared contract

Three agents build against this simultaneously. **These names, paths and shapes are
mandatory** — they are the seams between the three workstreams. If you believe one is
wrong, say so in your report; do not silently rename it.

| Phase | Owner | Owns these files |
|---|---|---|
| 1 — preferences store | agent A | `backend/app/apis/preferences/**`, `backend/routers.json`, `frontend/src/utils/preferences.ts` |
| 2 — sidebar + appearance UI | agent B | `frontend/src/components/Layout.tsx`, `frontend/src/pages/Settings.tsx` |
| 3+4 — theme system | agent C | `frontend/tailwind.config.js`, `frontend/src/index.css`, `frontend/src/utils/theme.ts`, raw-hex fixes in `frontend/src/pages/**` **except** `Settings.tsx` |

**No one else touches another owner's files.** Agent C must NOT edit `Layout.tsx` or
`Settings.tsx`; agent B must NOT edit `tailwind.config.js` or `index.css`.

## 1. Preference shape (agent A defines, B and C consume)

```ts
// frontend/src/utils/preferences.ts
export interface SidebarPrefs {
  /** Ordered nav item paths, e.g. ["/", "/designs", "/search"]. Missing items
   *  fall back to their default position, so newly-shipped tabs still appear. */
  order: string[];
  /** Nav item paths the user has hidden. "/" and "/settings" can never be hidden. */
  hidden: string[];
}

export interface ThemePrefs {
  mode: "system" | "light" | "dark";
  /** Accent key from THEME_ACCENTS in utils/theme.ts. */
  accent: string;
}

export interface UserPreferences {
  sidebar: SidebarPrefs;
  theme: ThemePrefs;
}

export const DEFAULT_PREFERENCES: UserPreferences;

/** Reads once, caches in localStorage for instant paint, revalidates from the
 *  server. `save` merges partially and is debounced. */
export function usePreferences(): {
  prefs: UserPreferences;
  save: (patch: DeepPartial<UserPreferences>) => void;
  reset: () => void;
  loading: boolean;
  saving: boolean;
};
```

### Endpoints (agent A)

- `GET /api/preferences` → `UserPreferences` — returns `DEFAULT_PREFERENCES` merged over
  whatever is stored, never 404s for a user with no row yet.
- `PUT /api/preferences` — accepts a **partial** object and deep-merges. Must not clobber
  keys it wasn't sent.

Scope preferences to the authenticated user via `app.apis.user_context.get_request_user_id`
(the pattern `app/apis/designs/__init__.py` already uses). Storage goes in the **`ll_app`
schema** — the `app` DB role cannot `CREATE TABLE` in `public`, but can in its own schema
(`ll_app.orders` is the precedent). Create the table idempotently at first use, the way
`app/apis/orders/__init__.py` does with its `DDL` constant + `ensure_schema`.

## 2. Theme contract (agent C defines, B consumes)

```ts
// frontend/src/utils/theme.ts
export interface ThemeAccent { key: string; label: string; swatch: string }
export const THEME_ACCENTS: ThemeAccent[];   // curated set; first entry is the default
export const DEFAULT_ACCENT: string;

/** Applies `.dark` on <html> and a `data-accent="<key>"` attribute. Resolves
 *  "system" against `prefers-color-scheme` and reacts to OS changes live. */
export function applyTheme(mode: ThemePrefs["mode"], accent: string): void;

/** Resolved appearance for UI that needs to branch on it. */
export function useTheme(): {
  mode: ThemePrefs["mode"];
  accent: string;
  resolved: "light" | "dark";
  setMode: (m: ThemePrefs["mode"]) => void;
  setAccent: (a: string) => void;
};
```

`useTheme` persists through `usePreferences().save({ theme: … })` — preferences are the
single source of truth. It must also write a synchronous pre-paint value so there is **no
flash of the wrong theme** on first load (an inline snippet in `index.html` reading the
cached preference is acceptable and preferred).

## 3. Dark mode — the design decision, already made

**The sidebar keeps its dark identity in both modes.** It is currently dark green
(`#1f3d2b` / `#2d5a33`) against a warm cream page (`#f7f4ef`). Do NOT invert it or make it
light in light mode. Dark mode darkens the **content area**; the sidebar stays dark and may
deepen slightly for contrast. This is why agent C does not own `Layout.tsx`.

## 4. Why theming is cheap here — do it this way

The groundwork already exists and is unused by the pages:

- `tailwind.config.js` already sets `darkMode: ["class"]`.
- `index.css` already defines a full semantic HSL variable set (`--background`,
  `--foreground`, `--card`, `--primary`, `--border`, …) and has a `.dark` block.
- The pages ignore all of it: **1,566 `stone-*`** and **536 `emerald-*`** class usages,
  plus **158 raw hex values across 16 files**.

**Do not hand-migrate 2,100 class usages.** Instead **remap the `stone` and `emerald`
palettes in `tailwind.config.js` to CSS variables**, so every existing usage becomes
themeable at once; dark mode is then a variable swap and the accent is an `emerald`-ramp
swap. Then fix only the **158 raw hex values**, which bypass Tailwind and would otherwise
stay stuck in light mode.

`stone` is the neutral ramp (surfaces/text) and `emerald` is the accent ramp. Keep the
`stone-50 … stone-900` and `emerald-50 … emerald-900` step names intact so no page edits
are needed. Note both ramps run light→dark, so in dark mode the neutral ramp must
**invert** (`stone-50` becomes near-black) while text/border usages keep working — verify
against real screens, not just the config.

## 5. Pinned / undeletable

`/` (Dashboard) and `/settings` can never be hidden or reordered out of reach, or a user
can lock themselves out of the very screen that fixes it.
