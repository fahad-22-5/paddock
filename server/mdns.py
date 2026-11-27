"""A friendly local name for your devices: https://paddock.local:8765

PadDock announces "<hostname>.local" (config.json → server.hostname, default "paddock")
on your Wi-Fi with multicast DNS (Bonjour), the same way printers announce themselves.
Phones, tablets and computers look .local names up automatically, so the address keeps working when the PC's IP
changes. The announcement only goes out on the PC's LAN interface.
"""
from __future__ import annotations

import logging
import re
import socket
import sys

log = logging.getLogger("paddock.mdns")

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
DEFAULT_NAME = "paddock"


def service_name() -> str:
    """The Bonjour service instance name (max 63 bytes)."""
    name = f"PadDock on {socket.gethostname().removesuffix('.local')}"
    while len(name.encode("utf-8")) > 63:
        name = name[:-1]
    return name


def clean_hostname(value: object) -> str:
    name = str(value or DEFAULT_NAME).strip().lower().removesuffix(".local")
    return name if NAME_RE.match(name) else DEFAULT_NAME


class NameAnnouncer:
    def __init__(self) -> None:
        self._zc = None
        self._info = None
        self._proc = None  # macOS: the dns-sd process that holds the registration

    async def start(self, hostname: str, ip: str, port: int, https: bool) -> bool:
        """Announce <hostname>.local -> ip. Returns False (quietly) if it can't."""
        if sys.platform == "darwin":
            return await self._start_mac(hostname, ip, port, https)
        try:
            from zeroconf import IPVersion, NonUniqueNameException, ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            log.warning("zeroconf isn't installed; %s.local won't work (run setup.bat again)", hostname)
            return False
        stype = "_https._tcp.local." if https else "_http._tcp.local."
        info = ServiceInfo(
            stype, f"{service_name()}.{stype}",
            addresses=[socket.inet_aton(ip)], port=port, server=f"{hostname}.local.",
            properties={"path": "/", "app": "PadDock"},
        )
        try:
            zc = AsyncZeroconf(interfaces=[ip], ip_version=IPVersion.V4Only)
            try:
                await zc.async_register_service(info, allow_name_change=True)
            except NonUniqueNameException:
                await zc.async_close()
                log.warning("Another device already announces this PadDock service name")
                return False
        except OSError as e:
            log.warning("Couldn't announce %s.local (%s); use the IP address instead", hostname, e)
            return False
        self._zc, self._info = zc, info
        log.info("Announcing %s.local -> %s", hostname, ip)
        return True

    async def _start_mac(self, hostname: str, ip: str, port: int, https: bool) -> bool:
        """macOS already runs Bonjour (mDNSResponder); ask it to publish the name for us.
        `dns-sd -P` registers a service plus an address record for <hostname>.local."""
        import asyncio
        import shutil
        import subprocess

        exe = shutil.which("dns-sd") or "/usr/bin/dns-sd"
        stype = "_https._tcp" if https else "_http._tcp"
        try:
            self._proc = subprocess.Popen(
                [exe, "-P", service_name(), stype, "local",
                 str(port), f"{hostname}.local", ip, "path=/", "app=PadDock"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as e:
            log.warning("Couldn't announce %s.local (%s); use the IP address instead", hostname, e)
            return False
        await asyncio.sleep(0.5)
        if self._proc.poll() is not None:
            log.warning("dns-sd stopped right away; %s.local may not work", hostname)
            self._proc = None
            return False
        log.info("Announcing %s.local -> %s (Bonjour)", hostname, ip)
        return True

    async def stop(self) -> None:
        if self._proc is not None:
            self._proc.terminate()
            self._proc = None
        if not self._zc:
            return
        try:
            await self._zc.async_unregister_service(self._info)
            await self._zc.async_close()
        except Exception:
            pass
        self._zc = self._info = None
