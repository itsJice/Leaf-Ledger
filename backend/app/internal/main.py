import os
import re
import signal
import time
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import Depends, FastAPI, HTTPException, params
from fastapi.routing import APIRoute, APIWebSocketRoute
from pydantic import BaseModel

from .apirouters import make_user_endpoints_router
from .config import Config, checked_config
from .exceptionmodel import ExceptionModel
from .logcapture import install_logcapture
from .messages import (
    BackendReady,
    BackendShutdown,
    RefreshOpenapiSpecParams,
    Topics,
)
from .mw.auth_mw import get_authorized_user_or_apikey
from .mw.cookie_mw import CookieKillerMiddleware
from .mw.requestid_mw import RequestIdMiddleware
from .mw.workspace_mw import WorkspacePublishMiddleware
from .notifications import DevxClient
from .pathutils import convert_exception_to_model
from .secrets import fetch_and_inject_secrets
from .state import AppStateDep, get_app_state, init_app_state, set_app_state
from .utils import compute_spec_signature, utc_now

# Get secrets from .env file or api, this must happen before loading the routers
fetch_and_inject_secrets()


def configure_log_forwarding(devx: DevxClient):
    """Configure log forwarding.

    Forwards logs to devx which sends them over websockets to web clients.

    Skip when running locally because then there may
    be circular dependencies in log captures so be careful.
    When running locally for development there may be no devx server.
    """

    def forward_stdout(s: str):
        devx.notify_logs(s, "info")

    def forward_stderr(s: str):
        devx.notify_logs(s, "error")

    install_logcapture(forward_stdout, forward_stderr)


class HealthResponse(BaseModel):
    status: str


# def signal_handler(sig: int, frame: Optional[FrameType]):
#     if sig in (signal.SIGTERM, signal.SIGINT, signal.SIGKILL):
#         print(f"Received signal {sig}, shutting down databutton app")
#         raise SystemExit(0)
#
#
# signal.signal(signal.SIGTERM, signal_handler)
# signal.signal(signal.SIGINT, signal_handler)


health_shutdown_counter = (
    5 if os.environ.get("SHUTDOWN_AFTER_HEALTHCHECK") == "1" else None
)


def _health_shutdown_countdown():
    """Special behaviour for Databutton service pool."""
    global health_shutdown_counter
    if health_shutdown_counter is None:
        return
    health_shutdown_counter -= 1
    if health_shutdown_counter < 0:
        print("Health checks completed, shutting down.")
        time.sleep(1)
        signal.raise_signal(signal.SIGTERM)
    else:
        print(f"{health_shutdown_counter} health checks left until shutdown")


