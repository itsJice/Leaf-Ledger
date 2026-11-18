import { describe, expect, it } from "vitest";
import {
  TRAIL_MAX_STEPS,
  dedupeKey,
  freezeGap,
  isChunkLoadErrorMessage,
  isIgnorableError,
  isLoggableStatus,
  isQuietUrl,
  pathOnly,
  pruneTrail,
  scrubText,
  tokenTiming,
  type TrailStep,
} from "utils/eventLog";
import { withFrameWatch } from "utils/scheduleFrameWatch";

const JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.c2lnbmF0dXJlLXZhbHVl";

describe("scrubText", () => {
  it("masks tokens, secrets and query strings", () => {
    const out = scrubText(
      `Bearer ${JWT} token=${JWT} password: hunter2 GET https://x.com/api/feed.ics?token=s3cret /clients?client=Allums`,
    );
    expect(out).not.toContain(JWT);
    expect(out).not.toContain("hunter2");
    expect(out).not.toContain("s3cret");
    expect(out).not.toContain("Allums");
    expect(out).toContain("https://x.com/api/feed.ics");
    expect(out).toContain("/clients");
  });

  it("caps length and never throws", () => {
    expect(scrubText("x".repeat(50), 10)).toHaveLength(10);
    const bad = { toString: () => { throw new Error("boom"); } };
    expect(scrubText(bad)).toBe("");
  });
});

describe("pathOnly", () => {
  it.each([
    ["https://leaf-ledger.onrender.com/clients?client=Allums#x", "/clients"],
    ["/set-password#access_token=abc", "/set-password"],
    ["/api/share/AbC123/view", "/api/share/[hidden]/view"],
    ["/install-schedule", "/install-schedule"],
    [null, ""],
  ])("%s -> %s", (raw, expected) => {
    expect(pathOnly(raw)).toBe(expected);
  });
});

describe("pruneTrail", () => {
  const now = Date.parse("2026-11-16T21:00:00Z");
  const step = (minutesAgo: number, n: number): TrailStep => ({
    t: new Date(now - minutesAgo * 60000).toISOString(),
    type: "click",
    label: `#${n}`,
  });

  it("keeps the last 10 minutes", () => {
    const out = pruneTrail([step(11, 1), step(9, 2), step(1, 3)], now);
    expect(out.map((s) => s.label)).toEqual(["#2", "#3"]);
  });

  it("keeps at most 50 steps, newest", () => {
    const many = Array.from({ length: 70 }, (_, i) => step(5, i));
    const out = pruneTrail(many, now);
    expect(out).toHaveLength(TRAIL_MAX_STEPS);
    expect(out[out.length - 1].label).toBe("#69");
  });

  it("drops steps with bad times", () => {
    expect(pruneTrail([{ t: "nope", type: "page", label: "x" }], now)).toEqual([]);
  });
});

describe("what gets logged", () => {
  it("logs the statuses past breakages hid", () => {
    for (const s of [500, 502, 401, 403, 409, 408, 413, 429]) expect(isLoggableStatus(s)).toBe(true);
    for (const s of [200, 204, 400, 404, 422]) expect(isLoggableStatus(s)).toBe(false);
  });

  it("never logs about the log", () => {
    expect(isQuietUrl("/api/app-events")).toBe(true);
    expect(isQuietUrl("/api/feedback")).toBe(false);
  });

  it("ignores noise and leaves stale chunks to lazyWithReload", () => {
    expect(isIgnorableError("Script error.")).toBe(true);
    expect(isIgnorableError("ResizeObserver loop completed with undelivered notifications.")).toBe(true);
    expect(isIgnorableError("Failed to fetch dynamically imported module: /assets/Clients-abc.js")).toBe(true);
    expect(isIgnorableError("Cannot read properties of undefined (reading 'days')")).toBe(false);
    expect(isChunkLoadErrorMessage("Importing a module script failed.")).toBe(true);
  });

  it("dedupes on kind and message", () => {
    expect(dedupeKey({ kind: "error", message: "a" })).toBe(dedupeKey({ kind: "error", message: "a" }));
    expect(dedupeKey({ kind: "error", message: "a" })).not.toBe(dedupeKey({ kind: "crash", message: "a" }));
  });
});

describe("freezeGap", () => {
  it("reports a 5s+ stall while on screen", () => {
    expect(freezeGap(0, 7000, true, true)).toBe(6000);
  });
  it("ignores small delays, hidden tabs and sleep", () => {
    expect(freezeGap(0, 3000, true, true)).toBeNull();
    expect(freezeGap(0, 7000, false, true)).toBeNull();
    expect(freezeGap(0, 7000, true, false)).toBeNull();
    expect(freezeGap(0, 5 * 60000, true, true)).toBeNull();
  });
});

describe("tokenTiming", () => {
  it("reads iat/exp without sending the token", () => {
    const payload = btoa(JSON.stringify({ iat: 1000, exp: 4600 })).replace(/=+$/, "");
    const header = `Bearer eyJhbGciOiJIUzI1NiJ9.${payload}.sig`;
    expect(tokenTiming(header, 2000 * 1000)).toEqual({ token_age_s: 1000, token_expires_in_s: 2600 });
  });
  it("is empty for junk", () => {
    expect(tokenTiming("Bearer nope", 0)).toEqual({});
  });
});

describe("withFrameWatch", () => {
  it("puts the watcher first in <head>, before the schedule's own scripts", () => {
    const out = withFrameWatch('<!DOCTYPE html><html><head lang="en"><script>window.TBDG_HOSTED=true;</script></head></html>');
    const watcher = out.indexOf("ll-frame-event");
    expect(watcher).toBeGreaterThan(out.indexOf('<head lang="en">'));
    expect(watcher).toBeLessThan(out.indexOf("TBDG_HOSTED"));
  });
  it("prepends when there's no <head>", () => {
    expect(withFrameWatch("<p>hi</p>").startsWith("<script>")).toBe(true);
  });
  it("never sends bodies or headers", () => {
    const out = withFrameWatch("<head></head>");
    expect(out).not.toMatch(/\.body\b|headers|Authorization/);
  });
});

describe("schedule reports (part 2)", () => {
  it("accepts only the schedule's own kinds", async () => {
    const { FRAME_KINDS } = await import("utils/scheduleFrameWatch");
    expect([...FRAME_KINDS].sort()).toEqual(["blank", "error", "save_blocked", "save_conflict"]);
  });

  it("keeps the schedule's detail flat, small and scrubbed", async () => {
    const { frameDetail } = await import("utils/scheduleFrameWatch");
    const out = frameDetail({
      daysInData: 40,
      booted: true,
      lastSaveOk: null,
      banner: `token=${JWT}`,
      nested: { name: "Allums" },
      list: ["Allums"],
    });
    expect(out).toEqual({ daysInData: 40, booted: true, lastSaveOk: null, banner: "token=[hidden]" });
    expect(frameDetail("junk")).toEqual({});
  });
});
