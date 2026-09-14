"""The review tool's JavaScript re-implements a few dynamic rules. Keep its
numbers equal to the Python ones.

Where the JS constants come from: review_template.html does NOT contain a
literal constants object. It reads `K = DATA.spec.const`, and build_review.py
fills that in (`spec = {"const": {...}}`) mostly as `S.<NAME>` straight from
schedule.py. So the mapping is:

    template K.<NAME>       build_review.py spec["const"][NAME]    Python
    K.WINDOW          ->    S.WINDOW                         ->    schedule.WINDOW
    K.DAY_CAP         ->    S.DAY_CAP                        ->    schedule.DAY_CAP
    K.DAY_MIN         ->    S.DAY_MIN                        ->    schedule.DAY_MIN
    K.LUNCH           ->    S.LUNCH                          ->    schedule.LUNCH
    K.NIGHT/_MIN/_MAX ->    S.NIGHT/_MIN/_MAX                ->    schedule.NIGHT/...
    K.RADIUS_S        ->    S.RADIUS_S                       ->    schedule.RADIUS_S
    K.RADIUS_RURAL_S  ->    literal 2700                     ->    NO named constant:
                            schedule.merge_singletons' `eff_r = RADIUS_S if
                            leg(D, 0, c["midx"]) <= 2700 else 2700`

build_review.py is parsed with `ast`, never imported (importing it runs the
build). The estimate helpers (ROAD_FUDGE, EST_AVG_MPH, earth radius) are
written as literals directly in the template.
"""
import ast
import os
import re

import pytest

import schedule

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE = open(os.path.join(HERE, "review_template.html"), encoding="utf-8").read()


def _read(name):
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        return f.read()


def spec_const():
    """build_review.py's spec["const"], with S.<NAME> resolved against schedule."""
    tree = ast.parse(_read("build_review.py"))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "spec" and isinstance(node.value, ast.Dict)):
            for k, v in zip(node.value.keys, node.value.values):
                if isinstance(k, ast.Constant) and k.value == "const":
                    break
            else:
                continue
            out = {}
            for ck, cv in zip(v.keys, v.values):
                if isinstance(cv, ast.Constant):
                    out[ck.value] = ("literal", cv.value)
                elif (isinstance(cv, ast.Attribute) and isinstance(cv.value, ast.Name)
                      and cv.value.id == "S"):
                    out[ck.value] = (cv.attr, getattr(schedule, cv.attr))
                else:
                    out[ck.value] = ("expr", None)
            return out
    raise AssertionError("spec = {'const': {...}} not found in build_review.py")


def python_rural_radius():
    """The rural radius as schedule.py actually uses it. A later change may
    name it RADIUS_RURAL_S; until then read the literal in merge_singletons."""
    named = getattr(schedule, "RADIUS_RURAL_S", None)
    if named is not None:
        return named
    tree = ast.parse(_read("schedule.py"))
    fn = next(n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "merge_singletons")
    assign = next(n for n in ast.walk(fn) if isinstance(n, ast.Assign)
                  and any(isinstance(t, ast.Name) and t.id == "eff_r" for t in n.targets))
    # eff_r = RADIUS_S if leg(D, 0, c["midx"]) <= <THRESHOLD> else <RURAL>
    ifexp = assign.value
    assert isinstance(ifexp, ast.IfExp) and isinstance(ifexp.test, ast.Compare)
    nums = {n.value for n in [*ifexp.test.comparators, ifexp.orelse]
            if isinstance(n, ast.Constant)}
    assert len(nums) == 1, f"expected threshold == rural radius, got {nums}"
    return nums.pop()


def test_every_K_name_the_template_uses_is_shipped():
    used = set(re.findall(r"\bK\.([A-Z_]+)\b", TEMPLATE))
    assert {"LUNCH", "DAY_CAP", "DAY_MIN", "NIGHT", "RADIUS_S", "RADIUS_RURAL_S"} <= used
    assert used <= set(spec_const())


def test_S_backed_constants_keep_their_names():
    # "LUNCH": S.NIGHT would type-check fine and silently break the tool.
    for key, (src, _) in spec_const().items():
        if src not in ("literal", "expr"):
            assert key == src, f"K.{key} is fed from S.{src}"


@pytest.mark.parametrize("key,python_value", [
    ("WINDOW", schedule.WINDOW),
    ("DAY_CAP", schedule.DAY_CAP),
    ("DAY_MIN", schedule.DAY_MIN),
    ("LUNCH", schedule.LUNCH),
    ("NIGHT", schedule.NIGHT),
    ("RADIUS_S", schedule.RADIUS_S),
])
def test_day_shape_constants_match(key, python_value):
    assert spec_const()[key][1] == python_value


def test_rural_radius_matches():
    assert spec_const()["RADIUS_RURAL_S"][1] == python_rural_radius() == 2700


def test_bare_2700_literals_in_template_equal_python_rural_radius():
    """radiusOK() compares the depot leg against a bare `2700` rather than
    K.RADIUS_RURAL_S (Python uses the same number for the rural threshold and
    the rural radius). That literal should become K.RADIUS_RURAL_S in a later
    change; the template is not edited here. Until then, pin it to Python."""
    literals = re.findall(r"(?<![\w.])2700(?![\w.])", TEMPLATE)
    assert literals, "no bare 2700 left -- drop this test once K.RADIUS_RURAL_S is used"
    assert all(int(x) == python_rural_radius() for x in literals)
    # same direction as Python: rural iff depot leg is strictly greater
    assert re.search(r"leg\(0,\s*v\)\s*>\s*2700", TEMPLATE)


def test_estimate_helpers_match():
    m = re.search(r"const ROAD_FUDGE\s*=\s*([\d.]+),\s*EST_AVG_MPH\s*=\s*([\d.]+)", TEMPLATE)
    assert m, "ROAD_FUDGE / EST_AVG_MPH declaration not found in template"
    assert float(m.group(1)) == schedule.ROAD_FUDGE
    assert float(m.group(2)) == schedule.EST_AVG_MPH
    js_r = re.search(r"function haversineMi\(a, b\)\{\s*const R=([\d.]+)", TEMPLATE)
    py_r = re.search(r"def haversine_mi\(a, b\):.*?R = ([\d.]+)", _read("schedule.py"), re.S)
    assert js_r and py_r and float(js_r.group(1)) == float(py_r.group(1))


def test_club_coverage_check_matches_rules():
    # rules.club_crew_ok: category == "Country Club" and any("Crew 1" in c)
    assert re.search(r"cat!=='Country Club'\) return;", TEMPLATE)
    assert re.search(r"crews\.some\(c2=>c2\.includes\('Crew 1'\)\)", TEMPLATE)
