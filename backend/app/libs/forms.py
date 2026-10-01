"""Data-driven forms (Google Forms, inside Leaf & Ledger) -- the pure part.

The API in app.apis.forms stores forms, sections, questions, responses and
answers in ll_app; everything here is free of the database so it can be
tested directly: the seed for the Product Purchase Request Form, answer
validation, the CSV export in the Google Sheet's exact column order, and the
parsing the response import needs.

A question's `export_position` is its column in the CSV, independent of the
order it is asked in: "Requestor" is asked first but was added to the Google
Form last, so it is the sheet's last column (N) and stays there.
"""
from __future__ import annotations

import csv
import datetime as _dt
import io
import re
from typing import Any, Iterable, Optional
from zoneinfo import ZoneInfo

QUESTION_TYPES = ("short_text", "long_text", "dropdown", "radio", "checkboxes", "date")
STATUSES = ("New", "Ordered", "Received", "Cancelled")
#: Rows the buyer is done with -- drawn struck through, like the sheet.
DONE_STATUSES = ("Ordered", "Received", "Cancelled")
REQUIRED_MESSAGE = "This is a required question"
#: The sheet's timestamps are the team's local time.
TZ = ZoneInfo("America/Chicago")

MATCH_OPTIONS = [
    "Yes, need more of the EXACT same product. Sí, necesitamos más unidades EXACTAMENTE iguales del mismo producto para completar el proyecto.",
    "Maybe, we can MIX in SIMILAR product with existing product. Quizás podamos mezclar un producto similar con el producto existente.",
    "No, use requested product as inspiration. No, usa el producto solicitado como inspiración.",
]
SAMPLES_OPTIONS = [
    "Samples assembled into labeled box left at buyers desk. Muestras organizadas en una caja con etiqueta dejadas en el escritorio del comprador.",
    "Pictures of items being used have been texted to Ms. Cynthia. Le han mandado fotos de los artículos en uso a la Sra. Cynthia por mensaje de texto.",
    "New Project. Do not have any existing items to be used. Nuevo proyecto. No tengo ningún elemento existente para usar.",
    "Pictures of items being used have been texted/emailed. Se han enviado por mensaje de texto o correo electrónico fotos de los artículos en uso.",
]
SAMPLES_LABEL = (
    "Samples & Pictures: Please provide samples or pictures of the items being used in this project. "
    "In case we need to find alternatives, pictures of the other items being used in this project will "
    "help the buyer find complimentary product options to present to you.\n\n"
    "Muestras y fotografías: Sírvase proporcionar muestras o fotografías de los artículos a utilizar en "
    "este proyecto. En caso de requerir alternativas, las imágenes de los demás elementos empleados "
    "ayudarán al comprador a hallar opciones de productos complementarios que presentarle."
)

PRODUCT_REQUEST_SLUG = "product-request"

#: The Product Purchase Request Form, exactly as the Google Form has it.
#: (key, label, helper, type, required, options, export_position)
PRODUCT_REQUEST_FORM = {
    "slug": PRODUCT_REQUEST_SLUG,
    "title": "Product Purchase Request Form",
    "description": "Please fill out one form per item.\nComplete un formulario por cada artículo, por favor.",
    "sections": [
        {
            "title": "Product Purchase Request Form",
            "description": None,
            "questions": [
                ("requestor", "Requestor", None, "dropdown", True,
                 ["Alberto", "Chris", "Cynthia", "Justice", "Laura", "Reyna", "Other"], 13),
                ("client_name", "Client Name/Nombre del Cliente", "(Por ejemplo: Smith, John)",
                 "short_text", True, None, 1),
                ("project_name", "Project Name/Título del Proyecto", "(Por ejemplo: Outdoor)",
                 "short_text", True, None, 2),
                ("location_item", "Location and Item / Lugar y Artículo",
                 "(Por ejemplo: Downstairs Fireplace Garland; Living room Christmas tree enhancers)",
                 "long_text", True, None, 3),
            ],
        },
        {
            "title": "Product Request Details",
            "description": (
                "Provide information for the buyer to find and purchase the product you need to create the item listed above.\n"
                "Incluya los datos necesarios para que el comprador localice y compre el producto que requiere para elaborar el artículo indicado arriba."
            ),
            "questions": [
                ("product_description", "Product Description / Describa el producto.",
                 "(Por ejemplo: 100mm matte gold mercury ball ornament)", "long_text", True, None, 4),
                ("most_important_quality",
                 "What is the most important quality for the product you picked? ¿Cuál es la característica más importante del producto que seleccionaste?",
                 "(Por ejemplo: ornament shape or color combination or finish)", "long_text", True, None, 5),
                ("match_existing", "Does this need to match an existing product?", None, "radio", True,
                 MATCH_OPTIONS, 6),
                ("preferred_vendor", "Preferred Vendor / Proveedor Recomendado", None, "short_text", False, None, 7),
                ("style_number_color", "Style Number and color / Número de modelo y color", None,
                 "short_text", False, None, 8),
                ("catalog_page", "Catalog Page Number / Página del catálogo", None, "short_text", False, None, 9),
                ("quantity_needed",
                 "Quantity Needed: Total Units or Total yards. / Cantidad necesaria: Cantidad total o yardas totales, no indique cajas ni rollos",
                 "(Por ejemplo: 20 ornaments or 120 yards of ribbon)", "short_text", True, None, 10),
                ("install_date",
                 "Install Date: When is the project being installed? / Fecha de instalación: ¿Cuándo van a instalar el proyecto?",
                 None, "date", True, None, 11),
                ("samples_pictures", SAMPLES_LABEL, None, "checkboxes", True, SAMPLES_OPTIONS, 12),
            ],
        },
    ],
}


