import time
from collections import Counter

from fastapi import APIRouter, params
from fastapi.routing import APIRoute, APIWebSocketRoute
from starlette.routing import WebSocketRoute

from .config import Config
from .messages import (
    Endpoint,
    ImportResult,
    WSEndpoint,
)
from .mw.auth_mw import (
    get_authorized_apikey,
    get_authorized_user,
    get_authorized_user_or_apikey,
)
from .notifications import DevxClient
from .pathutils import convert_exception_to_model, find_submodules, read_router_config
from .utils import debug

HAS_AUTH_TAG = "dbtn/hasAuth"
MODULE_TAG = "dbtn/module"


# Note: If reload issues continue, we could try to write these
# imports to a file with a timestamp on updates in devx,
# and import that file here instead.
def import_submodules(
    cfg: Config,
    devx: DevxClient,
    module_prefix: str,
    submodules: list[str],
) -> tuple[dict[str, APIRouter], list[ImportResult]]:
    routers: dict[str, APIRouter] = {}
    known_route_ids: set[int] = set()
    import_results: list[ImportResult] = []
    debug(f"import_submodules importing from {module_prefix}: {submodules}")
    for name in submodules:
        result = ImportResult(
            moduleName=name,
            importTime=0.0,
            ok=False,
            importException=None,
            errors=[],
            endpoints=[],
            wsEndpoints=[],
        )
        import_results.append(result)

        # Import the module from disk
        t0 = time.monotonic()
        try:
            name_parts = name.split("/")
            full_module_name = module_prefix + ".".join(name_parts)
            mod = __import__(full_module_name, fromlist=[name_parts[-1]])
            # mod = __import__(module_prefix + name, fromlist=[name])
            result.importTime = time.monotonic() - t0
        except Exception as ex:
            # import sys
            # import os
            # print("sp: ", sys.prefix)
            # print("pp: ", os.environ.get("PYTHONPATH"))

            result.importTime = time.monotonic() - t0
            result.importException = convert_exception_to_model(cfg, ex)
            mod = None
            if cfg.ENABLE_WORKSPACE_PUBLISH:
                # In development, publish errors on import, but try to stay alive
                devx.notify_import_error_sync(name, ex)
            else:
                # In production, raise, ideally we shouldn't allow deploying when import in dev resulted in errors
                debug(ex)
                pass
        if mod is None:
            continue

        # Get the router object from module
        user_router = getattr(mod, "router", None)
        if user_router is None:
            result.errors.append(f"Warning: No router found in user module {name}")
            continue

        # Check for router reuse (import of router from other api file is not allowed)
        if any(user_router is r for r in routers.values()):
            result.errors.append(
                f"In {name}: sharing routers between files is not allowed"
            )

        # Store router by module name (could be duplicates here)
        routers[name] = user_router

        # Find unique route instances that are not from a
        # previous import of the default router
        # or from a router shared between modules
        new_routes = [
            r
            for r in user_router.routes
            if isinstance(r, APIRoute) and id(r) not in known_route_ids
        ]
        known_route_ids.update(id(r) for r in new_routes)

        # Add websocket routes to import results
        new_ws_routes = [
            r
            for r in user_router.routes
            if isinstance(r, APIWebSocketRoute) and id(r) not in known_route_ids
        ]
        known_route_ids.update(id(r) for r in new_ws_routes)

        # Tag each route with module name so we can backtrack
        # from openapi spec to the backend component
        for r in new_routes:
            r.tags.append(f"{MODULE_TAG}:{name}")

        debug(
            f"import_submodules: new routes {name} {[(r.name, r.tags) for r in new_routes]}"
        )

        # Build minimal descriptions of all imported endpoints
        for r in new_routes:
            # Check for one method per handler
            methods = [m.upper() for m in r.methods]
            errors: list[str] = []
            if len(methods) == 1:
                method = methods[0]
            else:
                method = ", ".join(methods)
                errors.append(
                    f"Only one HTTP method supported per endpoint function, got {method}"
                )
            result.endpoints.append(
                Endpoint(
                    method=method,
                    path=r.path,
                    functionName=r.name,
                    errors=errors,
                )
            )
        for wr in new_ws_routes:
            result.wsEndpoints.append(
                WSEndpoint(
                    path=wr.path,
                    functionName=wr.name,
                    errors=[],
                )
            )

    add_uniqueness_check_errors(import_results)

    return routers, import_results


