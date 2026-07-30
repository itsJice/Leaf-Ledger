/**
 * The `stone` and `emerald` palettes are remapped onto CSS variables declared
 * in `src/index.css`, which is what makes ~2,100 existing class usages
 * themeable without touching a single page.
 *
 * Each palette is wired to TWO variable ramps, because a step's meaning depends
 * on the utility using it. `bg-stone-50` is a pale surface; `text-stone-800` is
 * ink on that surface. In dark mode the surface must darken while the ink
 * lightens, so one inverted ramp cannot serve both.
 *
 *   theme.extend.colors           → the CONTENT ramp (--nc-* / --ac-*)
 *                                   text, border, ring, divide, fill, stroke,
 *                                   outline, caret, accent, placeholder …
 *   theme.extend.backgroundColor  → the SURFACE ramp (--ns-* / --as-*)
 *
 * `backgroundColor` defaults to `theme('colors')`, so overriding only the two
 * palette keys there leaves every other colour (white, red, amber, the shadcn
 * semantic tokens) resolving exactly as before.
 *
 * All values use the `rgb(<channels> / <alpha-value>)` form so Tailwind's
 * opacity modifiers keep working — `bg-emerald-50/40` and `text-stone-500/70`
 * are both in use. A bare `var(--x)` would make Tailwind silently drop the
 * modifier.
 *
 * See the long comment at the top of `src/index.css` for the ramp strategy.
 */

/** `{ 50: "rgb(var(--pfx-50) / <alpha-value>)", … }` for one 11-step ramp. */
const ramp = (prefix) =>
	Object.fromEntries(
		[50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950].map((step) => [
			step,
			`rgb(var(--${prefix}-${step}) / <alpha-value>)`,
		]),
	);

const token = (name) => `rgb(var(--${name}) / <alpha-value>)`;

/** @type {import('tailwindcss').Config} */
export default {
	darkMode: ["class"],
	content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
	theme: {
		extend: {
			borderRadius: {
				lg: "var(--radius)",
				md: "calc(var(--radius) - 2px)",
				sm: "calc(var(--radius) - 4px)",
			},
			colors: {
				/* Themed palettes — CONTENT channel. */
				stone: ramp("nc"),
				emerald: ramp("ac"),

				/* Status palettes, same split. Not user-swappable, but they are
				   almost always a `bg-*-50` chip with `text-*-600/700` ink, which
				   would glow on a dark page if left alone. */
				amber: ramp("amc"),
				red: ramp("rdc"),
				rose: ramp("rsc"),

				/* Semantic tokens replacing the raw hex the pages used to inline.
				   The `brand` entries here are the CONTENT role (brand as ink);
				   `backgroundColor` below gives them their SURFACE counterparts. */
				brand: {
					DEFAULT: token("ll-brand-ink"),
					hover: token("ll-brand-hover"),
					deep: token("ll-ink"),
					deepest: token("ll-ink"),
					soft: token("ll-brand-soft"),
				},
				page: token("ll-page"),
				surface: token("ll-surface"),
				fav: token("ll-fav"),

				background: "hsl(var(--background))",
				foreground: "hsl(var(--foreground))",
				card: {
					DEFAULT: "hsl(var(--card))",
					foreground: "hsl(var(--card-foreground))",
				},
				popover: {
					DEFAULT: "hsl(var(--popover))",
					foreground: "hsl(var(--popover-foreground))",
				},
				primary: {
					DEFAULT: "hsl(var(--primary))",
					foreground: "hsl(var(--primary-foreground))",
				},
				secondary: {
					DEFAULT: "hsl(var(--secondary))",
					foreground: "hsl(var(--secondary-foreground))",
				},
				muted: {
					DEFAULT: "hsl(var(--muted))",
					foreground: "hsl(var(--muted-foreground))",
				},
				accent: {
					DEFAULT: "hsl(var(--accent))",
					foreground: "hsl(var(--accent-foreground))",
				},
				destructive: {
					DEFAULT: "hsl(var(--destructive))",
					foreground: "hsl(var(--destructive-foreground))",
				},
				border: "hsl(var(--border))",
				input: "hsl(var(--input))",
				ring: "hsl(var(--ring))",
				chart: {
					1: "hsl(var(--chart-1))",
					2: "hsl(var(--chart-2))",
					3: "hsl(var(--chart-3))",
					4: "hsl(var(--chart-4))",
					5: "hsl(var(--chart-5))",
				},
			},
			backgroundColor: {
				/* Themed palettes — SURFACE channel. */
				stone: ramp("ns"),
				emerald: ramp("as"),
				amber: ramp("ams"),
				red: ramp("rds"),
				rose: ramp("rss"),
				brand: {
					DEFAULT: token("ll-brand"),
					hover: token("ll-brand-hover"),
					deep: token("ll-brand-deep"),
					deepest: token("ll-brand-deepest"),
					soft: token("ll-brand-soft"),
				},
			},
			keyframes: {
				"accordion-down": {
					from: {
						height: "0",
					},
					to: {
						height: "var(--radix-accordion-content-height)",
					},
				},
				"accordion-up": {
					from: {
						height: "var(--radix-accordion-content-height)",
					},
					to: {
						height: "0",
					},
				},
			},
			animation: {
				"accordion-down": "accordion-down 0.2s ease-out",
				"accordion-up": "accordion-up 0.2s ease-out",
			},
		},
	},
	plugins: [require("tailwindcss-animate"), require("@tailwindcss/typography")],
};
