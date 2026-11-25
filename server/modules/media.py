"""Now playing + transport controls for any app that reports to Windows (Spotify, browsers,
Media Player, ...) through the Global System Media Transport Controls (WinRT).

Topics: "media" (state, every second while playing) and "media_art" (album art, only when
it changes, so the big image isn't resent every second)."""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from . import album_art
from .base import ActionError, Module, action

try:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as MediaManager,
    )
    from winrt.windows.storage.streams import Buffer, InputStreamOptions
except Exception:  # pragma: no cover - only on systems without WinRT
    MediaManager = None

WINRT_TIMEOUT = 5.0  # seconds; a stuck media app must not freeze the widget


async def _winrt(op, timeout: float = WINRT_TIMEOUT):
    """Await a WinRT async operation with a timeout."""
    return await asyncio.wait_for(op, timeout)


STATUS = {0: "closed", 1: "opened", 2: "changing", 3: "stopped", 4: "playing", 5: "paused"}
KNOWN_APPS = {
    "spotify": "Spotify", "chrome": "Chrome", "msedge": "Edge", "firefox": "Firefox", "308046b0af4a39cb": "Firefox",
    "zunemusic": "Media Player", "zunevideo": "Movies & TV", "vlc": "VLC", "brave": "Brave", "opera": "Opera",
    "applemusic": "Apple Music", "tidal": "TIDAL", "deezer": "Deezer", "foobar2000": "foobar2000", "musicbee": "MusicBee",
}


_START_APPS: dict[str, str] = {}  # app id (lower case) -> Start menu name
_start_apps_at = 0.0


def _load_start_apps() -> dict[str, str]:
    """Names of installed apps (incl. Chrome/Edge web apps like YouTube Music) by app id."""
    import json
    import subprocess

    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command",
                        "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(r.stdout or "[]")
    if isinstance(data, dict):
        data = [data]
    return {a["AppID"].lower(): a["Name"] for a in data if a.get("AppID") and a.get("Name")}


def app_name(aumid: str) -> str:
    # Installed web apps report as "Chrome._crx_<id>"; the Start menu knows their real name.
    if aumid.lower() in _START_APPS:
        return _START_APPS[aumid.lower()]
    base = aumid.split("!")[-1].split("\\")[-1]
    base = base[:-4] if base.lower().endswith(".exe") else base
    for k, v in KNOWN_APPS.items():
        if k in aumid.lower():
            return v
    return base.split("_")[0].split(".")[-1] or "Media"


def _seconds(v) -> float:
    if isinstance(v, dt.timedelta):
        return v.total_seconds()
    try:
        return int(v) / 10_000_000  # 100 ns ticks
    except (TypeError, ValueError):
        return 0.0


def _epoch(v) -> float | None:
    if isinstance(v, dt.datetime):
        if v.tzinfo is None:
            v = v.replace(tzinfo=dt.timezone.utc)
        ts = v.timestamp()
        return ts if ts > 0 else None
    return None


