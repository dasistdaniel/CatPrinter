"""PWG-Raster (PWG 5102.4) dekodieren – das Seitenformat, das der
Windows-IPP-Klassentreiber schickt. Ein Encoder ist für Tests dabei.
"""
import struct

from PIL import Image

SYNC = b"RaS2"
HEADER_SIZE = 1796

CS_BLACK = 3   # 1 = schwarz
CS_SGRAY = 18  # 255 = weiß
CS_SRGB = 19
CS_RGB = 1
CS_WHITE = 0   # Graustufen, 255 = weiß (wie sgray)


class PageHeader:
    def __init__(self, raw):
        u32 = lambda off: struct.unpack(">I", raw[off:off + 4])[0]
        self.hw_resolution = (u32(276), u32(280))
        self.page_size_pt = (u32(352), u32(356))
        self.width = u32(372)
        self.height = u32(376)
        self.bits_per_color = u32(384)
        self.bits_per_pixel = u32(388)
        self.bytes_per_line = u32(392)
        self.color_order = u32(396)
        self.color_space = u32(400)
        self.num_colors = u32(420)
        self.media_type = raw[128:192].split(b"\x00", 1)[0].decode("ascii", "replace")

    def __repr__(self):
        return (f"<Seite {self.width}x{self.height} px, {self.hw_resolution[0]}x{self.hw_resolution[1]} dpi, "
                f"{self.bits_per_pixel} bpp, Farbraum {self.color_space}>")


def _decode_page(data, pos, hdr):
    bpl = hdr.bytes_per_line
    unit = max(1, hdr.bits_per_pixel // 8)
    white = 0x00 if hdr.color_space == CS_BLACK else 0xFF
    out = bytearray()
    rows = 0
    while rows < hdr.height:
        repeat = data[pos] + 1
        pos += 1
        line = bytearray()
        while len(line) < bpl:
            n = data[pos]
            pos += 1
            if n == 0x80:
                line.extend(bytes([white]) * (bpl - len(line)))
            elif n < 0x80:
                px = data[pos:pos + unit]
                pos += unit
                line.extend(px * (n + 1))
            else:
                count = (257 - n) * unit
                line.extend(data[pos:pos + count])
                pos += count
        del line[bpl:]
        repeat = min(repeat, hdr.height - rows)
        out.extend(bytes(line) * repeat)
        rows += repeat
    return bytes(out), pos


def _to_image(hdr, pixels):
    w, h = hdr.width, hdr.height
    if hdr.color_space == CS_BLACK and hdr.bits_per_pixel == 1:
        # PIL-Modus "1": gesetztes Bit = weiß, also invertieren
        inverted = bytes(b ^ 0xFF for b in pixels)
        return Image.frombytes("1", (w, h), inverted, "raw", "1", hdr.bytes_per_line)
    if hdr.bits_per_pixel == 8:
        img = Image.frombytes("L", (w, h), pixels, "raw", "L", hdr.bytes_per_line)
        if hdr.color_space == CS_BLACK:
            img = img.point(lambda v: 255 - v)
        return img
    if hdr.bits_per_pixel == 24:
        return Image.frombytes("RGB", (w, h), pixels, "raw", "RGB", hdr.bytes_per_line).convert("L")
    if hdr.bits_per_pixel == 16 and hdr.color_space in (CS_SGRAY, CS_WHITE):
        img = Image.frombytes("I;16B", (w, h), pixels, "raw", "I;16B", hdr.bytes_per_line)
        return img.point(lambda v: v / 257).convert("L")
    raise ValueError(f"Nicht unterstütztes PWG-Format: {hdr!r}")


def decode(data):
    """Liefert eine Liste von (PageHeader, PIL-Bild im Modus 'L' oder '1')."""
    if data[:4] != SYNC:
        raise ValueError("Kein PWG-Raster (RaS2 fehlt)")
    pages = []
    pos = 4
    while pos + HEADER_SIZE <= len(data):
        hdr = PageHeader(data[pos:pos + HEADER_SIZE])
        pos += HEADER_SIZE
        pixels, pos = _decode_page(data, pos, hdr)
        pages.append((hdr, _to_image(hdr, pixels)))
    return pages


# ---------------------------------------------------------------- Encoder (Tests)

def _compress_line(line, unit):
    out = bytearray()
    pixels = [line[i:i + unit] for i in range(0, len(line), unit)]
    i = 0
    while i < len(pixels):
        j = i + 1
        while j < len(pixels) and pixels[j] == pixels[i] and j - i < 128:
            j += 1
        if j - i > 1:
            out.append(j - i - 1)
            out.extend(pixels[i])
            i = j
            continue
        j = i + 1
        while j < len(pixels) and j - i < 128 and (j + 1 >= len(pixels) or pixels[j] != pixels[j + 1]):
            j += 1
        # Ein einzelnes Pixel ist ein "Lauf" der Länge 1 (Zähler 0)
        out.append(0 if j - i == 1 else 257 - (j - i))
        for p in pixels[i:j]:
            out.extend(p)
        i = j
    return out


def encode(img, dpi=203, gray=True):
    """Kodiert ein PIL-Bild als einseitiges PWG-Raster (sgray_8 oder black_1)."""
    if gray:
        img = img.convert("L")
        bpp, cs, bpl = 8, CS_SGRAY, img.width
        raw = img.tobytes()
    else:
        img = img.convert("1")
        bpp, cs, bpl = 1, CS_BLACK, (img.width + 7) // 8
        raw = bytes(b ^ 0xFF for b in img.tobytes("raw", "1"))
    hdr = bytearray(HEADER_SIZE)
    put = lambda off, v: struct.pack_into(">I", hdr, off, v)
    put(276, dpi); put(280, dpi)
    put(352, round(img.width * 72 / dpi)); put(356, round(img.height * 72 / dpi))
    put(372, img.width); put(376, img.height)
    put(384, bpp); put(388, bpp); put(392, bpl); put(400, cs); put(420, 1)
    out = bytearray(SYNC + bytes(hdr))
    y = 0
    while y < img.height:
        line = raw[y * bpl:(y + 1) * bpl]
        rep = 1
        while y + rep < img.height and rep < 256 and raw[(y + rep) * bpl:(y + rep + 1) * bpl] == line:
            rep += 1
        out.append(rep - 1)
        out.extend(_compress_line(line, max(1, bpp // 8)))
        y += rep
    return bytes(out)
