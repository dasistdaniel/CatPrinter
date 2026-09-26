"""Einstiegspunkt für die exe (PyInstaller kann __main__.py mit relativen Imports nicht direkt nutzen)."""
import sys

from catprinter.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
