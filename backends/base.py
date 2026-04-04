from __future__ import annotations

from typing import Optional, Protocol


class BackendProtocol(Protocol):
    error: Optional[str]

    @property
    def available(self) -> bool:
        ...


class BackendMixin:
    error: Optional[str]

    def __init__(self) -> None:
        self.error = None

    @staticmethod
    def format_exception(exc: Exception) -> str:
        return f"{type(exc).__name__}: {exc}"
