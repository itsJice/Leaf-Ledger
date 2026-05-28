"""Fastapi dependency to extract user that has been authenticated by middleware.

Usage:

    from app.auth import AuthorizedUser, AuthorizedApiKey, User, ApiKeyClaims

    @router.get("/get-user")
    def get_user(user: AuthorizedUser) -> User:
        return user

    @router.get("/get-apikey")
    def get_apikey(apikey: AuthorizedApiKey) -> ApiKeyClaims:
        return apikey

"""

from typing import Annotated, Any

from fastapi import Depends

from app.internal.mw.auth_mw import (
    ApiKeyClaims,
    User,
    get_authorized_apikey,
    get_authorized_user,
    get_extra_stack_auth_metadata,
)

AuthorizedUser = Annotated[User, Depends(get_authorized_user)]

AuthorizedApiKey = Annotated[ApiKeyClaims, Depends(get_authorized_apikey)]

StackAuthUserData = Annotated[
    dict[str, Any] | None, Depends(get_extra_stack_auth_metadata)
]
