#!/usr/bin/env python3
"""
Normalization layer — the shared foundation for the ornament matcher AND the
catalog search engine.

Merges every evidence source into one canonical profile per product:
    structured columns  →  learned SKU grammar  →  name/description parse
Highest-confidence source wins; every source value is kept in provenance;
conflicts are flagged (never dropped). Strictly ADDITIVE — reads the enriched
findings CSVs (which already carry `learned_*` columns) and writes NEW
`*_normalized.csv` files with new `norm_*` columns appended.

Output per product:
    norm_class · norm_size_in · norm_color · norm_color_label · norm_finish
    norm_pack_qty · canonical_key · norm_confidence · needs_review · norm_provenance

Usage:
    python normalize_catalog.py
"""
from __future__ import annotations
import csv, json, re, sys, collections
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from sku_grammar_learner import (  # reuse the exact vocab/parsers  # noqa: E402
    color_family, color_from_code, size_in, finish_of, COLOR_KW,
)

ENRICHED = HERE.parent / "outputs" / "sku-grammar" / "enriched"
OUT = HERE.parent / "outputs" / "normalized"

# ── product class from name/type ──────────────────────────────────────────────
CLASS_KW = [
    ("ball_ornament", ["ball ornament", "ball orn", "ornament ball", "glass ball", "shatterproof ball",
                        "finish ball", "ball asst", "ball drilled", "ball, ", "ball "]),
    ("finial_ornament", ["finial"]),
    ("drop_ornament", ["drop ornament", "teardrop", "icicle"]),
    ("ornament_other", ["ornament", "bauble"]),
    ("pick", ["pick", "spray", "stem"]),
    ("garland", ["garland"]),
    ("wreath", ["wreath"]),
    ("tree", ["tree"]),
    ("ribbon", ["ribbon", "yds", "yard"]),
    ("floral", ["flower", "floral", "rose", "hydrangea", "peony", "bush", "fern", "foliage"]),
    ("container", ["vase", "pot", "planter", "container", "urn", "bowl"]),
]


def classify(name: str | None, ptype: str | None) -> str | None:
    for source in (ptype, name):
        t = (source or "").lower()
        for cls, kws in CLASS_KW:
            if any(k in t for k in kws):
                return cls
    return None


# specific color from a name, ignoring the "assortment/multi" catch-all so a
# stated color (e.g. "Emerald") beats the "4-Finish Asst" wording.
_SPECIFIC = [(fam, kws) for fam, kws in COLOR_KW if fam != "Multi"]


def specific_color(text: str | None) -> str | None:
    t = (text or "").lower()
    for fam, kws in _SPECIFIC:
        if any(k in t for k in kws):
            return fam
    return None


def size_bucket(v: float | None) -> str:
    if v is None:
        return "?"
    return f"{round(v * 4) / 4:g}"  # nearest 0.25"


def merge(candidates):
    """candidates: list[(value, confidence, source)] (value may be None).
    Returns (best_value, best_conf, provenance_dict, conflict_bool)."""
    seen = [(v, c, s) for v, c, s in candidates if v is not None]
    prov = {s: {"value": v, "conf": round(c, 3)} for v, c, s in seen}
    if not seen:
        return None, 0.0, prov, False
    seen.sort(key=lambda x: x[1], reverse=True)
    best_v, best_c, _ = seen[0]
    # conflict = two sources at decent confidence disagree with the winner
    conflict = any(str(v) != str(best_v) and c >= 0.6 for v, c, s in seen)
    return best_v, best_c, prov, conflict


