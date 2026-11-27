"""Touchpad on macOS: moves, clicks, drags and scrolls with Quartz mouse events.

macOS asks once for permission: System Settings → Privacy & Security → Accessibility →
allow PadDock (or Terminal/Python when running from source)."""
from __future__ import annotations

from ..base import ActionError, Module, action

try:
    import Quartz as Q
except ImportError:  # pragma: no cover - only without pyobjc
    Q = None

PIXELS_PER_WHEEL_UNIT = 0.4  # the dock sends Windows wheel units (120 per notch) ≈ 48 px per notch

_BUTTONS = {
    # name: (button, down event, up event, drag event)
    "left": ("kCGMouseButtonLeft", "kCGEventLeftMouseDown", "kCGEventLeftMouseUp", "kCGEventLeftMouseDragged"),
    "right": ("kCGMouseButtonRight", "kCGEventRightMouseDown", "kCGEventRightMouseUp", "kCGEventRightMouseDragged"),
    "middle": ("kCGMouseButtonCenter", "kCGEventOtherMouseDown", "kCGEventOtherMouseUp", "kCGEventOtherMouseDragged"),
}


def _int(v, lo, hi) -> int:
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


class TouchpadModule(Module):
    name = "touchpad"

    async def start(self) -> None:
        self._down: set[str] = set()
        if Q is None:
            self.log.warning("pyobjc-framework-Quartz isn't installed; the touchpad is disabled")

    # ---- helpers -------------------------------------------------------
    def _q(self):
        if Q is None:
            raise ActionError("The touchpad needs pyobjc-framework-Quartz (run setup.sh again).")
        return Q

    def _button(self, args):
        b = _BUTTONS.get(args.get("button", "left"))
        if not b:
            raise ActionError("Unknown mouse button.")
        q = self._q()
        return args.get("button", "left"), getattr(q, b[0]), getattr(q, b[1]), getattr(q, b[2]), getattr(q, b[3])

    def _position(self):
        q = self._q()
        p = q.CGEventGetLocation(q.CGEventCreate(None))
        return p.x, p.y

    def _bounds(self):
        """Union of all displays, so the pointer can travel between screens."""
        q = self._q()
        err, ids, n = q.CGGetActiveDisplayList(16, None, None)
        rects = [q.CGDisplayBounds(i) for i in (ids or [])[:n]] or [q.CGDisplayBounds(q.CGMainDisplayID())]
        x0 = min(r.origin.x for r in rects)
        y0 = min(r.origin.y for r in rects)
        x1 = max(r.origin.x + r.size.width for r in rects) - 1
        y1 = max(r.origin.y + r.size.height for r in rects) - 1
        return x0, y0, x1, y1

    def _post(self, etype, pos, button, click_state: int | None = None, dx: int = 0, dy: int = 0):
        q = self._q()
        ev = q.CGEventCreateMouseEvent(None, etype, pos, button)
        if click_state:
            q.CGEventSetIntegerValueField(ev, q.kCGMouseEventClickState, click_state)
        if dx or dy:
            q.CGEventSetIntegerValueField(ev, q.kCGMouseEventDeltaX, dx)
            q.CGEventSetIntegerValueField(ev, q.kCGMouseEventDeltaY, dy)
        q.CGEventPost(q.kCGHIDEventTap, ev)

    # ---- actions (synchronous, so moves stay in order) ------------------------------
    @action
    def move(self, args, client):
        dx, dy = _int(args.get("dx"), -3000, 3000), _int(args.get("dy"), -3000, 3000)
        if not (dx or dy):
            return
        q = self._q()
        x, y = self._position()
        x0, y0, x1, y1 = self._bounds()
        pos = (min(max(x + dx, x0), x1), min(max(y + dy, y0), y1))
        if "left" in self._down:
            etype, button = q.kCGEventLeftMouseDragged, q.kCGMouseButtonLeft
        elif "right" in self._down:
            etype, button = q.kCGEventRightMouseDragged, q.kCGMouseButtonRight
        else:
            etype, button = q.kCGEventMouseMoved, q.kCGMouseButtonLeft
        self._post(etype, pos, button, dx=dx, dy=dy)

    @action
    def click(self, args, client):
        name, button, down, up, _ = self._button(args)
        pos = self._position()
        for n in range(1, 3 if args.get("double") else 2):
            self._post(down, pos, button, click_state=n)
            self._post(up, pos, button, click_state=n)

    @action
    def down(self, args, client):
        name, button, down, _, _ = self._button(args)
        self._down.add(name)
        self._post(down, self._position(), button, click_state=1)

    @action
    def up(self, args, client):
        name, button, _, up, _ = self._button(args)
        self._down.discard(name)
        self._post(up, self._position(), button, click_state=1)

    @action
    def scroll(self, args, client):
        dy, dx = _int(args.get("dy"), -2400, 2400), _int(args.get("dx"), -2400, 2400)
        if not (dx or dy):
            return
        q = self._q()
        ev = q.CGEventCreateScrollWheelEvent(None, q.kCGScrollEventUnitPixel, 2,
                                             int(dy * PIXELS_PER_WHEEL_UNIT), int(dx * PIXELS_PER_WHEEL_UNIT))
        q.CGEventPost(q.kCGHIDEventTap, ev)
