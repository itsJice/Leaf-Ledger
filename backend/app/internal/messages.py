from datetime import datetime
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel

from .exceptionmodel import ExceptionModel

# TODO: Move topics and message types to location shared with devx


class Topics(str, Enum):
    """Topics sent from user-api server and forwarded by devx."""

    # Sent by user-api server on startup if importing user modules fail.
    backend_import_error = "backend.import_error"

    # Sent by user-api server at when ready to serve after a restart
    backend_ready = "backend.ready"

    # Sent by user-api server when shutting down
    backend_shutdown = "backend.shutdown"

    # Sent from user-api server to forward logs
    backend_log = "backend.log"

    # Sent by user-api middleware before executing request
    request_started = "request.started"

    # Sent by user-api middleware after executing request
    request_finished = "request.finished"


class RequestStarted(BaseModel):
    timestamp: datetime
    requestId: str
    method: str
    url: str


class RequestFinished(BaseModel):
    timestamp: datetime
    requestId: str
    method: str
    url: str
    duration: float
    statusCode: int
    exception: ExceptionModel | None = None


class JobStarted(BaseModel):
    timestamp: datetime
    jobName: str
    runId: str


class JobFinished(BaseModel):
    timestamp: datetime
    jobName: str
    runId: str
    duration: float
    statusCode: int
    exception: ExceptionModel | None = None


class BackendLog(BaseModel):
    timestamp: datetime
    level: Literal["debug", "info", "warning", "error"]
    text: str


class Endpoint(BaseModel):
    method: str
    path: str
    functionName: str
    errors: list[str]


class WSEndpoint(BaseModel):
    path: str
    functionName: str
    errors: list[str]


class ImportResult(BaseModel):
    moduleName: str
    importTime: float
    ok: bool
    importException: ExceptionModel | None
    errors: list[str]
    endpoints: list[Endpoint]
    wsEndpoints: list[WSEndpoint]


class BackendReady(BaseModel):
    timestamp: datetime
    startupTime: float
    ok: bool
    importResults: list[ImportResult]
    openapiSignature: str | None = None


class BackendImportError(BaseModel):
    timestamp: datetime
    name: str
    exception: ExceptionModel


class BackendShutdown(BaseModel):
    timestamp: datetime
    openapiSignature: str | None = None


class RefreshOpenapiSpecParams(BaseModel):
    """Request arguments, not a message."""

    timestamp: datetime
    openapiSignature: str
    openapiDoc: dict[str, Any]
    importResults: list[ImportResult]
