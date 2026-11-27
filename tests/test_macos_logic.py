"""Logic tests for the macOS modules that run on any OS (macOS APIs are replaced by fakes).

    python tests/test_macos_logic.py      (or: python -m pytest tests)

They check the commands PadDock sends to macOS and how it parses macOS output. The real
system integration is covered by tools/smoke_test.py on a Mac (GitHub Actions)."""
from __future__ import annotations

import asyncio
import json
import plistlib
import sys
import tempfile
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server.hub import Hub  # noqa: E402
from server.modules.base import ActionError, Context  # noqa: E402


class FakeConfig:
    def __init__(self, data=None):
        self.data = data or {}

    def get(self, key, default=None):
        return self.data.get(key, default)


class patched:
    """Temporarily replace an attribute (restored afterwards, so tests don't leak)."""

    def __init__(self, obj, name, value):
        self.obj, self.name, self.value = obj, name, value

    def __enter__(self):
        self.old = getattr(self.obj, self.name)
        setattr(self.obj, self.name, self.value)

    def __exit__(self, *exc):
        setattr(self.obj, self.name, self.old)


def ctx():
    return Context(hub=Hub(), config=FakeConfig({"media": {"online_art": False}}), devices=None, pairing=None)


# ---- volume ----------------------------------------------------------------------
def test_volume_parsing():
    from server.modules.mac.volume import parse_volume_settings

    assert parse_volume_settings("output volume:44, input volume:75, alert volume:100, output muted:false") == {"level": 0.44, "muted": False}
    assert parse_volume_settings("output volume:100, input volume:50, alert volume:100, output muted:true") == {"level": 1.0, "muted": True}
    assert parse_volume_settings("output volume:missing value, input volume:missing value, alert volume:100, output muted:missing value") == {"level": None, "muted": False}


def test_volume_actions():
    from server.modules.mac import volume

    scripts = []
    volume.osascript = lambda s, t=10: scripts.append(s) or "output volume:30, input volume:0, alert volume:100, output muted:false"
    m = volume.VolumeModule(ctx())
    asyncio.run(m.set_master({"level": 0.5}, None))
    asyncio.run(m.set_mute({"muted": True}, None))
    assert scripts[0] == "set volume output volume 50 without output muted", scripts
    assert "set volume output muted true" in scripts
    state = asyncio.run(m._read())
    assert state["level"] == 0.3 and state["per_app"] is False and state["apps"] == []
    try:
        asyncio.run(m.set_app({"key": "x", "level": 1}, None))
        raise AssertionError("per-app volume should be refused")
    except ActionError:
        pass


# ---- GPU -------------------------------------------------------------------------
IOREG_SAMPLE = '''+-o AGXAcceleratorG14X  <class AGXAcceleratorG14X, id 0x1000003a2, registered, matched, active, busy 0 (0 ms), retain 92>
    {
      "IOClass" = "AGXAcceleratorG14X"
      "model" = "Apple M2"
      "PerformanceStatistics" = {"In use system memory"=581402624,"Device Utilization %"=23,"Renderer Utilization %"=21,"Tiler Utilization %"=8}
    }
'''


def test_gpu_parsing():
    from server.modules.mac.gpu import parse_ioreg

    gpus = parse_ioreg(IOREG_SAMPLE)
    assert gpus == [{"name": "Apple M2", "util": 23.0, "temp": None, "mem_used": 581402624, "mem_total": 0, "power": None, "fan": None}], gpus
    assert parse_ioreg("+-o IOAccelerator <class Foo>\n  {\n  }\n") == []


# ---- media -----------------------------------------------------------------------
def test_spotify_script_parsing():
    from server.modules.mac import media

    sep = media.SEP
    media.osascript = lambda s, t=10: sep.join(["playing", "Dilhaara", "OutStation", "You Are Now Heading", "149000", "28,5", "https://i.scdn.co/image/x"])
    p = media.ScriptPlayer("Spotify", "Spotify", has_art_url=True, duration_in_ms=True)
    info = p.read()
    assert info["title"] == "Dilhaara" and info["status"] == "playing"
    assert info["duration"] == 149.0 and info["position"] == 28.5 and info["art_url"].startswith("https://")
    media.osascript = lambda s, t=10: "stopped"
    assert p.read() is None
    calls = []
    media.osascript = lambda s, t=10: calls.append(s) or ""
    p.command("play_pause")
    p.command("seek", 42.0)
    assert calls == ['tell application "Spotify" to playpause', 'tell application "Spotify" to set player position to 42.0']


