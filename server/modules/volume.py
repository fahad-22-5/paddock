"""Master volume + mute and a per-app mixer (pycaw / Windows Core Audio).
All COM calls run on one dedicated thread with COM initialised."""
from __future__ import annotations

import os

from fastapi import APIRouter
from fastapi.responses import Response

from .base import ActionError, ComThread, Module, action

PRETTY = {"msedge": "Edge", "chrome": "Chrome", "firefox": "Firefox", "spotify": "Spotify", "discord": "Discord",
          "teams": "Teams", "ms-teams": "Teams", "vlc": "VLC", "steam": "Steam", "zoom": "Zoom", "slack": "Slack"}


def _pretty(exe: str) -> str:
    stem = exe[:-4] if exe.lower().endswith(".exe") else exe
    return PRETTY.get(stem.lower(), stem[:1].upper() + stem[1:])


def _level(v) -> float:
    try:
        v = float(v)
    except (TypeError, ValueError):
        raise ActionError("Volume must be a number between 0 and 1.")
    return min(1.0, max(0.0, v))


class VolumeModule(Module):
    name = "volume"

    async def start(self) -> None:
        import importlib.util

        # Only check that pycaw is installed: importing it here would initialise COM on
        # the main thread. All pycaw calls run on the dedicated audio thread instead.
        if importlib.util.find_spec("pycaw") is None:
            self.log.warning("pycaw isn't installed; volume widget disabled")
            return
        self.com = ComThread("audio")
        self._exe_paths: dict[str, str] = {}
        self.spawn(self.poll("volume", 0.7, lambda: self.com.run(self._read)))

    # ---- COM thread ----------------------------------------------------
    @staticmethod
    def _endpoint():
        from pycaw.pycaw import AudioUtilities

        dev = AudioUtilities.GetSpeakers()
        if dev is None:
            raise ActionError("No audio output device.")
        return dev

    def _groups(self):
        """Audio sessions grouped by app (one app can own several sessions)."""
        from pycaw.pycaw import AudioUtilities

        groups: dict[str, dict] = {}
        for s in AudioUtilities.GetAllSessions():
            try:
                proc = s.Process
                if proc is None:
                    key, name = "system", "System sounds"
                else:
                    exe = proc.name()
                    key, name = exe.lower(), _pretty(exe)
                    if key not in self._exe_paths:
                        try:
                            self._exe_paths[key] = proc.exe()
                        except Exception:
                            pass
                g = groups.setdefault(key, {"key": key, "name": name, "sessions": []})
                g["sessions"].append(s)
            except Exception:
                continue  # process exited while we looked
        return groups

    def _read(self) -> dict:
        dev = self._endpoint()
        ev = dev.EndpointVolume
        apps = []
        for g in self._groups().values():
            vols = [s.SimpleAudioVolume for s in g["sessions"]]
            apps.append({
                "key": g["key"], "name": g["name"],
                "level": round(max(v.GetMasterVolume() for v in vols), 3),
                "muted": all(bool(v.GetMute()) for v in vols),
                "icon": g["key"] in self._exe_paths,
            })
        apps.sort(key=lambda a: (a["key"] == "system", a["name"].lower()))
        return {
            "device": getattr(dev, "FriendlyName", None) or "Speakers",
            "level": round(ev.GetMasterVolumeLevelScalar(), 3),
            "muted": bool(ev.GetMute()),
            "apps": apps,
        }

    def _set_master(self, level=None, muted=None):
        ev = self._endpoint().EndpointVolume
        if level is not None:
            ev.SetMasterVolumeLevelScalar(level, None)
            if level > 0 and ev.GetMute():
                ev.SetMute(0, None)
        if muted is not None:
            ev.SetMute(1 if muted else 0, None)
        return self._read()

    def _set_app(self, key, level=None, muted=None):
        g = self._groups().get(key)
        if not g:
            raise ActionError("That app isn't playing sound any more.")
        for s in g["sessions"]:
            v = s.SimpleAudioVolume
            if level is not None:
                v.SetMasterVolume(level, None)
                if level > 0:
                    v.SetMute(0, None)
            if muted is not None:
                v.SetMute(1 if muted else 0, None)
        return self._read()

    # ---- actions -------------------------------------------------------
    async def _apply(self, fn, *a):
        state = await self.com.run(fn, *a)
        self.hub.publish("volume", state)
        return True

    @action
    async def set_master(self, args, client):
        return await self._apply(self._set_master, _level(args.get("level")), None)

    @action
    async def set_mute(self, args, client):
        return await self._apply(self._set_master, None, bool(args.get("muted")))

    @action
    async def set_app(self, args, client):
        return await self._apply(self._set_app, str(args.get("key")), _level(args.get("level")), None)

    @action
    async def set_app_mute(self, args, client):
        return await self._apply(self._set_app, str(args.get("key")), None, bool(args.get("muted")))

    def router(self):
        r = APIRouter()

        @r.get("/icon/{key}")
        async def icon(key: str):
            path = self._exe_paths.get(key.lower())
            if not path or not os.path.isfile(path):
                return Response(status_code=404)
            import asyncio

            from ..winicons import extract_png

            png = await asyncio.to_thread(extract_png, path, 0, 96)
            if not png:
                return Response(status_code=404)
            return Response(png, media_type="image/png", headers={"cache-control": "private, max-age=86400"})

        return r