def export_header(q: dict) -> str:
    """The sheet's column header: the full question text, with the
    "(Por ejemplo ...)" line when there is one."""
    return q["label"] + (f" {q['helper_text']}" if q.get("helper_text") else "")


# ── validation ────────────────────────────────────────────────────────────────


def _empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str):
        return not v.strip()
    if isinstance(v, (list, tuple)):
        return not [x for x in v if str(x).strip()]
    return False


def clean_value(q: dict, v: Any) -> Any:
    """Trim whitespace; checkboxes become a de-duplicated list; a date is ISO."""
    if v is None:
        return None
    t = q["type"]
    if t == "checkboxes":
        items = v if isinstance(v, (list, tuple)) else [v]
        out = []
        for x in items:
            s = str(x).strip()
            if s and s not in out:
                out.append(s)
        return out or None
    s = re.sub(r"[ \t]+", " ", str(v)).strip() if t != "long_text" else str(v).strip()
    return s or None


def validate(questions: Iterable[dict], answers: dict, section_id: Optional[int] = None) -> dict:
    """{question key: error message} for the given answers -- empty when valid.

    With `section_id`, only that section's questions are checked (the Next
    button); without, every question (Submit). Answers are expected already
    cleaned (clean_value)."""
    errors = {}
    for q in questions:
        if section_id is not None and q.get("section_id") != section_id:
            continue
        v = answers.get(q["key"])
        if _empty(v):
            if q.get("required"):
                errors[q["key"]] = REQUIRED_MESSAGE
            continue
        t, opts = q["type"], q.get("options") or []
        if t in ("dropdown", "radio") and v not in opts:
            errors[q["key"]] = "Choose one of the options"
        elif t == "checkboxes" and any(x not in opts for x in v):
            errors[q["key"]] = "Choose from the options"
        elif t == "date":
            try:
                _dt.date.fromisoformat(str(v)[:10])
            except ValueError:
                errors[q["key"]] = "Enter a date"
    return errors


# ── CSV export (the Google Sheet's columns) ──────────────────────────────────


def fmt_timestamp(ts: _dt.datetime) -> str:
    """9/14/2026 19:04:29 -- the sheet's format, in the team's time zone."""
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    t = ts.astimezone(TZ)
    return f"{t.month}/{t.day}/{t.year} {t:%H:%M:%S}"


def fmt_date(v: Any) -> str:
    if not v:
        return ""
    try:
        d = _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return str(v)
    return f"{d.month}/{d.day}/{d.year}"


def export_columns(questions: Iterable[dict]) -> list[dict]:
    return sorted([q for q in questions if q.get("export_position")], key=lambda q: q["export_position"])


def export_headers(questions: Iterable[dict]) -> list[str]:
    return ["Timestamp"] + [export_header(q) for q in export_columns(questions)]


def export_cell(q: dict, v: Any) -> str:
    if v is None:
        return ""
    if q["type"] == "checkboxes":
        return ", ".join(v if isinstance(v, list) else [str(v)])
    if q["type"] == "date":
        return fmt_date(v)
    return str(v)


def export_csv(questions: list[dict], responses: list[dict]) -> str:
    """CSV with the sheet's headers and column order, oldest response first."""
    cols = export_columns(questions)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(export_headers(questions))
    for r in sorted(responses, key=lambda r: r["submitted_at"]):
        a = r.get("answers") or {}
        w.writerow([fmt_timestamp(r["submitted_at"])] + [export_cell(q, a.get(q["key"])) for q in cols])
    return buf.getvalue()


# ── import (from the sheet's CSV) ─────────────────────────────────────────────


def parse_timestamp(s: str) -> _dt.datetime:
    """"9/14/2026 19:04:29" in the team's time zone -> an aware datetime."""
    s = str(s).strip()
    for fmt in ("%m/%d/%Y %H:%M:%S", "%m/%d/%Y %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return _dt.datetime.strptime(s, fmt).replace(tzinfo=TZ)
        except ValueError:
            continue
    raise ValueError(f"unrecognised timestamp {s!r}")


def parse_date(s: str) -> Optional[str]:
    s = str(s or "").strip()
    if not s:
        return None
    for fmt in ("%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y"):
        try:
            return _dt.datetime.strptime(s, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip().lower()


def parse_choice(cell: str, options: list[str]) -> Optional[str]:
    """A radio/dropdown cell -> the option it names (full text, or a prefix
    of it, since the options themselves contain commas)."""
    c = _norm(cell)
    if not c:
        return None
    for o in options:
        if _norm(o) == c or _norm(o).startswith(c) or c.startswith(_norm(o)[:40]):
            return o
    return cell.strip()


def parse_checkboxes(cell: str, options: list[str]) -> list[str]:
    """A checkbox cell -> the options it names. Picks are joined with ", "
    but the option texts contain commas too, so this finds each known option
    in the cell instead of splitting; anything left over is kept as typed."""
    c = str(cell or "").strip()
    if not c:
        return []
    found = []
    rest = c
    for o in options:
        i = rest.find(o)
        if i >= 0:
            found.append((c.find(o), o))
            rest = rest[:i] + rest[i + len(o):]
    leftover = re.sub(r"^[\s,]+|[\s,]+$", "", re.sub(r"(,\s*)+", ", ", rest))
    out = [o for _, o in sorted(found)]
    if leftover:
        out.append(leftover)
    return out


def match_header(header: str, questions: list[dict]) -> Optional[dict]:
    """The question a sheet column header belongs to (tolerant of the
    header's line breaks and trailing helper text)."""
    h = _norm(header)
    for q in questions:
        if _norm(export_header(q)) == h or _norm(q["label"]) == h:
            return q
    for q in questions:
        lab = _norm(q["label"])[:30]
        if lab and h.startswith(lab):
            return q
    return None
