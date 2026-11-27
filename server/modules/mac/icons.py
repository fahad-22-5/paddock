"""Icons of Mac apps, files and folders as PNG.

Uses NSWorkspace (pyobjc) for any path. Without pyobjc, falls back to the .app's .icns
file converted with `sips`, or to Pillow for image files."""
from __future__ import annotations

import io
import os
import plistlib
import subprocess
import tempfile

from PIL import Image


def _png_from_image(path: str, size: int) -> bytes | None:
    try:
        img = Image.open(path).convert("RGBA")
    except Exception:
        return None
    img.thumbnail((size, size), Image.LANCZOS)
    out = io.BytesIO()
    img.save(out, "PNG")
    return out.getvalue()


def _workspace_icon(path: str, size: int) -> bytes | None:
    try:
        from AppKit import NSBitmapImageRep, NSPNGFileType, NSWorkspace
        from Foundation import NSMakeSize
    except ImportError:
        return None
    image = NSWorkspace.sharedWorkspace().iconForFile_(path)
    if image is None:
        return None
    image.setSize_(NSMakeSize(size, size))
    tiff = image.TIFFRepresentation()
    rep = NSBitmapImageRep.imageRepWithData_(tiff) if tiff is not None else None
    data = rep.representationUsingType_properties_(NSPNGFileType, None) if rep is not None else None
    if data is None:
        return None
    png = bytes(data)
    # NSImage may hand back several sizes; normalise to the one we want.
    try:
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        if max(img.size) != size:
            img = img.resize((size, size), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()
    except Exception:
        return png


def _app_icns(app: str) -> str | None:
    try:
        with open(os.path.join(app, "Contents", "Info.plist"), "rb") as f:
            info = plistlib.load(f)
    except Exception:
        return None
    name = info.get("CFBundleIconFile") or info.get("CFBundleIconName")
    if not name:
        return None
    icns = os.path.join(app, "Contents", "Resources", name if name.endswith(".icns") else name + ".icns")
    return icns if os.path.exists(icns) else None


def extract_png(path: str, index: int = 0, size: int = 256) -> bytes | None:
    path = os.path.expanduser(os.path.expandvars(str(path))).rstrip("/")
    if not os.path.exists(path):
        return None
    if path.lower().endswith((".png", ".jpg", ".jpeg")):
        return _png_from_image(path, size)
    png = _workspace_icon(path, size)
    if png:
        return png
    icns = _app_icns(path) if path.endswith(".app") else (path if path.endswith(".icns") else None)
    if icns:
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "icon.png")
            r = subprocess.run(["sips", "-s", "format", "png", "-Z", str(size), icns, "--out", out], capture_output=True)
            if r.returncode == 0 and os.path.exists(out):
                return open(out, "rb").read()
    return None
