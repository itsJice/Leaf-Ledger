from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

# https://fastapi.tiangolo.com/tutorial/middleware/
# https://github.com/encode/uvicorn/blob/master/uvicorn/middleware/message_logger.py
# https://www.starlette.io/authentication/
# https://github.com/thearchitector/starlette-securecookies/blob/main/securecookies/middleware.py


# Template for new middleware, copy paste and modify
class DoNothingMiddleware(BaseHTTPMiddleware):
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
        try:
            response: Response = await call_next(request)
            return response
        except Exception as exc:
            raise exc
