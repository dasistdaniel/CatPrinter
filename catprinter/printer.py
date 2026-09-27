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
WRITE_TIMEOUT = 300    # Hitzepause des Druckers: Schreiben blockiert, gemessen ~80 s
# Blockiertes Senden ist meist nur ein voller Puffer (Bluetooth bremst, gemessen bis ~13 s,
# wenn Aufträge direkt aufeinander folgen). Eine Hitzepause dauert deutlich länger (~80 s).
STALL_SECONDS = 30     # blockiert ein Schreibvorgang so lange, pausiert der Drucker wegen Hitze
HOT_BIT = 0x40         # DLE EOT 3: Druckkopf zu heiß
COOL_POLL = 5          # Sekunden zwischen Abfragen beim Abkühlen
COOL_MAX_WAIT = 240    # höchstens so lange vor einem Druck warten
IDLE_CLOSE = 90        # Verbindung erst nach so vielen Sekunden ohne Auftrag trennen


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
    bw = _to_bw(scale_to_width(img), mode)
    if trim:
        bw = _trim_bottom(bw)
    # Erst beschneiden, dann drehen: der weggeschnittene Weißraum am Seitenende
    # würde sonst nach dem Drehen vorn ausgedruckt
    return bw.rotate(180) if rotate else bw


def scale_to_width(img):
    """Seitenbild -> Graustufen in Druckbreite (384 Punkte)."""
    gray = img.convert("L")
    if abs(gray.width - WIDTH) <= 8:
        return _fit_width(gray)
    h = max(1, round(gray.height * WIDTH / gray.width))
    return gray.resize((WIDTH, h), Image.Resampling.LANCZOS)


# Tonwertkurve, die Windows (IPP-Klassentreiber) bei Fotos anwendet – gemessen am selben
# Foto einmal über Windows, einmal vom Android-Handy: Schatten werden deutlich aufgehellt,
# Mitteltöne bleiben. Auf Thermopapier laufen dunkle Bereiche sonst zu.
WINDOWS_PHOTO_CURVE = [(0, 66), (16, 69), (48, 71), (80, 84), (112, 111), (144, 137),
                       (176, 178), (208, 215), (240, 241), (255, 255)]


def _curve_lut(points):
    lut = []
    for v in range(256):
        for (x0, y0), (x1, y1) in zip(points, points[1:]):
            if x0 <= v <= x1:
                lut.append(round(y0 + (y1 - y0) * (v - x0) / (x1 - x0)))
                break
    return lut


_WINDOWS_LUT = _curve_lut(WINDOWS_PHOTO_CURVE)


def windows_tone(img):
    """Fotos von anderen Geräten so aufhellen, wie es Windows beim Drucken tut."""
    return img.convert("L").point(_WINDOWS_LUT)


def photo_brightness(img, percent):
    """Helligkeit als Gammakurve: +20 hellt Mitteltöne auf, Schwarz und Weiß bleiben."""
    gamma = max(0.3, 1 - percent / 100)
    return img.convert("L").point([round(255 * (v / 255) ** gamma) for v in range(256)])


def is_photo_page(img):
    return _is_photo(scale_to_width(img))


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


