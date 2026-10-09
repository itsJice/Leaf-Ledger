"""Crew cards on a date list in crewLabel order (user, 2026-10-09)."""
import json, pathlib, re, subprocess

TPL = pathlib.Path(__file__).resolve().parents[1] / "review_template.html"


def test_date_lists_sort_by_crew():
    s = TPL.read_text(encoding="utf-8")
    assert "const onThisDate = days.filter(d=>d.date===selDate).sort(byCrew);" in s
    assert "pool.filter(d=>d.date===dt).sort(byCrew)" in s
    assert "localeCompare(b.crew)" not in s


def test_bycrew_matches_label_order():
    src = re.search(r"function byCrew\(a,b\)\{[^\n]*\}", TPL.read_text(encoding="utf-8")).group(0)
    crews = ["Crew 3", "Crew 1", "Crew 2"]
    js = (src + f"const c={json.dumps(crews)};"
          "const cards=c.map(crew=>({crew})).sort(byCrew).map(x=>x.crew);"
          "const labels=[...new Set(c)].sort();"
          "console.log(JSON.stringify([cards,labels]));")
    cards, labels = json.loads(subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True).stdout)
    assert cards == labels == ["Crew 1", "Crew 2", "Crew 3"]
