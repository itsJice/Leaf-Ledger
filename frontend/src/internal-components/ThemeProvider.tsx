import { createContext, useContext } from "react";
import { useTheme as useAppTheme } from "utils/theme";

/**
 * Scaffolding kept for its context shape only.
 *
 * This used to own the `light`/`dark` class on `<html>`, driven by its own
 * `leaf-ledger:ui-theme` localStorage key. That made it a second, competing
 * source of truth: its mount effect ran `classList.remove("light", "dark")` and
 * re-added its own value, which stripped the class that the pre-paint snippet
 * and `utils/theme` had already set — dark mode simply could not stay on. Worse,
 * effects run child-first, so it clobbered the correct class *after* the app had
 * applied it, and nothing re-triggered a correction.
 *
 * Appearance now lives in one place: per-account preferences
 * (`utils/preferences`) reflected onto `<html>` by `utils/theme`. This component
 * no longer touches the DOM; it just re-publishes the resolved theme on the old
 * context so `@/hooks/use-theme` keeps working, and `setTheme` forwards to the
 * real writer.
 */

type Theme = "dark" | "light" | "system";

type ThemeProviderProps = {
	children: React.ReactNode;
	/** Ignored — the stored preference is authoritative. */
	defaultTheme?: Theme;
	/** Ignored — kept so existing call sites still typecheck. */
	storageKey?: string;
};

type ThemeProviderState = {
	theme: Theme;
	setTheme: (theme: Theme) => void;
};

const initialState: ThemeProviderState = {
	theme: "system",
	setTheme: () => null,
};

export const ThemeProviderContext =
	createContext<ThemeProviderState>(initialState);

export function ThemeProvider({
	children,
	defaultTheme: _defaultTheme,
	storageKey: _storageKey,
	...props
}: ThemeProviderProps) {
	const { mode, setMode } = useAppTheme();

	const value: ThemeProviderState = {
		theme: mode,
		setTheme: setMode,
	};

	return (
		<ThemeProviderContext.Provider {...props} value={value}>
			{children}
		</ThemeProviderContext.Provider>
	);
}

export const useTheme = () => {
	const context = useContext(ThemeProviderContext);

	if (context === undefined)
		throw new Error("useTheme must be used within a ThemeProvider");

	return context;
};
