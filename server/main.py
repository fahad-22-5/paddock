"""Command-line entry point: `python run.py [--tray] ...`."""
from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import logging
import logging.handlers
import os
import signal
import socket
import sys
import time

import uvicorn

from . import __version__, autostart
from .app import create_app
from .config import ConfigStore
from .hub import Hub
from .modules import MODULES
from .modules.base import Context
from .netutil import all_lan_ips, primary_lan_ip
from .platform import IS_MAC, NAME as PLATFORM, message_box
from .paths import FROZEN, LOG_PATH, SOURCE_HINT, USER_DIR, ensure_dirs
from .security import DeviceStore, Pairing
from .setup_site import create_setup_app
from .console import console_url
from .mdns import NameAnnouncer, clean_hostname

log = logging.getLogger("paddock")


class _Server(uvicorn.Server):
    """uvicorn server that leaves Ctrl+C handling to us, so two servers can share a loop."""

    @contextlib.contextmanager
    def capture_signals(self):
        yield


def _setup_logging(to_file: bool) -> None:
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s", "%H:%M:%S")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    if to_file:
        h = logging.handlers.RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    else:
        h = logging.StreamHandler(sys.stdout)
    h.setFormatter(fmt)
    root.addHandler(h)
    for noisy in ("uvicorn.access", "comtypes", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _bind_socket(host: str, port: int) -> socket.socket:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    s = socket.socket(family, socket.SOCK_STREAM)
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):  # Windows: no port sharing / hijacking
        s.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        s.bind((host, port))
    except OSError as e:
        s.close()
        raise SystemExit(
            f"\nCan't listen on {host}:{port} ({e.strerror}).\n"
            "Is PadDock already running (check the tray), or is another program using that port?\n"
            "You can change the port in config.json."
        ) from None
    s.listen(128)
    s.set_inheritable(True)
    return s


def _print_qr(url: str) -> None:
    try:
        import qrcode

        qr = qrcode.QRCode(border=1)
        qr.add_data(url)
        buf = io.StringIO()
        qr.print_ascii(out=buf, invert=True)
        print(buf.getvalue())
    except Exception:
        pass


