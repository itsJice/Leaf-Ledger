import os
import pathlib
import json
import dotenv
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Load the environment-specific file. Defaults to `supabase` — our own database.
# It used to default to `dev`, which pointed at the previous platform's Neon
# database, so running the app with no ENV set silently read and wrote someone
# else's data. In a deployed environment the host supplies these directly and
# there is no file to load.
environment = os.getenv("ENV", "supabase")
env_file = f".env.{environment}"
if os.path.exists(env_file):
    dotenv.load_dotenv(env_file, override=True)
    print(f"Loaded environment: {environment} ({env_file})")
else:
    print(f"No {env_file} — using environment variables as provided")

from app.auth import get_authorized_user

# Signing in is required for the whole API. The only way to turn it off is to
# set AUTH_DISABLED=true AND be running the local dev environment — it is
# deliberately impossible to disable auth in a deployed environment.
AUTH_DISABLED = (
    os.getenv("AUTH_DISABLED", "").lower() == "true"
    and os.getenv("ENV", "dev") == "dev"
)


def get_router_config() -> dict:
    try:
        # Note: This file is not available to the agent
        cfg = json.loads(open("routers.json").read())
    except:
        return False
    return cfg


def is_auth_disabled(router_config: dict, name: str) -> bool:
    """Whether this router should be left unauthenticated.

    `routers.json` is Databutton-generated scaffolding that marks every router
    `disableAuth: true`. We ignore it: the team's catalog, pricing and client
    data must never be readable without signing in. The one honoured escape
    hatch is the local-dev-only AUTH_DISABLED flag above.
    """
    return AUTH_DISABLED


def import_api_routers() -> APIRouter:
    """Create top level router including all user defined endpoints."""
    routes = APIRouter(prefix="/api")

    router_config = get_router_config()

    src_path = pathlib.Path(__file__).parent

    # Import API routers from "src/app/apis/*/__init__.py"
    apis_path = src_path / "app" / "apis"

    api_names = [
        p.relative_to(apis_path).parent.as_posix()
        for p in apis_path.glob("*/__init__.py")
    ]

    api_module_prefix = "app.apis."

    for name in api_names:
        print(f"Importing API: {name}")
        try:
            api_module = __import__(api_module_prefix + name, fromlist=[name])
            api_router = getattr(api_module, "router", None)
            if isinstance(api_router, APIRouter):
                routes.include_router(
                    api_router,
                    dependencies=(
                        []
                        if is_auth_disabled(router_config, name)
                        else [Depends(get_authorized_user)]
                    ),
                )
        except Exception as e:
            print(e)
            continue

    print(routes.routes)

    return routes


FRONTEND_DIST = pathlib.Path(__file__).parent.parent / "frontend" / "dist"


def mount_frontend(app: FastAPI) -> None:
    """Serve the built React app from this same server.

    Deploying one service instead of two keeps the frontend and the API on a
    single origin, which is what the frontend's api client already expects in
    production. In local dev the Vite server is used instead and `dist/` may
    not exist, so this degrades to an API-only app.
    """
    dist = FRONTEND_DIST.resolve()
    if not (dist / "index.html").is_file():
        print(f"frontend build not found at {dist} — serving API only")
        return

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str):
        # Unknown /api/* must 404 as an API call, not fall through to the SPA.
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found")
        # Serve a real file when one matches (favicon, images, etc), else the
        # SPA shell so client-side routes like /library work on a hard refresh.
        if full_path:
            candidate = (dist / full_path).resolve()
            if candidate.is_file() and candidate.is_relative_to(dist):
                return FileResponse(candidate)
        return FileResponse(dist / "index.html")

    print(f"serving frontend from {dist}")


def create_app() -> FastAPI:
    """Create the app. This is called by uvicorn with the factory option to construct the app object."""
    app = FastAPI()

    @app.get("/health", include_in_schema=False)
    async def health():
        """Public liveness probe for the host — deliberately exposes nothing."""
        return {"status": "ok", "auth": "disabled" if AUTH_DISABLED else "required"}

    app.include_router(import_api_routers())

    for route in app.routes:
        if hasattr(route, "methods"):
            for method in route.methods:
                print(f"{method} {route.path}")

    @app.on_event("startup")
    async def _warm_search_index():
        # Preload the in-memory catalog search index in the background so the
        # first real search is already fast. Never blocks startup.
        import asyncio

        async def _warm():
            try:
                from app.apis.products import (_INDEX_ENABLED, _ensure_facets_building,
                                               get_conn, _load_search_index)
                if not _INDEX_ENABLED:
                    # SQL-only mode: the big index would cost a full catalog
                    # read (and ~892 MB) for a path nothing serves from. Warm
                    # the unfiltered facet baseline instead - disk cache first,
                    # a single aggregate pass if there is none - so the first
                    # browse after a deploy has a sidebar.
                    _ensure_facets_building()
                    print("facet baseline warm-up started (SQL search mode)")
                    return
                conn = await get_conn()
                try:
                    await _load_search_index(conn)
                    print("search index warmed")
                finally:
                    await conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"search warm-up skipped: {e}")

        asyncio.create_task(_warm())

    # Registered last: its catch-all route must not shadow the API routes.
    mount_frontend(app)

    return app


app = create_app()
