import autoprefixer from "autoprefixer";
import tailwindcss from "tailwindcss";

/**
 * Printing uses the desktop layout (user, 2026-10-17: "every page ... when I
 * push Command P, to print the page I'm on ... everything on the page that I
 * can scroll up and down and see").
 *
 * A printed page is only ~740 CSS px wide (Letter, default margins), so the
 * browser evaluates breakpoints against that and printed the phone/tablet
 * layout -- the one that drops the desktop's detail panes and table columns
 * (Form responses printed its list but not the open response; Clients lost
 * its Last updated column). So the sm / md / lg breakpoints also match in
 * print, and the phone-only max-width rules don't. xl / 2xl stay width-based:
 * below them pages show the same data as cards, which fit the paper better.
 * Done here, on the generated CSS, rather than in tailwind.config's `screens`
 * because object/raw screens would switch off the min-[...] variants.
 */
const DESKTOP_MIN = /^\(min-width:\s*(640|768|1024)px\)$/;
const PHONE_MAX = /^\(max-width:\s*(639|767|1023)(\.\d+)?px\)$/;

const printUsesDesktopBreakpoints = () => ({
  postcssPlugin: "ll-print-desktop-breakpoints",
  OnceExit(root) {
    root.walkAtRules("media", (rule) => {
      const params = rule.params.trim();
      if (DESKTOP_MIN.test(params)) rule.params = `${params}, print`;
      else if (PHONE_MAX.test(params)) rule.params = `screen and ${params}`;
    });
  },
});
printUsesDesktopBreakpoints.postcss = true;

export default {
  plugins: [autoprefixer(), tailwindcss(), printUsesDesktopBreakpoints()],
};
