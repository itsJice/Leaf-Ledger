"""Dashboard summary — one call for everything the home screen shows.

The dashboard previously read `/api/products/stats`, which only knew about
products, suppliers, favourites and arrangements. The app has since grown a
design library, purchase orders and a historical recipe corpus, none of which
were represented. Aggregating here keeps the home screen to a single request
instead of fanning out to four routers.

Read-only. Every block is independently guarded, so a missing table or an empty
feature degrades that one number to null/0 rather than failing the whole screen.
"""
from fastapi import APIRouter, Request
from typing import Any, Optional

from app.apis.products import get_conn
from app.apis.user_context import get_request_user_id

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


async def _scalar(conn, sql: str, *args, default: Any = 0) -> Any:
    try:
        value = await conn.fetchval(sql, *args)
        return default if value is None else value
    except Exception:
        return default


async def _exists(conn, qualified: str) -> bool:
    try:
        return bool(await conn.fetchval("SELECT to_regclass($1)", qualified))
    except Exception:
        return False


@router.get("/summary")
async def dashboard_summary(request: Request):
    user_id = get_request_user_id(request)
    conn = await get_conn()
    try:
        catalog_products = await _scalar(
            conn, "SELECT COUNT(*) FROM products WHERE is_active = TRUE"
        )
        suppliers = await _scalar(conn, "SELECT COUNT(*) FROM suppliers")
        favorites = await _scalar(
            conn, "SELECT COUNT(*) FROM product_favorites WHERE user_id = $1", user_id
        )
        projects = await _scalar(conn, "SELECT COUNT(*) FROM arrangements")

        # Designs are containers; the LL_ROOM: pseudo-rows are not designs.
        designs = await _scalar(
            conn,
            """SELECT COUNT(*) FROM arrangement_containers
                 WHERE COALESCE(label, '') NOT LIKE 'LL_ROOM:%'""",
        )
        designs_with_parts = await _scalar(
            conn,
            """SELECT COUNT(DISTINCT container_id) FROM container_items""",
        )

        # Purchase orders live in ll_app and may not exist on a fresh database.
        orders: dict[str, Any] = {"count": 0, "open_value": 0.0, "vendors": 0, "items": 0}
        if await _exists(conn, "ll_app.orders"):
            orders["count"] = await _scalar(conn, "SELECT COUNT(*) FROM ll_app.orders")
            orders["items"] = await _scalar(
                conn, "SELECT COALESCE(SUM(quantity), 0) FROM ll_app.order_items"
            )
            orders["vendors"] = await _scalar(
                conn,
                """SELECT COUNT(DISTINCT p.supplier_id)
                     FROM ll_app.order_items i JOIN products p ON p.id = i.product_id""",
            )
            orders["open_value"] = float(
                await _scalar(
                    conn,
                    """SELECT COALESCE(SUM(i.quantity * COALESCE(i.unit_price, p.current_price)), 0)
                         FROM ll_app.order_items i
                         LEFT JOIN products p ON p.id = i.product_id""",
                    default=0,
                )
                or 0
            )

        recipes = await _scalar(conn, "SELECT COUNT(*) FROM historical_recipes")
        recipe_components = await _scalar(
            conn, "SELECT COUNT(*) FROM historical_recipe_components"
        )

        return {
            "catalog": {"products": catalog_products, "suppliers": suppliers},
            "designs": {"total": designs, "with_parts": designs_with_parts, "projects": projects},
            "orders": orders,
            "recipes": {"total": recipes, "components": recipe_components},
            "favorites": favorites,
        }
    finally:
        await conn.close()


@router.get("/recent-designs")
async def recent_designs(limit: int = 6):
    """Most recently touched designs, with the details a card needs."""
    conn = await get_conn()
    try:
        rows = await conn.fetch(
            """
            SELECT ac.id,
                   COALESCE(NULLIF(ac.label, ''), ac.build_type, 'Untitled design') AS name,
                   ac.build_type,
                   a.name  AS project_name,
                   a.client_name,
                   pr.name AS group_name,
                   ac.created_at,
                   (SELECT COUNT(*) FROM container_items ci WHERE ci.container_id = ac.id) AS item_count,
                   -- container_items carries no price of its own; cost comes
                   -- from the catalog product at read time.
                   (SELECT COALESCE(SUM(ci.quantity * p.current_price), 0)
                      FROM container_items ci JOIN products p ON p.id = ci.product_id
                     WHERE ci.container_id = ac.id) AS total_cost
              FROM arrangement_containers ac
              LEFT JOIN arrangements a  ON a.id = ac.arrangement_id
              LEFT JOIN project_rooms pr ON pr.id = ac.room_id
             WHERE COALESCE(ac.label, '') NOT LIKE 'LL_ROOM:%'
             ORDER BY ac.id DESC
             LIMIT $1
            """,
            max(1, min(limit, 24)),
        )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "build_type": r["build_type"],
                "project_name": r["project_name"],
                "client_name": r["client_name"],
                "group_name": r["group_name"],
                "item_count": r["item_count"],
                "total_cost": float(r["total_cost"] or 0),
            }
            for r in rows
        ]
    finally:
        await conn.close()