def add_uniqueness_check_errors(import_results: list[ImportResult]):
    """Add uniqueness check errors to import results."""

    # TODO: Checks for websocket routes as well
    # TODO: Make checks refer to where the duplicate is defined

    # Uniqueness checks
    empty_paths = set[str]()
    seen_method_paths: set[tuple[str, str]] = set()
    duplicate_method_paths: set[tuple[str, str]] = set()
    seen_names: set[str] = set()
    duplicate_names: set[str] = set()
    for result in import_results:
        for ep in result.endpoints:
            if not ep.path:
                # Empty paths can't be mounted on a router without a prefix
                empty_paths.add(ep.functionName)
            else:
                # Uniqueness check on method + url path
                # (other handlers can have same path but different method)
                method_path = (ep.method, ep.path)
                if method_path in seen_method_paths:
                    duplicate_method_paths.add(method_path)
                seen_method_paths.add(method_path)

            # Uniqueness check on handler function name
            # (other modules can have same function name but that would map
            # to the same function in the generated api client)
            if ep.functionName in seen_names:
                duplicate_names.add(ep.functionName)
            seen_names.add(ep.functionName)

    # Gather errors
    for result in import_results:
        for ep in result.endpoints:
            method_path = (ep.method, ep.path)
            if method_path in duplicate_method_paths:
                ep.errors.append(f"Duplicate endpoint route: {ep.method} {ep.path}")
            if ep.functionName in duplicate_names:
                ep.errors.append(f"Duplicate endpoint function: {ep.functionName}")
            if ep.functionName in empty_paths:
                ep.errors.append(
                    f"Illegal blank path for endpoint function: {ep.functionName}"
                )

    # Summarize as ok if nothing wrong, keep this updated if error structure changes
    for result in import_results:
        result.ok = (
            result.importException is None
            and len(result.errors) == 0
            and all(len(ep.errors) == 0 for ep in result.endpoints)
            and all(len(wep.errors) == 0 for wep in result.wsEndpoints)
        )


def make_user_endpoints_router(
    cfg: Config,
    devx: DevxClient,
    auth_dependencies: list[params.Depends],
    enable_auth: bool,
) -> tuple[APIRouter, list[ImportResult]]:
    """Create router for user defined endpoints."""
    prefix_router = APIRouter(prefix="/routes")

    # Import user defined submodules that add endpoints to router from .baserouter
    module_prefix, submodule_names = find_submodules(cfg)
    user_routers, import_results = import_submodules(
        cfg, devx, module_prefix, submodule_names
    )

    # Find duplicate routers (legacy default router or cross module imports)
    id_counts = Counter(id(router) for router in user_routers.values())
    duplicates = set(
        name for name, router in user_routers.items() if id_counts[id(router)] > 1
    )

    # Read router configs
    router_configs = read_router_config(cfg)

    # User routers are added as siblings, this includes the default router
    for name, user_router in user_routers.items():
        router_config = router_configs and router_configs.routers.get(name)

        # Router is configured to be public even if auth is enabled
        router_is_configured_public = (
            bool(router_config.disableAuth) if router_config else False
        )

        if name in duplicates and router_is_configured_public:
            # Changing publicness of shared routers can lead to unintended public endpoints,
            # so erring on the side of caution here and set not public and add error
            router_is_configured_public = False
            for ir in import_results:
                if ir.moduleName == name:
                    ir.errors.append(
                        "Cannot disable auth on router shared between modules."
                    )

        # Note: this code runs also when there is no auth, then enable_auth is False
        enable_router_auth = enable_auth and not router_is_configured_public

        # For each endpoint in the router, add the auth tag if needed
        for r in user_router.routes:
            if isinstance(r, WebSocketRoute):
                # TODO: Want to add auth tag to websockets but fastapi doesn't support tags on websocket routes,
                #       we'll need to pass it on a side channel outside the openapi spec
                pass
            elif isinstance(r, APIRoute):
                endpoint_has_direct_auth_dep = any(
                    d.dependency
                    in (
                        get_authorized_user_or_apikey,
                        get_authorized_user,
                        get_authorized_apikey,
                    )
                    for d in r.dependencies
                )
                if endpoint_has_direct_auth_dep or enable_router_auth:
                    if HAS_AUTH_TAG not in r.tags:
                        r.tags.append(HAS_AUTH_TAG)

        # Add auth dependency at the router level if needed
        deps = auth_dependencies if enable_router_auth else []
        prefix_router.include_router(user_router, dependencies=deps)

    # Returning the prefix router here ensures we're adding it
    # to the app AFTER user defined endpoints have been added
    return prefix_router, import_results
