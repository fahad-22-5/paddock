"""Album art helpers for the media module.

Windows only gets a small thumbnail from some players (YouTube Music in Chrome sends
120×120 px), which looks blurry on a high-resolution screen. So we:
  1. upscale small thumbnails smoothly on the PC (better than the device stretching them), and
  2. optionally look the song up in the iTunes Search API (free, no key) and use Apple's
     high-resolution cover, but only if it visibly matches the thumbnail Windows gave us,
     so a wrong search hit never replaces the right art.

Step 2 sends the song title and artist to Apple. Turn it off in the console
(Settings → Album art) or with config.json → "media": {"online_art": false}.
"""
from __future__ import annotations

import base64
import io
import json
import logging
import re
import urllib.parse
import urllib.request
from collections import OrderedDict

from PIL import Image, ImageChops, ImageFilter, ImageStat

log = logging.getLogger("paddock.media")

SMALL = 400  # thumbnails smaller than this (px) count as low resolution
UPSCALE_TO = 480
HIRES = 800
MATCH_THRESHOLD = 30.0  # mean per-channel difference (0–255) at 24×24 px; same cover ≈ 5–15
_cache: OrderedDict[tuple, bytes | None] = OrderedDict()


def _trim(img: Image.Image) -> Image.Image:
    """Some apps pad art with letterbox bars; cut uniform dark borders."""
    bbox = Image.eval(img.convert("L"), lambda p: 255 if p > 8 else 0).getbbox()
    if bbox and (bbox[2] - bbox[0]) > img.width * 0.5:
        img = img.crop(bbox)
    return img


def to_data_url(img: Image.Image, quality: int = 90) -> str:
    out = io.BytesIO()
    img.convert("RGB").save(out, "JPEG", quality=quality, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode()


def prepare_thumbnail(raw: bytes) -> tuple[Image.Image, str] | None:
    """Decode Windows' thumbnail. Returns (image, data URL) with small art upscaled."""
    try:
        img = _trim(Image.open(io.BytesIO(raw)).convert("RGB"))
    except Exception:
        return None
    shown = img
    if max(img.size) < SMALL:
        scale = UPSCALE_TO / max(img.size)
        shown = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
        shown = shown.filter(ImageFilter.UnsharpMask(radius=1.6, percent=55, threshold=2))
    else:
        shown = img.copy()
        shown.thumbnail((HIRES, HIRES), Image.LANCZOS)
    return img, to_data_url(shown)


def is_small(img: Image.Image) -> bool:
    return max(img.size) < SMALL


def _difference(a: Image.Image, b: Image.Image) -> float:
    a = a.convert("RGB").resize((24, 24), Image.BILINEAR)
    b = b.convert("RGB").resize((24, 24), Image.BILINEAR)
    return sum(ImageStat.Stat(ImageChops.difference(a, b)).mean) / 3


def _clean(text: str) -> str:
    text = re.sub(r"\s*[\(\[][^)\]]*(official|video|audio|lyric|visuali[sz]er|remaster|hd|4k)[^)\]]*[\)\]]", "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def _get(url: str, timeout: float = 6) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "PadDock/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def find_hires(title: str, artist: str, album: str, thumb: Image.Image) -> str | None:
    """High-resolution cover from iTunes that matches `thumb`, as a data URL (blocking)."""
    key = (title.lower(), artist.lower(), album.lower())
    if key in _cache:
        _cache.move_to_end(key)
        hit = _cache[key]
        return to_data_url(Image.open(io.BytesIO(hit))) if hit else None

    first_artist = re.split(r",|&|\bx\b|\bfeat\.?|\bft\.?|\band\b", artist, flags=re.I)[0].strip()
    title_c = _clean(title)
    found: bytes | None = None
    for term in dict.fromkeys(t for t in (f"{first_artist} {title_c}", f"{title_c} {_clean(album)}", title_c) if t.strip()):
        try:
            q = urllib.parse.urlencode({"term": term[:120], "media": "music", "entity": "song", "limit": 6})
            results = json.loads(_get(f"https://itunes.apple.com/search?{q}")).get("results", [])
        except Exception as e:
            log.debug("iTunes search failed: %s", e)
            break
        for r in results:
            art = r.get("artworkUrl100")
            if not art:
                continue
            try:
                raw = _get(re.sub(r"/\d+x\d+bb\.(jpg|png)$", f"/{HIRES}x{HIRES}bb.jpg", art))
                cand = Image.open(io.BytesIO(raw))
                diff = _difference(cand, thumb)
            except Exception:
                continue
            if diff <= MATCH_THRESHOLD:
                log.debug("Hi-res art for %r matched (difference %.1f)", title, diff)
                found = raw
                break
        if found:
            break

    _cache[key] = found
    while len(_cache) > 60:
        _cache.popitem(last=False)
    return to_data_url(Image.open(io.BytesIO(found))) if found else None


def _norm(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _clean(text).lower())


def find_by_name(title: str, artist: str, album: str = "") -> str | None:
    """A cover when there's no thumbnail to compare with (Apple Music on macOS): only an
    iTunes result whose title and artist match exactly is accepted (blocking)."""
    key = ("byname", title.lower(), artist.lower(), album.lower())
    if key in _cache:
        hit = _cache[key]
        return to_data_url(Image.open(io.BytesIO(hit))) if hit else None
    first_artist = re.split(r",|&|\bx\b|\bfeat\.?|\bft\.?|\band\b", artist, flags=re.I)[0].strip()
    found = None
    try:
        q = urllib.parse.urlencode({"term": f"{first_artist} {_clean(title)}"[:120], "media": "music", "entity": "song", "limit": 10})
        for r in json.loads(_get(f"https://itunes.apple.com/search?{q}")).get("results", []):
            if _norm(r.get("trackName", "")) == _norm(title) and _norm(first_artist) in _norm(r.get("artistName", "")):
                if album and r.get("collectionName") and _norm(album) != _norm(r["collectionName"]):
                    continue
                art = r.get("artworkUrl100")
                if art:
                    found = _get(re.sub(r"/\d+x\d+bb\.(jpg|png)$", f"/{HIRES}x{HIRES}bb.jpg", art))
                    break
    except Exception as e:
        log.debug("iTunes lookup failed: %s", e)
    _cache[key] = found
    while len(_cache) > 60:
        _cache.popitem(last=False)
    return to_data_url(Image.open(io.BytesIO(found))) if found else None
