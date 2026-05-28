import random

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


def get_current_request_id(request: Request) -> str:
    return request.state.request_id


# Note: There's possibly some standard middleware for this, maybe it does something smart
class RequestIdMiddleware(BaseHTTPMiddleware):
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
        # If missing, make up a request id (in practice this
        # only happens during testing with a funky environment)
        request_id = (
            request.headers.get("x-request-id") or "req-" + random.randbytes(8).hex()
        )
        request.state.request_id = request_id
        return await call_next(request)
