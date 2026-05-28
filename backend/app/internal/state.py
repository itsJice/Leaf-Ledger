import time
from threading import Event
from typing import Annotated, Callable

from fastapi import Depends, FastAPI
from fastapi.requests import HTTPConnection

from .config import AuthConfig, Config, parse_auth_configs
from .messages import (
    ImportResult,
)
from .notifications import DevxClient


class AppState:
    cfg: Config
    devx: DevxClient
    app_created_time: float
    started_event: Event
    submodule_import_results: list[ImportResult]
    auth_configs: list[AuthConfig]
    audit_log: Callable[[str], None] | None


def init_app_state(cfg: Config) -> AppState:
    s = AppState()
    s.cfg = cfg
    s.devx = DevxClient(cfg)
    s.app_created_time = time.monotonic()
    s.started_event = Event()
    s.submodule_import_results = []
    s.auth_configs = parse_auth_configs(cfg)
    s.audit_log = print
    return s


def set_app_state(app: FastAPI, app_state: AppState):
    app.state.databutton_app_state = app_state


def get_app_state(app: FastAPI) -> AppState:
    return app.state.databutton_app_state


def databutton_app_state(request: HTTPConnection) -> AppState:
    """Dependency injection function to return app state.

    Use as:

      @router.get("/")
      def get_endpoint(app_state: AppStateDep):
            ... app_state.cfg

    """
    return get_app_state(request.app)


AppStateDep = Annotated[AppState, Depends(databutton_app_state)]
