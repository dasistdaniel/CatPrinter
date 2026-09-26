"""Virtueller IPP-Drucker: nimmt Druckaufträge von Windows entgegen und
gibt sie auf dem Thermodrucker aus."""
import io
import itertools
import json
import logging
import os
import queue
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image

from . import ipp, netshare, pwg, statuspage
from .pages import calibration_page, short_test_page
from .history import History
from .printer import (DEFAULT_DENSITY, DPI, MODES, Printer, PrinterError, is_photo_page, photo_brightness,
                      prepare, scale_to_width, windows_tone)

log = logging.getLogger("server")

# Portable Variante: Einstellungen neben der exe (setzt packaging/launcher.py)
CONFIG_DIR = os.environ.get("CATPRINTER_HOME") or os.path.join(
    os.environ.get("APPDATA", os.path.expanduser("~")), "CatPrinterDriver")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

DEFAULT_CONFIG = {
    "http_host": "127.0.0.1",
    "http_port": 631,
    "com_port": None,          # None = automatisch über den Bluetooth-Namen suchen
    "bluetooth_name": "YHK-",
    "feed_mm": 15,
    "density": DEFAULT_DENSITY,  # Druckdichte/Heizstärke (1D 49 F0 n)
    "trim_bottom": True,
    "rotate_180": True,        # Ausdruck aus Sicht des Drucker-Gesichts lesbar
    "image_mode": "auto",      # Modus bei Druckqualität "Normal": auto, text oder photo
    "keep_history": False,     # Kopien gedruckter Seiten aufbewahren (Datenschutz: standardmäßig aus)
    "share_network": False,    # im Heimnetz freigeben (Drucken vom Handy), standardmäßig aus
    "match_windows_tone": True,  # Fotos vom Handy wie Windows aufhellen (gleiches Ergebnis wie vom PC)
    "photo_brightness": 0,     # Foto-Helligkeit in Prozent (-30 … +50), nur Fotos
    "printer_name": "Cat Printer",
}

# Papiergrößen in 1/100 mm (Breite = bedruckbare 48 mm, ohne Ränder).
# Größere Formate werden auf 48 mm Breite verkleinert.
MEDIA = [
    ("om_roll-40_48x40mm", 4800, 4000),
    ("om_roll-80_48x80mm", 4800, 8000),
    ("om_roll-150_48x150mm", 4800, 15000),
    ("om_roll-300_48x300mm", 4800, 30000),
    ("iso_a6_105x148mm", 10500, 14800),
    ("iso_a4_210x297mm", 21000, 29700),
    ("na_letter_8.5x11in", 21590, 27940),
]
DEFAULT_MEDIA = MEDIA[1]

FORMATS = ["image/pwg-raster", "application/octet-stream"]

# Job-Zustände
PENDING, PROCESSING, CANCELED, ABORTED, COMPLETED = 3, 5, 7, 8, 9
STATE_REASON = {PENDING: "none", PROCESSING: "job-printing", CANCELED: "job-canceled-by-user",
                ABORTED: "aborted-by-system", COMPLETED: "job-completed-successfully"}


def validate_settings(changes):
    """Prüft Änderungen von der Statusseite. Gibt bereinigte Werte zurück, sonst ValueError."""
    clean = {}
    for key, value in changes.items():
        if key == "density":
            if isinstance(value, bool) or not isinstance(value, int) or not 5 <= value <= 80:
                raise ValueError("Druckdichte muss eine ganze Zahl von 5 bis 80 sein")
        elif key == "feed_mm":
            if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 50:
                raise ValueError("Vorschub muss eine ganze Zahl von 0 bis 50 mm sein")
        elif key == "photo_brightness":
            if isinstance(value, bool) or not isinstance(value, int) or not -30 <= value <= 50:
                raise ValueError("Foto-Helligkeit muss eine ganze Zahl von -30 bis 50 sein")
        elif key == "image_mode":
            if value not in MODES:
                raise ValueError("Unbekannter Bildmodus")
        elif key in ("rotate_180", "trim_bottom", "keep_history", "share_network", "match_windows_tone"):
            if not isinstance(value, bool):
                raise ValueError(f"{key} muss true oder false sein")
        elif key == "com_port":
            value = (value or "").strip().upper() or None
            if value is not None and not (value.startswith("COM") and value[3:].isdigit()):
                raise ValueError("COM-Port muss wie COM13 aussehen oder leer sein (automatisch)")
        elif key == "bluetooth_name":
            value = str(value).strip()
            if not 1 <= len(value) <= 32:
                raise ValueError("Bluetooth-Name darf nicht leer sein")
        else:
            raise ValueError(f"Einstellung {key} kann hier nicht geändert werden")
        clean[key] = value
    return clean


