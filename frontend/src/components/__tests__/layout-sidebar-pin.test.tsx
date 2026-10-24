/**
 * The "Keep menu open" pin on the app shell's sidebar (components/Layout.tsx,
 * utils/sidebarPin.ts). vitest runs without a DOM here, so this renders the
 * shell to static markup and checks what the first paint looks like for each
 * pin state: the hover/focus behaviour itself is checked by hand in the
 * browser (screenshots in the PR).
 */
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { StaticRouter } from "react-router-dom/server";

const h = vi.hoisted(() => ({
  pinned: undefined as boolean | null | undefined,
  canHover: true,
  me: { email: "a@b.c", role: "admin", isAdmin: true, isSuperAdmin: false, fieldOnly: false, viewOnly: false } as Record<string, unknown>,
}));

vi.mock("app", () => ({ apiClient: { request: vi.fn(), list_arrangements: vi.fn() }, APP_BASE_PATH: "/" }));
vi.mock("utils/apiFetch", () => ({ apiFetch: vi.fn() }));
vi.mock("app/auth/AuthProvider", () => ({
  useAuth: () => ({ user: { email: "a@b.c", user_metadata: {} }, signOut: vi.fn() }),
}));
vi.mock("components/FeedbackWidget", () => ({ default: () => null }));
vi.mock("utils/theme", () => ({ useTheme: () => ({ mode: "system", setMode: vi.fn() }) }));
vi.mock("utils/me", () => ({
  currentMe: () => h.me,
  appHome: () => "/",
  pageAllowed: () => true,
}));
vi.mock("utils/preferences", () => ({
  usePreferences: () => ({
    prefs: {
      sidebar: { order: [], hidden: [], ...(h.pinned === undefined ? {} : { pinned: h.pinned }) },
      theme: { mode: "system", accent: "emerald" },
    },
    save: vi.fn(),
    reset: vi.fn(),
    loading: false,
    saving: false,
  }),
}));
vi.mock("utils/sidebarPin", async (importOriginal) => {
  const actual = await importOriginal<typeof import("utils/sidebarPin")>();
  return { ...actual, useCanHover: () => h.canHover };
});

import "../../test/setup";
import Layout from "../Layout";

function render(path: string): string {
  return renderToStaticMarkup(
    <StaticRouter location={path}>
      <Layout><div data-page>page</div></Layout>
    </StaticRouter>,
  );
}

const asideTag = (html: string) => html.match(/<aside[^>]*>/)?.[0] ?? "";
const pinButton = (html: string) => html.match(/<button[^>]*data-ll-pin[^>]*>/)?.[0] ?? null;
const contentTag = (html: string) => html.match(/<div data-scroll-root[^>]*>/)?.[0] ?? "";

beforeEach(() => {
  h.pinned = undefined;
  h.canHover = true;
  h.me = { ...h.me, fieldOnly: false, viewOnly: false };
});

describe("automatic (no pin saved): unchanged behaviour", () => {
  it("is open and pushes the page on ordinary pages", () => {
    const html = render("/jobs");
    expect(asideTag(html)).not.toContain("data-ll-rail");
    expect(contentTag(html)).toContain("lg:ml-60");
    const pin = pinButton(html)!;
    expect(pin).toContain('aria-pressed="true"');
    expect(pin).toContain('aria-label="Keep menu open"');
  });

  it("still folds to the rail on the Install Schedule", () => {
    const html = render("/install-schedule");
    expect(asideTag(html)).toContain("data-ll-rail");
    expect(contentTag(html)).toContain("lg:ml-[68px]");
  });
});

describe("pinned open", () => {
  it("stays open on the Install Schedule too", () => {
    h.pinned = true;
    const html = render("/install-schedule");
    expect(asideTag(html)).not.toContain("data-ll-rail");
    expect(contentTag(html)).toContain("lg:ml-60");
    expect(pinButton(html)).toContain('aria-pressed="true"');
  });
});

describe("unpinned", () => {
  it("folds to the icon rail on every page, and the page keeps the rail's width", () => {
    h.pinned = false;
    for (const path of ["/jobs", "/install-schedule", "/clients"]) {
      const html = render(path);
      expect(asideTag(html), path).toContain('data-ll-rail="folded"');
      expect(asideTag(html), path).toContain("lg:w-[68px]");
      // The overlay never reflows the page: the margin is the rail's either way.
      expect(contentTag(html), path).toContain("lg:ml-[68px]");
      // Folded, the labels are hidden on desktop and the pin hides with them;
      // it comes back when the rail slides open.
      expect(pinButton(html), path).toBeNull();
    }
  });

  it("falls back to automatic on a device that can't hover, with no pin control", () => {
    h.pinned = false;
    h.canHover = false;
    expect(asideTag(render("/jobs"))).not.toContain("data-ll-rail");
    expect(asideTag(render("/install-schedule"))).toContain("data-ll-rail");
    expect(pinButton(render("/jobs"))).toBeNull();
  });
});

describe("where the pin never appears", () => {
  it("is desktop-only (hidden below lg, where the drawer is)", () => {
    const pin = pinButton(render("/jobs"))!;
    expect(pin).toMatch(/\bhidden\b/);
    expect(pin).toContain("lg:flex");
  });

  it("is absent from the warehouse display and field layouts", () => {
    h.me = { ...h.me, viewOnly: true };
    const display = render("/install-schedule");
    expect(display).not.toContain("<aside");
    expect(pinButton(display)).toBeNull();
    h.me = { ...h.me, viewOnly: false, fieldOnly: true };
    const field = render("/shifts");
    expect(field).not.toContain("<aside");
    expect(pinButton(field)).toBeNull();
  });
});
