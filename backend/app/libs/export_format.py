"""Formatting helpers shared by the job and order exports.

``app.apis.orders.export`` and ``app.apis.jobs.export`` import these as
``_money`` / ``_esc``. Behaviour is pinned by ``tests/test_jobs_api.py``,
``tests/test_orders_api.py`` and ``tests/test_db.py``.
"""

from __future__ import annotations


def money(n) -> str:
    """``$1,234.50``; ``""`` for ``None`` or anything that is not a number."""
    if n is None:
        return ""
    try:
        return f"${float(n):,.2f}"
    except (TypeError, ValueError):
        return ""


def esc(s) -> str:
    """Escape text for reportlab paragraph markup, including double-quoted
    attribute values (``<a href="...">``). Only ``None`` becomes ``""``;
    falsy values such as ``0`` render as text. The templates use no
    single-quoted attributes, so ``'`` is left alone."""
    if s is None:
        return ""
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace('"', "&quot;"))
