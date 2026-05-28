import functools
import json
import os
import threading
import time
from http import HTTPStatus
from typing import Annotated, Any, Callable, Generic, TypeVar

import httpx
import jwt
from fastapi import Depends, HTTPException, WebSocket, WebSocketException, status
from fastapi.datastructures import URL
from fastapi.requests import HTTPConnection
from jwt import PyJWKClient
from pydantic import BaseModel
from starlette.requests import Request

from ..dbapi import get_dbapi_client
from ..extensions.auth import AuthConfig
from ..parsing import parse_dict
from ..state import databutton_app_state

# https://firebase.google.com/docs/auth/admin/verify-id-tokens#verify_id_tokens_using_a_third-party_jwt_library


RIFF_API_KEY_PREFIX = "rfk-"

# Short cache in dev, longer cache in prod
DEFAULT_CREDENTIALS_CACHE_SECONDS = (
    60.0
    if os.environ.get("ENVIRONMENT") == "development"
    or os.environ.get("DATABUTTON_SERVICE_TYPE") == "devx"
    else 300.0
)


T = TypeVar("T")


class TTLCache(Generic[T]):
    """Thread-safe TTL cache for token validation results."""

    def __init__(
        self,
        ttl_seconds: float = DEFAULT_CREDENTIALS_CACHE_SECONDS,
        max_size: int = 100,
    ):
        self._cache: dict[str, tuple[T, float]] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds
        self._max_size = max_size

    def get(self, key: str) -> T | None:
        with self._lock:
            if key not in self._cache:
                return None
            value, expiry = self._cache[key]
            if time.monotonic() > expiry:
                del self._cache[key]
                return None
            return value

    def set(self, key: str, value: T) -> None:
        with self._lock:
            if len(self._cache) >= self._max_size:
                self._evict_expired()
            if len(self._cache) >= self._max_size:
                oldest_key = min(self._cache.keys(), key=lambda k: self._cache[k][1])
                del self._cache[oldest_key]
            self._cache[key] = (value, time.monotonic() + self._ttl)

    def _evict_expired(self) -> None:
        now = time.monotonic()
        expired = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in expired:
            del self._cache[k]


@functools.cache
def get_project_id() -> str:
    project_id = os.environ.get("DATABUTTON_PROJECT_ID")
    if not project_id:
        raise RuntimeError("Missing DATABUTTON_PROJECT_ID")
    return project_id


@functools.cache
def get_dbapi_service_url() -> str:
    u = os.environ.get("DATABUTTON_API_URL")
    if u:
        return u
    project_id = get_project_id()
    return f"https://api.riff.new/_projects/{project_id}/dbtn"


def get_apikeys_service_url() -> str:
    dbapi_url = get_dbapi_service_url()
    return f"{dbapi_url}/riff-api/apikeys/v1"


class User(BaseModel):
    # The subject, or user ID, from the authenticated token
    sub: str

    # Optional extra user data
    user_id: str | None = None
    name: str | None = None
    picture: str | None = None
    email: str | None = None

    # Standard JWT claims
    aud: str | None = None
    iss: str | None = None


class ApiKeyClaims(BaseModel):
    sub: str
    claims: dict[str, Any] = {}


class ValidatedBearerContents(BaseModel):
    user: User | None = None
    apikey: ApiKeyClaims | None = None


# Separate caches: API key validation doesn't depend on URL, JWT does
_apikey_cache: TTLCache[ApiKeyClaims] = TTLCache()
_jwt_cache: TTLCache[User] = TTLCache()
_stack_metadata_cache: TTLCache[dict[str, Any]] = TTLCache()


@functools.cache
def get_jwks_client(url: str):
    """Reuse client cached by its url, client caches keys by default."""
    # TODO: We may want to cache keys on disk to survive hotreloads
    return PyJWKClient(url, cache_keys=True)


def get_signing_key(url: str, token: str) -> tuple[str, str]:
    client = get_jwks_client(url)
    signing_key = client.get_signing_key_from_jwt(token)
    key = signing_key.key
    alg = signing_key.algorithm_name
    if alg not in ("RS256", "ES256"):
        raise ValueError(f"Unsupported signing algorithm: {alg}")
    return (key, alg)


