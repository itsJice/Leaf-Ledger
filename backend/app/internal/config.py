import functools
import os
from enum import Enum
from typing import Any

from pydantic import BaseModel

from .extensions.auth import AuthConfig
from .extensions.firebase_auth import (
    FirebaseExtensionConfig,
    get_firebase_auth_config,
)
from .extensions.google_scheduler_auth import (
    get_google_scheduler_auth_config,
)
from .extensions.internal_auth import get_internal_auth_config
from .extensions.stack_auth import (
    StackAuthExtensionConfig,
    get_stack_auth_auth_config,
)
from .parsing import parse_json_list
from .utils import debug_enabled


class ExtensionType(str, Enum):
    """Type of extension."""

    shadcn = "shadcn"
    firebase_auth = "firebase-auth"
    stack_auth = "stack-auth"
    neon_database = "neon-database"
    mcp = "mcp"
    posthog = "posthog"


class Extension(BaseModel):
    # Note: Fallback to str for less strict parsing across versions etc
    name: ExtensionType | str
    version: str
    config: dict[str, Any] | None = None


class Config(BaseModel):
    ENVIRONMENT: str = "development"

    DATABUTTON_PROJECT_ID: str = ""
    DATABUTTON_SERVICE_TYPE: str = ""

    DATABUTTON_EXTENSIONS: str = ""

    # Port of the internal devx server
    DEVX_API_PORT: int | None = None
    DEVX_URL_INTERNAL: str | None = None

    # Toggle publishing messages to devx server
    ENABLE_WORKSPACE_PUBLISH: bool | None = None

    # Root path of the app
    DEVX_BACKEND_DIR: str = ""

    # The external host we're served from
    DEVX_HOST: str = ""

    # The external url path that devx_url_internal is exposed as
    DEVX_BASE_PATH: str = ""

    # TODO: Only used for this, replace both with a single SERVER_URL
    # servers=[{"url": f"{cfg.DEVX_HOST}{cfg.DEVX_BASE_PATH}/app"}],

    USER_API_PORT: int = 9999

    ENABLE_MCP: bool = False
    INTERNAL_MCP_TOKEN: str = ""

    DISABLE_API_AS_INIT_PY: bool = False


@functools.cache
def parse_extensions(databutton_extensions: str) -> list[Extension]:
    extensions: list[Extension] = []
    if not databutton_extensions:
        print("No extensions env var")
    else:
        extensions = parse_json_list(databutton_extensions, Extension)
        if len(extensions) == 0:
            print("No extensions found")
        else:
            print(f"Found extensions: {[e.name for e in extensions]}")
    return extensions


def get_extensions(cfg: Config) -> list[Extension]:
    return parse_extensions(cfg.DATABUTTON_EXTENSIONS)


def get_extension(cfg: Config, name: ExtensionType) -> Extension | None:
    extensions = [e for e in get_extensions(cfg) if e.name == name]
    if not extensions:
        return None
    if len(extensions) > 1:
        print(f"WARNING: Got duplicate extension: {extensions}")
    return extensions[0]


def get_firebase_extension_config(cfg: Config) -> FirebaseExtensionConfig | None:
    extension = get_extension(cfg, ExtensionType.firebase_auth)
    if not extension or not extension.config:
        return None
    return FirebaseExtensionConfig(**extension.config)


def get_stack_auth_extension_config(cfg: Config) -> StackAuthExtensionConfig | None:
    extension = get_extension(cfg, ExtensionType.stack_auth)
    if not extension or not extension.config:
        return None
    return StackAuthExtensionConfig(**extension.config)


