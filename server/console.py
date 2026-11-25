"""Management console for the PC: http://127.0.0.1:<setup_port>/console/

Runs on the setup site (plain HTTP) and only answers this PC:
  * the client must be 127.0.0.1 / ::1,
  * the Host header must be 127.0.0.1 or localhost (blocks DNS-rebinding),
  * every API call needs the console key from data/console.key in an X-PadDock-Key header.
    A custom header also means other websites in your browser can't call it (CORS preflight).
The key reaches the page through the URL fragment opened by console.bat / the tray icon.
"""
from __future__ import annotations

import asyncio
import ctypes
import hmac
import json
import os
import re
import secrets
import subprocess
import threading
import time
import uuid
from ctypes import wintypes
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response

from . import __version__, autostart
from .modules.actions import icon_source
from .modules.base import ActionError
from .modules.core import HEX_RE, clean_pages
from .modules.macros import parse_keys
from .paths import CONFIG_PATH, DATA_DIR, ICON_CACHE_DIR, LOG_PATH

if TYPE_CHECKING:
    from .main import PadDock

KEY_PATH = DATA_DIR / "console.key"
LOOPBACK = {"127.0.0.1", "::1"}
ACTION_TYPES = {"exe", "app", "folder", "url", "shell", "keys", "text", "steps"}


def console_key() -> str:
    """The console key, created once and kept in data/console.key."""
    try:
        key = KEY_PATH.read_text("utf-8").strip()
        if len(key) >= 32:
            return key
    except FileNotFoundError:
        pass
    key = secrets.token_urlsafe(32)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_text(key, "utf-8")
    return key


def console_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/console/#key={console_key()}"


# ---- validation ------------------------------------------------------------
def _s(v, name: str, maxlen: int = 2000, required: bool = False) -> str:
    if v is None or v == "":
        if required:
            raise ActionError(f"{name} is required.")
        return ""
    if not isinstance(v, str) or len(v) > maxlen:
        raise ActionError(f"{name} must be text (up to {maxlen} characters).")
    return v.strip() if name != "Text" else v


def clean_action(a: Any) -> dict:
    """Validate a shortcut from the console. The console is trusted (it's the PC itself),
    so every type is allowed, but the structure must be right."""
    if not isinstance(a, dict):
        raise ActionError("Bad shortcut.")
    t = a.get("type")
    if t not in ACTION_TYPES:
        raise ActionError("Unknown shortcut type.")
    out: dict[str, Any] = {"type": t, "label": _s(a.get("label"), "Label", 40, True)}
    if t == "exe":
        out["path"] = _s(a.get("path"), "Path", 1000, True)
        if a.get("args"):
            out["args"] = _s(a.get("args"), "Arguments", 2000)
        if a.get("cwd"):
            out["cwd"] = _s(a.get("cwd"), "Working folder", 1000)
        if a.get("admin"):
            out["admin"] = True
    elif t == "app":
        out["appid"] = _s(a.get("appid"), "App id", 1000, True)
    elif t == "folder":
        out["path"] = _s(a.get("path"), "Folder", 1000, True)
    elif t == "url":
        out["url"] = _s(a.get("url"), "Link", 2000, True)
        if not re.match(r"^[a-z][a-z0-9+.-]*:", out["url"], re.I):
            raise ActionError("Links need a scheme, like https:// or spotify:")
    elif t == "shell":
        out["command"] = _s(a.get("command"), "Command", 4000, True)
        if a.get("cwd"):
            out["cwd"] = _s(a.get("cwd"), "Working folder", 1000)
        if a.get("window"):
            out["window"] = True
    elif t == "keys":
        out["keys"] = _s(a.get("keys"), "Keys", 200, True).lower()
        parse_keys(out["keys"])
    elif t == "text":
        out["text"] = _s(a.get("text"), "Text", 5000, True)
    elif t == "steps":
        steps = a.get("steps")
        if not isinstance(steps, list) or not (1 <= len(steps) <= 100):
            raise ActionError("A macro needs 1–100 steps.")
        clean = []
        for st in steps:
            if not isinstance(st, dict):
                raise ActionError("Bad macro step.")
            if "keys" in st:
                parse_keys(st["keys"])
                clean.append({"keys": str(st["keys"]).strip().lower()})
            elif "text" in st:
                clean.append({"text": _s(st["text"], "Text", 5000, True)})
            elif "delay" in st:
                try:
                    d = float(st["delay"])
                except (TypeError, ValueError):
                    raise ActionError("Delays are in seconds, e.g. 0.5")
                clean.append({"delay": min(10.0, max(0.0, d))})
            else:
                raise ActionError("Each macro step needs keys, text or a delay.")
        out["steps"] = clean
    icon = _s(a.get("icon"), "Icon", 1000)
    if icon:
        out["icon"] = icon
    color = a.get("color")
    if color:
        if not isinstance(color, str) or not HEX_RE.match(color):
            raise ActionError("Colour must look like #1db954.")
        out["color"] = color.lower()
    return out


