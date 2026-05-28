from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class DevxValidationMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: ASGIApp,
        project_id: str,
        service_type: str,
    ) -> None:
        super().__init__(app)
        self.project_id = project_id
        self.service_type = service_type

    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        if request.url.path == "/_healthz":
            return await call_next(request)

        project_id = request.headers.get("x-databutton-project-id")
        if project_id != self.project_id:
            raise RuntimeError("Invalid project id")

        service_type = request.headers.get("x-databutton-service-type")
        if service_type and service_type != self.service_type:
            raise RuntimeError("Invalid service type")

        return await call_next(request)