def validate_token(
    token: str,
    expected_audience: str,
    auth_config: AuthConfig,
    options: dict[str, Any] | None,
    audit_log: Callable[[str], None] | None,
) -> dict[str, Any] | None:
    try:
        key, alg = get_signing_key(auth_config.jwks_url, token)
    except Exception as e:
        if audit_log:
            audit_log(f"Failed to get signing key {e}")
        return None

    try:
        payload = jwt.decode(
            token,
            key=key,
            algorithms=[alg],
            audience=expected_audience,
            options=options,
        )
    except jwt.PyJWTError as e:
        if audit_log:
            audit_log(f"Failed to decode and validate token {e}")
        return None

    if "sub" not in payload:
        if audit_log:
            audit_log("Missing sub in token payload")
        return None

    # Optional sub check
    if auth_config.sub and payload.get("sub") != auth_config.sub:
        if audit_log:
            audit_log(
                f"Sub mismatch in token payload {payload.get('sub')} != {auth_config.sub}"
            )
        return None

    # Optional email check
    if auth_config.email and not (
        payload.get("email_verified") and payload.get("email") == auth_config.email
    ):
        if audit_log:
            audit_log(
                f"Email mismatch in token payload {payload.get('email')} != {auth_config.email}"
            )
        return None

    # Optional sub override used for giving scheduler a fixed and intuitive sub from user code
    if auth_config.present_as_sub:
        payload["sub"] = auth_config.present_as_sub
        payload["user_id"] = auth_config.present_as_sub

    return payload


def determine_expected_audience(
    token_aud: str | None, auth_cfg: AuthConfig, url: URL
) -> str | None:
    if not token_aud:
        return None

    audiences: tuple[str, ...] = (
        (auth_cfg.audience,) if auth_cfg.audience is not None else auth_cfg.audiences
    )

    if token_aud in audiences:
        return token_aud

    for aud_templ in audiences:
        if token_aud == aud_templ.replace("{path}", url.path):
            return token_aud

    return None


def authorize_jwt_token(
    token: str,
    url: URL,
    auth_configs: list[AuthConfig],
    audit_log: Callable[[str], None] | None,
    options: dict[str, Any] | None,
) -> User | None:
    # Skip cache in dev mode; include path in key for audience matching
    use_cache = options is None
    cache_key = f"{token}:{url.path}"

    if use_cache:
        cached = _jwt_cache.get(cache_key)
        if cached is not None:
            if audit_log:
                audit_log("JWT validation from cache")
            return cached

    # Partially parse token without verification
    unverified_payload = jwt.decode(
        token,
        options={
            "verify_signature": False,
            "verify_aud": False,
            "verify_iss": False,
        },
    )
    token_aud: str | None = unverified_payload.get("aud")
    token_iss: str | None = unverified_payload.get("iss")

    for auth_cfg in auth_configs:
        if token_iss != auth_cfg.issuer:
            continue

        expected_audience = determine_expected_audience(token_aud, auth_cfg, url)
        if not expected_audience:
            if audit_log:
                audit_log(
                    f"Auth audience mismatch path={url.path} iss={token_iss} aud={token_aud}"
                )
            continue

        payload = validate_token(token, expected_audience, auth_cfg, options, audit_log)
        if payload is None:
            continue

        try:
            user = parse_dict(payload, User)
            if audit_log:
                audit_log(f"User {user.sub} authenticated")
            # Cache successful validation
            if use_cache:
                _jwt_cache.set(cache_key, user)
            return user
        except Exception as e:
            if audit_log:
                audit_log(f"Failed to parse token payload: {e}")
            return None

    if audit_log:
        audit_log("Failed to validate authorization token")
    return None


class ApiKeyValidateResponse(BaseModel):
    claims: dict[str, Any] = {}


