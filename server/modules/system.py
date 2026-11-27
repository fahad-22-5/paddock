"""System monitor: CPU, RAM, GPU (NVIDIA via nvidia-smi, if present), disks, network.
Publishes the "system" topic every second while anyone is watching."""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
import sys
import threading
import time

import psutil

from .base import Module

DISK_REFRESH = 30.0


class NvidiaSmi:
    """Streams readings from one long-running `nvidia-smi -lms` process instead of
    spawning it every second. Does nothing if there's no NVIDIA driver."""

    FIELDS = ["index", "name", "utilization.gpu", "temperature.gpu", "memory.used", "memory.total", "power.draw", "fan.speed"]

    def __init__(self) -> None:
        self.exe = shutil.which("nvidia-smi") or next(
            (p for p in (r"C:\Windows\System32\nvidia-smi.exe",
                         r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe") if os.path.exists(p)), None)
        self.data: dict[int, dict] = {}
        self.proc: subprocess.Popen | None = None
        self.failed = self.exe is None

    def ensure_running(self) -> None:
        if self.failed or (self.proc and self.proc.poll() is None):
            return
        try:
            self.proc = subprocess.Popen(
                [self.exe, f"--query-gpu={','.join(self.FIELDS)}", "--format=csv,noheader,nounits", "-lms", "1000"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, bufsize=1,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except OSError:
            self.failed = True
            return
        threading.Thread(target=self._reader, args=(self.proc,), daemon=True, name="nvidia-smi").start()

    def _reader(self, proc: subprocess.Popen) -> None:
        def num(s: str):
            try:
                return float(s)
            except ValueError:
                return None  # "[N/A]" on some laptops

        for line in proc.stdout:
            parts = [p.strip() for p in line.split(",")]
            if len(parts) != len(self.FIELDS):
                continue
            idx = int(num(parts[0]) or 0)
            self.data[idx] = {
                "name": parts[1].replace("NVIDIA ", "").replace("GeForce ", ""),
                "util": num(parts[2]), "temp": num(parts[3]),
                "mem_used": (num(parts[4]) or 0) * 1024 * 1024, "mem_total": (num(parts[5]) or 0) * 1024 * 1024,
                "power": num(parts[6]), "fan": num(parts[7]), "at": time.time(),
            }
        if proc.returncode not in (None, 0) and not self.data:
            self.failed = True  # e.g. driver without GPU access: stop trying quietly

    def snapshot(self) -> list[dict]:
        now = time.time()
        return [v for _, v in sorted(self.data.items()) if now - v["at"] < 5]

    def stop(self) -> None:
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


class SystemModule(Module):
    name = "system"

    async def start(self) -> None:
        psutil.cpu_percent(None)
        psutil.cpu_percent(None, percpu=True)
        if sys.platform == "darwin":
            from .mac.gpu import MacGpu

            self.gpu = MacGpu()
        else:
            self.gpu = NvidiaSmi()
        self._net = psutil.net_io_counters()
        self._dio = psutil.disk_io_counters()
        self._t = time.monotonic()
        self._disks: list[dict] = []
        self._disks_at = 0.0
        self.spawn(self.poll("system", 1.0, self.sample, only_changes=False))

    async def stop(self) -> None:
        self.gpu.stop()
        await super().stop()

    def _read_disks(self) -> list[dict]:
        out = []
        for p in psutil.disk_partitions(all=False):
            if sys.platform == "darwin":
                # The startup disk and external drives; skip macOS system/sealed volumes.
                if p.mountpoint != "/" and not p.mountpoint.startswith("/Volumes/"):
                    continue
            elif "cdrom" in p.opts or not p.fstype or "fixed" not in p.opts:
                continue
            try:
                u = psutil.disk_usage(p.mountpoint)
            except OSError:
                continue
            mount = p.mountpoint.rstrip("\\")
            if sys.platform == "darwin":
                mount = "Macintosh HD" if p.mountpoint == "/" else p.mountpoint.removeprefix("/Volumes/")
            out.append({"mount": mount, "used": u.used, "total": u.total, "percent": u.percent})
        return out

    def _sample_sync(self) -> dict:
        now = time.monotonic()
        dt = max(0.2, now - self._t)
        self._t = now
        net = psutil.net_io_counters()
        dio = psutil.disk_io_counters()
        up = max(0, net.bytes_sent - self._net.bytes_sent) / dt
        down = max(0, net.bytes_recv - self._net.bytes_recv) / dt
        rd = wr = None
        if dio and self._dio:
            rd = max(0, dio.read_bytes - self._dio.read_bytes) / dt
            wr = max(0, dio.write_bytes - self._dio.write_bytes) / dt
        self._net, self._dio = net, dio
        if now - self._disks_at > DISK_REFRESH:
            self._disks = self._read_disks()
            self._disks_at = now
        mem = psutil.virtual_memory()
        try:  # not available on Apple Silicon Macs
            freq = psutil.cpu_freq() if hasattr(psutil, "cpu_freq") else None
        except (OSError, NotImplementedError, RuntimeError):
            freq = None
        return {
            "t": time.time(),
            "cpu": psutil.cpu_percent(None),
            "cores": psutil.cpu_percent(None, percpu=True),
            "cpu_freq": round(freq.current) if freq else None,
            "mem": {"used": mem.total - mem.available, "total": mem.total, "percent": mem.percent},
            "net": {"up": up, "down": down},
            "disk_io": {"read": rd, "write": wr},
            "disks": self._disks,
            "uptime": time.time() - psutil.boot_time(),
        }

    async def sample(self) -> dict:
        self.gpu.ensure_running()
        data = await asyncio.to_thread(self._sample_sync)
        data["gpus"] = self.gpu.snapshot()
        return data
