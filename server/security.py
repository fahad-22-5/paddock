"""Pairing codes and device tokens.

* A 6-digit pairing code is kept in memory and rotated after every successful pairing.
* A paired device gets a random 256-bit token. Only its SHA-256 hash is stored on disk
  (data/devices.json), so reading that file doesn't let anyone pair.
* Wrong codes are rate-limited per IP, and the code is rotated after too many failures.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Callable

from .paths import DEVICES_PATH

log = logging.getLogger("paddock.security")

MAX_FAILS_PER_IP = 5
LOCKOUT_SECONDS = 60
MAX_FAILS_PER_CODE = 20


class NameTaken(ValueError):
    """Another paired device already uses this name."""


def clean_name(name: object) -> str:
    text = " ".join(str(name or "").split())[:40]
    return text or "Dock"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@dataclass
class Device:
    id: str
    name: str
    token_hash: str
    created: float
    last_seen: float

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "created": self.created, "last_seen": self.last_seen}


class DeviceStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._devices: dict[str, Device] = {}
        self._revoke_listeners: list[Callable[[str], None]] = []
        if DEVICES_PATH.exists():
            try:
                for d in json.loads(DEVICES_PATH.read_text("utf-8")):
                    self._devices[d["id"]] = Device(**d)
            except (ValueError, KeyError, TypeError) as e:
                log.error("devices.json is unreadable (%s); all devices must pair again", e)
            self._dedupe_names()

    def _dedupe_names(self) -> None:
        """Older versions allowed duplicate names: number them ("Dock", "Dock 2", …)."""
        seen: set[str] = set()
        changed = False
        for dev in sorted(self._devices.values(), key=lambda d: d.created):
            base, name, n = dev.name, dev.name, 2
            while name.lower() in seen:
                name, n = f"{base[:36]} {n}", n + 1
            if name != dev.name:
                log.info("Renamed duplicate device %r to %r", dev.name, name)
                dev.name, changed = name, True
            seen.add(name.lower())
        if changed:
            self._save()

    def name_in_use(self, name: str, except_id: str | None = None) -> bool:
        return any(d.name.lower() == name.lower() and d.id != except_id for d in self._devices.values())

    def suggest_name(self, name: str) -> str:
        """A free name like the wanted one: "Dock 2" taken -> "Dock 4" (not "Dock 2 2")."""
        import re

        base = re.sub(r"\s+\d+$", "", clean_name(name)) or "Dock"
        candidate, n = base, 2
        while self.name_in_use(candidate):
            candidate, n = f"{base[:36]} {n}", n + 1
        return candidate

    def _save(self) -> None:
        tmp = DEVICES_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps([d.__dict__ for d in self._devices.values()], indent=2), "utf-8")
        tmp.replace(DEVICES_PATH)

    def __len__(self) -> int:
        return len(self._devices)

    def add(self, name: str, replaces: str | None = None) -> tuple[Device, str]:
        """Pair a new device. `replaces` = id of this device's old entry (re-pairing)."""
        name = clean_name(name)
        token = secrets.token_urlsafe(32)
        now = time.time()
        with self._lock:
            if self.name_in_use(name, except_id=replaces):
                raise NameTaken(name)
            old = self._devices.pop(replaces, None) if replaces else None
            dev = Device(id=secrets.token_hex(6), name=name, token_hash=_hash(token),
                         created=old.created if old else now, last_seen=now)
            self._devices[dev.id] = dev
            self._save()
        if old:
            for fn in self._revoke_listeners:
                fn(old.id)  # disconnect the old entry's sockets
        return dev, token

    def rename(self, device_id: str, name: str) -> Device:
        name = clean_name(name)
        with self._lock:
            dev = self._devices.get(device_id)
            if dev is None:
                raise KeyError(device_id)
            if self.name_in_use(name, except_id=device_id):
                raise NameTaken(name)
            dev.name = name
            self._save()
        return dev

    def verify(self, token: object) -> Device | None:
        if not isinstance(token, str) or not (20 <= len(token) <= 200):
            return None
        h = _hash(token)
        for dev in list(self._devices.values()):
            if hmac.compare_digest(dev.token_hash, h):
                return dev
        return None

    def touch(self, dev: Device) -> None:
        if time.time() - dev.last_seen > 300:  # don't rewrite the file on every message
            dev.last_seen = time.time()
            with self._lock:
                self._save()

    def list(self) -> list[dict]:
        return [d.public() for d in sorted(self._devices.values(), key=lambda d: d.created)]

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            if self._devices.pop(device_id, None) is None:
                return False
            self._save()
        for fn in self._revoke_listeners:
            fn(device_id)
        return True

    def revoke_all(self) -> None:
        for dev_id in list(self._devices):
            self.revoke(dev_id)

    def on_revoke(self, fn: Callable[[str], None]) -> None:
        self._revoke_listeners.append(fn)


class Pairing:
    def __init__(self, devices: DeviceStore) -> None:
        self.devices = devices
        self._lock = threading.Lock()
        self._fails_by_ip: dict[str, list[float]] = {}
        self._fails_for_code = 0
        self.code = ""
        self._listeners: list[Callable[[str], None]] = []
        self.rotate()

    def rotate(self) -> str:
        self.code = f"{secrets.randbelow(1_000_000):06d}"
        self._fails_for_code = 0
        for fn in self._listeners:
            fn(self.code)
        return self.code

    def on_rotate(self, fn: Callable[[str], None]) -> None:
        self._listeners.append(fn)

    def attempt(self, ip: str, code: object, name: str, replace_token: object = None) -> tuple[str | None, str | None]:
        """Returns (token, error). `replace_token`: the device's previous token when it
        re-pairs; its old entry is replaced (and may keep its name)."""
        with self._lock:
            now = time.time()
            recent = [t for t in self._fails_by_ip.get(ip, []) if now - t < LOCKOUT_SECONDS]
            self._fails_by_ip[ip] = recent
            if len(recent) >= MAX_FAILS_PER_IP:
                wait = int(LOCKOUT_SECONDS - (now - recent[0])) + 1
                return None, f"Too many attempts. Try again in {wait} s."
            if not isinstance(code, str) or not hmac.compare_digest(code.strip(), self.code):
                recent.append(now)
                self._fails_for_code += 1
                if self._fails_for_code >= MAX_FAILS_PER_CODE:
                    log.warning("Too many wrong pairing codes; generating a new one")
                    self.rotate()
                return None, "That code isn't right. Check the code shown on the PC."
            self._fails_by_ip.pop(ip, None)
            old = self.devices.verify(replace_token) if replace_token else None
            try:
                dev, token = self.devices.add(name, replaces=old.id if old else None)
            except NameTaken as e:
                # The code stays valid: the user just picks another name.
                return None, (f"A device called “{e}” is already paired. Choose another name "
                              f"(e.g. “{self.devices.suggest_name(str(e))}”), or remove the old one "
                              "in the PC console under Devices.")
            log.info("%s device %r from %s", "Re-paired" if old else "Paired new", dev.name, ip)
            self.rotate()
            return token, None
