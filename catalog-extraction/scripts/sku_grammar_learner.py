#!/usr/bin/env python3
"""
SKU-grammar learner.

Learns each supplier's SKU encoding *from the full catalog* — no hand-written
rules — by correlating SKU substrings/tokens against attributes we can already
read from the product name, description, and columns. Then decodes every SKU,
recovering attributes (esp. color) that the name doesn't state.

Strictly ADDITIVE: original spreadsheets are never modified. Output is new
files only — a learned grammar (JSON), a decodability report (Markdown), and
enriched CSVs (original columns + new `learned_*` columns with provenance).

Usage:
    python sku_grammar_learner.py            # learn + report + enriched CSVs
    python sku_grammar_learner.py --no-csv   # skip enriched CSVs (faster)
"""
from __future__ import annotations
import csv, json, re, sys, collections
from pathlib import Path

FINDINGS = Path("/Users/justice/Documents/From Selenium To Leaf & Ledger/THE FINDINGS")
OUT = Path(__file__).resolve().parents[1] / "outputs" / "sku-grammar"

# ── attribute vocabularies ────────────────────────────────────────────────────
COLOR_KW = [
    ("Multi", ["multi", "assorted", "asst", "rainbow", "variegated", "two-tone", "two tone", "ombre"]),
    ("Green", ["green", "olive", "sage", "moss", "emerald", "mint", "lime", "hunter", "celadon", "fern", "forest"]),
    ("White", ["white", "snow", "frost"]),
    ("Cream", ["cream", "ivory", "bone", "vanilla", "almond"]),
    ("Burgundy", ["burgundy", "wine", "maroon", "merlot", "cranberry", "oxblood"]),
    ("Red", ["red", "crimson", "scarlet", "cardinal", "cherry", "ruby"]),
    ("Pink", ["pink", "blush", "fuchsia", "magenta"]),
    ("Rose", ["rose gold", "rose"]),
    ("Orange", ["orange", "rust", "terracotta", "terra cotta", "pumpkin", "tangerine", "copper", "amber"]),
    ("Yellow", ["yellow", "mustard", "lemon", "goldenrod"]),
    ("Gold", ["gold", "champagne"]),
    ("Blue", ["blue", "navy", "teal", "turquoise", "aqua", "cobalt", "denim", "sky", "indigo", "periwinkle"]),
    ("Purple", ["purple", "lavender", "lilac", "plum", "violet", "eggplant", "mauve", "orchid", "amethyst"]),
    ("Brown", ["brown", "chocolate", "coffee", "espresso", "mocha", "walnut", "chestnut", "cocoa"]),
    ("Natural", ["natural", "beige", "khaki", "sand", "wheat", "camel", "taupe", "burlap", "linen", "tan", "kraft"]),
    ("Silver", ["silver", "platinum", "pewter", "nickel", "chrome"]),
    ("Gray", ["gray", "grey", "charcoal", "slate", "ash", "smoke", "graphite"]),
    ("Black", ["black", "onyx", "ebony", "jet"]),
    ("Bronze", ["bronze", "brass"]),
    ("Clear", ["clear", "crystal", "transparent", "translucent"]),
]
# short color codes seen in dedicated color columns / SKU tokens
COLOR_CODE = {
    "gr": "Green", "wh": "White", "re": "Red", "rd": "Red", "bl": "Blue", "pk": "Pink",
    "br": "Brown", "bk": "Black", "go": "Gold", "ye": "Yellow", "cr": "Cream", "iv": "Cream",
    "si": "Silver", "sv": "Silver", "be": "Natural", "na": "Natural", "or": "Orange", "pu": "Purple",
    "gy": "Gray", "mx": "Multi", "tt": "Multi", "bu": "Burgundy", "bg": "Burgundy", "pl": "Purple",
    "tl": "Blue", "aq": "Blue", "cp": "Bronze", "brz": "Bronze",
}
FINISH_KW = {
    "Shiny": ["shiny", "glossy", "gloss"], "Matte": ["matte", "flat"], "Glitter": ["glitter", "glittered"],
    "Pearl": ["pearl", "pearlized"], "Sequin": ["sequin", "sequined"], "Flocked": ["flocked"],
    "Frosted": ["frosted", "frost"], "Iridescent": ["iridescent", "irid"], "Mercury": ["mercury"],
    "Candy": ["candy"], "Metallic": ["metallic"], "Velvet": ["velvet"],
}
SIZE_RE = re.compile(r'(\d+(?:\.\d+)?)\s*("|inch|in\b)', re.I)
MM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*mm', re.I)
CM_RE = re.compile(r'(\d+(?:\.\d+)?)\s*cm', re.I)


