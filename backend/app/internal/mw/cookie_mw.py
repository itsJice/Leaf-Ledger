from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from .utils import remove_header


class CookieKillerMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
    ) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Redact incoming cookies if any
        remove_header(request, "Cookie")

        # Call request handler
        response = await call_next(request)

        # Redact attempt at setting cookie if any
        if "Set-Cookie" in response.headers:
            del response.headers["Set-Cookie"]

        return response