def test_media_control_parsing():
    from server.modules.mac import media

    class R:
        returncode = 0
        stdout = json.dumps({"title": "Safar", "artist": "Bayaan", "album": "Suno", "duration": 200.5,
                             "elapsedTimeNow": 61.2, "playing": True, "bundleIdentifier": "com.google.Chrome"})

    with patched(media.subprocess, "run", lambda *a, **k: R()):
        p = media.MediaControlPlayer("/opt/homebrew/bin/media-control")
        info = p.read()
        assert info["title"] == "Safar" and info["position"] == 61.2 and info["status"] == "playing"
        assert p.app_name == "Chrome"
        R.stdout = "null"
        assert p.read() is None


def test_media_module_state():
    from server.modules.mac import media

    class FakePlayer:
        id, app_name = "Music", "Music"

        def running(self):
            return True

        def read(self):
            return {"status": "paused", "title": "Song", "artist": "Artist", "album": "Album", "duration": 100.0,
                    "position": 150.0, "art_url": None, "art_data": None}

        def command(self, what, value=None):
            self.last = (what, value)

    m = media.MediaModule(ctx())
    m.players, m.selected, m._art_key, m._current = [FakePlayer()], None, None, None
    m._kick = asyncio.Event()
    state = asyncio.run(m._sample())
    assert state["active"] and state["app_name"] == "Music" and state["position"] == 100.0  # clamped to duration
    assert state["sessions"] == [{"id": "Music", "name": "Music"}]
    asyncio.run(m.seek({"position": 12}, None))
    assert m._current.last == ("seek", 12.0)


# ---- launcher --------------------------------------------------------------------
def test_launcher_commands():
    from server.modules.mac import launcher

    opened, popen, scripts = [], [], []
    launcher._open = lambda cmd: opened.append(cmd)
    launcher.osascript = lambda s, t=10: scripts.append(s) or ""
    with patched(launcher.subprocess, "Popen", lambda cmd, **k: popen.append(cmd)), \
            patched(launcher.os, "access", lambda path, mode: not str(path).endswith(".pdf")):
        _launcher_checks(launcher, opened, popen, scripts)


def _launcher_checks(launcher, opened, popen, scripts):
    m = launcher.LauncherModule(ctx())
    tmp = Path(tempfile.mkdtemp())
    app = tmp / "Fake.app"
    app.mkdir()
    doc = tmp / "report.pdf"
    doc.write_text("x")

    asyncio.run(m.run_exe({"path": str(app), "args": "--new-window --foo"}))
    asyncio.run(m.run_exe({"path": str(doc)}))
    asyncio.run(m.run_app({"appid": "com.apple.Safari"}))
    asyncio.run(m.run_app({"appid": str(app)}))
    asyncio.run(m.run_url({"url": "spotify:"}))
    asyncio.run(m.run_folder({"path": str(tmp)}))
    asyncio.run(m.run_shell({"command": "echo hi"}))
    asyncio.run(m.run_shell({"command": "top", "window": True}))
    assert opened == [["open", "-a", str(app), "--args", "--new-window", "--foo"], ["open", str(doc)],
                      ["open", "-b", "com.apple.Safari"], ["open", "-a", str(app)], ["open", "spotify:"], ["open", str(tmp)]], opened
    assert popen == [["/bin/zsh", "-lc", "echo hi"]]
    assert 'tell application "Terminal"' in scripts[0] and "do script" in scripts[0]
    for bad in ({"path": str(tmp / "missing.app")},):
        try:
            asyncio.run(m.run_exe(bad))
            raise AssertionError("missing path should fail")
        except ActionError:
            pass
    try:
        asyncio.run(m.run_url({"url": "file:///etc/passwd", "origin": "ipad"}))
        raise AssertionError("device-made links must be http(s)")
    except ActionError:
        pass


# ---- power -----------------------------------------------------------------------
def test_power_delay_and_cancel():
    from server.modules.mac import power

    scripts = []
    power.osascript = lambda s, t=10: scripts.append(s) or ""
    power.DELAY = 0.2

    async def run():
        m = power.PowerModule(ctx())
        await m.start()
        await m.restart({}, None)
        assert m.pending == "restart"
        await m.cancel({}, None)
        await asyncio.sleep(0.4)
        assert scripts == [] and m.pending is None  # cancelled before it fired
        await m.shutdown({}, None)
        await asyncio.sleep(0.4)
        assert scripts == ['tell application "System Events" to shut down'], scripts

    asyncio.run(run())