def _new_id(label: str, existing: dict) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")[:30] or "shortcut"
    aid, n = base, 2
    while aid in existing:
        aid, n = f"{base}-{n}", n + 1
    return aid


# ---- native pickers (open on the PC's screen) --------------------------------
_pick_lock = threading.Lock()


def _pick(kind: str, initial: str | None) -> str | None:
    import tkinter as tk
    from tkinter import filedialog

    if not _pick_lock.acquire(blocking=False):
        raise ActionError("A file picker is already open on the PC.")
    try:
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        root.update()
        initialdir = initial if initial and os.path.isdir(os.path.expandvars(initial)) else None
        if initial and not initialdir and os.path.isfile(os.path.expandvars(initial)):
            initialdir = os.path.dirname(os.path.expandvars(initial))
        if kind == "folder":
            path = filedialog.askdirectory(parent=root, initialdir=initialdir, title="Choose a folder for PadDock")
        elif kind == "icon":
            path = filedialog.askopenfilename(parent=root, initialdir=initialdir, title="Choose an icon",
                                              filetypes=[("Icons", "*.ico *.png *.jpg *.exe *.dll"), ("All files", "*.*")])
        else:
            path = filedialog.askopenfilename(parent=root, initialdir=initialdir, title="Choose a program or file",
                                              filetypes=[("Programs", "*.exe *.lnk *.bat *.cmd"), ("All files", "*.*")])
        root.destroy()
        return os.path.normpath(path) if path else None
    finally:
        _pick_lock.release()


# ---- installed apps (Start menu) ------------------------------------------
_apps_cache: tuple[float, list] | None = None
_APPS_PS = r"""
$ErrorActionPreference = 'SilentlyContinue'
$sh = New-Object -ComObject WScript.Shell
$dirs = "$env:ProgramData\Microsoft\Windows\Start Menu\Programs", "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"
$lnks = Get-ChildItem $dirs -Recurse -Filter *.lnk | ForEach-Object {
  $t = $sh.CreateShortcut($_.FullName)
  [pscustomobject]@{ name = $_.BaseName; target = $t.TargetPath; icon = $t.IconLocation }
}
$apps = Get-StartApps | Select-Object Name, AppID
[pscustomobject]@{ lnks = @($lnks); apps = @($apps) } | ConvertTo-Json -Depth 3 -Compress
"""


def _known_folder(guid: str) -> str | None:
    shell32 = ctypes.windll.shell32
    ole32 = ctypes.windll.ole32

    class GUID(ctypes.Structure):
        _fields_ = [("d1", ctypes.c_ulong), ("d2", ctypes.c_ushort), ("d3", ctypes.c_ushort), ("d4", ctypes.c_ubyte * 8)]

    try:
        u = uuid.UUID(guid)
    except ValueError:
        return None
    g = GUID(u.fields[0], u.fields[1], u.fields[2], (ctypes.c_ubyte * 8).from_buffer_copy(u.bytes[8:]))
    p = ctypes.c_wchar_p()
    if shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(p)) != 0:
        return None
    try:
        return p.value
    finally:
        ole32.CoTaskMemFree(p)