def image_mode(quality, default="auto"):
    """Druckqualität aus dem Windows-Dialog -> Bildmodus."""
    if quality == 3:
        return "text"   # Entwurf: harte Schwelle
    if quality == 5:
        return "photo"  # Hoch: alles rastern
    return default if default in MODES else "auto"


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg.update(json.load(f))
    except FileNotFoundError:
        pass
    if not cfg.get("uuid"):
        # Einmal erzeugen und behalten, sonst hält Windows den Drucker für ein neues Gerät.
        # Portable: die ID einer vorhandenen Installation übernehmen (gleicher Windows-Drucker)
        cfg["uuid"] = _installed_uuid() or str(uuid.uuid4())
        save_config(cfg)
    return cfg


def _installed_uuid():
    default = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "CatPrinterDriver", "config.json")
    if os.path.normcase(default) == os.path.normcase(CONFIG_FILE):
        return None
    try:
        with open(default, encoding="utf-8") as f:
            return json.load(f).get("uuid")
    except (OSError, ValueError):
        return None


def save_config(cfg, path=None):
    path = path or CONFIG_FILE
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    os.replace(tmp, path)  # nie eine halb geschriebene Datei hinterlassen


class Job:
    def __init__(self, job_id, name, user, copies):
        self.id = job_id
        self.name = name
        self.user = user
        self.copies = copies
        self.state = PENDING
        self.message = ""
        self.created = int(time.time())
        self.processing = 0
        self.completed = 0
        self.pages = 0
        self.data = None
        self.quality = None  # IPP print-quality: 3 = Entwurf, 4 = Normal, 5 = Hoch
        self.density = None  # abweichende Druckdichte (Probedruck), sonst aus der Konfiguration
        self.images = None   # fertige Seitenbilder statt Dokumentdaten (Nachdruck aus dem Verlauf)
        self.from_network = False  # kam vom Handy/aus dem Heimnetz (nicht über Windows)
        self.internal = False  # Test-/Probe-/Nachdruck: nicht im Verlauf speichern
        self.history_id = None


