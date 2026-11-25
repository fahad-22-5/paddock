"""Optional system tray icon (pystray): show the pairing code, toggle start-at-login, quit."""
from __future__ import annotations

import logging
import threading
import webbrowser
from typing import Callable

from PIL import Image

from . import autostart
from .console import console_url
from .paths import WEB_DIR

log = logging.getLogger("paddock.tray")


def start_tray(get_state: Callable[[], dict], on_quit: Callable[[], None]):
    """Run the tray icon on its own thread. Returns the pystray Icon (or None)."""
    try:
        import pystray
    except Exception as e:  # pragma: no cover
        log.warning("Tray icon unavailable: %s", e)
        return None

    def local_setup() -> str:
        return f"http://127.0.0.1:{get_state()['setup_port']}"

    def toggle_autostart(icon, item):
        try:
            autostart.disable() if autostart.is_enabled() else autostart.enable()
        except Exception:
            log.exception("Could not change start-at-login")

    def quit_(icon, item):
        icon.stop()
        on_quit()

    menu = pystray.Menu(
        pystray.MenuItem(lambda item: f"PadDock · {get_state()['app_url']}", None, enabled=False),
        pystray.MenuItem("Open PadDock console", lambda: webbrowser.open(console_url(get_state()["setup_port"])), default=True),
        pystray.MenuItem("Show pairing code", lambda: webbrowser.open(local_setup() + "/local/pairing")),
        pystray.MenuItem("Open device setup page", lambda: webbrowser.open(local_setup() + "/")),
        pystray.MenuItem("Start at login", toggle_autostart, checked=lambda item: autostart.is_enabled()),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quit PadDock", quit_),
    )
    image = Image.open(WEB_DIR / "icons" / "icon-192.png")
    icon = pystray.Icon("PadDock", image, "PadDock", menu)
    threading.Thread(target=icon.run, name="tray", daemon=True).start()
    return icon
