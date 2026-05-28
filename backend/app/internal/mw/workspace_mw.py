import time
from typing import Any, Callable, Coroutine

from fastapi import HTTPException
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..exceptionmodel import ExceptionModel
from ..messages import RequestFinished, RequestStarted, Topics
from ..utils import utc_now
from .requestid_mw import get_current_request_id


class WorkspacePublishMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        # Exception converter
        exception_to_model: Callable[[BaseException], ExceptionModel],
        # Callback for publishing events
        publish: Callable[[Topics, BaseModel], Coroutine[Any, Any, None]],
    ) -> None:
        super().__init__(app)
        self.exception_to_model = exception_to_model
        self.publish = publish

    async def publish_request_started(
        self,
        request: Request,
        *,
        request_id: str,
    ):
        await self.publish(
            Topics.request_started,
            RequestStarted(
                requestId=request_id,
                method=request.method,
                url=str(request.url.path),
                timestamp=utc_now(),
            ),
        )

    async def publish_request_finished(
        self,
        request: Request,
        *,
        response: Response | None,
        exception: Exception | None,
        duration: float,
        request_id: str,
    ):
        await self.publish(
            Topics.request_finished,
            RequestFinished(
                requestId=request_id,
                method=request.method,
                url=str(request.url.path),
                timestamp=utc_now(),
                duration=duration,
                statusCode=(
                    response.status_code
                    if response is not None
                    else exception.status_code
                    if isinstance(exception, HTTPException)
                    else 500
                ),
                exception=None
                if exception is None
                else self.exception_to_model(exception),
            ),
        )

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        # Assuming RequestIdMiddleware is already in place
        request_id = get_current_request_id(request)

        await self.publish_request_started(request, request_id=request_id)
        start_time = time.monotonic()
        try:
            response: Response = await call_next(request)

            await self.publish_request_finished(
                request,
                response=response,
                exception=None,
                duration=time.monotonic() - start_time,
                request_id=request_id,
            )
            return response
        except Exception as exc:
            await self.publish_request_finished(
                request,
                response=None,
                exception=exc,
                duration=time.monotonic() - start_time,
                request_id=request_id,
            )
            raise exc
