"""FastAPI dependency for the signed-in user.

Identity comes from **Supabase Auth** — see `app.auth.supabase_auth`. The name
`AuthorizedUser` is kept from the original Databutton scaffolding so existing
endpoints keep working unchanged, but it now resolves against Supabase and the
token signature is actually verified.

Usage:

    from app.auth import AuthorizedUser, User

    @router.get("/get-user")
    def get_user(user: AuthorizedUser) -> User:
        return user  # user.sub is the verified Supabase user id
"""

from typing import Annotated, Optional

from fastapi import Depends
from pydantic import BaseModel

from app.auth.supabase_auth import AuthUser, get_current_user


class User(BaseModel):
    """The signed-in user, in the shape the existing endpoints expect."""

    sub: str
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None

    @property
    def display_name(self) -> str:
        return self.name or self.email or self.sub


def get_authorized_user(
    verified: Annotated[AuthUser, Depends(get_current_user)],
) -> User:
    """Adapt the verified Supabase user to the `User` shape used by endpoints."""
    return User(
        sub=verified.sub,
        user_id=verified.sub,
        email=verified.email,
        # Supabase has no display name by default; fall back to the email local part.
        name=(verified.email or "").split("@")[0] or None,
    )


AuthorizedUser = Annotated[User, Depends(get_authorized_user)]
