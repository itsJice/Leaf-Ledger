import type { DesignStyle } from "utils/ornamentRecipe";

// Links from the Tree Install page to its printouts (pages/TreeInstallPrint.tsx):
// the 2-page Tree Design Map and the paper cone model, for the tree as picked.

export type TreeSheet = "design" | "cone";

/** The query string the Tree Install page builds for these sheets. */
export interface PrintParams {
  heightFt: number;
  widthIn: number;
  colorCount: number;
  style: DesignStyle;
  wholePacks: boolean;
  colors: string[];
  ribbonA: string;
  ribbonB: string;
  topper: string;
}

export function treeInstallPrintUrl(sheet: TreeSheet, p: PrintParams): string {
  const q = new URLSearchParams({
    sheet,
    h: String(p.heightFt),
    w: String(p.widthIn),
    n: String(p.colorCount),
    style: p.style,
    packs: p.wholePacks ? "1" : "0",
    c: p.colors.map((c) => c.replace("#", "")).join(","),
    a: p.ribbonA.replace("#", ""),
    b: p.ribbonB.replace("#", ""),
    t: p.topper.replace("#", ""),
  });
  return `/tree-install/print?${q.toString()}`;
}

