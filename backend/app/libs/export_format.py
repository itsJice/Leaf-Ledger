"""Formatting helpers shared by the job and order exports.

Copied verbatim from ``app.apis.orders.export`` (``_money`` / ``_esc``), which
are byte-identical to the copies in ``app.apis.jobs.export``. Behaviour is
pinned by ``tests/test_jobs_api.py`` and ``tests/test_orders_api.py``.
"""

from __future__ import annotations


def money(n) -> str:
    return "" if n is None else f"${float(n):,.2f}"


def esc(s: str) -> str:
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