def norm_row(row, ci):
    def col(name):
        i = ci.get(name)
        return row[i] if i is not None and i < len(row) else None

    name, desc = col("product_name"), col("description")
    ptype = col("product_type")

    # ── color ── name (specific) > structured column > learned SKU > desc > name(multi)
    lc = col("learned_color")
    lc_conf = float(col("learned_color_conf") or 0) if col("learned_color_conf") else 0.0
    color, ccf, cprov, cconf = merge([
        (specific_color(name), 0.92, "name"),
        (color_from_code(col("color")), 0.9, "column"),
        (lc, lc_conf, "sku"),
        (specific_color(desc), 0.72, "desc"),
        (color_family(name), 0.6, "name_multi"),
    ])
    color_label = (col("color") or "").strip() or None

    # ── size ── name > dimension columns > learned SKU
    ls = col("learned_size")
    ls_conf = float(col("learned_size_conf") or 0) if col("learned_size_conf") else 0.0
    dim = None
    for dc in ("diameter_in", "width_in", "height_in", "dimensions_in"):
        v = col(dc)
        if v:
            m = re.search(r'\d+(\.\d+)?', str(v))
            if m:
                dim = float(m.group(0)); break
    size, scf, sprov, sconf = merge([
        (size_in(name), 0.9, "name"),
        (dim, 0.8, "column"),
        (float(ls) if ls else None, ls_conf, "sku"),
    ])

    # ── finish ── name > learned SKU > desc
    lf = col("learned_finish")
    lf_conf = float(col("learned_finish_conf") or 0) if col("learned_finish_conf") else 0.0
    finish, fcf, fprov, fconf = merge([
        (finish_of(name), 0.9, "name"),
        (lf, lf_conf, "sku"),
        (finish_of(desc), 0.7, "desc"),
    ])

    # ── pack ──
    pack = None
    for pc in ("box_quantity", "case_quantity", "piece_count", "case_qty"):
        v = col(pc)
        if v and str(v).replace(".0", "").isdigit() and int(float(v)) > 0:
            pack = int(float(v)); break
    if pack is None and name:
        m = re.search(r'(\d+)\s*(?:/|per\s)\s*(?:bx|box|bag|bg|pk|pack|set)', name, re.I)
        if m:
            pack = int(m.group(1))

    cls = classify(name, ptype)
    canonical_key = "|".join([
        cls or "?", size_bucket(size),
        (color or "?").lower(), (finish or "any").lower(),
    ])
    confs = [c for c in (ccf, scf, fcf) if c]
    confidence = round(sum(confs) / len(confs), 3) if confs else 0.0
    needs_review = confidence < 0.6 or cconf or sconf or fconf
    provenance = {"color": cprov, "size": sprov, "finish": fprov}

    return {
        "norm_class": cls or "",
        "norm_size_in": size if size is not None else "",
        "norm_color": color or "",
        "norm_color_label": color_label or "",
        "norm_finish": finish or "",
        "norm_pack_qty": pack if pack is not None else "",
        "canonical_key": canonical_key,
        "norm_confidence": confidence,
        "needs_review": "yes" if needs_review else "",
        "norm_provenance": json.dumps(provenance, separators=(",", ":")),
    }


NORM_COLS = ["norm_class", "norm_size_in", "norm_color", "norm_color_label", "norm_finish",
             "norm_pack_qty", "canonical_key", "norm_confidence", "needs_review", "norm_provenance"]


def process(path, agg):
    with open(path, newline="") as f:
        r = csv.reader(f)
        hdr = next(r)
        ci = {h: i for i, h in enumerate(hdr)}
        OUT.mkdir(parents=True, exist_ok=True)
        dst = OUT / path.name.replace("_enriched", "_normalized")
        with open(dst, "w", newline="") as g:
            w = csv.writer(g)
            w.writerow(hdr + NORM_COLS)
            n = ncls = ncol = nsz = nfin = nrev = 0
            for row in r:
                nr = norm_row(row, ci)
                w.writerow(row + [nr[c] for c in NORM_COLS])
                n += 1
                ncls += bool(nr["norm_class"]); ncol += bool(nr["norm_color"])
                nsz += nr["norm_size_in"] != ""; nfin += bool(nr["norm_finish"])
                nrev += nr["needs_review"] == "yes"
                if nr["norm_class"] == "ball_ornament":
                    agg["ball"] += 1
    sup = path.name.split("_")[0]
    return {"supplier": sup, "n": n, "class%": round(100 * ncls / n) if n else 0,
            "color%": round(100 * ncol / n) if n else 0, "size%": round(100 * nsz / n) if n else 0,
            "finish%": round(100 * nfin / n) if n else 0, "review%": round(100 * nrev / n) if n else 0}


def main():
    files = sorted(ENRICHED.glob("*_enriched.csv"))
    if not files:
        print("No enriched CSVs — run sku_grammar_learner.py first."); return
    agg = collections.Counter()
    stats = []
    for p in files:
        s = process(p, agg)
        stats.append(s)
        print(f"  {s['supplier']:<22} {s['n']:>6}  class {s['class%']:>3}%  color {s['color%']:>3}%  "
              f"size {s['size%']:>3}%  finish {s['finish%']:>3}%  review {s['review%']:>3}%")
    total = sum(s["n"] for s in stats)
    print(f"\n  {total:,} products normalized · {agg['ball']:,} ball ornaments · "
          f"→ {OUT}/*_normalized.csv (additive)")


if __name__ == "__main__":
    main()