def _resolve_appid(appid: str) -> str | None:
    m = re.match(r"^\{([0-9A-Fa-f-]{36})\}\\(.+)$", appid)
    if m:
        base = _known_folder(m.group(1))
        return os.path.join(base, m.group(2)) if base else None
    return appid if re.match(r"^[A-Za-z]:\\", appid) else None


def _installed_apps() -> list[dict]:
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _APPS_PS],
                       capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    data = json.loads(r.stdout or "{}")
    lnk_by_name: dict[str, dict] = {}
    for l in data.get("lnks") or []:
        lnk_by_name.setdefault((l.get("name") or "").lower(), l)
    out = []
    for a in data.get("apps") or []:
        name, appid = a.get("Name") or "", a.get("AppID") or ""
        if not name or not appid:
            continue
        icon = None
        path = _resolve_appid(appid)
        if path and path.lower().endswith(".exe") and os.path.isfile(path):
            icon = path
        else:
            l = lnk_by_name.get(name.lower())
            if l:
                loc = (l.get("icon") or "").split(",")[0].strip()
                tgt = l.get("target") or ""
                if loc and os.path.isfile(os.path.expandvars(loc)):
                    icon = loc
                elif tgt.lower().endswith(".exe") and os.path.isfile(tgt):
                    icon = tgt
        if re.match(r"^https?://", appid, re.I):
            continue  # web links pinned to Start; add those as links instead
        out.append({"name": name, "appid": appid, "icon": icon, "path": path})
    out.sort(key=lambda x: x["name"].lower())
    return out