def color_family(text: str | None) -> str | None:
    t = (text or "").lower()
    for fam, kws in COLOR_KW:
        if any(k in t for k in kws):
            return fam
    return None


def color_from_code(val: str | None) -> str | None:
    if not val:
        return None
    tok = re.sub(r"[^a-z]", "", str(val).lower())
    if tok in COLOR_CODE:
        return COLOR_CODE[tok]
    return color_family(val)


def size_in(name: str | None) -> float | None:
    if not name:
        return None
    m = SIZE_RE.search(name)
    if m:
        v = float(m.group(1))
        return v if 0.4 <= v <= 60 else None
    m = MM_RE.search(name)
    if m:
        return round(float(m.group(1)) / 25.4, 2)
    m = CM_RE.search(name)
    if m:
        return round(float(m.group(1)) / 2.54, 2)
    return None


def finish_of(text: str | None) -> str | None:
    t = (text or "").lower()
    for fam, kws in FINISH_KW.items():
        if any(k in t for k in kws):
            return fam
    return None


# ── SKU feature extractors ────────────────────────────────────────────────────
def lead_alpha(s: str) -> str:
    m = re.match(r'^[A-Za-z]+', s)
    return m.group(0) if m else ""


def family_key(s: str) -> tuple[str, int]:
    return (lead_alpha(s), len(s))


# supplier-level, length-independent features (kind -> extractor)
TOKEN_FEATURES = {
    "prefix2": lambda s: s[:2],
    "prefix3": lambda s: s[:3],
    "last_delim_token": lambda s: (re.split(r'[.\-_/ ]', s)[-1] if re.search(r'[.\-_/ ]', s) else ""),
    "trail_alpha2": lambda s: (re.search(r'([A-Za-z]{2})$', s).group(1) if re.search(r'([A-Za-z]{2})$', s) else ""),
    "trail_alpha3": lambda s: (re.search(r'([A-Za-z]{3})$', s).group(1) if re.search(r'([A-Za-z]{3})$', s) else ""),
}


def learn_table(pairs, min_support=4, purity=0.82):
    """pairs: list[(feature_value, attr_value)] with attr_value known (not None).
    Returns (table, quality, coverage, covered_rows)."""
    groups = collections.defaultdict(collections.Counter)
    total = 0
    for fv, val in pairs:
        if val is None:
            continue
        total += 1
        if fv:
            groups[fv][val] += 1
    table = {}
    covered = correct = 0
    for fv, cnt in groups.items():
        s = sum(cnt.values())
        if s < min_support:
            continue
        top, topn = cnt.most_common(1)[0]
        if topn / s >= purity:
            table[fv] = top
            covered += s
            correct += topn
    quality = correct / covered if covered else 0.0
    coverage = covered / total if total else 0.0
    return table, quality, coverage, covered


def learn_attribute(rows, attr):
    """rows: list[(sku, known_value)]. Returns list of accepted decoders sorted by quality."""
    decoders = []
    # 1) supplier-level token features
    for kind, fn in TOKEN_FEATURES.items():
        pairs = [(fn(s), v) for s, v in rows]
        table, q, cov, covered = learn_table(pairs)
        if q >= 0.85 and covered >= 15 and len(table) >= 2:
            decoders.append({"scope": "all", "kind": kind, "table": table,
                             "quality": round(q, 3), "coverage": round(cov, 3), "n": covered})
    # 2) family-level fixed-position features
    fam_rows = collections.defaultdict(list)
    for s, v in rows:
        fam_rows[family_key(s)].append((s, v))
    for (lead, ln), frows in fam_rows.items():
        known = [(s, v) for s, v in frows if v is not None]
        if len(known) < 20 or ln > 18:
            continue
        best = None
        for i in range(0, min(ln, 15)):
            for w in (1, 2, 3):
                j = i + w
                if j > ln:
                    continue
                pairs = [(s[i:j], v) for s, v in frows]
                table, q, cov, covered = learn_table(pairs)
                if q >= 0.90 and covered >= 15 and len(table) >= 2:
                    score = q * cov
                    if best is None or score > best["_score"]:
                        best = {"scope": "family", "lead": lead, "len": ln, "kind": f"pos[{i}:{j}]",
                                "i": i, "j": j, "table": table, "quality": round(q, 3),
                                "coverage": round(cov, 3), "n": covered, "_score": score}
        if best:
            best.pop("_score")
            decoders.append(best)
    decoders.sort(key=lambda d: (d["quality"], d["n"]), reverse=True)
    return decoders


