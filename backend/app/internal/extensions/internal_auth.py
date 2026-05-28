import os

from .auth import AuthConfig


def get_internal_auth_config(
    *,
    internal_devx_url: str,
    project_id: str,
    service_type: str,
) -> AuthConfig:
    devx_host = os.environ.get("DEVX_HOST") or "https://api.riff.new"
    devx_base_path = (
        os.environ.get("DEVX_BASE_PATH")
        or f"/_projects/{project_id}/dbtn/{service_type}"
    )
    return AuthConfig(
        issuer=f"{devx_host}{devx_base_path}/workspace/auth",
        jwks_url=f"{internal_devx_url}/workspace/auth/jwks",
        audience=f"{devx_host}{devx_base_path}",
    )
