from pydantic import BaseModel


class AuthConfig(BaseModel):
    issuer: str
    jwks_url: str
    audience: str | None = None
    audiences: tuple[str, ...] = ()
    sub: str | None = None
    email: str | None = None
    present_as_sub: str | None = None
