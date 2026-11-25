"""LAN address helpers and the private-network check."""
from __future__ import annotations

import ipaddress
import socket

import psutil

_PRIVATE_NETS = [
    ipaddress.ip_network(n)
    for n in (
        "10.0.0.0/8",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "169.254.0.0/16",  # link-local
        "127.0.0.0/8",
        "::1/128",
        "fc00::/7",  # unique local
        "fe80::/10",  # link-local
    )
]


def is_private_address(host: str | None) -> bool:
    if not host:
        return False
    try:
        addr = ipaddress.ip_address(host.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return any(addr in net for net in _PRIVATE_NETS)


def primary_lan_ip() -> str | None:
    """The address Windows would use to reach the internet. No packets are sent."""
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.connect(("192.0.2.1", 9))  # TEST-NET address, never routed anywhere
            ip = s.getsockname()[0]
        except OSError:
            return None
    return ip if is_private_address(ip) and not ip.startswith("127.") else None


def all_lan_ips() -> list[str]:
    """Every private IPv4 address on an interface that is up."""
    stats = psutil.net_if_stats()
    ips: list[str] = []
    for name, addrs in psutil.net_if_addrs().items():
        if not stats.get(name) or not stats[name].isup:
            continue
        for a in addrs:
            if a.family == socket.AF_INET and is_private_address(a.address) and not a.address.startswith(("127.", "169.254.")):
                ips.append(a.address)
    return sorted(set(ips))
