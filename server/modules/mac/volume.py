"""Volume on macOS: master output volume and mute (via AppleScript's volume settings).

macOS has no per-app volume without a third-party audio driver, so the mixer list stays
empty and the dock says so ("per_app": false)."""
from __future__ import annotations

import asyncio
import re

from fastapi import APIRouter
from fastapi.responses import Response

from ...platform import osascript
from ..base import ActionError, Module, action


def parse_volume_settings(text: str) -> dict:
    """'output volume:44, input volume:75, alert volume:100, output muted:false' -> dict."""
    out = {}
    for key, value in re.findall(r"(\w[\w ]*?):\s*([^,]+)", text):
        out[key.strip()] = value.strip()
    level = out.get("output volume", "missing value")
    return {
        "level": None if level == "missing value" else max(0.0, min(1.0, int(level) / 100)),
        "muted": out.get("output muted") == "true",
    }


def _level(v) -> float:
    try:
        return min(1.0, max(0.0, float(v)))
    except (TypeError, ValueError):
        raise ActionError("Volume must be a number between 0 and 1.")


class VolumeModule(Module):
    name = "volume"

    async def start(self) -> None:
        self.spawn(self.poll("volume", 1.0, self._read))

    async def _read(self) -> dict:
        try:
            s = parse_volume_settings(await asyncio.to_thread(osascript, "get volume settings", 5))
        except (RuntimeError, OSError) as e:
            raise ActionError(f"Couldn't read the volume: {e}")
        return {
            "device": "Mac sound output",
            "level": s["level"] if s["level"] is not None else 0.0,
            "fixed": s["level"] is None,  # e.g. HDMI/optical outputs without volume control
            "muted": s["muted"],
            "apps": [],
            "per_app": False,
        }

    async def _apply(self, script: str):
        await asyncio.to_thread(osascript, script, 5)
        self.hub.publish("volume", await self._read())
        return True

    @action
    async def set_master(self, args, client):
        level = round(_level(args.get("level")) * 100)
        return await self._apply(f"set volume output volume {level}" + (" without output muted" if level > 0 else ""))

    @action
    async def set_mute(self, args, client):
        return await self._apply(f"set volume output muted {'true' if args.get('muted') else 'false'}")

    @action
    async def set_app(self, args, client):
        raise ActionError("Per-app volume isn't available on macOS.")

    @action
    async def set_app_mute(self, args, client):
        raise ActionError("Per-app volume isn't available on macOS.")

    def router(self):
        r = APIRouter()

        @r.get("/icon/{key}")
        async def icon(key: str):
            return Response(status_code=404)

        return r
