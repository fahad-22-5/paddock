"""Icons of programs, apps, files and folders as PNG, on Windows or macOS."""
from __future__ import annotations

from .platform import IS_MAC


def extract_png(path: str, index: int = 0, size: int = 256) -> bytes | None:
    if IS_MAC:
        from .modules.mac.icons import extract_png as extract
    else:
        from .winicons import extract_png as extract
    return extract(path, index, size)
