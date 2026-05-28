import base64
import os
import time

import dotenv
import httpx
from pydantic import BaseModel

from app.internal.dbapi import get_dbapi_client


def from_b64(name: str, b64: str) -> str:
    try:
        value_bytes = base64.urlsafe_b64decode(b64.encode("utf-8"))
    except Exception:
        print(f"Error(1) decoding value of secret {name}, try adding it again")
        return ""
    try:
        value_str = value_bytes.decode("utf-8")
    except UnicodeDecodeError:
        print(f"Error(2) decoding value of secret {name}, try adding it again")
        value_str = value_bytes.decode("utf-8", errors="ignore")
    return value_str


def fetch_deployment_secrets_v2(deployment_id: str) -> dict[str, str]:
    if os.environ.get("DISABLE_SECRETS_V2") == "1":
        return {}

    client: httpx.Client = get_dbapi_client()
    t0 = time.monotonic()
    delay = 1.0
    response: httpx.Response | None = None

    attempt = 1
    while True:
        response = client.get(
            f"/secrets/v2/deployment/{deployment_id}",
            timeout=30.0,
        )
        if 200 <= response.status_code < 300:
            break

        # Retry logic
        attempt += 1
        if attempt > 5:
            break
        print(f"Retrying secrets fetch in {delay}s after {attempt} attempts")
        time.sleep(delay)
        delay *= 2.0
    t1 = time.monotonic()
    print(f"Time to fetch secrets v2: {t1 - t0}")

    # Can raise if the last attempt failed
    response.raise_for_status()

    result = response.json()

    # Note: result data type here is RefreshSecretsResponse from devx
    secrets: list[dict[str, str]] = result.get("secrets")
    items = ((s.get("name"), s.get("valueBase64")) for s in secrets)
    cleaned_vars = {k: from_b64(k, v) for k, v in items if v is not None and k}
    return cleaned_vars


class ConfigValue(BaseModel):
    value: str
    ref: str
    error: str | None = None


class ResolvedEnvConfig(BaseModel):
    variables: dict[str, ConfigValue]


class ResolvedConfigResponse(BaseModel):
    environments: dict[str, ResolvedEnvConfig]


def fetch_deployment_secrets_v3(deployment_id: str) -> dict[str, str]:
    client: httpx.Client = get_dbapi_client()
    t0 = time.monotonic()
    delay = 1.0
    response: httpx.Response | None = None

    attempt = 1
    while True:
        response = client.get(
            f"/riff-api/configs/v1/deployment/{deployment_id}",
            timeout=30.0,
        )
        if 200 <= response.status_code < 300:
            print("Successfully fetched secrets for deployment")
            break

        # Retry logic
        attempt += 1
        if attempt > 5:
            break
        print(f"Retrying secrets fetch in {delay}s after {attempt} attempts")
        time.sleep(delay)
        delay *= 2.0
    t1 = time.monotonic()
    print(f"Time to fetch secrets v3: {t1 - t0}")

    # Can raise if the last attempt failed
    response.raise_for_status()

    cfg = ResolvedConfigResponse.model_validate_json(response.text)
    secrets: dict[str, str] = {}
    for env in ("app", "prod"):
        if environment := cfg.environments.get(env):
            for name, var in environment.variables.items():
                if error := var.error:
                    print(f"Failed to fetch variable {name} from {var.ref}: {error}")
                else:
                    secrets[name] = var.value
    return secrets


def fetch_and_inject_deployment_secrets() -> None:
    deployment_id = os.environ.get("DATABUTTON_DEPLOYMENT_ID")
    if not deployment_id:
        print("Missing deployment id, not fetching secrets")
        return

    try:
        vars_v2 = fetch_deployment_secrets_v2(deployment_id)
        os.environ.update(**vars_v2)
    except Exception:
        # Catch all exceptions to avoid leaking secrets into logs
        raise RuntimeError("Failed to fetch v2 secrets")

    try:
        vars_v3 = fetch_deployment_secrets_v3(deployment_id)
        os.environ.update(**vars_v3)
    except Exception:
        # Catch all exceptions to avoid leaking secrets into logs
        raise RuntimeError("Failed to fetch v3 secrets")


def fetch_and_inject_workspace_secrets() -> None:
    dotenv.load_dotenv(os.environ.get("DOT_ENV_FILE", ".env"))


def fetch_and_inject_secrets() -> None:
    service_type = os.environ.get("DATABUTTON_SERVICE_TYPE")

    if service_type == "devx":
        fetch_and_inject_workspace_secrets()
    elif service_type == "prodx":
        is_deployed = bool(os.environ.get("DATABUTTON_DEPLOYMENT_ID"))
        if is_deployed:
            fetch_and_inject_deployment_secrets()
        else:
            raise RuntimeError("Unexpected undeployed prodx app")
    else:
        raise RuntimeError(
            f"Unexpected environment '{service_type}' when fetching secrets"
        )