def authorize_apikey(
    apikey: str,
    request_id: str | None,
    audit_log: Callable[[str], None] | None,
) -> ApiKeyClaims | None:
    # Check cache first (keyed by apikey only - no URL dependency)
    cached = _apikey_cache.get(apikey)
    if cached is not None:
        if audit_log:
            audit_log("API key validation from cache")
        return cached

    try:
        client: httpx.Client = get_dbapi_client()
        response = client.post(
            "/riff-api/apikeys/v1/validate",
            headers={"X-Request-Id": request_id} if request_id else None,
            json={"apikey": apikey},
        )
        if response.status_code == 200:
            resp = ApiKeyValidateResponse.model_validate_json(response.text)
            sub = resp.claims.get("sub")
            if not sub:
                if audit_log:
                    audit_log("Missing sub in apikey validation response")
                return None

            result = ApiKeyClaims(sub=sub, claims=resp.claims)
            _apikey_cache.set(apikey, result)
            return result
    except Exception as e:
        if audit_log:
            audit_log(f"Failed to validate apikey: {e}")

    return None


def authorize_token(
    token: str,
    url: URL,
    request_id: str | None,
    auth_configs: list[AuthConfig],
    audit_log: Callable[[str], None] | None,
    options: dict[str, Any] | None,
) -> ValidatedBearerContents:
    if token.startswith(RIFF_API_KEY_PREFIX):
        parts = token.split(";")
        apikey = parts[0]

        apikey_claims = authorize_apikey(apikey, request_id, audit_log)

        # Optional user token in addition
        jwt_token = parts[1] if len(parts) == 2 else None

        # If apikey_claims has stackAuth config, use it to check jwt_token aud/iss
        if jwt_token and apikey_claims and apikey_claims.claims:
            if stack_auth_config := apikey_claims.claims.get("stackAuth"):
                if stack_auth_project_id := stack_auth_config.get("projectId"):
                    stack_auth_config = AuthConfig(
                        issuer=f"https://api.stack-auth.com/api/v1/projects/{stack_auth_project_id}",
                        jwks_url=f"https://api.stack-auth.com/api/v1/projects/{stack_auth_project_id}/.well-known/jwks.json",
                        audience=stack_auth_project_id,
                    )
                    # Check jwt only against this stack-auth project, ignore other config
                    auth_configs = [stack_auth_config]
    else:
        apikey_claims = None
        jwt_token = token

    user = (
        authorize_jwt_token(jwt_token, url, auth_configs, audit_log, options)
        if jwt_token
        else None
    )

    return ValidatedBearerContents(user=user, apikey=apikey_claims)


def insecure_auth_options_for_dev(
    request: Request,
    audit_log: Callable[[str], None] | None,
) -> dict[str, Any] | None:
    """Configure auth options for doing only partial JWT verification for development testing.

    export INSECURE_AUTH_BYPASS_ENABLED=true
    export ENVIRONMENT=development

    IT IS REALLY IMPORTANT THAT WE DON'T ENABLE THIS IN PRODUCTION!
    """

    if (
        # This should only run when explicitly enabled
        os.environ.get("INSECURE_AUTH_BYPASS_ENABLED") == "true"
        # This should never run in production
        and os.environ.get("ENVIRONMENT") == "development"
    ):
        options: dict[str, Any] = {
            "verify_signature": False,
            "verify_aud": False,
            "verify_exp": False,
        }
        if audit_log:
            audit_log(
                f"ENABLED INSECURE AUTH OPTIONS FOR DEBUGGING {json.dumps(options)}"
            )
        return options

    return None


def authorize_websocket(
    request: WebSocket,
    auth_configs: list[AuthConfig],
    audit_log: Callable[[str], None] | None,
) -> ValidatedBearerContents | None:
    # Parse Sec-Websocket-Protocol
    header = "Sec-Websocket-Protocol"
    sep = ","
    prefix = "Authorization.Bearer."
    protocols_header = request.headers.get(header)
    protocols = (
        [h.strip() for h in protocols_header.split(sep)] if protocols_header else []
    )

    token: str | None = None
    for p in protocols:
        if p.startswith(prefix):
            token = p.removeprefix(prefix)
            break

    if not token:
        if audit_log:
            audit_log(f"Missing bearer {prefix}.<token> in protocols")
        return None

    # Can't replace header here
    # request.headers[header] = sep.join(p for p in protocols if not p.startswith(prefix))

    request_id = request.headers.get("X-Request-Id")

    options = None
    return authorize_token(
        token, request.url, request_id, auth_configs, audit_log, options
    )


