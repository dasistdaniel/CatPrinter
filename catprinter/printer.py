"""Ansteuerung des YHK-Thermodruckers über Bluetooth-SPP mit ESC/POS."""
import logging
import re
import subprocess
import time

import serial
from PIL import Image, ImageChops, ImageFilter, ImageOps
from serial.tools import list_ports

log = logging.getLogger("printer")

WIDTH = 384            # Druckpunkte pro Zeile (48 mm bei 203 dpi)
DPI = 203
MAX_ROWS = 0xFFFF      # Höhe eines GS-v-0-Blocks ist 16 Bit
DEFAULT_DENSITY = 40   # per Kalibrierung ermittelt (WalkPrint schickt 25 = 1D 49 F0 19)
CHUNK = 256            # Bytes pro Schreibvorgang
CHUNK_DELAY = 0.03     # Pause zwischen Schreibvorgängen (Puffer des Druckers)


class PrinterError(Exception):
    pass


def find_port(name_prefix="YHK-"):
    """Sucht den COM-Port des gekoppelten Druckers anhand seiner MAC-Adresse."""
    ps = ("Get-PnpDevice -Class Bluetooth | Where-Object { $_.FriendlyName -like '%s*' } "
          "| ForEach-Object { $_.InstanceId }" % name_prefix)
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                             text=True, timeout=20, creationflags=subprocess.CREATE_NO_WINDOW).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    macs = re.findall(r"DEV_([0-9A-F]{12})", out.upper())
    for port in list_ports.comports():
        hwid = (port.hwid or "").upper()
        if any(mac in hwid for mac in macs):
            return port.device
    return None


MODES = ("auto", "text", "photo")
THRESHOLD = 128        # Schwelle schwarz/weiß im Textmodus
PHOTO_GRAY_LEVELS = 64 # ab so vielen häufigen Grautönen gilt eine Seite als Foto
FLAT_RANGE = 48        # max. Helligkeitsspanne im 3x3-Umfeld für "gleichmäßige Graufläche"


def prepare(img, trim=True, rotate=False, mode="auto"):
    """Skaliert ein Seitenbild auf 384 Punkte Breite und wandelt es in 1 Bit um.

    mode: "photo" rastert alles (Floyd-Steinberg), "text" nutzt eine harte
    Schwelle, "auto" entscheidet pro Seite (siehe _to_bw).
    rotate=True dreht um 180°, damit der Ausdruck richtig herum steht, wenn
    man von der Gesichtsseite des Druckers auf das herauskommende Papier schaut.
    """
    gray = img.convert("L")
    if abs(gray.width - WIDTH) <= 8:
        gray = _fit_width(gray)
    else:
        h = max(1, round(gray.height * WIDTH / gray.width))
        gray = gray.resize((WIDTH, h), Image.Resampling.LANCZOS)
    bw = _to_bw(gray, mode)
    if trim:
        bw = _trim_bottom(bw)
    # Erst beschneiden, dann drehen: der weggeschnittene Weißraum am Seitenende
    # würde sonst nach dem Drehen vorn ausgedruckt
    return bw.rotate(180) if rotate else bw


def _to_bw(gray, mode):
    threshold = gray.point(lambda v: 0 if v < THRESHOLD else 255)
    if mode == "text":
        return threshold.convert("1", dither=Image.Dither.NONE)
    dithered = gray.convert("1")  # Floyd-Steinberg
    if mode == "photo" or _is_photo(gray):
        return dithered
    # Text/Grafik: Kanten (auch geglättete Schriftkanten) hart schwellen, damit sie
    # nicht ausfransen; nur gleichmäßige Grauflächen (Füllungen, Verläufe) rastern.
    spread = ImageChops.subtract(gray.filter(ImageFilter.MaxFilter(3)),
                                 gray.filter(ImageFilter.MinFilter(3)))
    flat = spread.point(lambda r: 255 if r < FLAT_RANGE else 0)
    midtone = gray.point(lambda v: 255 if 8 <= v < 248 else 0)
    mask = ImageChops.multiply(flat, midtone)
    return Image.composite(dithered.convert("L"), threshold, mask).convert("1", dither=Image.Dither.NONE)


def _is_photo(gray):
    """Fotos nutzen viele verschiedene Grautöne, Text und Grafik nur wenige."""
    hist = gray.histogram()
    minimum = gray.width * gray.height * 0.001
    return sum(1 for count in hist[32:224] if count > minimum) >= PHOTO_GRAY_LEVELS


