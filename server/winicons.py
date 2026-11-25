"""Extract icons from programs, DLLs and folders as PNG (Win32 via ctypes + Pillow)."""
from __future__ import annotations

import ctypes
import io
import os
from ctypes import wintypes

from PIL import Image

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
shell32 = ctypes.WinDLL("shell32", use_last_error=True)


class ICONINFO(ctypes.Structure):
    _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]


class BITMAP(ctypes.Structure):
    _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG), ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG), ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                ("bmBits", wintypes.LPVOID)]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG), ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [("hIcon", wintypes.HICON), ("iIcon", ctypes.c_int), ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260), ("szTypeName", wintypes.WCHAR * 80)]


user32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                        ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT), wintypes.UINT, wintypes.UINT]
user32.PrivateExtractIconsW.restype = wintypes.UINT
user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
user32.DestroyIcon.argtypes = [wintypes.HICON]
user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
gdi32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT, wintypes.LPVOID,
                            ctypes.POINTER(BITMAPINFOHEADER), wintypes.UINT]
gdi32.DeleteObject.argtypes = [wintypes.HANDLE]
shell32.SHGetFileInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, ctypes.POINTER(SHFILEINFOW), wintypes.UINT, wintypes.UINT]
shell32.SHGetFileInfoW.restype = ctypes.c_size_t

SHGFI_ICON = 0x100
SHGFI_LARGEICON = 0x0


def _bitmap_rgba(hdc, hbm) -> tuple[Image.Image, int, int] | None:
    bmp = BITMAP()
    if not gdi32.GetObjectW(hbm, ctypes.sizeof(bmp), ctypes.byref(bmp)):
        return None
    w, h = bmp.bmWidth, abs(bmp.bmHeight)
    hdr = BITMAPINFOHEADER(biSize=ctypes.sizeof(BITMAPINFOHEADER), biWidth=w, biHeight=-h, biPlanes=1, biBitCount=32, biCompression=0)
    buf = ctypes.create_string_buffer(w * h * 4)
    if not gdi32.GetDIBits(hdc, hbm, 0, h, buf, ctypes.byref(hdr), 0):
        return None
    return Image.frombuffer("RGBA", (w, h), buf.raw, "raw", "BGRA", 0, 1), w, h


def hicon_to_png(hicon) -> bytes | None:
    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        return None
    hdc = user32.GetDC(None)
    try:
        if not info.hbmColor:
            return None
        res = _bitmap_rgba(hdc, info.hbmColor)
        if not res:
            return None
        img, w, h = res
        if img.getchannel("A").getextrema() == (0, 0):
            # Old-style icon without alpha: build it from the AND mask.
            mask = _bitmap_rgba(hdc, info.hbmMask)
            if mask:
                alpha = mask[0].convert("L").point(lambda p: 0 if p > 127 else 255).crop((0, 0, w, h))
                img.putalpha(alpha)
            else:
                img.putalpha(255)
        bbox = img.getchannel("A").getbbox()
        if bbox is None:
            return None
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()
    finally:
        user32.ReleaseDC(None, hdc)
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)


def extract_png(path: str, index: int = 0, size: int = 256) -> bytes | None:
    """Icon of an .exe/.dll/.ico (by index), or the shell icon of any file or folder."""
    path = os.path.expandvars(path)
    if os.path.isdir(path):
        return extract_png(os.path.expandvars(r"%SystemRoot%\System32\imageres.dll"), 3, size)
    if path.lower().endswith((".png", ".jpg", ".jpeg")) and os.path.isfile(path):
        img = Image.open(path).convert("RGBA")
        img.thumbnail((size, size))
        out = io.BytesIO()
        img.save(out, "PNG")
        return out.getvalue()
    hicon = wintypes.HICON()
    icon_id = wintypes.UINT()
    n = user32.PrivateExtractIconsW(path, index, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0)
    if n and n != 0xFFFFFFFF and hicon:
        try:
            png = hicon_to_png(hicon)
            if png:
                return png
        finally:
            user32.DestroyIcon(hicon)
    # Fallback: whatever Explorer shows for this file (32 px).
    sfi = SHFILEINFOW()
    if shell32.SHGetFileInfoW(path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), SHGFI_ICON | SHGFI_LARGEICON) and sfi.hIcon:
        try:
            return hicon_to_png(sfi.hIcon)
        finally:
            user32.DestroyIcon(sfi.hIcon)
    return None