def decode(sku, decoders):
    """Return (value, confidence, source) for the best matching decoder, else (None,0,None)."""
    best = (None, 0.0, None)
    for d in decoders:
        if d["scope"] == "family":
            if lead_alpha(sku) != d["lead"] or len(sku) != d["len"]:
                continue
            fv = sku[d["i"]:d["j"]]
        else:
            fv = TOKEN_FEATURES[d["kind"]](sku)
        val = d["table"].get(fv)
        if val is not None and d["quality"] > best[1]:
            src = f'{d["kind"]}' + (f'@{d["lead"]}·len{d["len"]}' if d["scope"] == "family" else "")
            best = (val, d["quality"], src)
    return best


# ── per-file processing ───────────────────────────────────────────────────────
def load_rows(path):
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    hdr = [str(h) if h is not None else "" for h in next(it)]
    ci = {h: i for i, h in enumerate(hdr)}
    if "sku" not in ci or "product_name" not in ci:
        wb.close()
        return None, None, None
    supplier = None
    out = []
    scol = ci.get("color")
    dcol = ci.get("description")
    for r in it:
        sku = r[ci["sku"]]
        if sku is None:
            continue
        sku = str(sku)
        name = r[ci["product_name"]]
        desc = r[dcol] if dcol is not None else None
        colcell = r[scol] if scol is not None else None
        supplier = supplier or (r[ci["supplier"]] if "supplier" in ci else path.stem)
        # known attributes from NON-SKU sources
        known_color = color_from_code(colcell) or color_family(name) or color_family(desc)
        name_color = color_family(name)
        out.append({
            "sku": sku, "name": name, "desc": desc,
            "known_color": known_color, "name_color": name_color,
            "known_size": size_in(name),
            "known_finish": finish_of(name) or finish_of(desc),
            "row": r, "hdr": hdr,
        })
    wb.close()
    return supplier, hdr, out


def opaque_frac(rows):
    n = len(rows)
    if not n:
        return 0.0
    op = sum(1 for x in rows if re.fullmatch(r'\d{9,}', x["sku"]) or re.search(r'[0-9a-f]{8}-[0-9a-f]{4}', x["sku"]))
    return op / n


def process(path, write_csv=True):
    supplier, hdr, rows = load_rows(path)
    if rows is None:
        return None
    n = len(rows)
    grammar = {}
    stats = {"supplier": supplier, "file": path.name, "products": n,
             "families": len({family_key(x["sku"]) for x in rows}),
             "opaque_pct": round(opaque_frac(rows) * 100)}

    for attr, known_key in [("color", "known_color"), ("size", "known_size"), ("finish", "known_finish")]:
        pairs = [(x["sku"], x[known_key]) for x in rows]
        decoders = learn_attribute(pairs, attr)
        grammar[attr] = decoders
        # decode every row, measure recovery vs known + agreement
        known_n = sum(1 for x in rows if x[known_key] is not None)
        decoded_n = added = agree = both = 0
        for x in rows:
            val, conf, src = decode(x["sku"], decoders)
            x[f"learned_{attr}"] = val
            x[f"learned_{attr}_conf"] = round(conf, 3) if val is not None else ""
            x[f"learned_{attr}_src"] = src or ""
            if val is not None:
                decoded_n += 1
                if x[known_key] is None:
                    added += 1
                else:
                    both += 1
                    if str(val) == str(x[known_key]):
                        agree += 1
        stats[attr] = {
            "known_pct": round(100 * known_n / n) if n else 0,
            "decoded_pct": round(100 * decoded_n / n) if n else 0,
            "added_pct": round(100 * added / n) if n else 0,
            "agreement_pct": round(100 * agree / both) if both else None,
            "decoders": len(decoders),
        }

    if write_csv:
        write_enriched(path, hdr, rows)
    return stats, grammar


