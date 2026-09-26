"""Erzeugt packaging/CatPrinter.ico aus dem Tray-Symbol (mehrere Größen)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from PIL import Image, ImageDraw  # noqa: E402


def cat(size):
    """Katzengesicht ohne Statuspunkt, wie im Tray, in beliebiger Größe."""
    s = size / 64
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fur, line = (250, 250, 250, 255), (60, 60, 60, 255)
    w = max(1, round(2.5 * s))
    p = lambda pts: [(x * s, y * s) for x, y in pts]
    d.polygon(p([(8, 26), (12, 4), (26, 16)]), fill=fur, outline=line, width=w)
    d.polygon(p([(56, 26), (52, 4), (38, 16)]), fill=fur, outline=line, width=w)
    d.rounded_rectangle([6 * s, 14 * s, 58 * s, 56 * s], radius=16 * s, fill=fur, outline=line, width=w)
    d.ellipse([17 * s, 28 * s, 25 * s, 36 * s], fill=line)
    d.ellipse([39 * s, 28 * s, 47 * s, 36 * s], fill=line)
    d.ellipse([10 * s, 37 * s, 18 * s, 42 * s], fill=(236, 138, 156, 160))
    d.ellipse([46 * s, 37 * s, 54 * s, 42 * s], fill=(236, 138, 156, 160))
    d.arc([24 * s, 36 * s, 40 * s, 48 * s], start=20, end=160, fill=line, width=w)
    return img


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "CatPrinter.ico")
    big = cat(256)
    big.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("Icon:", out)