def build_job(images, feed_mm=15, density=DEFAULT_DENSITY, init=False):
    """Baut den kompletten ESC/POS-Datenstrom für mehrere Seiten.

    Dichte (1D 49 F0 n), dann jede Seite als ein zusammenhängender
    GS-v-0-Block. Aufteilen in mehrere Blöcke führt zu sichtbaren Streifen,
    weil der Drucker an jeder Blockgrenze neu ansetzt.

    Kein ESC @ (init) am Anfang: Es verwirft alles, was noch im Puffer des
    Druckers wartet. Folgt ein Auftrag direkt auf den vorigen, während der
    noch gedruckt wird, würde dessen Ende abgeschnitten. Die Dichte setzt
    jeder Auftrag ohnehin selbst.
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
        self.last_hot = False
        self._ser = None

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
                ser = serial.Serial(port, 115200, timeout=1, write_timeout=WRITE_TIMEOUT)
                break
            except serial.SerialException as e:
                if attempt == attempts:
                    raise PrinterError(f"{port} lässt sich nicht öffnen (Drucker aus oder "
                                       f"mit dem Handy verbunden?): {e}") from e
                log.info("Verbindung fehlgeschlagen, neuer Versuch in %.0f s", retry_delay)
                time.sleep(retry_delay)
        time.sleep(0.8)
        return ser

    # Die Verbindung bleibt zwischen Aufträgen offen. Ein neuer Verbindungsaufbau, während
    # der Drucker noch den vorigen Auftrag druckt, schneidet dessen Ende ab (gemessen:
    # mehrere Fotos hintereinander, jeweils der Rest fehlte). Der Drucker meldet nicht,
    # wann er fertig ist – deshalb trennt der Server erst nach einer Ruhezeit (close()).

    def _connection(self):
        """Offene Verbindung wiederverwenden oder neu öffnen. Gibt (ser, neu) zurück."""
        if self._ser is not None and self._ser.is_open:
            return self._ser, False
        self._ser = self._open()
        return self._ser, True

    def close(self, linger=0):
        """Verbindung trennen; linger = vorher warten, bis der Drucker fertig ist."""
        if self._ser is None:
            return
        if linger:
            time.sleep(linger)
        try:
            self._ser.close()
        except (serial.SerialException, OSError):
            pass
        self._ser = None
        log.info("Bluetooth-Verbindung getrennt")

    def status(self):
        """Fragt Firmware/Akku ab, z. B. {'HV': 'H1.0', 'SV': 'V1.01', 'VOLT': '7260mv', 'DPI': '384'}."""
        ser, _new = self._connection()
        try:
            self.last_status = _query_status(ser)
        except serial.SerialException as e:
            self.close()
            raise PrinterError(f"Verbindung zum Drucker verloren: {e}") from e
        return self.last_status

    def print_images(self, images, feed_mm=15, density=DEFAULT_DENSITY, notify=None):
        self.send(build_job(images, feed_mm, density), notify)

    def _ready_connection(self, notify):
        """Verbindung holen und prüfen; eine alte, inzwischen tote Verbindung neu aufbauen."""
        ser, new = self._connection()
        try:
            hot = is_hot(ser)
        except serial.SerialException:
            hot = None
        if hot is None and not new:
            # Keine Antwort über die alte Verbindung (Drucker aus/an, Handy war dran): neu verbinden
            log.info("Alte Verbindung antwortet nicht – verbinde neu")
            self.close()
            ser, _new = self._connection()
            hot = is_hot(ser)
        if hot:
            self._wait_until_cool(ser, notify)
        return ser

    def send(self, job, notify=None):
        """Sendet einen Auftrag. notify(ereignis) meldet Hitze:
        "cooling" (wartet vor dem Druck), "cooled", "paused_hot" (Pause mitten im Druck)."""
        notify = notify or (lambda _e: None)
        log.info("Sende %d Bytes (Pause %.0f ms je %d Bytes)", len(job), self.chunk_delay * 1000, CHUNK)
        try:
            ser = self._ready_connection(notify)
        except serial.SerialException as e:
            self.close()
            raise PrinterError(f"Keine Verbindung zum Drucker: {e}") from e
        try:
            start = time.monotonic()
            slowest = 0.0
            paused = False
            for i in range(0, len(job), CHUNK):
                t = time.monotonic()
                ser.write(job[i:i + CHUNK])
                ser.flush()
                took = time.monotonic() - t
                slowest = max(slowest, took)
                if took > STALL_SECONDS and not paused:
                    # Drucker nimmt nichts mehr an: Hitzeschutz hat mitten im Druck angehalten
                    paused = True
                    log.warning("Drucker pausiert mitten im Druck (vermutlich zu heiß)")
                    notify("paused_hot")
                if self.chunk_delay:
                    time.sleep(self.chunk_delay)
                if ser.in_waiting:
                    log.debug("Drucker meldet: %r", ser.read(ser.in_waiting))
            elapsed = time.monotonic() - start
            log.info("Übertragen in %.1f s (%.1f KB/s), längster Schreibvorgang %.0f ms",
                     elapsed, len(job) / 1024 / max(elapsed, 0.001), slowest * 1000)
        except serial.SerialException as e:
            self.close()
            raise PrinterError(f"Verbindung während des Drucks abgebrochen: {e}") from e
        # Akkustand gleich über dieselbe Verbindung mitnehmen
        try:
            self.last_status = _query_status(ser) or self.last_status
            self.last_hot = bool(is_hot(ser))
            if self.last_hot:
                log.info("Druckkopf nach dem Druck heiß")
                if not paused:
                    notify("paused_hot")  # Hitzeschutz greift – melden, auch ohne lange Blockade
        except serial.SerialException:
            pass

    def _wait_until_cool(self, ser, notify):
        """Vor dem Druck: Ist der Kopf noch heiß, abwarten statt mitten im Bild zu pausieren."""
        log.info("Druckkopf heiß – warte vor dem Druck (max. %d s)", COOL_MAX_WAIT)
        notify("cooling")
        start = time.monotonic()
        while time.monotonic() - start < COOL_MAX_WAIT:
            time.sleep(COOL_POLL)
            if not is_hot(ser):
                break
        log.info("Abgekühlt nach %.0f s", time.monotonic() - start)
        notify("cooled")


def is_hot(ser):
    """Hitzeschutz aktiv? DLE EOT 3 (Fehlerstatus): Bit 0x40 ist gesetzt, solange der Kopf zu heiß ist.

    Gemessen: kalt 0x12, nach 5 dunklen Fotos am Stück 0x52; nach ca. 1 Minute wieder 0x12.
    Gibt None zurück, wenn keine Antwort kommt (Verbindung vermutlich tot).
    """
    ser.reset_input_buffer()
    ser.write(b"\x10\x04\x03")
    deadline = time.monotonic() + 1.0
    while time.monotonic() < deadline and not ser.in_waiting:
        time.sleep(0.05)
    reply = ser.read(ser.in_waiting or 0)
    if not reply:
        return None
    return bool(reply[-1] & HOT_BIT)


def _query_status(ser):
    ser.reset_input_buffer()
    ser.write(b"\x1e\x47\x03")
    time.sleep(0.5)
    text = ser.read(ser.in_waiting or 0).decode("ascii", "replace").strip("\x00")
    return dict(p.split("=", 1) for p in text.split(",") if "=" in p)


# Entladekurve einer Li-Ionen-Zelle (Spannung je Zelle -> Ladestand). Der Drucker hat zwei
# Zellen in Reihe: voll geladen gemessen 8,42 V, nach längerem Drucken ~7,0 V.
_CELL_CURVE = [(3.30, 0), (3.50, 5), (3.60, 10), (3.65, 20), (3.70, 30), (3.75, 40), (3.80, 50),
               (3.85, 58), (3.90, 65), (3.95, 72), (4.00, 80), (4.05, 85), (4.10, 90), (4.20, 100)]
CELLS = 2


def battery_percent(volts):
    """Geschätzter Ladestand in Prozent (grob – die Spannung schwankt mit der Last)."""
    if volts is None:
        return None
    cell = volts / CELLS
    if cell <= _CELL_CURVE[0][0]:
        return 0
    if cell >= _CELL_CURVE[-1][0]:
        return 100
    for (v0, p0), (v1, p1) in zip(_CELL_CURVE, _CELL_CURVE[1:]):
        if v0 <= cell <= v1:
            return round(p0 + (p1 - p0) * (cell - v0) / (v1 - v0))
    return None


def battery_volts(status):
    """'7180mv' -> 7.18 (oder None)."""
    match = re.match(r"(\d+)\s*mv", str(status.get("VOLT", "")), re.I)
    return int(match.group(1)) / 1000 if match else None
