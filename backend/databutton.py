"""Local Databutton storage shim for exported-app development.

The hosted runtime provides ``databutton.storage``. The public PyPI package is
not compatible with this exported app's dependency stack, so local preview uses
this small filesystem-backed replacement.
"""
from __future__ import annotations

import json as _json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parent / ".local_databutton_storage"


def _safe_key(key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9._=-]", "-", key)


@dataclass
class _StorageFile:
    name: str


class _TextStorage:
    _dir = _ROOT / "text"

    def put(self, key: str, value: str) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / _safe_key(key)).write_text(value, encoding="utf-8")

    def get(self, key: str, default: str | None = None) -> str | None:
        path = self._dir / _safe_key(key)
        if not path.exists():
            return default
        return path.read_text(encoding="utf-8")


class _JsonStorage:
    _dir = _ROOT / "json"

    def put(self, key: str, value: Any) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / _safe_key(key)).write_text(_json.dumps(value), encoding="utf-8")

    def get(self, key: str, default: Any = None) -> Any:
        path = self._dir / _safe_key(key)
        if not path.exists():
            return default
        try:
            return _json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return default


class _BinaryStorage:
    _dir = _ROOT / "binary"

    def put(self, key: str, value: bytes) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / _safe_key(key)).write_bytes(value)

    def get(self, key: str, default: bytes | None = None) -> bytes | None:
        path = self._dir / _safe_key(key)
        if not path.exists():
            return default
        return path.read_bytes()

    def list(self) -> list[_StorageFile]:
        self._dir.mkdir(parents=True, exist_ok=True)
        return [_StorageFile(path.name) for path in self._dir.iterdir() if path.is_file()]

    def delete(self, key: str) -> None:
        path = self._dir / _safe_key(key)
        if path.exists():
            path.unlink()


class _Storage:
    text = _TextStorage()
    json = _JsonStorage()
    binary = _BinaryStorage()


storage = _Storage()
