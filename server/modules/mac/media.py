"""Now playing on macOS.

Two sources, picked automatically:
  * `media-control` (Homebrew: `brew install media-control`): any app that shows up in
    the macOS Now Playing widget (browsers, Spotify, Music, podcasts…).
  * Otherwise AppleScript for Spotify and Apple Music, which works out of the box.
    macOS asks once whether PadDock may control those apps.

Publishes the same "media" / "media_art" topics as the Windows module.
"""
from __future__ import annotations

import asyncio
import base64
import datetime as dt
import json
import os
import shutil
import subprocess
import time
import urllib.request

import psutil

from ...platform import applescript_quote, osascript
from .. import album_art
from ..base import ActionError, Module, action

SEP = "\x1f"  # field separator in AppleScript output
BUNDLE_NAMES = {
    "com.spotify.client": "Spotify", "com.apple.Music": "Music", "com.apple.Safari": "Safari",
    "com.google.Chrome": "Chrome", "org.mozilla.firefox": "Firefox", "com.microsoft.edgemac": "Edge",
    "com.brave.Browser": "Brave", "com.apple.podcasts": "Podcasts", "com.apple.TV": "TV",
    "org.videolan.vlc": "VLC", "com.tidal.desktop": "TIDAL", "com.deezer.deezer-desktop": "Deezer",
}


def _num(text: str) -> float:
    try:
        return float(str(text).strip().replace(",", "."))  # AppleScript uses the locale's decimal comma
    except ValueError:
        return 0.0


def find_media_control() -> str | None:
    """`media-control` from PATH or Homebrew (apps started from Finder get a minimal PATH)."""
    return shutil.which("media-control") or next(
        (p for p in ("/opt/homebrew/bin/media-control", "/usr/local/bin/media-control") if os.path.exists(p)), None)


# ---- AppleScript players -------------------------------------------------------
class ScriptPlayer:
    """Spotify or Apple Music, controlled with AppleScript."""

    def __init__(self, app: str, process: str, has_art_url: bool, duration_in_ms: bool):
        self.app, self.process, self.has_art_url, self.duration_in_ms = app, process, has_art_url, duration_in_ms

    @property
    def id(self) -> str:
        return self.app

    def running(self) -> bool:
        # Only talk to apps that are open: scripting an app that isn't installed would
        # make macOS ask "Where is …?".
        return any(p.info["name"] == self.process for p in psutil.process_iter(["name"]))

    def read(self) -> dict | None:
        art = f' & sep & (artwork url of t)' if self.has_art_url else ' & sep & ""'
        script = f'''set sep to character id 31
tell application {applescript_quote(self.app)}
    set st to player state as string
    if st is "stopped" then return "stopped"
    set t to current track
    return st & sep & (name of t) & sep & (artist of t) & sep & (album of t) & sep & (duration of t) & sep & (player position){art}
end tell'''
        out = osascript(script, 5)
        if not out or out == "stopped":
            return None
        parts = out.split(SEP)
        if len(parts) < 7:
            return None
        state, title, artist, album, duration, position, art_url = parts[:7]
        dur = _num(duration) / (1000 if self.duration_in_ms else 1)
        return {"status": "playing" if state == "playing" else "paused", "title": title, "artist": artist,
                "album": album, "duration": dur, "position": _num(position), "art_url": art_url or None, "art_data": None}

    def command(self, what: str, value: float | None = None) -> None:
        verbs = {"play_pause": "playpause", "next": "next track", "prev": "previous track"}
        stmt = f"set player position to {value:.1f}" if what == "seek" else verbs[what]
        osascript(f"tell application {applescript_quote(self.app)} to {stmt}", 5)


# ---- media-control (any app) ----------------------------------------------------
class MediaControlPlayer:
    id = "system"

    def __init__(self, exe: str):
        self.exe = exe
        self.app_name = "Now Playing"

    def running(self) -> bool:
        return True

    def read(self) -> dict | None:
        r = subprocess.run([self.exe, "get"], capture_output=True, text=True, timeout=5)
        text = (r.stdout or "").strip()
        if r.returncode != 0 or not text or text == "null":
            return None
        d = json.loads(text)
        if not d or not d.get("title"):
            return None
        bundle = d.get("bundleIdentifier") or d.get("parentApplicationBundleIdentifier") or ""
        self.app_name = BUNDLE_NAMES.get(bundle, bundle.split(".")[-1].capitalize() if bundle else "Now Playing")
        playing = bool(d.get("playing"))
        pos = d.get("elapsedTimeNow")
        if pos is None:
            pos = float(d.get("elapsedTime") or 0)
            ts = d.get("timestamp")
            if playing and ts:
                try:
                    if isinstance(ts, (int, float)):
                        then = float(ts) / (1000 if ts > 1e11 else 1)
                    else:
                        then = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
                    pos += max(0.0, time.time() - then)
                except (ValueError, TypeError):
                    pass
        art = d.get("artworkData")
        return {"status": "playing" if playing else "paused", "title": d.get("title") or "", "artist": d.get("artist") or "",
                "album": d.get("album") or "", "duration": float(d.get("duration") or 0), "position": float(pos or 0),
                "art_url": None, "art_data": base64.b64decode(art) if art else None}

    def command(self, what: str, value: float | None = None) -> None:
        args = {"play_pause": ["toggle-play-pause"], "next": ["next-track"], "prev": ["previous-track"],
                "seek": ["seek", f"{value:.1f}"]}[what]
        r = subprocess.run([self.exe, *args], capture_output=True, text=True, timeout=5)
        if r.returncode != 0:
            raise ActionError((r.stderr or "media-control failed").strip())