class PrintService:
    def __init__(self, cfg, save_jobs_dir=None, config_file=None):
        self.config_file = config_file or CONFIG_FILE
        self.cfg = cfg
        self.printer = Printer(cfg.get("com_port"), cfg.get("bluetooth_name", "YHK-"))
        self.jobs = {}
        self.ids = itertools.count(1)
        self.lock = threading.Lock()
        self.queue = queue.Queue()
        self.start_time = int(time.time())
        self.last_error = None
        self.save_jobs_dir = save_jobs_dir
        self.listeners = []   # Callbacks listener(event, **daten), z. B. für das Tray-Icon
        self.status = {}      # zuletzt gemeldeter Druckerstatus (Firmware, VOLT, …)
        self.active = False   # gerade am Drucken?
        self.checking = False # Akkuabfrage läuft?
        self.cooling = False  # Drucker zu heiß, wartet/pausiert
        self.printed = 0      # erfolgreich gedruckte Aufträge seit dem Start
        self.net_status = {}  # Netzwerkfreigabe: Adressen, Firewall, Netzwerkprofil (setzt das Tray)
        self.history = History(os.path.join(os.path.dirname(self.config_file), "history"))
        self._stopped = False
        threading.Thread(target=self._worker, daemon=True).start()

    def emit(self, event, **data):
        for listener in list(self.listeners):
            try:
                listener(event, **data)
            except Exception:  # noqa: BLE001 – ein fehlerhafter Listener darf den Druck nicht stören
                log.exception("Fehler im Listener für %s", event)

    def run_task(self, fn):
        """Führt fn im Druck-Thread aus – so greift nie mehr als einer gleichzeitig auf den COM-Port zu."""
        self.queue.put(fn)

    def refresh_status(self):
        def task():
            try:
                self.status = self.printer.status()
                self.last_error = None
                self.emit("status", status=self.status)
            except PrinterError as e:
                self.last_error = (time.time(), str(e))
                self.emit("status_failed", error=str(e))
            finally:
                self.checking = False
        if not self.checking:
            self.checking = True
            self.run_task(task)

    def print_image(self, name, img, density=None):
        """Druckt ein PIL-Bild über die normale Auftragsverarbeitung (z. B. Testseite)."""
        buf = io.BytesIO()
        img.save(buf, "PNG")
        job = self.new_job(name, "CatPrinterDriver", 1)
        job.density = density
        job.internal = True
        self.submit(job, buf.getvalue())
        return job

    def reprint(self, hid):
        """Druckt einen Auftrag aus dem Verlauf erneut (mit den aktuellen Einstellungen)."""
        meta = self.history.meta(hid)
        job = self.new_job(f"{meta['name']} (erneut)", "CatPrinterDriver", 1)
        job.quality = meta.get("quality")
        job.from_network = meta.get("network", False)  # Handy-Fotos auch beim Nachdruck aufhellen
        job.internal = True
        self.submit(job, images=self.history.pages(hid))
        return job

    def update_settings(self, changes):
        """Übernimmt geprüfte Einstellungen sofort und speichert sie in config.json."""
        clean = validate_settings(changes)
        share_changed = "share_network" in clean and clean["share_network"] != bool(self.cfg.get("share_network"))
        if clean.get("keep_history") is False and self.cfg.get("keep_history"):
            self.history.clear()  # Datenschutz: ausschalten = alles Gespeicherte löschen
            log.info("Verlauf ausgeschaltet und gelöscht")
        self.cfg.update(clean)
        if "com_port" in clean or "bluetooth_name" in clean:
            # Leerer Port = beim nächsten Druck neu suchen
            self.printer.port = self.cfg.get("com_port")
            self.printer.name_prefix = self.cfg.get("bluetooth_name", "YHK-")
        save_config(self.cfg, self.config_file)
        log.info("Einstellungen geändert: %s", clean)
        self.emit("settings", changes=clean)
        if share_changed:
            # Braucht einen Server-Neustart (andere Adresse) – erst nach der HTTP-Antwort
            threading.Timer(0.5, self.emit, args=("share_changed",),
                            kwargs={"enabled": clean["share_network"]}).start()
        return clean

    def stop(self):
        self._stopped = True
        self.queue.put(None)

    def uptime(self):
        return max(1, int(time.time()) - self.start_time)

    def new_job(self, name, user, copies):
        with self.lock:
            job = Job(next(self.ids), name, user, copies)
            self.jobs[job.id] = job
            # Nur die letzten 50 Aufträge merken
            for old in sorted(self.jobs)[:-50]:
                del self.jobs[old]
        return job

    def submit(self, job, data=b"", images=None):
        job.data = data
        job.images = images
        self.queue.put(job)

    def busy(self):
        return any(j.state in (PENDING, PROCESSING) and j.data is not None for j in list(self.jobs.values()))

    def _worker(self):
        while True:
            job = self.queue.get()
            if job is None or self._stopped:
                return
            if callable(job):
                try:
                    job()
                except Exception:  # noqa: BLE001
                    log.exception("Fehler in Hintergrundaufgabe")
                continue
            if job.state == CANCELED:
                continue
            job.state = PROCESSING
            job.processing = self.uptime()
            self.active = True
            self.emit("job_started", job=job)
            try:
                self._print(job)
                job.state = COMPLETED
                self.printed += 1
                self.last_error = None
                log.info("Auftrag %d '%s' gedruckt (%d Seite(n))", job.id, job.name, job.pages)
                if self.printer.last_status:
                    self.status = self.printer.last_status
                self.emit("job_done", job=job, status=self.status)
            except Exception as e:  # noqa: BLE001 – jeder Fehler bricht nur diesen Auftrag ab
                job.state = ABORTED
                job.message = str(e)
                self.last_error = (time.time(), str(e))
                log.error("Auftrag %d abgebrochen: %s", job.id, e,
                          exc_info=not isinstance(e, PrinterError))
                self.emit("job_failed", job=job, error=str(e))
            finally:
                self.active = False
                job.completed = self.uptime()
                job.data = job.images = None
                if job.history_id:
                    self.history.set_state(job.history_id, "done" if job.state == COMPLETED else "failed")

    def _print(self, job):
        pages = job.images or self._decode(job)
        if self.cfg.get("keep_history") and not job.internal:
            try:
                job.history_id = self.history.add(job.name, [scale_to_width(p) for p in pages], job.quality,
                                                  network=job.from_network)
            except OSError:
                log.exception("Auftrag konnte nicht im Verlauf gespeichert werden")
        rotate = self.cfg.get("rotate_180", True)
        mode = image_mode(job.quality, self.cfg.get("image_mode", "auto"))
        log.info("  Bildmodus: %s (Druckqualität %s)%s", mode, job.quality,
                 ", vom Netzwerk" if job.from_network else "")
        pages = [self._tone(p, mode, job.from_network) for p in pages]
        images = [prepare(p, self.cfg.get("trim_bottom", True), rotate, mode) for p in pages]
        if rotate:
            # Gedreht kommt das Seitenende zuerst – bei mehreren Seiten also
            # mit der letzten beginnen, damit der Streifen von oben nach unten lesbar bleibt
            images.reverse()
        images = images * max(1, job.copies)
        job.pages = len(images)
        density = job.density or self.cfg.get("density", DEFAULT_DENSITY)
        try:
            self.printer.print_images(images, self.cfg.get("feed_mm", 15), density, notify=self._heat_event)
        finally:
            self.cooling = False

    def _heat_event(self, kind):
        """Hitzeschutz des Druckers: "cooling" (wartet vor dem Druck), "paused_hot", "cooled"."""
        if kind in ("cooling", "paused_hot"):
            self.cooling = True
            self.emit("hot", waiting=kind == "cooling")
        elif kind == "cooled":
            self.cooling = False
            self.emit("cooled")

    def _tone(self, page, mode, from_network):
        """Tonwerte von Fotos anpassen (nur Fotos – Text und Grafik bleiben unverändert).

        - Fotos vom Handy wie Windows aufhellen, damit sie gleich aussehen wie vom PC
        - Foto-Helligkeit aus den Einstellungen (Thermopunkte laufen etwas aus)
        """
        match = from_network and self.cfg.get("match_windows_tone", True)
        brightness = self.cfg.get("photo_brightness", 0)
        if not match and not brightness:
            return page
        if not (mode == "photo" or (mode == "auto" and is_photo_page(page))):
            return page
        if match:
            log.info("  Foto vom Netzwerk: Tonwerte wie unter Windows angepasst")
            page = windows_tone(page)
        if brightness:
            page = photo_brightness(page, brightness)
        return page

    def _decode(self, job):
        data = job.data
        if self.save_jobs_dir:
            os.makedirs(self.save_jobs_dir, exist_ok=True)
            with open(os.path.join(self.save_jobs_dir, f"job{job.id}.bin"), "wb") as f:
                f.write(data)
        if data[:4] == pwg.SYNC:
            pages = []
            for hdr, img in pwg.decode(data):
                log.info("  %r", hdr)
                pages.append(img)
            return pages
        return [Image.open(io.BytesIO(data))]  # PNG/JPEG direkt (auch Testseite aus dem Tray)

    def preview(self, hid, number, thumb=False):
        """Verlaufsseite so, wie sie gedruckt würde (1 Bit, ungedreht), als PNG.

        thumb=True liefert eine kleine Graustufen-Miniatur – ein verkleinertes
        Punktraster wäre nur Rauschen.
        """
        meta = self.history.meta(hid)
        page = self.history.page(hid, number)
        if thumb:
            img = page.copy()
            img.thumbnail((128, 256))
        else:
            mode = image_mode(meta.get("quality"), self.cfg.get("image_mode", "auto"))
            page = self._tone(page, mode, meta.get("network", False))
            img = prepare(page, self.cfg.get("trim_bottom", True), False, mode)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


