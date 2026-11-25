"""Config and layout: what the dock sees of config.json, saving the layout from edit
mode, the accent colour, and managing paired devices."""
from __future__ import annotations

import json
import re

from .actions import icon_source
from .base import ActionError, Module, action

ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,48}$")
TYPE_RE = re.compile(r"^[a-z0-9_-]{1,32}$")
HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
MAX_PAGES = 20
MAX_ITEMS = 120

# Action types the device may see the details of (and create; see actions.py).
SAFE_DETAIL_TYPES = {"keys", "text", "url"}


def public_config(data: dict) -> dict:
    """The parts of config.json the UI needs. Program paths and commands stay on the PC."""
    actions = {}
    for aid, a in (data.get("actions") or {}).items():
        if not isinstance(a, dict):
            continue
        pub = {k: a[k] for k in ("label", "type", "icon", "color", "origin") if k in a}
        pub.setdefault("label", aid)
        pub["has_icon"] = icon_source(a) is not None
        if pub["has_icon"]:
            pub.pop("icon", None)  # a file path, not an emoji
        if a.get("type") in SAFE_DETAIL_TYPES:
            for k in ("keys", "text", "url"):
                if k in a:
                    pub[k] = a[k]
        actions[aid] = pub
    w = data.get("weather") or {}
    return {
        "pages": data.get("pages") or [],
        "appearance": data.get("appearance") or {},
        "weather": {
            "enabled": bool(w.get("enabled", True)),
            "name": w.get("name") or "",
            "units": w.get("units") or "celsius",
            "configured": w.get("latitude") is not None and w.get("longitude") is not None,
        },
        "actions": actions,
    }


def clean_pages(pages: object, actions: dict) -> list[dict]:
    """Validate a layout sent by the device. Raises ActionError on bad structure."""
    if not isinstance(pages, list) or not (1 <= len(pages) <= MAX_PAGES):
        raise ActionError(f"A layout needs 1–{MAX_PAGES} pages.")
    seen: set[str] = set()
    out = []
    for p in pages:
        if not isinstance(p, dict) or not ID_RE.match(str(p.get("id", ""))):
            raise ActionError("Each page needs a valid id.")
        if p["id"] in seen:
            raise ActionError("Duplicate page id.")
        seen.add(p["id"])
        items_in = p.get("items") or []
        if not isinstance(items_in, list) or len(items_in) > MAX_ITEMS:
            raise ActionError(f"A page can hold at most {MAX_ITEMS} items.")
        items = []
        for it in items_in:
            if not isinstance(it, dict) or not ID_RE.match(str(it.get("id", ""))) or it["id"] in seen:
                raise ActionError("Each item needs a unique id.")
            seen.add(it["id"])
            kind = it.get("kind")
            if kind == "action":
                if it.get("action") not in actions:
                    continue  # its action was removed from config.json; drop the tile
                items.append({"id": it["id"], "kind": "action", "action": it["action"]})
            elif kind == "widget":
                if not TYPE_RE.match(str(it.get("type", ""))):
                    raise ActionError("Unknown widget type.")
                w, h = it.get("w", 2), it.get("h", 2)
                if not (isinstance(w, int) and isinstance(h, int) and 1 <= w <= 8 and 1 <= h <= 6):
                    raise ActionError("Widget size out of range.")
                item = {"id": it["id"], "kind": "widget", "type": it["type"], "w": w, "h": h}
                opts = it.get("options")
                if isinstance(opts, dict) and opts:
                    if len(json.dumps(opts)) > 2000:
                        raise ActionError("Widget options are too large.")
                    item["options"] = opts
                items.append(item)
            else:
                raise ActionError("Unknown item kind.")
        title = str(p.get("title") or "Page").strip()[:40] or "Page"
        out.append({"id": p["id"], "title": title, "items": items})
    return out


class CoreModule(Module):
    name = "core"

    async def start(self) -> None:
        self.hub.publish("config", public_config(self.config.data))
        self.config.on_change(lambda data: self.hub.publish("config", public_config(data)))
        self.ctx.devices.on_revoke(self.hub.drop_device)
        self.spawn(self._watch_file())

    async def _watch_file(self) -> None:
        import asyncio

        while True:
            await asyncio.sleep(2)
            self.config.check_for_external_edit()

    @action
    async def save_layout(self, args, client):
        actions = self.config.get("actions") or {}
        pages = clean_pages(args.get("pages"), actions)
        self.config.update(lambda d: d.__setitem__("pages", pages))
        return True

    @action
    async def set_appearance(self, args, client):
        accent = args.get("accent")
        if not isinstance(accent, str) or not HEX_RE.match(accent):
            raise ActionError("Accent must be a colour like #0a84ff.")
        self.config.update(lambda d: d.setdefault("appearance", {}).__setitem__("accent", accent.lower()))
        return True

    @action
    async def devices(self, args, client):
        return {"devices": self.ctx.devices.list(), "you": client.device.id}

    @action
    async def revoke_device(self, args, client):
        if not self.ctx.devices.revoke(str(args.get("id", ""))):
            raise ActionError("No such device.")
        return True