class PadDock:
    def __init__(self, args) -> None:
        self.args = args
        self.config = ConfigStore()
        self.devices = DeviceStore()
        if args.reset_pairing:
            self.devices.revoke_all()
            log.info("All paired devices were removed.")
        self.pairing = Pairing(self.devices)
        self.servers: list[_Server] = []
        self.ctx: Context | None = None
        self._restart = False
        self.started = time.time()
        self.quitting = False
        self.state = {"app_url": "", "app_url_ip": "", "local_name": None, "setup_url": "", "https": True, "code": "", "host": "", "setup_port": 0}
        self.pairing.on_rotate(self._on_code)
        self._console = not args.tray_only_log

    # ---- state shared with the setup site and tray ----------------------
    def get_state(self) -> dict:
        return {**self.state, "code": self.pairing.code}

    def _on_code(self, code: str) -> None:
        if self._console and self.state["app_url"]:
            print(f"\n  New pairing code for the next device:  {code[:3]} {code[3:]}\n", flush=True)

    def restart(self) -> None:
        """Restart the servers (e.g. after changing ports in the console)."""
        self._restart = True
        for s in self.servers:
            s.should_exit = True

    def quit(self) -> None:
        self.quitting = True
        for s in self.servers:
            s.should_exit = True

    # ---- run -----------------------------------------------------------
    async def run_once(self) -> bool:
        """Serve until quit or the LAN address changes. Returns True to restart."""
        srv = self.config.get("server")
        port, setup_port = int(srv["port"]), int(srv["setup_port"])
        use_https = bool(srv.get("https", True)) and not self.args.http
        bind = str(srv.get("bind") or "auto")
        lan_ip = primary_lan_ip()

        if bind == "auto":
            hosts = ([lan_ip] if lan_ip else []) + ["127.0.0.1"]
        else:
            hosts = [bind]
        shown_ip = lan_ip if bind in ("auto", "0.0.0.0") else bind
        shown_ip = shown_ip or "127.0.0.1"
        scheme = "https" if use_https else "http"
        hostname = clean_hostname(srv.get("hostname"))
        local_name = f"{hostname}.local"

        ssl_kwargs = {}
        if use_https:
            from .certs import ensure_certs

            certfile, keyfile = ensure_certs(
                all_lan_ips() + ([lan_ip] if lan_ip else []) + ([bind] if bind not in ("auto", "0.0.0.0") else []),
                [local_name])
            ssl_kwargs = {"ssl_certfile": str(certfile), "ssl_keyfile": str(keyfile)}

        # Friendly name (https://paddock.local:8765) announced on the LAN with mDNS.
        announcer = NameAnnouncer()
        announced = False
        if shown_ip != "127.0.0.1" and srv.get("hostname", "paddock") not in ("", None, False):
            announced = await announcer.start(hostname, shown_ip, port, use_https)
        ip_url = f"{scheme}://{shown_ip}:{port}/"
        self.state.update(
            app_url=f"{scheme}://{local_name}:{port}/" if announced else ip_url,
            app_url_ip=ip_url,
            local_name=local_name if announced else None,
            setup_url=f"http://{shown_ip}:{setup_port}/",
            https=use_https, host=socket.gethostname(), setup_port=setup_port,
        )

        # Listeners belong to the modules of one run; drop those of a previous run (restart on IP change).
        self.config._listeners.clear()
        self.devices._revoke_listeners.clear()
        hub = Hub()
        ctx = Context(hub=hub, config=self.config, devices=self.devices, pairing=self.pairing)
        ctx.info = {"name": socket.gethostname().removesuffix(".local"), "version": __version__, "platform": PLATFORM}
        self.ctx = ctx
        modules = [cls(ctx) for cls in MODULES]
        app = create_app(ctx, modules)
        setup_app = create_setup_app(self.get_state, self)

        main_socks = [_bind_socket(h, port) for h in hosts]
        setup_socks = [_bind_socket(h, setup_port) for h in hosts]
        common = {"log_level": "warning", "log_config": None, "proxy_headers": False, "server_header": False}
        main = _Server(uvicorn.Config(app, ws_ping_interval=20, ws_ping_timeout=20, **ssl_kwargs, **common))
        setup = _Server(uvicorn.Config(setup_app, lifespan="off", **common))
        self.servers = [main, setup]

        self._banner(hosts)

        restart = False

        async def watch_ip():
            nonlocal restart
            while not main.should_exit:
                await asyncio.sleep(15)
                if bind == "auto" and primary_lan_ip() not in (lan_ip, None):
                    log.warning("This PC's network address changed; restarting the server…")
                    restart = True
                    for s in self.servers:
                        s.should_exit = True

        watcher = asyncio.create_task(watch_ip())
        try:
            await asyncio.gather(main.serve(sockets=main_socks), setup.serve(sockets=setup_socks))
        finally:
            watcher.cancel()
            await announcer.stop()
            for s in main_socks + setup_socks:
                s.close()
        wanted, self._restart = self._restart, False
        return (restart or wanted) and not self.quitting

    def _banner(self, hosts: list[str]) -> None:
        s = self.get_state()
        if not self._console:
            log.info("PadDock %s at %s (setup page %s)", __version__, s["app_url"], s["setup_url"])
            return
        line = "─" * 60
        print(f"\n{line}\n  PadDock {__version__} is running on {s['host']}\n{line}")
        if "127.0.0.1" in hosts and len(hosts) == 1:
            print("  ⚠ No Wi-Fi/Ethernet address found; only reachable from this PC.")
        print(f"  Open on your device:   {s['app_url']}")
        if s.get("local_name"):
            print(f"  (or by IP address:   {s['app_url_ip']})")
        print(f"  First-time setup:    {s['setup_url']}   (scan the QR code below)")
        print(f"  Listening on:        {', '.join(hosts)}")
        print(f"  PC console:          {console_url(s['setup_port'])}")
        print(f"\n  Pairing code:  {s['code'][:3]} {s['code'][3:]}"
              + ("   ← enter this on your device" if len(self.devices) == 0 else "   (for adding another device)"))
        print()
        _print_qr(s["setup_url"])
        print("  Press Ctrl+C to stop.\n", flush=True)

    def serve_forever(self) -> None:
        import threading

        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, lambda *a: self.quit())
        while True:
            restart = asyncio.run(self.run_once())
            if not restart:
                break


def _run_with_menu_bar_icon(dock: "PadDock", no_console: bool) -> None:
    """macOS: the menu bar icon needs the main thread, so the server runs on another one."""
    import threading

    from .tray import build_icon

    icon = build_icon(dock.get_state, dock.quit)
    problem: dict = {}

    def serve():
        try:
            dock.serve_forever()
        except SystemExit as e:
            problem["text"] = e.code if isinstance(e.code, str) else None
        except Exception:
            log.exception("PadDock stopped because of an error")
            problem["text"] = f"PadDock stopped because of an error. Details are in\n{LOG_PATH}"
        finally:
            if icon is not None:
                with contextlib.suppress(Exception):
                    icon.stop()

    server = threading.Thread(target=serve, name="server", daemon=True)
    server.start()
    if icon is None:
        server.join()
    else:
        try:
            icon.run()  # blocks until "Quit PadDock" or the server stops
        except Exception:
            log.exception("The menu bar icon couldn't start; PadDock keeps running without it")
            server.join()
        dock.quit()
        server.join(timeout=10)
    if problem.get("text") and no_console:
        _message(problem["text"].strip(), error=True)


