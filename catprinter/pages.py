"""Test- und Kalibrierseiten."""
import time

from PIL import Image, ImageDraw, ImageFont

from .i18n import t
from .printer import WIDTH


def _fonts():
    try:
        return ImageFont.truetype("arial.ttf", 34), ImageFont.truetype("arial.ttf", 20)
    except OSError:
        return ImageFont.load_default(), ImageFont.load_default()


def calibration_page(density):
    """Beschriftung, schwarzer Block, 50-%-Raster und feine Linien für eine Dichtestufe."""
    big, _small = _fonts()
    img = Image.new("L", (WIDTH, 250), 255)
    d = ImageDraw.Draw(img)
    d.text((8, 4), t("density_label", d=density), font=big, fill=0)
    d.rectangle([0, 50, WIDTH - 1, 150], fill=0)
    d.rectangle([0, 160, WIDTH - 1, 200], fill=128)
    for x in range(0, WIDTH, 6):
        d.line([(x, 210), (x, 245)], fill=0)
    return img


def test_page():
    """Lange Testseite: viele Textzeilen, Graustufenverlauf, "ENDE" am Schluss."""
    big, small = _fonts()
    img = Image.new("L", (WIDTH, 900), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH - 1, img.height - 1], outline=0, width=3)
    d.text((16, 16), t("test_page"), font=big, fill=0)
    y = 70
    for i in range(24):
        d.text((16, y), t("test_line", n=i + 1), font=small, fill=0)
        y += 26
    for x in range(WIDTH - 32):
        d.line([(16 + x, y + 10), (16 + x, y + 60)], fill=int(255 * x / (WIDTH - 33)))
    d.text((16, img.height - 40), t("test_end"), font=small, fill=0)
    return img


def short_test_page(info=""):
    """Kurze Testseite für das Tray-Menü (spart Papier)."""
    big, small = _fonts()
    img = Image.new("L", (WIDTH, 170), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, WIDTH - 1, img.height - 1], outline=0, width=3)
    d.text((14, 12), "Cat Printer", font=big, fill=0)
    d.text((14, 58), time.strftime(t("test_page_short")), font=small, fill=0)
    if info:
        d.text((14, 86), info, font=small, fill=0)
    for x in range(WIDTH - 28):
        d.line([(14 + x, 120), (14 + x, 155)], fill=int(255 * x / (WIDTH - 29)))
    return img
