from __future__ import annotations

from typing import Any

__all__ = ["LibraryError", "LibraryManager"]


def __getattr__(name: str) -> Any:
    if name in {"LibraryError", "LibraryManager"}:
        from ur_arms_manager.services.library_manager import LibraryError, LibraryManager

        return {"LibraryError": LibraryError, "LibraryManager": LibraryManager}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
