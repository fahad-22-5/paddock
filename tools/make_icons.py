"""Generate the PWA / tray icons in web/icons. Run: python tools/make_icons.py"""
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parent.parent / "web" / "icons"
SS = 4  # supersampling for smooth edges


def lerp(a, b, t):
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def draw_icon(size: int, maskable: bool = False, rounded: bool = True) -> Image.Image:
    S = size * SS
    top, bottom = (40, 120, 255), (94, 52, 230)
    bg = Image.new("RGB", (S, S))
    px = ImageDraw.Draw(bg)
    for y in range(S):
        px.line([(0, y), (S, y)], fill=lerp(top, bottom, y / S))
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    mask = Image.new("L", (S, S), 0)
    md = ImageDraw.Draw(mask)
    if rounded and not maskable:
        md.rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 0.225), fill=255)
    else:
        md.rectangle([0, 0, S, S], fill=255)
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)
    # A 3x2 grid of tiles over a "dock" bar: the PadDock mark.
    safe = 0.62 if maskable else 0.74  # maskable icons keep content inside the safe zone
    box = S * safe
    x0 = (S - box) / 2
    y0 = (S - box) / 2
    gap = box * 0.07
    tile = (box - 2 * gap) / 3
    tile_h = tile * 0.92
    r = tile * 0.24
    for row in range(2):
        for col in range(3):
            tx = x0 + col * (tile + gap)
            ty = y0 + row * (tile_h + gap)
            alpha = 255 if (row, col) != (0, 0) else 255
            fill = (255, 255, 255, 235) if (row + col) % 2 == 0 else (255, 255, 255, 150)
            d.rounded_rectangle([tx, ty, tx + tile, ty + tile_h], radius=r, fill=fill)
    bar_y = y0 + 2 * (tile_h + gap) + gap * 0.4
    d.rounded_rectangle([x0, bar_y, x0 + box, bar_y + tile * 0.42], radius=tile * 0.21, fill=(255, 255, 255, 255))
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    draw_icon(192).save(OUT / "icon-192.png")
    draw_icon(512).save(OUT / "icon-512.png")
    draw_icon(512, maskable=True).save(OUT / "icon-maskable-512.png")
    # iPadOS rounds Home Screen icons itself, so the touch icon is a full square.
    draw_icon(180, rounded=False).convert("RGB").save(OUT / "apple-touch-icon.png")
    draw_icon(256).save(OUT / "paddock.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    draw_icon(64).save(OUT / "favicon.png")
    # macOS: menu bar icon (22 pt @2x) and the app icon
    draw_icon(44).save(OUT / "menubar.png")
    draw_icon(1024).save(OUT / "paddock.icns", sizes=[(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)])
    print("Icons written to", OUT)


if __name__ == "__main__":
    main()