def _fit_width(img):
    """Kleine Breitenabweichungen (Rundung) mit Weiß auffüllen bzw. mittig beschneiden."""
    if img.width == WIDTH:
        return img
    if img.width > WIDTH:
        left = (img.width - WIDTH) // 2
        return img.crop((left, 0, left + WIDTH, img.height))
    canvas = Image.new("L", (WIDTH, img.height), 255)
    canvas.paste(img, ((WIDTH - img.width) // 2, 0))
    return canvas


def _trim_bottom(bw, keep=8):
    """Entfernt weiße Zeilen am Seitenende (spart Papier)."""
    bbox = ImageOps.invert(bw.convert("L")).getbbox()
    if bbox is None:
        return bw.crop((0, 0, WIDTH, 1))
    return bw.crop((0, 0, WIDTH, min(bw.height, bbox[3] + keep)))


def raster_rows(bw):
    """1-Bit-Bild -> Zeilendaten, gesetztes Bit = schwarzer Punkt."""
    return bytes(b ^ 0xFF for b in bw.tobytes("raw", "1"))


def _gs_v0(data, rows):
    bpr = WIDTH // 8
    return bytes([0x1D, 0x76, 0x30, 0x00, bpr & 0xFF, bpr >> 8, rows & 0xFF, rows >> 8]) + data


def build_job(images, feed_mm=15, density=DEFAULT_DENSITY, init=True):
    """Baut den kompletten ESC/POS-Datenstrom für mehrere Seiten.

    Wie die WalkPrint-App: Init, Dichte (1D 49 F0 n), dann jede Seite als
    ein zusammenhängender GS-v-0-Block. Aufteilen in mehrere Blöcke führt
    zu sichtbaren Streifen, weil der Drucker an jeder Blockgrenze neu ansetzt.

    ESC @ verwirft alles, was noch im Puffer des Druckers wartet – beim
    Aneinanderhängen mehrerer Aufträge darf nur der erste init=True haben.
    """
    bpr = WIDTH // 8
    out = bytearray(b"\x1b\x40" if init else b"")
    out += bytes([0x1D, 0x49, 0xF0, max(0, min(255, int(density)))])
    feed_rows = round(feed_mm * DPI / 25.4)
    for i, bw in enumerate(images):
        rows = bw.height
        data = raster_rows(bw)
        if i == len(images) - 1:
            # Vorschub als leere Zeilen im selben Block, damit das Ende über die Abreißkante kommt
            data += bytes(feed_rows * bpr)
            rows += feed_rows
        if rows > MAX_ROWS:
            raise PrinterError(f"Seite zu lang ({rows} Zeilen, maximal {MAX_ROWS})")
        out += _gs_v0(data, rows)
    return bytes(out)


class Printer:
    def __init__(self, port=None, name_prefix="YHK-"):
        self.port = port
        self.name_prefix = name_prefix
        self.chunk_delay = CHUNK_DELAY
        self.last_status = {}

    def _resolve_port(self):
        if self.port:
            return self.port
        port = find_port(self.name_prefix)
        if not port:
            raise PrinterError(f"Kein gekoppelter Drucker '{self.name_prefix}*' mit COM-Port gefunden")
        log.info("Drucker gefunden auf %s", port)
        self.port = port
        return port

    def _open(self, attempts=3, retry_delay=3.0):
        # Direkt nach dem Trennen lehnt der Drucker neue Verbindungen einige Sekunden ab
        port = self._resolve_port()
        for attempt in range(1, attempts + 1):
            try:
                ser = serial.Serial(port, 115200, timeout=1, write_timeout=15)
                break
            except serial.SerialException as e:
                if attempt == attempts:
                    raise PrinterError(f"{port} lässt sich nicht öffnen (Drucker aus oder "
                                       f"mit dem Handy verbunden?): {e}") from e
                log.info("Verbindung fehlgeschlagen, neuer Versuch in %.0f s", retry_delay)
                time.sleep(retry_delay)
        time.sleep(0.8)
        return ser

    def status(self):
        """Fragt Firmware/Akku ab, z. B. {'HV': 'H1.0', 'SV': 'V1.01', 'VOLT': '7260mv', 'DPI': '384'}."""
        with self._open() as ser:
            self.last_status = _query_status(ser)
        return self.last_status

    def print_images(self, images, feed_mm=15, density=DEFAULT_DENSITY):
        self.send(build_job(images, feed_mm, density))

    def send(self, job):
        log.info("Sende %d Bytes (Pause %.0f ms je %d Bytes)", len(job), self.chunk_delay * 1000, CHUNK)
        with self._open() as ser:
            try:
                start = time.monotonic()
                slowest = 0.0
                for i in range(0, len(job), CHUNK):
                    t = time.monotonic()
                    ser.write(job[i:i + CHUNK])
                    ser.flush()
                    slowest = max(slowest, time.monotonic() - t)
                    if self.chunk_delay:
                        time.sleep(self.chunk_delay)
                    if ser.in_waiting:
                        log.debug("Drucker meldet: %r", ser.read(ser.in_waiting))
                elapsed = time.monotonic() - start
                log.info("Übertragen in %.1f s (%.1f KB/s), längster Schreibvorgang %.0f ms",
                         elapsed, len(job) / 1024 / max(elapsed, 0.001), slowest * 1000)
                # Genug Zeit lassen, bis der Drucker seinen Puffer abgearbeitet hat
                time.sleep(2.0)
            except serial.SerialException as e:
                raise PrinterError(f"Verbindung während des Drucks abgebrochen: {e}") from e
            # Akkustand gleich über dieselbe Verbindung mitnehmen (ohne neuen Verbindungsaufbau)
            try:
                self.last_status = _query_status(ser) or self.last_status
            except serial.SerialException:
                pass


def _query_status(ser):
    ser.reset_input_buffer()
    ser.write(b"\x1e\x47\x03")
    time.sleep(0.5)
    text = ser.read(ser.in_waiting or 0).decode("ascii", "replace").strip("\x00")
    return dict(p.split("=", 1) for p in text.split(",") if "=" in p)


def battery_volts(status):
    """'7180mv' -> 7.18 (oder None)."""
    match = re.match(r"(\d+)\s*mv", str(status.get("VOLT", "")), re.I)
    return int(match.group(1)) / 1000 if match else None
