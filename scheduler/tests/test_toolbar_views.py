"""The Install Schedule's top toolbar follows the view (user, 2026-10-15:
"Buttons at the top of the page need to correspond to what's on the page.
Right now, the print button doesn't print the roster."), and Cmd+P prints
the whole page. FAKE people only."""
import json
import shutil

import pytest

from test_client_name_editor import TEMPLATE, js_function, run_js

NODE = shutil.which("node")


def test_print_and_download_dispatch_on_the_view():
    pr = TEMPLATE[TEMPLATE.index("document.getElementById('tbprint').onclick"):][:300]
    for fn in ("openRosterPrintDlg()", "printStaffing()", "printCalendar()", "printDays()"):
        assert fn in pr
    dl = TEMPLATE[TEMPLATE.index("document.getElementById('billexportbtn').onclick"):][:500]
    assert "curView()==='roster'" in dl and "billdlg.showModal()" in dl
    assert "downloadRoster('xlsx')" in TEMPLATE and "downloadRoster('csv')" in TEMPLATE


def test_each_control_is_labelled_or_hidden_per_view():
    s = js_function("syncViewToolbar")
    assert "'Print the roster: choose who, which columns and the layout'" in s
    assert "Print the staffing sheet" in s and "`Print ${calPrintTitle()}`" in s
    assert "'Download the roster (Excel or CSV)'" in s
    assert "v!=='staff');" in s                      # no schedule export on Staffing
    assert "v==='cal');" in s                        # TV mode only on the Calendar
    assert "'Add an installer'" in s and "set('newclientbtn', null, v==='days'||v==='cal')" in s
    assert "syncViewToolbar();" in js_function("setView")
    assert "syncViewToolbar();" in js_function("renderStaffing")
    nb = TEMPLATE[TEMPLATE.index("const btn=document.getElementById('newbtn')"):][:600]
    assert "openPersonDlg(null)" in nb


def test_search_from_another_view_opens_the_day():
    assert "if(viewMode!=='days') setView('days')" in js_function("jumpToClient")


@pytest.mark.skipif(NODE is None, reason="node not installed")
@pytest.mark.parametrize("admin", [True, False])
def test_roster_rows_gate_contractor_fields(admin):
    src = "const MONTHS=['January','February','March','April','May','June','July','August','September','October','November','December'];\n"
    src += js_function("fmtFreeDays") + "\n" + js_function("rosterRows") + "\n"
    src += "function fmtPhone(p){ return '('+p.slice(0,3)+') '+p.slice(3,6)+'-'+p.slice(6); }\n"
    src += f"function canSeeContractor(){{ return {str(admin).lower()}; }}\n"
    src += """
      const people=[{name:'Ana Test', phone:'7135550101', title:'Lead', lang:'Both', gender:'Female',
        dates:['2026-11-02','2026-10-26','2026-11-03'], legalName:'Ana Q Test', street:'1 Main St', city:'Houston',
        state:'TX', zip:'77002', tax1099:true, directDeposit:true},
        {name:'Luis Test', phone:'', title:'General Installer', lang:'Spanish', gender:'Male', dates:[]}];
      console.log(JSON.stringify(rosterRows([{people}])));
    """
    rows = json.loads(run_js(src))
    assert rows[0][:7] == ["Name", "Phone", "Title", "Language", "M/F", "Free days", "Free dates"]
    assert rows[1][:7] == ["Ana Test", "(713) 555-0101", "Lead", "Both", "F", 3, "Oct 26 · Nov 2, 3"]
    assert rows[2][4:7] == ["M", 0, ""]
    if admin:
        assert rows[0][7:] == ["Legal name", "Address", "1099", "Direct deposit"]
        assert rows[1][7:] == ["Ana Q Test", "1 Main St, Houston, TX 77002", "Yes", "On file"]
    else:
        assert len(rows[0]) == 7 and "Ana Q Test" not in json.dumps(rows)


def test_cmd_p_prints_the_whole_schedule():
    css = TEMPLATE[TEMPLATE.index("/* ---- Cmd+P / Ctrl+P prints the whole view"):]
    css = css[:css.index("</style>")]
    assert "@media print" in css and "overflow:visible!important" in css
    assert "#datecol,header,#phonebar,#map" in css
    # inside the app, the shortcut prints this document, not the app around it
    assert "if(HOSTED) document.addEventListener('keydown'" in TEMPLATE
    assert "window.tbdgPrint = ()=>window.print();" in TEMPLATE