# ---------------------------------------------------------------- IPP-Attribute

def _col(*attrs):
    return list(attrs)


def _media_col(name, x, y):
    return _col(
        ("media-size", ipp.BEGIN_COLLECTION, [_col(("x-dimension", ipp.INTEGER, [x]),
                                                  ("y-dimension", ipp.INTEGER, [y]))]),
        ("media-size-name", ipp.KEYWORD, [name]),
        ("media-bottom-margin", ipp.INTEGER, [0]),
        ("media-left-margin", ipp.INTEGER, [0]),
        ("media-right-margin", ipp.INTEGER, [0]),
        ("media-top-margin", ipp.INTEGER, [0]),
        ("media-source", ipp.KEYWORD, ["main"]),
        ("media-type", ipp.KEYWORD, ["stationery"]),
    )


def printer_attributes(service, host):
    cfg = service.cfg
    uri = f"ipp://{host}/ipp/print"
    busy = service.busy()
    reasons = ["none"]
    message = "Bereit"
    if service.last_error and time.time() - service.last_error[0] < 120:
        reasons = ["offline-report"]
        message = service.last_error[1][:200]
    elif service.cooling:
        message = "Drucker zu heiß – kühlt ab, druckt dann weiter"
    elif busy:
        message = "Druckt"
    name = cfg.get("printer_name", "Cat Printer")
    I, K, B, T, N, E = ipp.INTEGER, ipp.KEYWORD, ipp.BOOLEAN, ipp.TEXT, ipp.NAME, ipp.ENUM
    ops = [ipp.PRINT_JOB, ipp.VALIDATE_JOB, ipp.CREATE_JOB, ipp.SEND_DOCUMENT, ipp.CANCEL_JOB,
           ipp.GET_JOB_ATTRIBUTES, ipp.GET_JOBS, ipp.GET_PRINTER_ATTRIBUTES, ipp.CLOSE_JOB]
    return [
        ("charset-configured", ipp.CHARSET, ["utf-8"]),
        ("charset-supported", ipp.CHARSET, ["utf-8"]),
        ("color-supported", B, [False]),
        ("compression-supported", K, ["none"]),
        ("copies-default", I, [1]),
        ("copies-supported", ipp.RANGE, [(1, 99)]),
        ("document-format-default", ipp.MIME, [FORMATS[0]]),
        ("document-format-preferred", ipp.MIME, [FORMATS[0]]),
        ("document-format-supported", ipp.MIME, FORMATS),
        ("finishings-default", E, [3]),
        ("finishings-supported", E, [3]),
        ("generated-natural-language-supported", ipp.LANGUAGE, ["en"]),
        ("ipp-versions-supported", K, ["1.1", "2.0"]),
        ("job-creation-attributes-supported", K, ["copies", "media", "media-col", "orientation-requested",
                                                  "print-color-mode", "print-quality", "print-scaling",
                                                  "printer-resolution", "sides"]),
        ("media-bottom-margin-supported", I, [0]),
        ("media-left-margin-supported", I, [0]),
        ("media-right-margin-supported", I, [0]),
        ("media-top-margin-supported", I, [0]),
        ("media-col-database", ipp.BEGIN_COLLECTION, [_media_col(*m) for m in MEDIA]),
        ("media-col-default", ipp.BEGIN_COLLECTION, [_media_col(*DEFAULT_MEDIA)]),
        ("media-col-ready", ipp.BEGIN_COLLECTION, [_media_col(*DEFAULT_MEDIA)]),
        ("media-col-supported", K, ["media-bottom-margin", "media-left-margin", "media-right-margin",
                                    "media-size", "media-size-name", "media-source", "media-top-margin",
                                    "media-type"]),
        ("media-default", K, [DEFAULT_MEDIA[0]]),
        ("media-ready", K, [DEFAULT_MEDIA[0]]),
        ("media-supported", K, [m[0] for m in MEDIA]),
        ("media-size-supported", ipp.BEGIN_COLLECTION,
         [_col(("x-dimension", I, [x]), ("y-dimension", I, [y])) for _n, x, y in MEDIA]),
        ("media-source-default", K, ["main"]),
        ("media-source-supported", K, ["main"]),
        ("media-type-supported", K, ["stationery"]),
        ("multiple-document-jobs-supported", B, [False]),
        ("multiple-document-handling-default", K, ["separate-documents-uncollated-copies"]),
        ("multiple-document-handling-supported", K, ["separate-documents-uncollated-copies"]),
        ("multiple-operation-time-out", I, [60]),
        ("natural-language-configured", ipp.LANGUAGE, ["en"]),
        ("number-up-default", I, [1]),
        ("number-up-supported", I, [1]),
        ("operations-supported", E, ops),
        ("orientation-requested-default", E, [3]),
        ("orientation-requested-supported", E, [3, 4]),
        ("output-bin-default", K, ["face-up"]),
        ("output-bin-supported", K, ["face-up"]),
        ("pdl-override-supported", K, ["attempted"]),
        ("print-color-mode-default", K, ["monochrome"]),
        ("print-color-mode-supported", K, ["monochrome"]),
        ("print-quality-default", E, [4]),
        ("print-quality-supported", E, [3, 4, 5]),
        ("print-scaling-default", K, ["fit"]),
        ("print-scaling-supported", K, ["auto", "fit", "fill", "none"]),
        ("printer-device-id", T, ["MFG:YHK;MDL:Cat Printer;CMD:PWGRaster;CLS:PRINTER;"]),
        ("printer-firmware-name", N, ["CatPrinterDriver"]),
        ("printer-firmware-string-version", T, ["0.1"]),
        ("printer-info", T, [name]),
        ("printer-is-accepting-jobs", B, [True]),
        ("printer-location", T, ["Bluetooth"]),
        ("printer-make-and-model", T, ["YHK Cat Printer"]),
        ("printer-more-info", ipp.URI, [f"http://{host}/"]),
        ("printer-name", N, [name]),
        ("printer-resolution-default", ipp.RESOLUTION, [(DPI, DPI, 3)]),
        ("printer-resolution-supported", ipp.RESOLUTION, [(DPI, DPI, 3)]),
        ("printer-state", E, [4 if busy else 3]),
        ("printer-state-message", T, [message]),
        ("printer-state-reasons", K, reasons),
        ("printer-up-time", I, [service.uptime()]),
        ("printer-uri-supported", ipp.URI, [uri]),
        ("printer-uuid", ipp.URI, [f"urn:uuid:{cfg['uuid']}"]),
        ("pwg-raster-document-resolution-supported", ipp.RESOLUTION, [(DPI, DPI, 3)]),
        ("pwg-raster-document-sheet-back", K, ["normal"]),
        ("pwg-raster-document-type-supported", K, ["sgray_8", "black_1"]),
        ("queued-job-count", I, [sum(1 for j in list(service.jobs.values()) if j.state in (PENDING, PROCESSING))]),
        ("sides-default", K, ["one-sided"]),
        ("sides-supported", K, ["one-sided"]),
        ("uri-authentication-supported", K, ["none"]),
        ("uri-security-supported", K, ["none"]),
        ("which-jobs-supported", K, ["completed", "not-completed"]),
    ]


