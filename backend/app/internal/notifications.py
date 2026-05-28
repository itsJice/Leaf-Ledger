import inspect
import time
from typing import Awaitable, Callable, Literal

import anyio
import httpx
from pydantic import BaseModel

from .config import Config
from .messages import BackendImportError, BackendLog, RefreshOpenapiSpecParams, Topics
from .parsing import stringify_basemodel
from .pathutils import convert_exception_to_model
from .utils import utc_now

LevelType = Literal["debug", "info", "warning", "error"]

NotifyLogsAsyncType = Callable[
    [str, LevelType],
    Awaitable[None],
]

NotifyLogsType = Callable[
    [str, LevelType],
    None,
]


def params_as_json(params: BaseModel | None = None, indent: int | None = None) -> str:
    if params is None:
        return "{}"
    return stringify_basemodel(params, indent=indent)


def _print_instead_of_post(path: str, params: BaseModel | None = None):
    # For local debugging without devx server running
    # NB! Careful to avoid circular print streaming
    print(f"[notify devx] {path}\n{params_as_json(params, indent=2)}")


def is_recursive_call() -> bool:
    """Return if the function that called this directly is twice on the callstack."""
    stack = inspect.stack()
    current_func_name = stack[1].function
    return any(stack[i].function == current_func_name for i in range(2, len(stack)))


def get_devx_client(url: str) -> httpx.Client:
    "Mockable client creation."
    return httpx.Client(base_url=url)


def get_devx_async_client(url: str) -> httpx.AsyncClient:
    "Mockable client creation."
    return httpx.AsyncClient(base_url=url)


class DevxClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg

    def _get_devx_client(self) -> httpx.Client | None:
        if self.cfg.DEVX_URL_INTERNAL:
            return get_devx_client(self.cfg.DEVX_URL_INTERNAL)
        return None

    def _get_devx_async_client(self) -> httpx.AsyncClient | None:
        if self.cfg.DEVX_URL_INTERNAL:
            return get_devx_async_client(self.cfg.DEVX_URL_INTERNAL)
        return None

    def ping(self) -> bool:
        """Ping devx server once."""
        client = self._get_devx_client()
        if client is None:
            return True
        with client:
            try:
                return client.get("/ready").status_code == 200
            except Exception:
                pass
        return False

    def wait_for_devx_ready(
        self,
        *,
        max_retries: int = 50,
        delay: float = 0.1,
    ) -> bool:
        """Ping devx server until it's ready, meaning the files we need are in place.

        Retries only actually happen on initial startup.
        This is not supposed to fail so it defaults to plenty of retries.
        """
        for _ in range(max_retries):
            if self.ping():
                return True
            time.sleep(delay)
        return False

    def _post_devx_sync(self, path: str, params: BaseModel | None = None):
        """Make post request endpoint in internal devx server."""
        client = self._get_devx_client()
        if client is None:
            # If we don't have a sync client use the async client,
            # in an attempt to make test setup more useful...
            # This should never happen outside of tests.
            return anyio.run(self._post_devx_async, *(path, params))
        with client:
            return client.post(
                f"/workspace{path}",
                headers={"Content-Type": "application/json"},
                content=params_as_json(params),
            )

    async def _post_devx_async(self, path: str, params: BaseModel | None = None):
        """Make post request endpoint in internal devx server."""
        client = self._get_devx_async_client()
        if client is None:
            _print_instead_of_post(path, params)
            return
        async with client:
            return await client.post(
                f"/workspace{path}",
                headers={"Content-Type": "application/json"},
                content=params_as_json(params),
            )

    async def notify_devx_refresh_openapi_spec(self, params: RefreshOpenapiSpecParams):
        await self._post_devx_async(
            path="/internal/refresh-openapi-spec", params=params
        )

    async def notify_devx_async(self, topic: Topics, params: BaseModel) -> None:
        """Post message to publish endpoint in internal devx server.

        Message then gets forwarded as a notification to all subscribed frontend clients.
        """
        await self._post_devx_async(f"/internal/publish/{topic.value}", params)

    def notify_devx_sync(self, topic: Topics, params: BaseModel) -> None:
        """Post message to publish endpoint in internal devx server.

        Message then gets forwarded as a notification to all subscribed frontend clients.
        """
        self._post_devx_sync(f"/internal/publish/{topic.value}", params)

    async def notify_import_error_async(self, name: str, ex: BaseException):
        await self.notify_devx_async(
            Topics.backend_import_error,
            BackendImportError(
                timestamp=utc_now(),
                name=name,
                exception=convert_exception_to_model(self.cfg, ex),
            ),
        )

    def notify_import_error_sync(self, name: str, ex: BaseException):
        self.notify_devx_sync(
            Topics.backend_import_error,
            BackendImportError(
                timestamp=utc_now(),
                name=name,
                exception=convert_exception_to_model(self.cfg, ex),
            ),
        )

    # Note: Is it possible to make the stdout/stderr log forwarding async?
    def notify_logs(
        self,
        text: str,
        level: LevelType,
    ):
        if is_recursive_call():
            return
        self.notify_devx_sync(
            Topics.backend_log,
            BackendLog(
                timestamp=utc_now(),
                text=text,
                level=level,
            ),
        )

    async def notify_logs_async(
        self,
        text: str,
        level: LevelType,
    ):
        if is_recursive_call():
            return
        await self.notify_devx_async(
            Topics.backend_log,
            BackendLog(
                timestamp=utc_now(),
                text=text,
                level=level,
            ),
        )
