import os
from datetime import datetime

import asyncpg
from fastapi import APIRouter, Request

from app.apis.arrangements import ensure_project_schema, has_item_status_column
from app.apis.clients import build_client_list, saved_clients_only
from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/bootstrap", tags=["bootstrap"])
DATABASE_URL = os.environ.get("DATABASE_URL")


async def get_conn():
    return await asyncpg.connect(DATABASE_URL, statement_cache_size=0)


@router.get("/summary")
async def get_bootstrap_summary(request: Request):
    user_id = get_request_user_id(request)
    generated_at = datetime.utcnow().isoformat()

    try:
        conn = await get_conn()
    except Exception:
        return {
            "generated_at": generated_at,
            "status": "partial",
            "clients": saved_clients_only(user_id),
            "projects": [],
            "suppliers": [],
            "stats": None,
        }

    try:
        await ensure_project_schema(conn)
        supports_status = await has_item_status_column(conn)
        cost_expression = (
            "CASE WHEN ci.status = 'selected' THEN ci.quantity * p.current_price ELSE 0 END"
            if supports_status
            else "ci.quantity * p.current_price"
        )

        clients = await build_client_list(conn, user_id)
        projects = await conn.fetch(f"""
            SELECT
                a.id,
                a.name,
                a.client_name,
                a.notes,
                a.created_at,
                a.updated_at,
                COUNT(DISTINCT CASE WHEN ac.label IS NULL OR ac.label NOT LIKE 'LL_ROOM:%' THEN ac.id END)::int AS container_count,
                COALESCE(SUM({cost_expression}), 0)::float AS total_cost
            FROM arrangements a
            LEFT JOIN arrangement_containers ac ON ac.arrangement_id = a.id
            LEFT JOIN container_items ci ON ci.container_id = ac.id
            LEFT JOIN products p ON p.id = ci.product_id
            WHERE a.created_by = $1
            GROUP BY a.id
            ORDER BY a.updated_at DESC
        """, user_id)
        suppliers = await conn.fetch("""
            SELECT
                s.id,
                s.name,
                s.scraper_key,
                s.login_url,
                s.contact_name,
                s.contact_email,
                s.contact_phone,
                s.notes,
                s.categories,
                s.created_at,
                s.updated_at,
                s.last_price_synced_at,
                s.last_full_sync_at,
                COUNT(p.id)::int AS product_count,
                (
                    s.login_username IS NOT NULL
                    AND s.login_username != ''
                    AND s.login_password IS NOT NULL
                    AND s.login_password != ''
                ) AS has_credentials
            FROM suppliers s
            LEFT JOIN products p ON p.supplier_id = s.id AND p.is_active = TRUE
            GROUP BY s.id
            ORDER BY s.name
        """)
        stats = {
            "total_products": await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = TRUE"),
            "total_suppliers": await conn.fetchval("SELECT COUNT(*) FROM suppliers"),
            "total_favorites": await conn.fetchval(
                "SELECT COUNT(*) FROM product_favorites WHERE user_id = $1",
                user_id,
            ),
            "total_arrangements": await conn.fetchval(
                "SELECT COUNT(*) FROM arrangements WHERE created_by = $1",
                user_id,
            ),
        }

        return {
            "generated_at": generated_at,
            "status": "ok",
            "clients": [dict(row) for row in clients],
            "projects": [dict(row) for row in projects],
            "suppliers": [dict(row) for row in suppliers],
            "stats": stats,
        }
    finally:
        await conn.close()