NEW_COLS = []
for a in ("color", "size", "finish"):
    NEW_COLS += [f"learned_{a}", f"learned_{a}_conf", f"learned_{a}_src"]


def write_enriched(path, hdr, rows):
    (OUT / "enriched").mkdir(parents=True, exist_ok=True)
    dst = OUT / "enriched" / (path.stem + "_enriched.csv")
    with open(dst, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(list(hdr) + NEW_COLS)          # originals + new cols (additive)
        for x in rows:
            base = ["" if c is None else c for c in x["row"]]
            w.writerow(base + [x.get(c, "") for c in NEW_COLS])


def main():
    write_csv = "--no-csv" not in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in FINDINGS.glob("*.xlsx") if "CategoryBreakdown" not in p.name)
    all_stats, all_grammar = [], {}
    for p in files:
        res = process(p, write_csv=write_csv)
        if not res:
            print(f"  skip (no sku/name): {p.name}")
            continue
        stats, grammar = res
        all_stats.append(stats)
        all_grammar[stats["supplier"]] = grammar
        c = stats["color"]
        print(f"  {stats['supplier']:<26} {stats['products']:>6} prod  "
              f"color: known {c['known_pct']:>3}% → decoded {c['decoded_pct']:>3}% "
              f"(+{c['added_pct']:>2}% new, agree {c['agreement_pct']}%)")

    (OUT / "grammar.json").write_text(json.dumps(all_grammar, indent=1, default=str))
    write_report(all_stats)
    print(f"\nWrote: {OUT/'grammar.json'}, {OUT/'REPORT.md'}"
          + (f", {OUT/'enriched'}/*.csv" if write_csv else ""))


def write_report(all_stats):
    all_stats.sort(key=lambda s: -s["products"])
    L = ["# SKU-Grammar Decodability Report", "",
         "Learned per-supplier SKU grammars from the raw findings, then decoded every SKU.",
         "All output is additive — originals untouched.", "",
         "**Columns:** _known_ = attribute already readable from name/columns · "
         "_decoded_ = share the learned SKU grammar can assign · "
         "_+new_ = rows where the name lacked it but the SKU supplied it · "
         "_agree_ = where both exist, how often they match (grammar trust).", "",
         "## Color (the highest-value attribute)", "",
         "| Supplier | Products | Families | Opaque | Known | Decoded | +New | Agree |",
         "|---|--:|--:|--:|--:|--:|--:|--:|"]
    tot_added = tot = 0
    for s in all_stats:
        c = s["color"]
        tot += s["products"]; tot_added += c["added_pct"] * s["products"] / 100
        L.append(f"| {s['supplier']} | {s['products']:,} | {s['families']} | {s['opaque_pct']}% | "
                 f"{c['known_pct']}% | {c['decoded_pct']}% | +{c['added_pct']}% | "
                 f"{c['agreement_pct'] if c['agreement_pct'] is not None else '—'}% |")
    L += ["", f"**Across all catalogs:** ~{round(tot_added):,} products gain a color they "
          f"didn't have in their name, from SKU decoding alone.", "",
          "## Size & Finish", "",
          "| Supplier | Size known→dec (+new) | Finish known→dec (+new) |",
          "|---|--:|--:|"]
    for s in all_stats:
        sz, fi = s["size"], s["finish"]
        L.append(f"| {s['supplier']} | {sz['known_pct']}%→{sz['decoded_pct']}% (+{sz['added_pct']}%) "
                 f"| {fi['known_pct']}%→{fi['decoded_pct']}% (+{fi['added_pct']}%) |")
    (OUT / "REPORT.md").write_text("\n".join(L))


if __name__ == "__main__":
    main()