def authorize_request(
    request: Request,
    auth_configs: list[AuthConfig],
    audit_log: Callable[[str], None] | None,
) -> ValidatedBearerContents | None:
    cfg = databutton_app_state(request).cfg

    auth_header_name = "Authorization"

    auth_header = request.headers.get(auth_header_name)
    if not auth_header:
        if audit_log:
            audit_log(f'Missing header "{auth_header_name}"')
        return None

    token = auth_header.startswith("Bearer ") and auth_header.removeprefix("Bearer ")
    if not token:
        if audit_log:
            audit_log(f'Missing bearer token in "{auth_header_name}"')
        return None

    request_id = request.headers.get("X-Request-Id")

    if (
        cfg.ENABLE_MCP
        and cfg.INTERNAL_MCP_TOKEN
        and token.startswith(cfg.INTERNAL_MCP_TOKEN)
    ):
        # Short term solution for allowing MCP auth code to bypass the auth system.
        # The INTERNAL_MCP_TOKEN is generated randomly on service startup.
        mcp_client_id = request.headers.get("X-MCP-Client-Id")
        if audit_log:
            audit_log(f"Internal token accepted for MCP client {mcp_client_id}")
        return ValidatedBearerContents(
            user=User(sub="mcp-client", name=mcp_client_id or None),
            apikey=None,
        )

    options = (
        insecure_auth_options_for_dev(request, audit_log)
        if cfg.ENVIRONMENT == "development"
        else None
    )
    return authorize_token(
        token, request.url, request_id, auth_configs, audit_log, options
    )


def get_auth_configs(request: HTTPConnection) -> list[AuthConfig]:
    app_state = getattr(request.app.state, "databutton_app_state", None)
    if app_state is None:
        return []
    auth_configs: list[AuthConfig] = (
        getattr(app_state, "auth_configs", None) or []
    )
    return auth_configs


AuthConfigsDep = Annotated[list[AuthConfig], Depends(get_auth_configs)]


def get_audit_log(request: HTTPConnection) -> Callable[[str], None] | None:
    app_state = getattr(request.app.state, "databutton_app_state", None)
    if app_state is None:
        return None
    return getattr(app_state, "audit_log", None)


AuditLogDep = Annotated[Callable[[str], None] | None, Depends(get_audit_log)]


def get_validated_bearer_contents(
    request: HTTPConnection,
    auth_configs: AuthConfigsDep,
    audit_log: AuditLogDep,
) -> ValidatedBearerContents | None:
    try:
        if isinstance(request, WebSocket):
            return authorize_websocket(request, auth_configs, audit_log)
        elif isinstance(request, Request):
            return authorize_request(request, auth_configs, audit_log)
        else:
            if audit_log:
                audit_log(
                    "Request authorization validation skipped for unknown request type"
                )
            return None

    except Exception as e:
        if audit_log:
            audit_log(f"Request authorization validation failed: {e}")
        return None


AuthenticatedBearerContentsDep = Annotated[
    ValidatedBearerContents | None, Depends(get_validated_bearer_contents)
]


def get_authorized_user(
    request: HTTPConnection,
    auth_configs: AuthConfigsDep,
    audit_log: AuditLogDep,
    bearer_contents: AuthenticatedBearerContentsDep,
) -> User:
    if bearer_contents is not None and bearer_contents.user is not None:
        return bearer_contents.user

    if audit_log:
        audit_log("Request middleware could not authenticate user")

    if isinstance(request, WebSocket):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Not authenticated",
        )
    else:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED,
            detail="Not authenticated",
        )


AuthorizedUser = Annotated[User, Depends(get_authorized_user)]


def get_authorized_apikey(
    request: HTTPConnection,
    auth_configs: AuthConfigsDep,
    audit_log: AuditLogDep,
    bearer_contents: AuthenticatedBearerContentsDep,
) -> ApiKeyClaims:
    if bearer_contents is not None and bearer_contents.apikey is not None:
        return bearer_contents.apikey

    if audit_log:
        audit_log("Request middleware could not authenticate apikey")

    if isinstance(request, WebSocket):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated"
        )
    else:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED, detail="Not authenticated"
        )


AuthorizedApiKey = Annotated[ApiKeyClaims, Depends(get_authorized_apikey)]


