"""Einstiegspunkt für die exe (PyInstaller kann __main__.py mit relativen Imports nicht direkt nutzen)."""
import os
import sys


def _portable_home():
    """Portable Variante: Datei "portable" neben der exe oder "portable" im Dateinamen.

    Dann liegen Einstellungen, Log und Verlauf in CatPrinterData neben der exe.
    """
    exe = os.path.abspath(sys.executable)
    folder = os.path.dirname(exe)
    marker = any(os.path.exists(os.path.join(folder, n)) for n in ("portable", "portable.txt"))
    if marker or "portable" in os.path.basename(exe).lower():
        return os.path.join(folder, "CatPrinterData")
    return None


if __name__ == "__main__":
    home = _portable_home() if getattr(sys, "frozen", False) else None
    if home:
        # Muss vor dem Import von catprinter gesetzt sein (CONFIG_DIR wird beim Import festgelegt)
        os.environ["CATPRINTER_HOME"] = home
        os.environ["CATPRINTER_PORTABLE"] = "1"

    from catprinter.__main__ import main

    sys.exit(main())