class MediaModule(Module):
    name = "media"

    async def start(self) -> None:
        exe = find_media_control()
        if exe:
            self.players = [MediaControlPlayer(exe)]
            self.log.info("Now playing via media-control (all apps)")
        else:
            self.players = [ScriptPlayer("Spotify", "Spotify", has_art_url=True, duration_in_ms=True),
                            ScriptPlayer("Music", "Music", has_art_url=False, duration_in_ms=False)]
            self.log.info("Now playing via AppleScript (Spotify, Music). For all apps: brew install media-control")
        self.selected: str | None = None
        self._current = None
        self._art_key = None
        self._kick = asyncio.Event()
        self.spawn(self._loop())

    def _name(self, p) -> str:
        return getattr(p, "app_name", None) or p.app

    async def _loop(self) -> None:
        last = None
        while True:
            if not (self.hub.subscribers("media") or self.hub.subscribers("media_art")):
                await self.hub.wait_for_subscribers("media")
                last, self._art_key = None, None
            try:
                state = await asyncio.wait_for(self._sample(), 8)
                if state != last:
                    self.hub.publish("media", state)
                    last = state
            except asyncio.CancelledError:
                raise
            except Exception as e:
                self.log.debug("media sampling failed: %s", e)
                await asyncio.sleep(2)
            self._kick.clear()
            try:
                await asyncio.wait_for(self._kick.wait(), timeout=1.0)
                await asyncio.sleep(0.3)
            except asyncio.TimeoutError:
                pass

    async def _sample(self) -> dict:
        running = [p for p in self.players if await asyncio.to_thread(p.running)]
        readings = {}
        for p in running:
            try:
                info = await asyncio.to_thread(p.read)
            except Exception as e:
                self.log.debug("%s: %s", p.id, e)
                info = None
            if info:
                readings[p.id] = (p, info)
        listing = [{"id": p.id, "name": self._name(p)} for p, _ in readings.values()]
        pick = readings.get(self.selected) or next((v for v in readings.values() if v[1]["status"] == "playing"), None) \
            or next(iter(readings.values()), None)
        if not pick:
            self._current = None
            if self._art_key is not None:
                self._art_key = None
                self.hub.publish("media_art", {"key": None, "src": None})
            return {"active": False, "sessions": listing}
        p, s = pick
        self._current = p
        duration = max(0.0, s["duration"])
        position = min(max(0.0, s["position"]), duration) if duration else max(0.0, s["position"])
        key = (p.id, s["title"], s["artist"], s["album"])
        await self._update_art(key, s)
        return {
            "active": True, "app": p.id, "app_name": self._name(p),
            "title": s["title"], "artist": s["artist"], "album": s["album"],
            "status": s["status"], "position": round(position, 1), "duration": round(duration, 1),
            "can": {"play_pause": True, "next": True, "prev": True, "seek": duration > 0},
            "art_key": f"{hash(key) & 0xFFFFFFFF:x}",
            "sessions": listing,
        }

    async def _update_art(self, key, s) -> None:
        if key == self._art_key:
            return
        self._art_key = key
        art_id = f"{hash(key) & 0xFFFFFFFF:x}"
        raw = s.get("art_data")
        if raw is None and s.get("art_url"):
            try:
                raw = await asyncio.to_thread(lambda: urllib.request.urlopen(
                    urllib.request.Request(s["art_url"], headers={"User-Agent": "PadDock/1.0"}), timeout=6).read())
            except Exception as e:
                self.log.debug("artwork download failed: %s", e)
        prepared = await asyncio.to_thread(album_art.prepare_thumbnail, raw) if raw else None
        self.hub.publish("media_art", {"key": art_id, "src": prepared[1] if prepared else None})
        online = (self.config.get("media") or {}).get("online_art", True)
        _, title, artist, album = key
        if online and title and (prepared is None or album_art.is_small(prepared[0])):
            self.spawn(self._upgrade_art(key, art_id, title, artist, album, prepared[0] if prepared else None))

    async def _upgrade_art(self, key, art_id, title, artist, album, thumb) -> None:
        try:
            if thumb is not None:
                src = await asyncio.to_thread(album_art.find_hires, title, artist, album, thumb)
            else:
                src = await asyncio.to_thread(album_art.find_by_name, title, artist, album)
        except Exception:
            return
        if src and key == self._art_key:
            self.hub.publish("media_art", {"key": art_id, "src": src, "hires": True})

    # ---- controls ------------------------------------------------------
    async def _do(self, what: str, value: float | None = None) -> bool:
        p = self._current
        if p is None:
            raise ActionError("Nothing is playing.")
        try:
            await asyncio.to_thread(p.command, what, value)
        except RuntimeError as e:
            raise ActionError(f"{self._name(p)} didn't accept that: {e}")
        self._kick.set()
        return True

    @action
    async def play_pause(self, args, client):
        return await self._do("play_pause")

    @action
    async def next(self, args, client):
        return await self._do("next")

    @action
    async def prev(self, args, client):
        return await self._do("prev")

    @action
    async def seek(self, args, client):
        try:
            return await self._do("seek", max(0.0, float(args.get("position"))))
        except (TypeError, ValueError):
            raise ActionError("Bad position.")

    @action
    async def select(self, args, client):
        sid = args.get("id")
        self.selected = sid if isinstance(sid, str) and sid else None
        self._art_key = None
        self._kick.set()
        return True
