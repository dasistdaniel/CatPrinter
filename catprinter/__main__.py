"""python -m catprinter [serve|status|test|image DATEI|calibrate WERTE...] [--verbose] [--port COMx]"""
import argparse
import logging
import sys

from PIL import Image, ImageDraw, ImageFont

from .printer import DEFAULT_DENSITY, WIDTH, Printer, PrinterError, build_job, prepare
from .server import CONFIG_FILE, load_config, serve


def _fonts():
    try:
        return ImageFont.truetype("arial.ttf", 34), ImageFont.truetype("arial.ttf", 20)
    except OSError:
        return ImageFont.load_default(), ImageFont.load_default()


def calibration_page(density):
    """Beschriftung, schwarzer Block, 50-%-Raster und feine Linien für eine Dichtestufe."""
    big, small = _fonts()
    img = Image.new("L", (WIDTH, 250), 255)
    d = ImageDraw.Draw(img)
    d.text((8, 4), f"Dichte {density}", font=big, fill=0)
    d.rectangle([0, 50, WIDTH - 1, 150], fill=0)
    d.rectangle([0, 160, WIDTH - 1, 200], fill=128)
    for x in range(0, WIDTH, 6):
        d.line([(x, 210), (x, 245)], fill=0)
    return img


def test_page():
    img = Image.new("L", (WIDTH, 900), 255)
    d = ImageDraw.Draw(img)
    try:
        big, small = ImageFont.truetype("arial.ttf", 34), ImageFont.truetype("arial.ttf", 20)
    except OSError:
        big = small = ImageFont.load_default()
    d.rectangle([0, 0, WIDTH - 1, img.height - 1], outline=0, width=3)
    d.text((16, 16), "Testseite", font=big, fill=0)
    y = 70
    for i in range(24):
        d.text((16, y), f"Zeile {i + 1:02d}: Das ist ein langer Testdruck", font=small, fill=0)
        y += 26
    for x in range(WIDTH - 32):
        d.line([(16 + x, y + 10), (16 + x, y + 60)], fill=int(255 * x / (WIDTH - 33)))
    d.text((16, img.height - 40), "ENDE", font=small, fill=0)
    return img


def main():
    ap = argparse.ArgumentParser(prog="catprinter")
    ap.add_argument("command", nargs="?", default="serve",
                    choices=["serve", "status", "test", "image", "calibrate"])
    ap.add_argument("file", nargs="*", help="Bilddatei (image) bzw. Dichtewerte (calibrate)")
    ap.add_argument("--density", type=int, help="Druckdichte für test/image")
    ap.add_argument("--chunk-delay", type=float, metavar="MS", help="Pause je 256 Bytes in ms (Test)")
    ap.add_argument("--port", help="COM-Port (Standard: automatisch)")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--save-jobs", metavar="ORDNER", help="Empfangene Aufträge zur Analyse speichern")
    ap.add_argument("--log-file", metavar="DATEI", help="Log in eine Datei schreiben (nötig mit pythonw)")
    args = ap.parse_args()

    log_kwargs = {"filename": args.log_file, "encoding": "utf-8"} if args.log_file else {}
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", **log_kwargs)
    cfg = load_config()
    if args.port:
        cfg["com_port"] = args.port

    if args.command == "serve":
        logging.info("Konfiguration: %s", CONFIG_FILE)
        try:
            httpd, _service = serve(cfg, args.save_jobs)
        except OSError as e:
            logging.error("Port %d ist belegt – läuft der Server schon? (%s)", cfg["http_port"], e)
            return 1
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
        return 0

    printer = Printer(cfg.get("com_port"), cfg.get("bluetooth_name", "YHK-"))
    if args.chunk_delay is not None:
        printer.chunk_delay = args.chunk_delay / 1000
    density = args.density if args.density is not None else cfg.get("density", DEFAULT_DENSITY)
    feed = cfg.get("feed_mm", 15)
    rotate = cfg.get("rotate_180", True)
    try:
        if args.command == "status":
            print(printer.status(), "auf", printer.port)
        elif args.command == "test":
            printer.print_images([prepare(test_page(), rotate=rotate)], feed, density)
        elif args.command == "image":
            if len(args.file) != 1:
                ap.error("genau eine Bilddatei angeben")
            printer.print_images([prepare(Image.open(args.file[0]), rotate=rotate)], feed, density)
        elif args.command == "calibrate":
            values = [int(v) for v in args.file] or [15, 25, 40]
            # Alle Stufen über eine Verbindung; jede mit eigenem Dichtebefehl,
            # aber nur ein ESC @ am Anfang (sonst wird der Puffer verworfen)
            job = b"".join(
                build_job([prepare(calibration_page(v), trim=False, rotate=rotate)],
                          feed if i == len(values) - 1 else 2, v, init=(i == 0))
                for i, v in enumerate(values))
            printer.send(job)
    except PrinterError as e:
        print("Fehler:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
