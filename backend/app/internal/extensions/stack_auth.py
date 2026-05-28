from pydantic import BaseModel

from .auth import AuthConfig


class SecretRef(BaseModel):
    name: str


class StackAuthExtensionConfig(BaseModel):
    projectId: str
    publishableClientKey: str
    jwksUrl: str
    secretRefForSecretServerKey: SecretRef


def get_stack_auth_issuer(c: StackAuthExtensionConfig) -> str:
    return f"https://api.stack-auth.com/api/v1/projects/{c.projectId}"


def get_stack_auth_audience(c: StackAuthExtensionConfig) -> str:
    return c.projectId


def get_stack_auth_auth_config(c: StackAuthExtensionConfig) -> AuthConfig:
    return AuthConfig(
        issuer=get_stack_auth_issuer(c),
        jwks_url=c.jwksUrl,
        audience=get_stack_auth_audience(c),
    )