def job_attributes(service, job, host):
    reason = STATE_REASON[job.state]
    if job.state == PENDING and job.data is None:
        reason = "job-incoming"
    attrs = [
        ("job-id", ipp.INTEGER, [job.id]),
        ("job-uri", ipp.URI, [f"ipp://{host}/ipp/print/{job.id}"]),
        ("job-printer-uri", ipp.URI, [f"ipp://{host}/ipp/print"]),
        ("job-name", ipp.NAME, [job.name]),
        ("job-originating-user-name", ipp.NAME, [job.user]),
        ("job-state", ipp.ENUM, [job.state]),
        ("job-state-reasons", ipp.KEYWORD, [reason]),
        ("job-printer-up-time", ipp.INTEGER, [service.uptime()]),
        ("time-at-creation", ipp.INTEGER, [max(1, job.created - service.start_time)]),
        ("job-impressions-completed", ipp.INTEGER, [job.pages if job.state == COMPLETED else 0]),
    ]
    attrs.append(("time-at-processing", ipp.INTEGER, [job.processing]) if job.processing
                 else ("time-at-processing", ipp.NO_VALUE, [None]))
    attrs.append(("time-at-completed", ipp.INTEGER, [job.completed]) if job.completed
                 else ("time-at-completed", ipp.NO_VALUE, [None]))
    if job.message:
        attrs.append(("job-state-message", ipp.TEXT, [job.message[:200]]))
    return attrs


