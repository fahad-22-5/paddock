"""End-to-end smoke test: start PadDock in a temporary home, pair over HTTPS, exercise the
API, WebSocket topics and console, then check the log for errors. Works on Windows and macOS.

    python tools/smoke_test.py                 # run from source
    python tools/smoke_test.py --exe PATH      # test a built PadDock.exe / PadDock.app binary

Hardware-dependent topics (volume, media, clipboard) are reported but don't fail the run,
because CI machines have no sound card or desktop session.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT, SETUP_PORT = 18765, 18766
REQUIRED_TOPICS = ["config", "system", "notes"]
SOFT_TOPICS = ["volume", "media", "clipboard", "power"]
failures: list[str] = []


def check(ok: bool, what: str, detail: str = "") -> None:
    print(f"  {'PASS' if ok else 'FAIL'}  {what}" + (f"  ({detail})" if detail else ""), flush=True)
    if not ok:
        failures.append(what)


def note(what: str) -> None:
    print(f"  info  {what}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--exe", help="built PadDock binary to test instead of run.py")
    ap.add_argument("--keep", action="store_true", help="keep the temporary home folder")
    a = ap.parse_args()

    home = Path(tempfile.mkdtemp(prefix="paddock-smoke-"))
    example = ROOT / ("config.example.macos.json" if sys.platform == "darwin" else "config.example.json")
    cfg = json.loads(example.read_text("utf-8"))
    cfg["server"].update(port=PORT, setup_port=SETUP_PORT, https=True, hostname="paddock-smoke", bind="auto")
    (home / "config.json").write_text(json.dumps(cfg), "utf-8")
    env = {**os.environ, "PADDOCK_HOME": str(home), "PADDOCK_NO_BROWSER": "1"}
    cmd = [str(Path(a.exe).resolve())] if a.exe else [sys.executable, str(ROOT / "run.py")]
    log_file = open(home / "stdout.log", "w", encoding="utf-8")
    print(f"Starting {' '.join(cmd)}\n  home: {home}", flush=True)
    proc = subprocess.Popen(cmd, env=env, cwd=ROOT, stdout=log_file, stderr=subprocess.STDOUT)
    try:
        return asyncio.run(run_checks(home, proc))
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log_file.close()
        logs = "".join(p.read_text("utf-8", "replace") for p in [home / "stdout.log", home / "data" / "paddock.log"] if p.exists())
        tracebacks = logs.count("Traceback")
        check(tracebacks == 0, "no tracebacks in the server log", f"{tracebacks} found" if tracebacks else "")
        if tracebacks or failures:
            print("\n----- server log -----\n" + logs[-6000:])
        if not a.keep:
            shutil.rmtree(home, ignore_errors=True)
        print(f"\n{'SMOKE TEST PASSED' if not failures else 'SMOKE TEST FAILED: ' + ', '.join(failures)}")


async def run_checks(home: Path, proc: subprocess.Popen) -> int:
    ca = home / "data" / "certs" / "ca.crt"
    key_file = home / "data" / "console.key"
    deadline = time.time() + 90
    ctx = None
    while time.time() < deadline:
        if proc.poll() is not None:
            check(False, "server starts", f"exited with code {proc.returncode}")
            return 1
        if ca.exists() and key_file.exists():
            try:
                ctx = ssl.create_default_context(cafile=str(ca))
                urllib.request.urlopen(f"https://127.0.0.1:{PORT}/api/health", context=ctx, timeout=3)
                break
            except Exception:
                pass
        await asyncio.sleep(1)
    else:
        check(False, "server starts within 90 s")
        return 1
    check(True, "server starts and serves HTTPS with its own certificate")
    key = key_file.read_text().strip()

    def console(method, path, body=None):
        req = urllib.request.Request(f"http://127.0.0.1:{SETUP_PORT}/console/api{path}", method=method,
                                     data=json.dumps(body).encode() if body is not None else None,
                                     headers={"x-paddock-key": key, "content-type": "application/json"})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())

    # pairing + unique names
    def pair(name):
        code = console("GET", "/rev")["pairing_code"]
        req = urllib.request.Request(f"https://127.0.0.1:{PORT}/api/pair", data=json.dumps({"code": code, "name": name}).encode(),
                                     headers={"content-type": "application/json"})
        try:
            return json.loads(urllib.request.urlopen(req, context=ctx).read())
        except urllib.error.HTTPError as e:
            return {"error": e.code}

    token = pair("Smoke").get("token")
    check(bool(token), "pairing with the code from the console")
    check(pair("smoke").get("error") == 403, "a second device can't reuse the same name")

    # WebSocket topics and calls
    import websockets

    got, results = {}, {}
    async with websockets.connect(f"wss://127.0.0.1:{PORT}/ws", ssl=ctx) as ws:
        await ws.send(json.dumps({"type": "auth", "token": token}))
        await ws.send(json.dumps({"type": "sub", "t": token, "topics": REQUIRED_TOPICS + SOFT_TOPICS}))
        calls = [
            ("core", "devices", {}),
            ("actions", "create", {"type": "keys", "label": "Smoke keys", "keys": "ctrl+shift+m"}),
            ("notes", "save", {"text": "smoke test"}),
            ("macros", "key", {"key": "ctrl+alt+x"}),  # must be refused (not a plain key)
        ]
        for i, (mod, act, args) in enumerate(calls, 1):
            await ws.send(json.dumps({"type": "call", "t": token, "id": i, "mod": mod, "act": act, "args": args}))
        end = time.time() + 15
        while time.time() < end and (len(results) < len(calls) or any(t not in got for t in REQUIRED_TOPICS)):
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, end - time.time())))
            except asyncio.TimeoutError:
                break
            if m.get("type") == "event":
                got.setdefault(m["topic"], m["data"])
            elif m.get("type") == "result":
                results[m["id"]] = m
        # give slow hardware topics a moment more
        end = time.time() + 5
        while time.time() < end and any(t not in got for t in SOFT_TOPICS[:3]):
            try:
                m = json.loads(await asyncio.wait_for(ws.recv(), max(0.1, end - time.time())))
                if m.get("type") == "event":
                    got.setdefault(m["topic"], m["data"])
            except asyncio.TimeoutError:
                break

    for t in REQUIRED_TOPICS:
        check(t in got, f"topic '{t}' delivers data")
    sysd = got.get("system") or {}
    check("cpu" in sysd and "mem" in sysd, "system monitor has CPU and memory", f"gpus={[g.get('name') for g in sysd.get('gpus', [])]}")
    for t in SOFT_TOPICS[:3]:
        note(f"topic '{t}': {'ok ' + json.dumps(got[t])[:120] if t in got else 'no data (fine on CI without sound/desktop)'}")
    check(results.get(1, {}).get("ok") is True, "call core.devices")
    created = results.get(2, {})
    check(created.get("ok") is True, "create a keyboard shortcut from a device")
    check(results.get(3, {}).get("ok") is True, "save notes")
    check(results.get(4, {}).get("ok") is False, "touchpad keyboard refuses key combos")

    # console
    st = console("GET", "/state")
    check(created.get("data") in st["config"]["actions"], "console sees the new shortcut")
    check(st.get("platform") in ("windows", "macos"), "console reports the platform", st.get("platform", ""))
    apps = console("GET", "/apps")
    check(isinstance(apps, list), "console lists installed apps", f"{len(apps)} apps")
    probe = "/System/Applications/Calculator.app" if sys.platform == "darwin" else r"C:\Windows\explorer.exe"
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{SETUP_PORT}/console/api/icon?path={urllib.parse.quote(probe)}",
                                     headers={"x-paddock-key": key})
        png = urllib.request.urlopen(req, timeout=30).read()
        check(png[:8] == b"\x89PNG\r\n\x1a\n", "icon extraction returns a PNG", f"{len(png)} bytes for {probe}")
    except Exception as e:
        check(False, "icon extraction returns a PNG", str(e))
    console("DELETE", f"/actions/{created.get('data')}")
    check(created.get("data") not in console("GET", "/state")["config"]["actions"], "console deletes the shortcut")
    return 1 if failures else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: F401  (used above)

    rc = main()
    sys.exit(rc if isinstance(rc, int) else (1 if failures else 0))