# ---- touchpad --------------------------------------------------------------------
def test_touchpad_events():
    from server.modules.mac import touchpad

    events = []

    class Point:
        def __init__(self, x, y):
            self.x, self.y = x, y

    class Rect:
        def __init__(self, x, y, w, h):
            self.origin, self.size = Point(x, y), types.SimpleNamespace(width=w, height=h)

    q = types.SimpleNamespace(
        kCGMouseButtonLeft=0, kCGMouseButtonRight=1, kCGMouseButtonCenter=2,
        kCGEventLeftMouseDown=1, kCGEventLeftMouseUp=2, kCGEventRightMouseDown=3, kCGEventRightMouseUp=4,
        kCGEventMouseMoved=5, kCGEventLeftMouseDragged=6, kCGEventRightMouseDragged=7,
        kCGEventOtherMouseDown=25, kCGEventOtherMouseUp=26, kCGEventOtherMouseDragged=27,
        kCGMouseEventClickState=1, kCGMouseEventDeltaX=4, kCGMouseEventDeltaY=5, kCGHIDEventTap=0, kCGScrollEventUnitPixel=0,
        CGEventCreate=lambda src: "now", CGEventGetLocation=lambda ev: Point(1915, 10),
        CGGetActiveDisplayList=lambda n, a, b: (0, [1], 1), CGDisplayBounds=lambda i: Rect(0, 0, 1920, 1080),
        CGMainDisplayID=lambda: 1,
        CGEventCreateMouseEvent=lambda src, etype, pos, button: {"type": etype, "pos": pos, "button": button, "fields": {}},
        CGEventSetIntegerValueField=lambda ev, field, value: ev["fields"].__setitem__(field, value),
        CGEventCreateScrollWheelEvent=lambda src, unit, count, dy, dx: {"type": "scroll", "dy": dy, "dx": dx},
        CGEventPost=lambda tap, ev: events.append(ev),
    )
    touchpad.Q = q
    m = touchpad.TouchpadModule(ctx())
    asyncio.run(m.start())
    m.move({"dx": 20, "dy": -50}, None)
    assert events[-1]["type"] == 5 and events[-1]["pos"] == (1919, 0), events[-1]  # clamped to the screen
    m.down({"button": "left"}, None)
    m.move({"dx": -5, "dy": 5}, None)
    assert events[-1]["type"] == 6  # dragging while the button is down
    m.up({"button": "left"}, None)
    events.clear()
    m.click({"button": "left", "double": True}, None)
    assert [e["fields"][1] for e in events] == [1, 1, 2, 2]  # click states for a double click
    m.scroll({"dy": 120, "dx": -240}, None)
    assert events[-1] == {"type": "scroll", "dy": 48, "dx": -96}


# ---- installed apps, pickers, icons ------------------------------------------------
def test_installed_apps_and_picker():
    from server.modules.mac import apps

    tmp = Path(tempfile.mkdtemp())
    for name, info in {"Safari.app": {"CFBundleName": "Safari", "CFBundleIdentifier": "com.apple.Safari"},
                       "Helper.app": {"CFBundleName": "Helper", "CFBundleIdentifier": "x.helper", "LSUIElement": True},
                       "Code.app": {"CFBundleDisplayName": "Visual Studio Code", "CFBundleIdentifier": "com.microsoft.VSCode"}}.items():
        (tmp / name / "Contents").mkdir(parents=True)
        with open(tmp / name / "Contents" / "Info.plist", "wb") as f:
            plistlib.dump(info, f)
    apps.APP_DIRS = [tmp]
    found = apps.installed_apps()
    assert [a["name"] for a in found] == ["Safari", "Visual Studio Code"], found  # background helpers skipped
    assert found[0]["appid"] == "com.apple.Safari"

    class R:
        returncode, stdout = 0, "/Applications/Safari.app/\n"

    seen = {}
    with patched(apps.subprocess, "run", lambda cmd, **k: seen.setdefault("script", cmd[2]) and R()):
        assert apps.pick("file") == "/Applications/Safari.app"
        assert "choose file" in seen["script"]
        R.returncode = 1
        assert apps.pick("folder") is None  # cancelled


def test_icons_fallback_png():
    from PIL import Image

    from server.modules.mac import icons

    tmp = Path(tempfile.mkdtemp()) / "logo.png"
    Image.new("RGBA", (300, 200), (255, 0, 0, 255)).save(tmp)
    png = icons.extract_png(str(tmp), 0, 64)
    assert png[:8] == b"\x89PNG\r\n\x1a\n"


