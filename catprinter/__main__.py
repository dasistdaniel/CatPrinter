"""python -m catprinter [serve|tray|status|test|image DATEI|calibrate WERTE...] [--verbose] [--port COMx]"""
import argparse
import logging
import sys

from PIL import Image

from .pages import calibration_page, test_page
from .printer import DEFAULT_DENSITY, Printer, PrinterError, build_job, prepare
from .server import CONFIG_DIR, CONFIG_FILE, load_config, serve


def main():
    ap = argparse.ArgumentParser(prog="catprinter")
    ap.add_argument("command", nargs="?", default="serve",
                    choices=["serve", "tray", "status", "test", "image", "calibrate"])
    ap.add_argument("file", nargs="*", help="Bilddatei (image) bzw. Dichtewerte (calibrate)")
    ap.add_argument("--density", type=int, help="Druckdichte für test/image")
    ap.add_argument("--mode", choices=["auto", "text", "photo"], help="Bildmodus für test/image")
    ap.add_argument("--chunk-delay", type=float, metavar="MS", help="Pause je 256 Bytes in ms (Test)")
    ap.add_argument("--port", help="COM-Port (Standard: automatisch)")
    ap.add_argument("--verbose", "-v", action="store_true")
    ap.add_argument("--save-jobs", metavar="ORDNER", help="Empfangene Aufträge zur Analyse speichern")
    ap.add_argument("--log-file", metavar="DATEI", help="Log in eine Datei schreiben (nötig mit pythonw)")
    args = ap.parse_args()

    if args.command == "tray" and not args.log_file:
        # Tray läuft ohne Konsole (pythonw) – ohne Datei ginge das Log verloren
        import os
        os.makedirs(CONFIG_DIR, exist_ok=True)
        args.log_file = os.path.join(CONFIG_DIR, "server.log")
    log_kwargs = {"filename": args.log_file, "encoding": "utf-8"} if args.log_file else {}
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S", **log_kwargs)
    cfg = load_config()
    if args.port:
        cfg["com_port"] = args.port

    if args.command == "tray":
        from .tray import TrayApp  # pystray nur laden, wenn gebraucht
        logging.info("Konfiguration: %s", CONFIG_FILE)
        return TrayApp(args.save_jobs).run()

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
    mode = args.mode or cfg.get("image_mode", "auto")
    try:
        if args.command == "status":
            print(printer.status(), "auf", printer.port)
        elif args.command == "test":
            printer.print_images([prepare(test_page(), rotate=rotate, mode=mode)], feed, density)
        elif args.command == "image":
            if len(args.file) != 1:
                ap.error("genau eine Bilddatei angeben")
            printer.print_images([prepare(Image.open(args.file[0]), rotate=rotate, mode=mode)], feed, density)
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
