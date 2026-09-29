"""Erzeugt packaging/CatPrinter.ico aus dem Logo (mehrere Größen)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from catprinter import logo  # noqa: E402

SIZES = [16, 24, 32, 48, 64, 128, 256]


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "CatPrinter.ico")
    # Kleine Größen bekommen die vereinfachte Kleinversion
    images = [logo.draw(size) for size in SIZES]
    images[-1].save(out, sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print("Icon:", out)
