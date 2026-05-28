from pathlib import Path
import sys

from pydantic import BaseModel

from .config import Config
from .exceptionmodel import exception_to_model
from .parsing import parse_json


class RouterConfig(BaseModel):
    disableAuth: bool


class RouterConfigs(BaseModel):
    routers: dict[str, RouterConfig]


def src_path(cfg: Config) -> Path:
    """Path where backend source is located and PYTHONPATH points to."""
    return Path(cfg.DEVX_BACKEND_DIR)


def read_router_config(cfg: Config) -> RouterConfigs | None:
    """Read router config from file."""
    config_file = src_path(cfg) / "routers.json"
    return (
        parse_json(config_file.read_text(), RouterConfigs)
        if config_file.exists()
        else None
    )


def find_submodules(cfg: Config):
    """Find user defined submodules for dynamic importing."""
    # Parent module we're looking for submodules in
    module_prefix = "app.apis."
    apis_path = src_path(cfg) / "app" / "apis"

    if cfg.DISABLE_API_AS_INIT_PY:
        # New API submodules following **/{name}.py pattern
        submodules = [
            p.relative_to(apis_path).as_posix().removesuffix(".py")
            for p in [p for p in apis_path.glob("**/*.py")]
            if p.name != "__init__.py"
        ]
    else:
        # Old submodules following {name}/__init__.py pattern
        submodules = [
            p.relative_to(apis_path).parent.as_posix()
            for p in apis_path.glob("*/__init__.py")
        ]

    return module_prefix, submodules


def convert_exception_to_model(cfg: Config, ex: BaseException):
    """Make exception model with venv and app paths cleaned up a bit."""

    sp = src_path(cfg)
    parent_path = sp.parent.as_posix()
    app_path = (sp / "app").as_posix()

    replace_paths: list[tuple[str, str]] = []

    # Map /disk/backend/.venv/lib/python3.11/site-packages/... -> /venv/...
    for p in sys.path:
        if p.startswith(sys.prefix):
            replace_paths.append(
                (p, ".venv/..."),
            )

    # Map /disk/backend/app/... -> backend/app/...
    replace_paths.append(
        (parent_path, ""),
    )

    return exception_to_model(
        ex,
        # Root dir is used to skip up to the first frame that lies in the app dir,
        # shortening the stacktrace to the more interesting parts that can be changed
        root_dir=app_path,
        # Paths are modified after checking if they lie in the root dir
        replace_paths=replace_paths,
    )
