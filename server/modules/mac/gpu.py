"""GPU load on Macs, from `ioreg` (no admin rights needed).

Apple Silicon and most Intel/AMD Mac GPUs publish "Device Utilization %" in the
IOAccelerator PerformanceStatistics. Temperatures need root (powermetrics), so they're
left out; the dock shows "n/a" for GPU temperature on a Mac.
"""
from __future__ import annotations

import re
import subprocess
import threading
import time


def parse_ioreg(text: str) -> list[dict]:
    """Pull GPU name and utilisation out of `ioreg -r -d 1 -w 0 -c IOAccelerator` output."""
    gpus = []
    for block in re.split(r"\n(?=\+-o )", text):
        util = re.search(r'"Device Utilization %"\s*=\s*(\d+)', block)
        if not util:
            continue
        name = re.search(r'"model"\s*=\s*<?"([^"]+)"', block) or re.search(r'"IOGLBundleName"\s*=\s*"([^"]+)"', block)
        cls = re.search(r"\+-o (\S+)", block)
        used = re.search(r'"(?:In use system memory|Alloc system memory)"\s*=\s*(\d+)', block)
        gpus.append({
            "name": (name.group(1) if name else (cls.group(1) if cls else "GPU")).replace("AGXAccelerator", "Apple GPU"),
            "util": float(util.group(1)),
            "temp": None,
            "mem_used": int(used.group(1)) if used else 0,
            "mem_total": 0,
            "power": None, "fan": None,
        })
    return gpus


class MacGpu:
    """Same interface as the NvidiaSmi reader: ensure_running(), snapshot(), stop()."""

    INTERVAL = 2.0

    def __init__(self) -> None:
        self.data: list[dict] = []
        self.at = 0.0
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self.failed = False

    def ensure_running(self) -> None:
        if self.failed or (self._thread and self._thread.is_alive()):
            return
        self._thread = threading.Thread(target=self._loop, daemon=True, name="mac-gpu")
        self._thread.start()

    def _loop(self) -> None:
        misses = 0
        while not self._stop.is_set():
            try:
                out = subprocess.run(["ioreg", "-r", "-d", "1", "-w", "0", "-c", "IOAccelerator"],
                                     capture_output=True, text=True, timeout=5).stdout
                gpus = parse_ioreg(out)
                if gpus:
                    self.data, self.at, misses = gpus, time.time(), 0
                else:
                    misses += 1
            except Exception:
                misses += 1
            if misses >= 5 and not self.data:
                self.failed = True  # no readable GPU statistics on this Mac: stop quietly
                return
            self._stop.wait(self.INTERVAL)

    def snapshot(self) -> list[dict]:
        if time.time() - self.at > 10:
            return []
        return [{**g, "at": self.at} for g in self.data]

    def stop(self) -> None:
        self._stop.set()
