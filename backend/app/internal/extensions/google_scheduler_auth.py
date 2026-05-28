from .auth import AuthConfig

# TODO: We should probably use a generic oidc client instead and get better caching etc
# https://developers.google.com/identity/openid-connect/openid-connect#discovery
# openid_config_url = "https://accounts.google.com/.well-known/openid-configuration"

# TODO: Make this configurable via env instead of hardcoding
SCHEDULER_EMAIL = "riff-user-apps-scheduler@databutton.iam.gserviceaccount.com"
SCHEDULER_SUB = "103554423707375679125"

PUBLIC_RIFF_SCHEDULER_SUB = "riff-scheduler"


def get_google_scheduler_auth_config(
    *,
    project_id: str,
    service_type: str,
    host: str,
) -> AuthConfig:
    if not host.startswith("https://"):
        host = f"https://{host}"

    # Keep an open mind here because we've been changing domains a lot, but
    # we're going to stick to project_id in the future and can clean up this later
    audiences = (project_id,) + tuple(
        f"{devx_host}/_projects/{project_id}/dbtn/{service_type}/app{{path}}"
        for devx_host in (
            host,
            "https://api.databutton.com",
            "https://api.riff.new",
            "https://api.riff.ai",
            "https://api.useriff.ai",
            "https://api.riff.hot",
        )
    )

    return AuthConfig(
        issuer="https://accounts.google.com",
        jwks_url="https://www.googleapis.com/oauth2/v3/certs",
        audiences=audiences,
        sub=SCHEDULER_SUB,
        email=SCHEDULER_EMAIL,
        present_as_sub=PUBLIC_RIFF_SCHEDULER_SUB,
    )