GROUP_KEYWORDS = {"all", "printer-description", "job-template", "job-description",
                  "job-status", "printer-status", "media-col-database"}


def _filter(attrs, requested):
    if not requested or any(r in GROUP_KEYWORDS for r in requested):
        return attrs
    wanted = set(requested)
    return [a for a in attrs if a[0] in wanted]


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "CatPrinterDriver/0.1"
    service: PrintService = None

    def log_message(self, fmt, *args):
        log.debug("HTTP %s", fmt % args)

    def _read_body(self):
        if "chunked" in self.headers.get("Transfer-Encoding", "").lower():
            body = bytearray()
            while True:
                size_line = self.rfile.readline()
                size = int(size_line.split(b";", 1)[0].strip() or b"0", 16)
                if size == 0:
                    while self.rfile.readline() not in (b"\r\n", b"\n", b""):
                        pass
                    return bytes(body)
                body += self.rfile.read(size)
                self.rfile.readline()  # CRLF nach dem Block
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(length) if length else b""

    def _send(self, status, ctype, body):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _host_ok(self, ipp_request=False):
        """Wer darf was?

        - Vom PC selbst (Loopback): alles, aber nur mit Host 127.0.0.1/localhost –
          Schutz vor DNS-Rebinding (fremde Domain, die auf 127.0.0.1 zeigt).
        - Aus dem Heimnetz (nur mit Netzwerkfreigabe): ausschließlich IPP-Drucken,
          Host muss eine IP oder der Name dieses PCs sein. Statusseite, Einstellungen
          und Verlauf bleiben lokal.
        """
        client = self.client_address[0]
        host = (self.headers.get("Host") or "").lower()
        if netshare.is_loopback(client):
            port = self.server.server_address[1]
            if host in (f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"):
                return True
            reason = f"fremder Host-Header {host!r}"
        elif not self.service.cfg.get("share_network"):
            reason = f"Netzwerkzugriff von {client} (Freigabe aus)"
        elif not netshare.is_lan(client):
            reason = f"Adresse {client} ist nicht im Heimnetz"
        elif not ipp_request:
            reason = f"{client} darf nur drucken"
        elif not netshare.lan_host_ok(host):
            reason = f"fremder Host-Header {host!r} von {client}"
        else:
            return True
        log.warning("Anfrage abgelehnt: %s", reason)
        self._send(403, "text/plain", b"forbidden")
        return False

    def do_GET(self):
        if not self._host_ok():
            return
        path = self.path.split("?", 1)[0]
        svc = self.service
        if path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", statuspage.PAGE.encode("utf-8"))
        elif path == "/status.json":
            self._json(200, statuspage.status_dict(svc))
        elif path == "/history.json":
            enabled = bool(svc.cfg.get("keep_history"))
            self._json(200, {"enabled": enabled, "entries": svc.history.list() if enabled else []})
        elif path.startswith("/history/"):
            # /history/<id>/<seite>.png – so wie gedruckt; ?thumb=1 als Graustufen-Miniatur
            parts = path.split("/")
            try:
                if len(parts) != 4 or not parts[3].endswith(".png"):
                    raise KeyError(path)
                body = svc.preview(parts[2], int(parts[3][:-4]), thumb="thumb=1" in self.path)
            except (KeyError, ValueError, OSError):
                self._send(404, "text/plain", b"not found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")  # gedruckte Inhalte nicht im Browser-Cache
            self.end_headers()
            self.wfile.write(body)
        else:
            self._send(404, "text/plain", b"not found")

    def _json(self, status, data):
        self._send(status, "application/json", json.dumps(data).encode("utf-8"))

    def _action(self, name, body):
        # Eigener Header: fremde Webseiten können ihn nicht ohne CORS-Vorabfrage
        # setzen, also weder drucken noch Einstellungen ändern
        if self.headers.get("X-CatPrinter") != "1":
            self._send(403, "text/plain", b"forbidden")
            return
        svc = self.service
        try:
            data = json.loads(body or b"{}")
            if not isinstance(data, dict):
                raise ValueError("JSON-Objekt erwartet")
        except ValueError as e:
            self._json(400, {"error": f"Ungültige Daten: {e}"})
            return
        if name == "test":
            volts = statuspage.battery_volts(svc.status)
            info = f"Akku {volts:.2f} V".replace(".", ",") if volts else ""
            svc.print_image("Testseite", short_test_page(info))
        elif name == "battery":
            svc.refresh_status()
        elif name == "calibrate":
            try:
                density = validate_settings({"density": data.get("density")})["density"]
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            svc.print_image(f"Probedruck Dichte {density}", calibration_page(density), density)
        elif name == "settings":
            try:
                applied = svc.update_settings(data)
            except ValueError as e:
                self._json(400, {"error": str(e)})
                return
            self._json(200, {"applied": applied})
            return
        elif name in ("reprint", "history-delete"):
            try:
                if name == "reprint":
                    svc.reprint(data.get("id"))
                else:
                    svc.history.delete(data.get("id"))
            except (KeyError, OSError):
                self._json(404, {"error": "Eintrag nicht gefunden"})
                return
        elif name == "history-clear":
            svc.history.clear()
        elif name == "quit":
            # Für Installation/Update: laufende Instanz sauber beenden
            log.info("Beenden angefordert")
            self._json(202, {"ok": True})
            threading.Thread(target=svc.emit, args=("quit",), daemon=True).start()
            return
        else:
            self._send(404, "text/plain", b"unknown action")
            return
        self._json(202, {"ok": True})

    def do_POST(self):
        body = self._read_body()
        is_ipp = (not self.path.startswith("/action/")
                  and self.headers.get("Content-Type", "").split(";")[0].strip() == "application/ipp")
        if not self._host_ok(ipp_request=is_ipp):
            return
        if self.path.startswith("/action/"):
            self._action(self.path[len("/action/"):], body)
            return
        if self.headers.get("Content-Type", "").split(";")[0].strip() != "application/ipp":
            self._send(400, "text/plain", b"expected application/ipp")
            return
        try:
            req, doc = ipp.decode(body)
        except (ValueError, IndexError) as e:
            log.warning("Ungültige IPP-Anfrage: %s", e)
            self._send(400, "text/plain", b"bad ipp")
            return
        host = self.headers.get("Host") or f"{self.server.server_address[0]}:{self.server.server_address[1]}"
        op = ipp.OPERATION_NAMES.get(req.code, f"0x{req.code:04x}")
        log.info("IPP %s (Anfrage %d, %d Bytes Dokument)", op, req.request_id, len(doc))
        log.debug("Anfrage-Attribute:\n%s", ipp.describe(req))
        try:
            resp = self._dispatch(req, doc, host)
        except Exception:  # noqa: BLE001
            log.exception("Fehler bei %s", op)
            resp = self._response(req, ipp.INTERNAL_ERROR)
        log.debug("Antwort 0x%04x", resp.code)
        self._send(200, "application/ipp", ipp.encode(resp))

    # -------------------------------------------------------- IPP-Operationen

    def _response(self, req, status, message=None):
        op_attrs = [("attributes-charset", ipp.CHARSET, ["utf-8"]),
                    ("attributes-natural-language", ipp.LANGUAGE, ["en"])]
        if message:
            op_attrs.append(("status-message", ipp.TEXT, [message]))
        return ipp.Message(req.version if req.version[0] <= 2 else (2, 0), status, req.request_id,
                           [(ipp.OPERATION, op_attrs)])

    def _dispatch(self, req, doc, host):
        svc = self.service
        op = req.code
        if op == ipp.GET_PRINTER_ATTRIBUTES:
            resp = self._response(req, ipp.OK)
            requested = req.get_all("requested-attributes", ipp.OPERATION)
            resp.add_group(ipp.PRINTER, _filter(printer_attributes(svc, host), requested))
            return resp

        if op in (ipp.VALIDATE_JOB, ipp.CLOSE_JOB, ipp.IDENTIFY_PRINTER):
            return self._response(req, ipp.OK)

        if op in (ipp.PRINT_JOB, ipp.CREATE_JOB):
            fmt = req.get("document-format", ipp.OPERATION)
            if op == ipp.PRINT_JOB and not _format_ok(fmt, doc):
                return self._response(req, ipp.DOCUMENT_FORMAT_NOT_SUPPORTED, f"Format {fmt} nicht unterstützt")
            job = svc.new_job(req.get("job-name", ipp.OPERATION) or "Dokument",
                              req.get("requesting-user-name", ipp.OPERATION) or "Windows",
                              req.get("copies", ipp.JOB) or 1)
            job.quality = req.get("print-quality", ipp.JOB)
            job.from_network = not netshare.is_loopback(self.client_address[0])
            if op == ipp.PRINT_JOB:
                svc.submit(job, doc)
            resp = self._response(req, ipp.OK)
            resp.add_group(ipp.JOB, _filter(job_attributes(svc, job, host),
                                            ["job-id", "job-uri", "job-state", "job-state-reasons"]))
            return resp

        job = svc.jobs.get(_job_id(req))

        if op == ipp.SEND_DOCUMENT:
            if job is None:
                return self._response(req, ipp.NOT_FOUND, "Auftrag nicht gefunden")
            fmt = req.get("document-format", ipp.OPERATION)
            if doc and not _format_ok(fmt, doc):
                job.state, job.completed = ABORTED, svc.uptime()
                return self._response(req, ipp.DOCUMENT_FORMAT_NOT_SUPPORTED, f"Format {fmt} nicht unterstützt")
            if doc:
                svc.submit(job, doc)
            elif req.get("last-document", ipp.OPERATION):
                job.state, job.completed = COMPLETED, svc.uptime()  # leerer Auftrag
            resp = self._response(req, ipp.OK)
            resp.add_group(ipp.JOB, _filter(job_attributes(svc, job, host),
                                            ["job-id", "job-uri", "job-state", "job-state-reasons"]))
            return resp

        if op == ipp.GET_JOB_ATTRIBUTES:
            if job is None:
                return self._response(req, ipp.NOT_FOUND, "Auftrag nicht gefunden")
            resp = self._response(req, ipp.OK)
            resp.add_group(ipp.JOB, _filter(job_attributes(svc, job, host),
                                            req.get_all("requested-attributes", ipp.OPERATION)))
            return resp

        if op == ipp.CANCEL_JOB:
            if job is None:
                return self._response(req, ipp.NOT_FOUND, "Auftrag nicht gefunden")
            if job.state in (COMPLETED, ABORTED, CANCELED) or job.state == PROCESSING:
                return self._response(req, ipp.NOT_POSSIBLE, "Auftrag kann nicht mehr abgebrochen werden")
            job.state, job.completed = CANCELED, svc.uptime()
            return self._response(req, ipp.OK)

        if op == ipp.GET_JOBS:
            which = req.get("which-jobs", ipp.OPERATION) or "not-completed"
            done = (COMPLETED, ABORTED, CANCELED)
            jobs = [j for j in sorted(list(svc.jobs.values()), key=lambda j: -j.id)
                    if (j.state in done) == (which == "completed") or which == "all"]
            limit = req.get("limit", ipp.OPERATION)
            if limit:
                jobs = jobs[:limit]
            requested = req.get_all("requested-attributes", ipp.OPERATION) or ["job-id", "job-uri"]
            resp = self._response(req, ipp.OK)
            for j in jobs:
                resp.add_group(ipp.JOB, _filter(job_attributes(svc, j, host), requested))
            return resp

        return self._response(req, ipp.OPERATION_NOT_SUPPORTED)


def _job_id(req):
    job_id = req.get("job-id", ipp.OPERATION)
    if job_id is None:
        uri = req.get("job-uri", ipp.OPERATION) or ""
        tail = uri.rstrip("/").rsplit("/", 1)[-1]
        job_id = int(tail) if tail.isdigit() else None
    return job_id


def _format_ok(fmt, doc):
    if doc[:4] == pwg.SYNC:
        return True
    if fmt in (None, "application/octet-stream", "image/png", "image/jpeg"):
        return doc[:8] == b"\x89PNG\r\n\x1a\n" or doc[:3] == b"\xff\xd8\xff"
    return False


def serve(cfg, save_jobs_dir=None, config_file=None):
    service = PrintService(cfg, save_jobs_dir, config_file)
    handler = type("BoundHandler", (Handler,), {"service": service})
    # Kein SO_REUSEADDR: unter Windows könnte sonst eine zweite Instanz denselben Port belegen
    server_cls = type("SingleServer", (ThreadingHTTPServer,), {"allow_reuse_address": False})
    # Mit Netzwerkfreigabe auf allen Adressen hören; der Handler lässt aus dem Netz nur IPP zu
    bind = "0.0.0.0" if cfg.get("share_network") else cfg["http_host"]
    httpd = server_cls((bind, cfg["http_port"]), handler)
    httpd.daemon_threads = True
    log.info("IPP-Drucker läuft: ipp://%s:%d/ipp/print%s", cfg["http_host"], cfg["http_port"],
             " (im Heimnetz freigegeben)" if cfg.get("share_network") else "")
    return httpd, service
