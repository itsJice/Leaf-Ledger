import os
import pathlib
import json
import dotenv
from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

# Load environment files
# First load shared .env file
dotenv.load_dotenv(".env")

# Then load environment-specific file (defaults to dev)
# Environment-specific values will override shared values
environment = os.getenv("ENV", "dev")
env_file = f".env.{environment}"
dotenv.load_dotenv(env_file, override=True)

print(f"Loaded environment: {environment}")

from databutton_app.mw.auth_mw import AuthConfig
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


def get_firebase_config() -> dict | None:
    extensions = os.environ.get("DATABUTTON_EXTENSIONS", "[]")
    extensions = json.loads(extensions)

    for ext in extensions:
        if ext["name"] == "firebase-auth":
            return ext["config"]["firebaseConfig"]

    return None


def get_stack_auth_config() -> dict | None:
    extensions = os.environ.get("DATABUTTON_EXTENSIONS", "[]")
    extensions = json.loads(extensions)

    for ext in extensions:
        if ext["name"] == "stack-auth":
            return ext["config"]

    return None


def parse_auth_configs() -> list[AuthConfig]:
    """Parse auth configs from both firebase-auth and stack-auth extensions."""
    auth_configs: list[AuthConfig] = []

    # Add stack-auth config if extension is enabled
    stack_auth_cfg = get_stack_auth_config()
    if stack_auth_cfg:
        project_id = stack_auth_cfg["projectId"]
        auth_configs.append(
            AuthConfig(
                issuer=f"https://api.stack-auth.com/api/v1/projects/{project_id}",
                jwks_url=stack_auth_cfg["jwksUrl"],
                audience=project_id,
            )
        )

    # Add firebase auth config if extension is enabled
    firebase_cfg = get_firebase_config()
    if firebase_cfg:
        project_id = firebase_cfg["projectId"]
        auth_configs.append(
            AuthConfig(
                issuer=f"https://securetoken.google.com/{project_id}",
                jwks_url="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
                audience=project_id,
            )
        )

    return auth_configs


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

    auth_configs = parse_auth_configs()

    if len(auth_configs) == 0:
        print("No auth extensions found")
        app.state.auth_configs = None
    else:
        print(f"Found {len(auth_configs)} auth config(s)")
        app.state.auth_configs = auth_configs

    @app.on_event("startup")
    async def _warm_search_index():
        # Preload the in-memory catalog search index in the background so the
        # first real search is already fast. Never blocks startup.
        import asyncio

        async def _warm():
            try:
                from app.apis.products import get_conn, _load_search_index
                conn = await get_conn()
                try:
                    await _load_search_index(conn)
                    print("search index warmed")
                finally:
                    await conn.close()
            except Exception as e:  # noqa: BLE001
                print(f"search index warm-up skipped: {e}")

        asyncio.create_task(_warm())

    # Registered last: its catch-all route must not shadow the API routes.
    mount_frontend(app)

    return app


app = create_app()