# NB: Name of this function becomes a property of the generated api client and callable by the user web app
def check_health(
    app_state: AppStateDep,
) -> HealthResponse:
    """Check health of application. Returns 200 when OK, 500 when not."""
    if not app_state.started_event.is_set():
        raise HTTPException(status_code=500)
    _health_shutdown_countdown()
    return HealthResponse(status="healthy")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle context manager for the app in devx mode."""

    app_state = get_app_state(app)
    cfg = app_state.cfg
    devx = app_state.devx

    # Hack to avoid TestClient running lifespan multiple times
    skip_init = app_state.started_event.is_set()

    enable_publishing = bool(cfg.ENABLE_WORKSPACE_PUBLISH and not skip_init)

    # Generate and post openapi spec to devx
    spec: Dict[str, Any] | None = None
    signature: str | None = None
    if enable_publishing:
        try:
            spec = app.openapi()
            signature = compute_spec_signature(spec)
        except Exception as ex:
            # TODO: Publish other error type
            await devx.notify_import_error_async("<openapi-spec>", ex)

        if spec is not None and signature is not None:
            try:
                await devx.notify_devx_refresh_openapi_spec(
                    RefreshOpenapiSpecParams(
                        timestamp=utc_now(),
                        openapiSignature=signature,
                        openapiDoc=spec,
                        importResults=app_state.submodule_import_results,
                    ),
                )
            except Exception as ex:
                # TODO: Publish other error type
                await devx.notify_import_error_async("<openapi-publish>", ex)

    # Set flag for health endpoint to start returning OK
    app_state.started_event.set()

    # Publish that we're up and running again
    if enable_publishing:
        await devx.notify_devx_async(
            Topics.backend_ready,
            BackendReady(
                timestamp=utc_now(),
                openapiSignature=signature,
                startupTime=time.monotonic() - app_state.app_created_time,
                importResults=app_state.submodule_import_results,
                ok=all(m.ok for m in app_state.submodule_import_results),
            ),
        )

    # Yield for the active lifespan of the app
    yield

    # App is shutting down
    if enable_publishing:
        await devx.notify_devx_async(
            Topics.backend_shutdown,
            BackendShutdown(
                timestamp=utc_now(),
                openapiSignature=signature,
            ),
        )


def add_middleware(app: FastAPI):
    """Adds middleware to the app."""

    #
    # NB! Middleware added with app.add_middleware runs in the opposite order!
    # E.g. the request-id middleware is at the end here so the request id is
    # available in the other middlewares.
    #

    app_state = get_app_state(app)
    cfg = app_state.cfg
    devx = app_state.devx

    # Publish request checkpoint messages to workspace if enabled
    if cfg.ENABLE_WORKSPACE_PUBLISH:

        def e2m(ex: BaseException) -> ExceptionModel:
            return convert_exception_to_model(cfg, ex)

        app.add_middleware(
            WorkspacePublishMiddleware,
            exception_to_model=e2m,
            publish=devx.notify_devx_async,
        )

    # Kill cookies (can perhaps open up when all apps are on subdomains, although if we
    # want to open up cookies on databutton.com, we need to enforce path restriction)
    app.add_middleware(
        CookieKillerMiddleware,
    )

    # Skip some extra validation when working in a local environment
    # Disabled, don't think this is very useful
    # if cfg.ENVIRONMENT != "development":
    #     app.add_middleware(
    #         DevxValidationMiddleware,
    #         project_id=cfg.DATABUTTON_PROJECT_ID,
    #         service_type=cfg.DATABUTTON_SERVICE_TYPE,
    #     )

    # Note: CORS is configured in external proxy

    # Extract or make up a request id
    app.add_middleware(
        RequestIdMiddleware,
    )


def custom_generate_unique_id(route: APIRoute | APIWebSocketRoute):
    """We use a custom openapi route id generation.

    Here we produce ids that can be used as unique method names
    in the generated brain client in typescript.
    """

    # Example route properties:
    # route.name: name_of_handler_function
    # route.path_format: /routes/unrelated/path/name/{param}
    # route.endpoint: <function name_of_handler_function>
    # route.tags: []
    # route.methods: {'GET'}

    # Just use the name of the python handler function!
    # Assuming:
    # - nobody uses both @router.get and @router.post on the same handler.
    # - nobody uses the same python function name for handlers in different files
    return re.sub(r"\W", "_", route.name)


def create_app(cfg: Config | None = None) -> FastAPI:
    """Factory function to create app object.

    This is called by e.g. uvicorn to construct the app object.
    """
    cfg = checked_config(cfg)
    app_state = init_app_state(cfg)
    devx = app_state.devx

    app = FastAPI(
        title="Databutton generated API",
        version="0.0.1",
        servers=[
            {
                "url": f"http://127.0.0.1:{cfg.USER_API_PORT}",
                "description": "Internal",
            },
            {
                "url": f"{cfg.DEVX_HOST}{cfg.DEVX_BASE_PATH}/app",
                "description": "External",
            },
        ],
        generate_unique_id_function=custom_generate_unique_id,
        lifespan=lifespan,
    )

    # Attach app-wide state without using global variables, this is what
    # will make testing with different app configurations possible
    set_app_state(app, app_state)

    # Process exceptions more?
    # def exception_handler(request: Request, exc: Exception) -> Response:
    # app.add_exception_handler(Exception, exception_handler)
    # app.add_exception_handler(422, exception_handler)

    # Add middleware applying to all routers
    add_middleware(app)

    # Internal health check endpoint.
    # Called by infrastructure on container startup.
    # Included in api spec to ensure brain client is always generated.
    # Can also be used by users webapp to ping user's backend for faster perceived startup in prod.
    app.get("/_healthz")(check_health)

    # Build dependencies to inject in routers
    auth_dependencies: list[params.Depends] = (
        [Depends(get_authorized_user_or_apikey)] if app_state.auth_configs else []
    )

    if cfg.ENABLE_WORKSPACE_PUBLISH and cfg.DEVX_URL_INTERNAL:
        # Wait for devx server to have written initial code files
        # to disk before we try to import user endpoint modules.
        # NB! This is deliberately NOT the regular devx health endpoint,
        # because that one waits for this app to be ready!
        if not devx.wait_for_devx_ready():
            raise RuntimeError("Devx server not ready.")

        # Configure log forwarding here so prints during imports are included
        configure_log_forwarding(devx)

    # Import user code to define routes
    try:
        user_endpoints_router, import_results = make_user_endpoints_router(
            cfg,
            devx,
            auth_dependencies=auth_dependencies,
            enable_auth=len(app_state.auth_configs) > 0,
        )
        app.include_router(user_endpoints_router)
        app_state = get_app_state(app)
        app_state.submodule_import_results = import_results

    except Exception as ex:
        if cfg.ENABLE_WORKSPACE_PUBLISH:
            devx.notify_import_error_sync("<router>", ex)

    return app