# ---- router ------------------------------------------------------------
def create_console_router(dock: "PadDock") -> APIRouter:
    key = console_key()

    def guard(request: Request):
        if request.client is None or request.client.host not in LOOPBACK:
            raise HTTPException(403, "The console only works on the PC itself.")
        host = (request.headers.get("host") or "").rsplit(":", 1)[0].strip("[]").lower()
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise HTTPException(403, "Open the console at http://127.0.0.1")
        origin = request.headers.get("origin")
        if origin and not re.match(r"^http://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$", origin):
            raise HTTPException(403, "Cross-site request refused.")
        given = request.headers.get("x-paddock-key", "")
        if not hmac.compare_digest(given.encode(), key.encode()):
            raise HTTPException(401, "Missing or wrong console key. Open the console from the tray icon or console.bat.")

    r = APIRouter(prefix="/console/api", dependencies=[Depends(guard)])

    def bad(e: ActionError):
        raise HTTPException(400, str(e))

    def connected() -> list[dict]:
        ctx = dock.ctx
        if not ctx:
            return []
        seen: dict[str, dict] = {}
        for c in list(ctx.hub.clients):
            d = seen.setdefault(c.device.id, {"id": c.device.id, "name": c.device.name, "sockets": 0})
            d["sockets"] += 1
        return list(seen.values())

    @r.get("/state")
    async def state():
        s = dock.get_state()
        return {
            "rev": dock.config.rev,
            "config": dock.config.data,
            "devices": dock.devices.list(),
            "connected": connected(),
            "pairing_code": dock.pairing.code,
            "app_url": s["app_url"], "app_url_ip": s["app_url_ip"], "local_name": s["local_name"],
            "setup_url": s["setup_url"], "https": s["https"],
            "host": s["host"], "version": __version__, "started": dock.started,
            "autostart": autostart.is_enabled(),
            "config_path": str(CONFIG_PATH), "data_dir": str(DATA_DIR),
        }

    @r.get("/rev")
    async def rev():
        return {"rev": dock.config.rev, "connected": connected(), "devices": len(dock.devices),
                "pairing_code": dock.pairing.code}

    # ---- shortcuts ----
    @r.post("/actions")
    async def save_action(body: dict):
        try:
            spec = clean_action(body.get("action"))
        except ActionError as e:
            bad(e)
        aid = body.get("id")
        page_id = body.get("add_to_page")
        actions = dock.config.get("actions") or {}
        if aid is not None and aid not in actions:
            raise HTTPException(404, "No such shortcut.")
        aid = aid or _new_id(spec["label"], actions)

        def mutate(d):
            d.setdefault("actions", {})[aid] = spec
            if page_id:
                for p in d.get("pages", []):
                    if p["id"] == page_id:
                        p["items"].append({"id": f"a-{secrets.token_hex(4)}", "kind": "action", "action": aid})

        dock.config.update(mutate)
        return {"id": aid}

    @r.delete("/actions/{aid}")
    async def delete_action(aid: str):
        def mutate(d):
            if d.get("actions", {}).pop(aid, None) is None:
                raise HTTPException(404, "No such shortcut.")
            for p in d.get("pages", []):
                p["items"] = [i for i in p["items"] if not (i.get("kind") == "action" and i.get("action") == aid)]

        dock.config.update(mutate)
        return True

    @r.post("/actions/{aid}/test")
    async def test_action(aid: str):
        a = (dock.config.get("actions") or {}).get(aid)
        if not a:
            raise HTTPException(404, "No such shortcut.")
        fn = dock.ctx.executors.get(a.get("type")) if dock.ctx else None
        if not fn:
            raise HTTPException(400, f"No runner for type {a.get('type')}.")
        try:
            await fn(a)
        except ActionError as e:
            bad(e)
        return True

    @r.put("/pages")
    async def save_pages(body: dict):
        try:
            pages = clean_pages(body.get("pages"), dock.config.get("actions") or {})
        except ActionError as e:
            bad(e)
        dock.config.update(lambda d: d.__setitem__("pages", pages))
        return True

    # ---- helpers that act on the PC ----
    @r.post("/pick")
    async def pick(body: dict):
        kind = body.get("kind") if body.get("kind") in ("file", "folder", "icon") else "file"
        try:
            return {"path": await asyncio.to_thread(_pick, kind, body.get("initial"))}
        except ActionError as e:
            bad(e)

    @r.get("/apps")
    async def apps(refresh: bool = False):
        global _apps_cache
        if refresh or not _apps_cache or time.time() - _apps_cache[0] > 600:
            _apps_cache = (time.time(), await asyncio.to_thread(_installed_apps))
        return _apps_cache[1]

    async def _png(src: str | None, index: int = 0):
        if not src:
            return Response(status_code=404)
        from .winicons import extract_png

        png = await asyncio.to_thread(extract_png, src, index, 128)
        if not png:
            return Response(status_code=404)
        return Response(png, media_type="image/png", headers={"cache-control": "private, max-age=600"})

    @r.get("/icon")
    async def icon(path: str, index: int = 0):
        return await _png(path, index)

    @r.get("/action-icon/{aid}")
    async def action_icon(aid: str):
        a = (dock.config.get("actions") or {}).get(aid)
        return await _png(icon_source(a) if isinstance(a, dict) else None, int((a or {}).get("icon_index", 0)))

    # ---- settings ----
    @r.post("/settings")
    async def settings(body: dict):
        if "accent" in body:
            if not isinstance(body["accent"], str) or not HEX_RE.match(body["accent"]):
                raise HTTPException(400, "Bad colour.")
            dock.config.update(lambda d: d.setdefault("appearance", {}).__setitem__("accent", body["accent"].lower()))
        if "units" in body:
            if body["units"] not in ("celsius", "fahrenheit"):
                raise HTTPException(400, "Bad units.")
            dock.config.update(lambda d: d.setdefault("weather", {}).__setitem__("units", body["units"]))
        if "online_art" in body:
            dock.config.update(lambda d: d.setdefault("media", {}).__setitem__("online_art", bool(body["online_art"])))
        if "weather_enabled" in body:
            dock.config.update(lambda d: d.setdefault("weather", {}).__setitem__("enabled", bool(body["weather_enabled"])))
        if body.get("city"):
            from .modules.weather import GEOCODE, _get_json

            try:
                res = await asyncio.to_thread(_get_json, GEOCODE, {"name": str(body["city"])[:80], "count": 1, "language": "en", "format": "json"})
            except Exception:
                raise HTTPException(502, "Couldn't reach Open-Meteo.")
            hit = (res.get("results") or [None])[0]
            if not hit:
                raise HTTPException(404, f"No place called “{body['city']}”.")
            name = ", ".join(x for x in (hit.get("name"), hit.get("admin1"), hit.get("country_code")) if x)
            dock.config.update(lambda d: d.setdefault("weather", {}).update(
                name=name, latitude=hit["latitude"], longitude=hit["longitude"], enabled=True))
        if isinstance(body.get("server"), dict):
            srv = body["server"]
            try:
                port, setup_port = int(srv["port"]), int(srv["setup_port"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(400, "Ports must be numbers.")
            if not (1024 <= port <= 65535 and 1024 <= setup_port <= 65535) or port == setup_port:
                raise HTTPException(400, "Use two different ports between 1024 and 65535.")
            bind = str(srv.get("bind") or "auto").strip()
            if bind not in ("auto", "0.0.0.0") and not re.match(r"^\d{1,3}(\.\d{1,3}){3}$", bind):
                raise HTTPException(400, "Bind must be auto, 0.0.0.0 or an IPv4 address.")
            from .mdns import NAME_RE

            hostname = str(srv.get("hostname") or "paddock").strip().lower().removesuffix(".local")
            if not NAME_RE.match(hostname):
                raise HTTPException(400, "The name can use a–z, 0–9 and dashes (up to 32 characters).")
            dock.config.update(lambda d: d.setdefault("server", {}).update(
                port=port, setup_port=setup_port, bind=bind, https=bool(srv.get("https", True)), hostname=hostname))
        return True

    @r.post("/autostart")
    async def set_autostart(body: dict):
        try:
            await asyncio.to_thread(autostart.enable if body.get("enabled") else autostart.disable)
        except Exception as e:
            raise HTTPException(500, f"Couldn't change start at login: {e}")
        return {"enabled": autostart.is_enabled()}

    # ---- devices ----
    @r.post("/devices/{dev_id}/revoke")
    async def revoke(dev_id: str):
        if not dock.devices.revoke(dev_id):
            raise HTTPException(404, "No such device.")
        return True

    @r.post("/devices/{dev_id}/rename")
    async def rename_device(dev_id: str, body: dict):
        from .security import NameTaken

        try:
            dev = dock.devices.rename(dev_id, body.get("name"))
        except KeyError:
            raise HTTPException(404, "No such device.")
        except NameTaken as e:
            raise HTTPException(409, f"Another device is already called “{e}”.")
        return dev.public()

    @r.post("/pairing/rotate")
    async def rotate():
        return {"code": dock.pairing.rotate()}

    @r.get("/pairing/qr")
    async def pairing_qr():
        from .setup_site import _qr_svg

        return Response(_qr_svg(dock.get_state()["setup_url"]), media_type="image/svg+xml")

    # ---- misc ----
    @r.post("/open")
    async def open_thing(body: dict):
        target = {"config": CONFIG_PATH, "data": DATA_DIR, "log": LOG_PATH}.get(body.get("what"))
        if target is None or not target.exists():
            raise HTTPException(404, "Not found.")
        os.startfile(target)  # noqa: S606 - opens the user's own file in its default app
        return True

    @r.post("/restart")
    async def restart():
        asyncio.get_running_loop().call_later(0.4, dock.restart)
        return True

    return r