def get_authorized_user_or_apikey(
    request: HTTPConnection,
    auth_configs: AuthConfigsDep,
    audit_log: AuditLogDep,
    bearer_contents: AuthenticatedBearerContentsDep,
) -> AuthenticatedBearerContentsDep:
    if bearer_contents is not None and (
        bearer_contents.user is not None or bearer_contents.apikey is not None
    ):
        return bearer_contents

    if audit_log:
        audit_log("Request middleware could not authenticate user or apikey")

    if isinstance(request, WebSocket):
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION, reason="Not authenticated"
        )
    else:
        raise HTTPException(
            status_code=HTTPStatus.UNAUTHORIZED, detail="Not authenticated"
        )


def get_stack_auth_user_metadata(
    access_token: str,
    user_id: str,
    project_id: str,
    publishable_key: str,
) -> dict:
    """Get user metadata from Stack Auth using only public credentials."""

    response = httpx.get(
        "https://api.stack-auth.com/api/v1/users/me",
        headers={
            "X-Stack-Access-Type": "client",
            "X-Stack-Project-Id": project_id,
            "X-Stack-Publishable-Client-Key": publishable_key,
            "X-Stack-Access-Token": access_token,
        },
    )
    user_data = response.json()

    # metadata = user_data.get("clientReadOnlyMetadata", {})
    #
    # return {
    #     "user_id": user_id,
    #     "email": user_data.get("primaryEmail"),
    #     "groups": metadata.get("entra_groups", []),
    #     "roles": metadata.get("entra_roles", []),
    #     "org_id": metadata.get("organization_id"),
    # }

    return user_data


def get_extra_stack_auth_metadata(
    request: HTTPConnection,
    auth_configs: AuthConfigsDep,
    audit_log: AuditLogDep,
    bearer_contents: AuthenticatedBearerContentsDep,
) -> dict[str, Any] | None:
    """Call stackauth metadata http endpoints to get extra custom claims."""

    # Assuming here an already validated stackauth user token
    if bearer_contents is None or bearer_contents.user is None:
        return None
    user_id = bearer_contents.user.sub
    if not user_id:
        return None

    authorization = request.headers.get("Authorization")
    if not authorization:
        return None
    bearer_token = authorization.removeprefix("Bearer ")

    use_cache = True
    cache_key = bearer_token
    if use_cache:
        cached = _stack_metadata_cache.get(cache_key)
        if cached is not None:
            if audit_log:
                audit_log("Stack Auth user metadata from cache")
            return cached

    # Extract access token from header with apikey;accesstoken, already validated
    bearer_token_parts = bearer_token.split(";")
    if len(bearer_token_parts) == 1:
        access_token = bearer_token
    elif len(bearer_token_parts) == 2:
        access_token = bearer_token_parts[1]
    else:
        return None

    stack_auth_project_id: str | None = None
    stack_auth_publishable_client_key: str | None = None

    if bearer_contents.apikey is not None and bearer_contents.apikey.claims:
        # We've got a validated apikey, check for stackauth config in apikey claims
        stack_auth_config = bearer_contents.apikey.claims.get("stackAuth")
        if not stack_auth_config:
            return None
        stack_auth_project_id = stack_auth_config.get("projectId")
        stack_auth_publishable_client_key = stack_auth_config.get(
            "publishableClientKey"
        )
    else:
        # Get stackauth config from databutton extension
        try:
            for ext in json.loads(os.environ.get("DATABUTTON_EXTENSIONS", "")):
                if ext["name"] == "stack-auth":
                    config = ext["config"]
                    stack_auth_project_id = config["projectId"]
                    stack_auth_publishable_client_key = config["publishableClientKey"]
        except Exception:
            return None

    if not stack_auth_project_id:
        return None
    if not stack_auth_publishable_client_key:
        return None

    metadata = get_stack_auth_user_metadata(
        access_token,
        user_id,
        stack_auth_project_id,
        stack_auth_publishable_client_key,
    )
    if use_cache:
        _stack_metadata_cache.set(cache_key, metadata)
    return metadata


StackAuthUserData = Annotated[
    dict[str, Any] | None, Depends(get_extra_stack_auth_metadata)
]
