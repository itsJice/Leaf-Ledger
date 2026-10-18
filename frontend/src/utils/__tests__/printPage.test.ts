import { describe, expect, it } from "vitest";
import postcss from "postcss";
import config from "../../../postcss.config.js";
import { fitScale, isPrintShortcut, needsLandscape, PRINT_ATTR, PRINT_ZOOM, scopeDocumentCss } from "../printPage";
import { readSrc } from "./source-text";

const key = (k: string, mods: Partial<KeyboardEvent> = {}) =>
  ({ key: k, metaKey: false, ctrlKey: false, altKey: false, shiftKey: false, ...mods }) as KeyboardEvent;

describe("isPrintShortcut", () => {
  it("is Cmd+P and Ctrl+P, either case", () => {
    expect(isPrintShortcut(key("p", { metaKey: true }))).toBe(true);
    expect(isPrintShortcut(key("P", { ctrlKey: true }))).toBe(true);
  });
  it("is not plain P or the Shift/Alt variants", () => {
    expect(isPrintShortcut(key("p"))).toBe(false);
    expect(isPrintShortcut(key("p", { metaKey: true, shiftKey: true }))).toBe(false);
    expect(isPrintShortcut(key("p", { metaKey: true, altKey: true }))).toBe(false);
    expect(isPrintShortcut(key("o", { metaKey: true }))).toBe(false);
  });
});

describe("scopeDocumentCss (the schedule's styles inside a shadow root)", () => {
  it("swaps html/body/:root in selectors only", () => {
    const out = scopeDocumentCss(
      ":root{--page:#fff}html,body{height:100%}body.apple #app{display:grid}.x{content:'body html'}",
    );
    expect(out).toContain(":host{--page:#fff}");
    expect(out).toContain(".ll-frame-html,.ll-frame-body{height:100%}");
    expect(out).toContain(".ll-frame-body.apple #app{display:grid}");
    expect(out).toContain(".x{content:'body html'}"); // declarations untouched
  });
  it("reaches into @media print and leaves keyframes and ids alone", () => {
    const out = scopeDocumentCss(
      "@media print{html body #main{display:block}#bodywrap{color:red}}@keyframes body{from{opacity:0}to{opacity:1}}",
    );
    expect(out).toContain("@media print{.ll-frame-html .ll-frame-body #main{display:block}#bodywrap{color:red}}");
    expect(out).toContain("@keyframes body{from{opacity:0}to{opacity:1}}");
  });
  it("drops comments (braces inside them can't derail it)", () => {
    expect(scopeDocumentCss("/* body { */body{margin:0}")).toBe(".ll-frame-body{margin:0}");
  });
});

describe("fitting sideways scrollers to the paper", () => {
  it("leaves content that already fits alone", () => {
    expect(fitScale(0.5, 300, false)).toBe(1);
  });
  it("shrinks a wide comparison board to the page width", () => {
    const z = fitScale(0.7, 900, false);
    expect(z).toBeGreaterThan(0.6);
    expect(z).toBeLessThan(1);
    expect(needsLandscape(0.7, 900)).toBe(false);
  });
  it("turns very wide tables landscape, and never below 40%", () => {
    expect(needsLandscape(0.95, 2200)).toBe(true);
    expect(fitScale(0.95, 2200, true)).toBeGreaterThan(fitScale(0.95, 2200, false));
    expect(fitScale(0.95, 9000, true)).toBe(0.4);
  });
});

describe("print breakpoints (postcss.config.js)", () => {
  const run = async (css: string) => (await postcss(config.plugins.slice(2)).process(css, { from: undefined })).css;
  it("sm/md/lg also match in print, so print shows the desktop layout", async () => {
    const out = await run("@media (min-width: 1024px){.a{display:block}}@media (min-width: 768px){.b{x:1}}");
    expect(out).toContain("@media (min-width: 1024px), print{.a");
    expect(out).toContain("@media (min-width: 768px), print{.b");
  });
  it("xl / 2xl and arbitrary min-[...] stay width-based; phone max-width rules are screen-only", async () => {
    const out = await run("@media (min-width: 1280px){.a{x:1}}@media (min-width: 360px){.b{x:1}}@media (max-width: 767px){.c{x:1}}");
    expect(out).toContain("@media (min-width: 1280px){.a");
    expect(out).toContain("@media (min-width: 360px){.b");
    expect(out).toContain("@media screen and (max-width: 767px){.c");
  });
});

describe("wiring", () => {
  it("styles every mark printPage.ts sets", () => {
    const css = readSrc("index.css");
    for (const attr of Object.values(PRINT_ATTR)) expect(css, attr).toContain(`[${attr}`);
  });
  it("index.css zooms the page area by PRINT_ZOOM", () => {
    expect(readSrc("index.css")).toContain(`zoom: ${PRINT_ZOOM};`);
  });
  it("the app installs it, and the schedule forwards Cmd+P and registers the File > Print copy", () => {
    expect(readSrc("main.tsx")).toContain("installPrintSupport()");
    const page = readSrc("pages/InstallSchedule.tsx");
    expect(page).toContain("printWithoutFallback(");
    expect(page).toContain("setPrintFallback(() => copyFrameForPrint(frameRef.current))");
  });
});