class MediaModule(Module):
    name = "media"

    async def start(self) -> None:
        self.manager = None
        self.selected: str | None = None
        self._art_key = None
        self._kick = asyncio.Event()
        if MediaManager is None:
            self.log.warning("WinRT media controls unavailable; media widget disabled")
            return
        try:
            self.manager = await _winrt(MediaManager.request_async(), 10)
        except asyncio.TimeoutError:
            self.log.error("Windows media controls didn't answer; the media widget is disabled. Restart PadDock.")
            return
        except Exception as e:
            self.log.warning("Media controls unavailable: %s", e)
            return
        self.spawn(self._loop())

    def _session(self):
        sessions = list(self.manager.get_sessions())
        if self.selected:
            for s in sessions:
                if s.source_app_user_model_id == self.selected:
                    return s, sessions
        return self.manager.get_current_session(), sessions

    async def _loop(self) -> None:
        last = None
        while True:
            if not (self.hub.subscribers("media") or self.hub.subscribers("media_art")):
                await self.hub.wait_for_subscribers("media")
                last = None
                self._art_key = None
            try:
                state = await self._sample()
                if state != last:
                    self.hub.publish("media", state)
                    last = state
            except asyncio.CancelledError:
                raise
            except asyncio.TimeoutError:
                self.log.warning("A media app didn't answer in time; retrying")
            except Exception:
                self.log.exception("media sampling failed")
                await asyncio.sleep(3)
            self._kick.clear()
            try:
                await asyncio.wait_for(self._kick.wait(), timeout=1.0)
                await asyncio.sleep(0.25)  # let the app apply the command before re-reading
            except asyncio.TimeoutError:
                pass

    async def _sample(self) -> dict:
        session, sessions = self._session()
        await self._learn_names([s.source_app_user_model_id for s in sessions])
        listing = [{"id": s.source_app_user_model_id, "name": app_name(s.source_app_user_model_id)} for s in sessions]
        if session is None:
            if self._art_key is not None:
                self._art_key = None
                self.hub.publish("media_art", {"key": None, "src": None})
            return {"active": False, "sessions": listing}

        props = await _winrt(session.try_get_media_properties_async())
        info = session.get_playback_info()
        tl = session.get_timeline_properties()
        controls = info.controls
        status = STATUS.get(int(info.playback_status), "unknown")

        start, end = _seconds(tl.start_time), _seconds(tl.end_time)
        duration = max(0.0, end - start)
        position = _seconds(tl.position) - start
        updated = _epoch(tl.last_updated_time)
        if status == "playing" and updated:
            position += max(0.0, time.time() - updated)
        if duration:
            position = min(max(0.0, position), duration)

        aumid = session.source_app_user_model_id
        title, artist, album = props.title or "", props.artist or "", props.album_title or ""
        await self._update_art((aumid, title, artist, album), props.thumbnail)

        return {
            "active": True,
            "app": aumid,
            "app_name": app_name(aumid),
            "title": title,
            "artist": artist or props.album_artist or "",
            "album": album,
            "status": status,
            "position": round(position, 1),
            "duration": round(duration, 1),
            "can": {
                "play_pause": bool(controls.is_play_pause_toggle_enabled or controls.is_play_enabled or controls.is_pause_enabled),
                "next": bool(controls.is_next_enabled),
                "prev": bool(controls.is_previous_enabled),
                "seek": bool(controls.is_playback_position_enabled) and duration > 0,
            },
            "art_key": f"{hash(self._art_key) & 0xFFFFFFFF:x}" if self._art_key else None,
            "sessions": listing,
        }

    async def _learn_names(self, ids: list[str]) -> None:
        """Look app names up in the Start menu when an unknown app starts playing (max once a minute)."""
        global _START_APPS, _start_apps_at
        if all(i.lower() in _START_APPS for i in ids) or time.time() - _start_apps_at < 60:
            return
        _start_apps_at = time.time()
        try:
            _START_APPS = await asyncio.to_thread(_load_start_apps)
        except Exception as e:
            self.log.debug("Couldn't read Start menu app names: %s", e)

    async def _update_art(self, key, thumb) -> None:
        if key == self._art_key:
            return
        self._art_key = key
        art_id = f"{hash(key) & 0xFFFFFFFF:x}"
        prepared = None
        if thumb is not None:
            try:
                stream = await _winrt(thumb.open_read_async())
                size = int(stream.size)
                if 0 < size < 20_000_000:
                    buf = await _winrt(stream.read_async(Buffer(size), size, InputStreamOptions.READ_AHEAD))
                    prepared = await asyncio.to_thread(album_art.prepare_thumbnail, bytes(buf))
            except Exception as e:
                self.log.debug("No album art: %s", e)
        # Show Windows' thumbnail right away…
        self.hub.publish("media_art", {"key": art_id, "src": prepared[1] if prepared else None})
        # …then swap in a sharp cover if the thumbnail is small and online lookup is on.
        _, title, artist, album = key
        online = (self.config.get("media") or {}).get("online_art", True) if self.config else False
        if prepared and online and title and album_art.is_small(prepared[0]):
            self.spawn(self._upgrade_art(key, art_id, title, artist, album, prepared[0]))

    async def _upgrade_art(self, key, art_id, title, artist, album, thumb) -> None:
        try:
            src = await asyncio.to_thread(album_art.find_hires, title, artist, album, thumb)
        except Exception as e:
            self.log.debug("Hi-res art lookup failed: %s", e)
            return
        if src and key == self._art_key:  # still the same song
            self.hub.publish("media_art", {"key": art_id, "src": src, "hires": True})

    # ---- controls ------------------------------------------------------
    def _current(self):
        if not self.manager:
            raise ActionError("Media controls aren't available on this PC.")
        s, _ = self._session()
        if s is None:
            raise ActionError("Nothing is playing.")
        return s

    async def _do(self, coro) -> bool:
        try:
            ok = await _winrt(coro)
        except asyncio.TimeoutError:
            raise ActionError("The media app didn't respond.")
        self._kick.set()
        if not ok:
            raise ActionError("The app didn't accept that command.")
        return True

    @action
    async def play_pause(self, args, client):
        return await self._do(self._current().try_toggle_play_pause_async())

    @action
    async def next(self, args, client):
        return await self._do(self._current().try_skip_next_async())

    @action
    async def prev(self, args, client):
        return await self._do(self._current().try_skip_previous_async())

    @action
    async def seek(self, args, client):
        s = self._current()
        try:
            seconds = float(args.get("position"))
        except (TypeError, ValueError):
            raise ActionError("Bad position.")
        start = _seconds(s.get_timeline_properties().start_time)
        return await self._do(s.try_change_playback_position_async(int((start + max(0.0, seconds)) * 10_000_000)))

    @action
    async def select(self, args, client):
        """Follow a specific app instead of whatever Windows considers current (None = auto)."""
        sid = args.get("id")
        self.selected = sid if isinstance(sid, str) and sid else None
        self._art_key = None
        self._kick.set()
        return True
