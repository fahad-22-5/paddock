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

log = logging.getLogger("paddock.mdns")

NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]{0,30}[a-z0-9])?$")
DEFAULT_NAME = "paddock"


def clean_hostname(value: object) -> str:
    name = str(value or DEFAULT_NAME).strip().lower().removesuffix(".local")
    return name if NAME_RE.match(name) else DEFAULT_NAME


class NameAnnouncer:
    def __init__(self) -> None:
        self._zc = None
        self._info = None

    async def start(self, hostname: str, ip: str, port: int, https: bool) -> bool:
        """Announce <hostname>.local -> ip. Returns False (quietly) if it can't."""
        try:
            from zeroconf import IPVersion, NonUniqueNameException, ServiceInfo
            from zeroconf.asyncio import AsyncZeroconf
        except ImportError:
            log.warning("zeroconf isn't installed; %s.local won't work (run setup.bat again)", hostname)
            return False
        stype = "_https._tcp.local." if https else "_http._tcp.local."
        info = ServiceInfo(
            stype, f"PadDock on {socket.gethostname()}.{stype}",
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

    async def stop(self) -> None:
        if not self._zc:
            return
        try:
            await self._zc.async_unregister_service(self._info)
            await self._zc.async_close()
        except Exception:
            pass
        self._zc = self._info = None