def parse_auth_configs(cfg: Config) -> list[AuthConfig]:
    # Each auth config has an audience and a jwks url to get signing key from,
    # the jwt bearer token is validated with the signing key from jwks urls
    # matching the audience found in the token
    auth_configs: list[AuthConfig] = []

    # Add stack auth config if extension is enabled
    if stack_auth_cfg := get_stack_auth_extension_config(cfg):
        auth_configs.append(get_stack_auth_auth_config(stack_auth_cfg))

    # Add firebase auth config if extension is enabled
    if firebase_auth_cfg := get_firebase_extension_config(cfg):
        auth_configs.append(get_firebase_auth_config(firebase_auth_cfg))

    # TODO: Add other JWKS compatible auth integrations like supabase here

    # The rest of the auth configs will be added only if the above configs are present
    if len(auth_configs) == 0:
        return auth_configs

    # Add google OIDC issuer config for scheduler
    auth_configs.append(
        get_google_scheduler_auth_config(
            project_id=cfg.DATABUTTON_PROJECT_ID,
            service_type=cfg.DATABUTTON_SERVICE_TYPE,
            host=cfg.DEVX_HOST,
        )
    )

    # Add internal devx audience and jwks url to get signing key from for test tokens
    if cfg.DATABUTTON_SERVICE_TYPE == "devx" and cfg.DEVX_URL_INTERNAL:
        auth_configs.append(
            get_internal_auth_config(
                internal_devx_url=cfg.DEVX_URL_INTERNAL,
                project_id=cfg.DATABUTTON_PROJECT_ID,
                service_type=cfg.DATABUTTON_SERVICE_TYPE,
            )
        )

    # TODO: This is only used in the mcp server for now, want to add api tokens for endpoints later
    # Config for databutton signed api tokens with the app as audience
    # auth_configs.append(
    #     AuthConfig(
    #         issuer="https://securetoken.google.com/databutton",
    #         jwks_url="https://www.googleapis.com/service_accounts/v1/jwk/securetoken@system.gserviceaccount.com",
    #         audience="databutton",
    #         require_dbtn_claims={
    #             "appId": cfg.DATABUTTON_PROJECT_ID,
    #             "env": cfg.DATABUTTON_SERVICE_TYPE,
    #         },
    #     )
    # )

    return auth_configs


def log_config(
    cfg: Config,
):
    lines = [
        "Environment",
        f"path = {os.environ.get('PATH')}",
        f"pythonpath = {os.environ.get('PYTHONPATH')}",
        f"virtual_env = {os.environ.get('VIRTUAL_ENV')}",
        "Config",
        f"environment               = {cfg.ENVIRONMENT}",
        f"project_id                = {cfg.DATABUTTON_PROJECT_ID}",
        f"service_type              = {cfg.DATABUTTON_SERVICE_TYPE}",
        f"devx_backend_dir          = {cfg.DEVX_BACKEND_DIR}",
        f"devx_api_port             = {cfg.DEVX_API_PORT}",
        f"devx_url_internal         = {cfg.DEVX_URL_INTERNAL}",
        f"enable_workspace_publish  = {cfg.ENABLE_WORKSPACE_PUBLISH}",
        f"devx_host                 = {cfg.DEVX_HOST}",
        f"devx_base_path            = {cfg.DEVX_BASE_PATH}",
        f"databutton_extensions     = {cfg.DATABUTTON_EXTENSIONS}",
    ]
    print("\n".join(lines))


def validate_config(cfg: Config):
    issues: list[str] = []
    if not cfg.DATABUTTON_PROJECT_ID:
        issues.append("Missing DATABUTTON_PROJECT_ID")
    if not cfg.DATABUTTON_SERVICE_TYPE:
        issues.append("Missing DATABUTTON_SERVICE_TYPE")
    if not cfg.DEVX_API_PORT:
        issues.append("Missing DEVX_API_PORT")
    if not cfg.DEVX_BACKEND_DIR:
        issues.append("Missing DEVX_BACKEND_DIR")

    if cfg.DATABUTTON_SERVICE_TYPE == "devx":
        if not cfg.DEVX_URL_INTERNAL:
            issues.append("Missing DEVX_URL_INTERNAL")

    try:
        parse_extensions(cfg.DATABUTTON_EXTENSIONS)
    except Exception as e:
        issues.append(f"Failed to parse extensions: {e}")

    if issues:
        if cfg.ENVIRONMENT == "development":
            print("\n".join("WARNING:" + msg for msg in issues))
        else:
            raise ValueError("; ".join(issues))


def parse_environment() -> Config:
    """Read config from env vars.

    Instead of using BaseSettings, just read env vars directly,
    avoiding the dependency on pydantic_settings.
    """
    cfg = Config()
    for k in cfg.__dict__.keys():
        if k in os.environ:
            setattr(cfg, k, os.environ[k])
    return cfg


def checked_config(cfg: Config | None = None) -> Config:
    """Read config from environment if not passed in, and validate it before returning."""
    if cfg is None:
        cfg = parse_environment()

    # TODO: Set this outside app?
    if cfg.ENABLE_WORKSPACE_PUBLISH is None:
        cfg.ENABLE_WORKSPACE_PUBLISH = cfg.DATABUTTON_SERVICE_TYPE != "prodx"

    # TODO: Set this outside app?
    if cfg.DEVX_API_PORT and not cfg.DEVX_URL_INTERNAL:
        cfg.DEVX_URL_INTERNAL = f"http://localhost:{cfg.DEVX_API_PORT}"

    if debug_enabled():
        log_config(cfg)

    validate_config(cfg)

    return cfg