# ---- autostart, mDNS, module selection -------------------------------------------------
def test_launch_agent_plist():
    from server import autostart

    agent = autostart.mac_launch_agent()
    assert agent["Label"] == "com.paddock.server" and agent["RunAtLoad"] is True
    assert agent["ProgramArguments"][-1] == "--tray"
    plistlib.dumps(agent)  # serialisable


def test_bonjour_registration():
    from server import mdns

    calls = []

    class Proc:
        def poll(self):
            return None

        def terminate(self):
            calls.append("terminated")

    import subprocess

    real = subprocess.Popen
    subprocess.Popen = lambda cmd, **k: calls.append(cmd) or Proc()
    mdns.sys = types.SimpleNamespace(platform="darwin")
    try:
        a = mdns.NameAnnouncer()
        assert asyncio.run(a.start("paddock", "192.168.1.20", 8765, True)) is True
        cmd = calls[0]
        assert cmd[1:4] == ["-P", cmd[2], "_https._tcp"] and cmd[5:8] == ["8765", "paddock.local", "192.168.1.20"], cmd
        asyncio.run(a.stop())
        assert calls[-1] == "terminated"
    finally:
        subprocess.Popen = real
        mdns.sys = sys


def test_mac_module_selection():
    """With IS_MAC set, the module list uses the mac/ implementations (checked in a subprocess)."""
    import subprocess

    code = ("import sys; sys.path.insert(0, %r)\n"
            "import server.platform as p; p.IS_MAC = True\n"
            "import server.modules as m\n"
            "print(sorted({c.__module__ for c in m.MODULES}))") % str(ROOT)
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    mods = out.stdout
    for name in ("clipboard", "launcher", "media", "power", "touchpad", "volume"):
        assert f"server.modules.mac.{name}" in mods, mods
    assert "server.modules.core" in mods and "server.modules.system" in mods


def test_mac_macros_keymap():
    """On macOS, letters are characters (not Windows virtual-key codes) and F-keys are Key.fN."""
    from server.modules import macros

    real = macros.sys
    macros.sys = types.SimpleNamespace(platform="darwin")
    macros._TABLE = None
    try:
        keys = macros.parse_combo("cmd+shift+4")
        assert str(keys[0]) == "Key.cmd" and getattr(keys[2], "char", None) == "4"
        assert str(macros.parse_combo("f5")[0]) == "Key.f5"
        assert str(macros.parse_combo("option+a")[0]) == "Key.alt"
    finally:
        macros.sys = real
        macros._TABLE = None


def test_mac_keyboard_without_pc_keys():
    """pynput on macOS has no insert/print_screen/pause/num_lock/scroll_lock/menu keys.
    The key table must still build, and those names must give a clear error."""
    import pynput.keyboard as real_kb

    from server.modules import macros

    mac_keys = ["ctrl", "shift", "alt", "alt_gr", "cmd", "enter", "esc", "tab", "space", "backspace", "delete",
                "home", "end", "page_up", "page_down", "up", "down", "left", "right", "caps_lock",
                "media_play_pause", "media_next", "media_previous", "media_volume_up", "media_volume_down",
                "media_volume_mute"] + [f"f{n}" for n in range(1, 21)]
    FakeKey = types.SimpleNamespace(**{k: f"Key.{k}" for k in mac_keys})
    fake_module = types.SimpleNamespace(Key=FakeKey, KeyCode=real_kb.KeyCode)
    saved = sys.modules["pynput.keyboard"]
    sys.modules["pynput.keyboard"] = fake_module
    real_sys = macros.sys
    macros.sys = types.SimpleNamespace(platform="darwin")
    macros._TABLE = None
    try:
        assert macros.parse_combo("cmd+shift+4")[0] == "Key.cmd"
        assert macros.parse_combo("ctrl+cmd+q")[1] == "Key.cmd"
        assert macros.parse_combo("media_play_pause") == ["Key.media_play_pause"]
        for missing in ("insert", "printscreen", "pause"):
            try:
                macros.parse_combo(missing)
                raise AssertionError(f"{missing} should be refused on a Mac")
            except ActionError as e:
                assert "has no" in str(e), e
    finally:
        sys.modules["pynput.keyboard"] = saved
        macros.sys = real_sys
        macros._TABLE = None


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    failed = 0
    for name, fn in tests:
        try:
            fn()
            print(f"  PASS  {name}")
        except Exception as e:  # noqa: BLE001
            failed += 1
            import traceback

            print(f"  FAIL  {name}: {e!r}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
