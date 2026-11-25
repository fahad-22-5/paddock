"""The action catalogue in config.json["actions"], and running actions by id.

The device only ever sends an action *id*. Programs, folders and shell commands can only be
defined by editing config.json on the PC. From a device you can create keyboard shortcuts,
text snippets and http(s) links (marked "origin": "ipad"), and edit or delete only those.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import secrets

from fastapi import APIRouter
from fastapi.responses import Response

from ..paths import ICON_CACHE_DIR
from .base import ActionError, Module, action
from .macros import parse_keys

CLIENT_TYPES = {"keys", "text", "url"}
ICON_TYPES = {"exe", "folder"}
ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")


def icon_source(a: dict) -> str | None:
    """Which file to take an action's icon from, if any."""
    icon = a.get("icon")
    if isinstance(icon, str) and re.search(r"\.(ico|png|jpe?g|exe|dll)$", icon, re.I):
        return icon
    if not icon and a.get("type") in ICON_TYPES and a.get("path"):
        return a["path"]
    if not icon and a.get("type") == "shell" and isinstance(a.get("command"), str):
        exe = a["command"].strip().strip('"').split('"')[0].split(" ")[0]
        return exe if exe.lower().endswith(".exe") and os.path.isabs(exe) else None
    return None


def _clean_client_action(args: dict) -> dict:
    typ = args.get("type")
    if typ not in CLIENT_TYPES:
        raise ActionError("From a device you can create keyboard shortcuts, text snippets and web links.")
    label = str(args.get("label") or "").strip()[:40]
    if not label:
        raise ActionError("Give the shortcut a label.")
    out = {"type": typ, "label": label, "origin": "ipad"}
    icon = str(args.get("icon") or "").strip()
    if icon:
        if len(icon) > 8 or re.search(r"[\\/.:]", icon):
            raise ActionError("The icon must be an emoji.")
        out["icon"] = icon
    value = args.get(typ)
    if typ == "keys":
        parse_keys(value)
        out["keys"] = value.strip().lower()
    elif typ == "text":
        if not isinstance(value, str) or not value or len(value) > 5000:
            raise ActionError("A snippet needs 1–5000 characters of text.")
        out["text"] = value
    else:
        if not isinstance(value, str) or not re.match(r"^https?://[^\s]{1,2000}$", value.strip(), re.I):
            raise ActionError("Links must start with http:// or https://")
        out["url"] = value.strip()
    return out


class ActionsModule(Module):
    name = "actions"

    @action
    async def run(self, args, client):
        aid = args.get("id")
        a = (self.config.get("actions") or {}).get(aid) if isinstance(aid, str) else None
        if not isinstance(a, dict):
            raise ActionError("This shortcut no longer exists in config.json.")
        fn = self.ctx.executors.get(a.get("type"))
        if fn is None:
            raise ActionError(f"Unknown action type “{a.get('type')}” in config.json.")
        self.log.info("%s runs action %r", client.device.name, aid)
        await fn(a)
        return True

    @action
    async def create(self, args, client):
        spec = _clean_client_action(args)
        aid = f"ipad-{secrets.token_hex(4)}"
        self.config.update(lambda d: d.setdefault("actions", {}).__setitem__(aid, spec))
        return aid

    def _own(self, aid) -> dict:
        a = (self.config.get("actions") or {}).get(aid) if isinstance(aid, str) else None
        if not isinstance(a, dict):
            raise ActionError("No such shortcut.")
        if a.get("origin") != "ipad":
            raise ActionError("This shortcut is defined in config.json on the PC; edit it there.")
        return a

    @action
    async def update(self, args, client):
        aid = args.get("id")
        old = self._own(aid)
        spec = _clean_client_action({**args, "type": old["type"]})
        self.config.update(lambda d: d["actions"].__setitem__(aid, spec))
        return True

    @action
    async def delete(self, args, client):
        aid = args.get("id")
        self._own(aid)

        def mutate(d):
            d["actions"].pop(aid, None)
            for p in d.get("pages", []):
                p["items"] = [i for i in p.get("items", []) if not (i.get("kind") == "action" and i.get("action") == aid)]

        self.config.update(mutate)
        return True

    def router(self):
        r = APIRouter()

        @r.get("/icon/{aid}")
        async def icon(aid: str):
            a = (self.config.get("actions") or {}).get(aid)
            src = icon_source(a) if isinstance(a, dict) and ID_RE.match(aid) else None
            if not src:
                return Response(status_code=404)
            key = hashlib.sha1(json.dumps([src, a.get("icon_index", 0)]).encode()).hexdigest()[:16]
            cached = ICON_CACHE_DIR / f"{key}.png"
            if cached.exists():
                png = cached.read_bytes()
            else:
                from ..winicons import extract_png

                png = await asyncio.to_thread(extract_png, src, int(a.get("icon_index", 0)), 256)
                if not png:
                    return Response(status_code=404)
                cached.write_bytes(png)
            return Response(png, media_type="image/png", headers={"cache-control": "private, max-age=3600"})

        return r
