"""Das Cat-Printer-Logo (Kassenbon mit Katzenohren) als Pillow-Bild.

Die Formen entsprechen docs/logo/catprinter-symbol.svg (Raster 256×256, Bon von
x 64–192, y 28–232). Unter 48 px wird die Kleinversion mit größeren Augen,
einer Druckzeile und gröberen Zähnen gezeichnet.
"""
from PIL import Image, ImageDraw

ROSE = (201, 79, 104)      # #C94F68
INK = (34, 37, 43)         # #22252B
WHITE = (255, 255, 255)

SUPERSAMPLE = 4


def _outline(small):
    """Umriss des Bons: Ohren oben, gezackte Abrisskante unten."""
    dip = 62 if small else 61
    top = [(64, 40), (66, 32), (72, 33), (100 if small else 102, dip - 3), (108, dip), (148, dip),
           (156 if small else 154, dip - 3), (184, 33), (190, 32), (192, 40)]
    depth = 212 if small else 216
    teeth = [(192, 232)]
    for i, x in enumerate(range(176, 63, -16)):
        teeth.append((x, depth if i % 2 == 0 else 232))
    teeth.append((64, 232))
    return top + teeth


def _features(small):
    if small:
        return [(100, 116, 20), (156, 116, 20)], [(88, 164, 168, 184)]
    return [(104, 110, 14), (152, 110, 14)], [(88, 150, 168, 164), (88, 178, 144, 192)]


def draw(size, color=ROSE, features=WHITE, small=None, box=None):
    """Logo als RGBA-Bild der Größe size×size.

    features=None stanzt Augen und Druckzeilen aus (transparent). box=(x0, y0, x1, y1)
    legt fest, in welchen Teil des 256er-Rasters das Bild blickt (Standard: Bon zentriert).
    """
    if small is None:
        small = size < 48
    x0, y0, x1, y1 = box or (20, 22, 236, 238)
    big = size * SUPERSAMPLE
    sx, sy = big / (x1 - x0), big / (y1 - y0)
    p = lambda x, y: ((x - x0) * sx, (y - y0) * sy)
    mask = Image.new("L", (big, big), 0)
    d = ImageDraw.Draw(mask)
    d.polygon([p(x, y) for x, y in _outline(small)], fill=255)
    holes = Image.new("L", (big, big), 0)
    h = ImageDraw.Draw(holes)
    eyes, lines = _features(small)
    for cx, cy, r in eyes:
        h.ellipse([*p(cx - r, cy - r), *p(cx + r, cy + r)], fill=255)
    for a, b, c, e in lines:
        h.rectangle([*p(a, b), *p(c, e)], fill=255)
    img = Image.new("RGBA", (big, big), color + (0,))
    img.paste(Image.new("RGBA", (big, big), color + (255,)), mask=mask)
    if features is None:
        alpha = img.getchannel("A")
        alpha.paste(0, mask=holes)
        img.putalpha(alpha)
    else:
        img.paste(Image.new("RGBA", (big, big), features + (255,)), mask=holes)
    return img.resize((size, size), Image.LANCZOS)