def _message(text: str, error: bool = False) -> None:
    """A dialog box (the installed app has no console window to print to)."""
    message_box(text, error)


def _running_instance_port() -> int | None:
    """The setup/console port if a PadDock is already running on this PC."""
    import urllib.request

    try:
        port = int(ConfigStore().get("server")["setup_port"])
        urllib.request.urlopen(f"http://127.0.0.1:{port}/console/", timeout=1.5)
        return port
    except Exception:
        return None


def _open_console() -> None:
    import webbrowser

    port = _running_instance_port()
    if port is None:
        msg = "PadDock isn't running. Start it from the Start menu." if FROZEN else \
            "PadDock isn't running. Start it with start.bat or start-tray.bat first."
        _message(msg, error=True) if FROZEN else print(msg)
        return
    if os.environ.get("PADDOCK_NO_BROWSER"):
        log.info("Console: %s", console_url(port))
        return
    webbrowser.open(console_url(port))


def main() -> None:
    p = argparse.ArgumentParser(prog="paddock", description="PadDock: touch dock for your Windows PC")
    p.add_argument("--tray", action="store_true", help="show a system tray icon (Quit / Show pairing code)")
    p.add_argument("--http", action="store_true", help="serve plain HTTP (no keep-awake or clipboard on the device)")
    p.add_argument("--reset-pairing", action="store_true", help="forget all paired devices")
    p.add_argument("--install-autostart", action="store_true", help="start PadDock (with tray icon) when you log in")
    p.add_argument("--remove-autostart", action="store_true", help="stop starting PadDock at login")
    p.add_argument("--console", action="store_true", help="open the management console of the running PadDock")
    p.add_argument("--uninstall", action="store_true", help=argparse.SUPPRESS)
    args = p.parse_args()
    if FROZEN:
        args.tray = True  # the installed app always lives in the tray
    if args.uninstall:
        # Before logging starts: the log lives in the settings folder the uninstaller may delete.
        from .uninstall import uninstall

        uninstall()
        return

    # pythonw.exe (tray / autostart) has no console: log to data/paddock.log instead.
    no_console = FROZEN or sys.stdout is None or sys.stderr is None or sys.executable.lower().endswith("pythonw.exe")
    ensure_dirs()
    if not FROZEN:
        with contextlib.suppress(OSError):
            SOURCE_HINT.write_text(str(USER_DIR), "utf-8")
    if no_console:
        sys.stdout = sys.stderr = open(LOG_PATH.with_suffix(".out.log"), "a", encoding="utf-8", buffering=1)
    else:
        with contextlib.suppress(Exception):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args.tray_only_log = no_console
    _setup_logging(to_file=no_console)

    if args.install_autostart:
        print(f"PadDock will start at login: {autostart.enable()}")
        return
    if args.console:
        _open_console()
        return
    if args.remove_autostart:
        print("Removed the login shortcut." if autostart.disable() else "PadDock wasn't set to start at login.")
        return

    # Already running? Open its console instead of failing on a busy port.
    if not args.reset_pairing and _running_instance_port() is not None:
        log.info("PadDock is already running; opening its console")
        _open_console()
        return

    dock = PadDock(args)
    if FROZEN and len(dock.devices) == 0 and not os.environ.get("PADDOCK_NO_BROWSER"):
        # First run of the app: show the console (pairing code + QR code for the device).
        import threading
        import webbrowser

        port = int(dock.config.get("server")["setup_port"])
        threading.Timer(2.5, lambda: webbrowser.open(console_url(port))).start()
    if args.tray and IS_MAC:
        _run_with_menu_bar_icon(dock, no_console)
        return
    if args.tray:
        from .tray import start_tray

        icon = start_tray(dock.get_state, dock.quit)
    else:
        icon = None
    try:
        dock.serve_forever()
    except SystemExit as e:
        if no_console and isinstance(e.code, str):
            _message(e.code.strip(), error=True)  # e.g. port already in use
        raise
    except Exception:
        log.exception("PadDock stopped because of an error")
        if no_console:
            _message(f"PadDock stopped because of an error. Details are in\n{LOG_PATH}", error=True)
        raise
    finally:
        if icon is not None:
            with contextlib.suppress(Exception):
                icon.stop()
