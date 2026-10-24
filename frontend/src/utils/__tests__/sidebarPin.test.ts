import { describe, expect, it } from "vitest";
import {
  CAN_HOVER_QUERY,
  RAIL_CLOSE_DELAY_MS,
  RAIL_OPEN_DELAY_MS,
  effectivePinned,
  isRailMode,
  nextPinned,
} from "../sidebarPin";



describe("isRailMode", () => {
  const cases: Array<[boolean | null | undefined, boolean, boolean, boolean]> = [
    // pinned, onInstallPage, canHover -> rail?
    // Automatic (the default): unchanged from before the setting existed.
    [undefined, false, true, false],
    [undefined, true, true, true],
    [null, false, true, false],
    [null, true, true, true],
    // Pinned open: open everywhere, the Install Schedule included.
    [true, false, true, false],
    [true, true, true, false],
    [true, true, false, false],
    // Unpinned: the rail everywhere, on a device that can hover.
    [false, false, true, true],
    [false, true, true, true],
    // ...but a device that can't hover falls back to automatic.
    [false, false, false, false],
    [false, true, false, true],
  ];
  it.each(cases)("pinned=%s install=%s hover=%s -> rail %s", (pinned, onInstallPage, canHover, rail) => {
    expect(isRailMode({ pinned, onInstallPage, canHover })).toBe(rail);
  });
});

describe("effectivePinned", () => {
  it("ignores an explicit unpin where hover can't reopen the rail", () => {
    expect(effectivePinned({ pinned: false, canHover: false })).toBeUndefined();
    expect(effectivePinned({ pinned: false, canHover: true })).toBe(false);
    expect(effectivePinned({ pinned: true, canHover: false })).toBe(true);
    expect(effectivePinned({ pinned: undefined, canHover: true })).toBeUndefined();
  });
});

describe("nextPinned", () => {
  it("always flips what the user sees", () => {
    expect(nextPinned(true)).toBe(true); // folded -> pin open
    expect(nextPinned(false)).toBe(false); // open -> fold to the rail
  });
});

describe("timing and media query", () => {
  it("opens a little faster than it closes, both short", () => {
    expect(RAIL_OPEN_DELAY_MS).toBe(150);
    expect(RAIL_CLOSE_DELAY_MS).toBe(300);
  });
  it("asks for a real hover pointer", () => {
    expect(CAN_HOVER_QUERY).toBe("(hover: hover) and (pointer: fine)");
  });
});
