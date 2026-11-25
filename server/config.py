"""config.json: server settings, page layout and the action catalogue.

The file is the single source of truth. It is re-read automatically when you edit it
by hand while the server runs, and written atomically when the dock saves a layout.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import shutil
import threading
from typing import Any, Callable

from .paths import CONFIG_PATH, EXAMPLE_CONFIG_PATH

log = logging.getLogger("paddock.config")

DEFAULTS: dict[str, Any] = {
    "server": {"port": 8765, "setup_port": 8766, "bind": "auto", "https": True, "hostname": "paddock"},
    "appearance": {"accent": "#0a84ff"},
    "media": {"online_art": True},
    "weather": {"enabled": True, "name": "", "latitude": None, "longitude": None, "units": "celsius"},
    "pages": [],
    "actions": {},
}


def _merge(defaults: dict, data: dict) -> dict:
    out = copy.deepcopy(defaults)
    for key, value in data.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class ConfigStore:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._mtime = 0
        self.rev = 0  # bumps on every change; the console polls it
        self._listeners: list[Callable[[dict], None]] = []
        self._load()

    # ---- reading -------------------------------------------------------
    def _load(self) -> None:
        if not CONFIG_PATH.exists():
            shutil.copyfile(EXAMPLE_CONFIG_PATH, CONFIG_PATH)
            log.info("Created config.json from config.example.json")
        with open(CONFIG_PATH, encoding="utf-8") as f:
            raw = json.load(f)
        self._data = _merge(DEFAULTS, raw)
        self._mtime = CONFIG_PATH.stat().st_mtime_ns

    @property
    def data(self) -> dict[str, Any]:
        """A deep copy; mutate it freely."""
        with self._lock:
            return copy.deepcopy(self._data)

    def get(self, section: str, default: Any = None) -> Any:
        with self._lock:
            return copy.deepcopy(self._data.get(section, default))

    # ---- writing -------------------------------------------------------
    def update(self, mutate: Callable[[dict], None]) -> dict:
        """Apply `mutate` to a copy, write it atomically, then notify listeners."""
        with self._lock:
            data = copy.deepcopy(self._data)
            mutate(data)
            tmp = CONFIG_PATH.with_suffix(".json.tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
                f.write("\n")
            os.replace(tmp, CONFIG_PATH)
            self._data = data
            self.rev += 1
            self._mtime = CONFIG_PATH.stat().st_mtime_ns
        self._notify()
        return self.data

    def check_for_external_edit(self) -> bool:
        """Reload if config.json changed on disk. Returns True if it did."""
        try:
            mtime = CONFIG_PATH.stat().st_mtime_ns
        except FileNotFoundError:
            return False
        if mtime == self._mtime:
            return False
        try:
            with self._lock:
                self._load()
        except (json.JSONDecodeError, OSError) as e:
            self._mtime = mtime  # don't spam the log; wait for the next save
            log.error("config.json has an error and was not reloaded: %s", e)
            return False
        self.rev += 1
        log.info("config.json changed on disk; reloaded")
        self._notify()
        return True

    def on_change(self, fn: Callable[[dict], None]) -> None:
        self._listeners.append(fn)

    def _notify(self) -> None:
        data = self.data
        for fn in self._listeners:
            try:
                fn(data)
            except Exception:  # a broken listener must not break saving
                log.exception("config listener failed")
