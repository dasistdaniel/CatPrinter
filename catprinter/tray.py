"""Symbol im Infobereich: startet den Druckserver und zeigt Status, Akku und Menü."""
import ctypes
import logging
import os
import subprocess
import threading
import webbrowser

import pystray
from PIL import Image, ImageDraw

from .pages import short_test_page
from .printer import battery_volts
from .server import CONFIG_DIR, CONFIG_FILE, load_config, serve

log = logging.getLogger("tray")

LOG_FILE = os.path.join(CONFIG_DIR, "server.log")
LOW_BATTERY_VOLTS = 6.8

COLORS = {"ready": (46, 160, 67), "printing": (31, 111, 235), "error": (218, 54, 51)}
LABELS = {"ready": "Bereit", "printing": "Druckt …", "error": "Fehler"}


def make_icon(state):
    """Katzengesicht mit farbigem Statuspunkt, 64×64 Pixel."""
    img = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    fur, line = (250, 250, 250, 255), (60, 60, 60, 255)
    d.polygon([(8, 26), (12, 4), (26, 16)], fill=fur, outline=line, width=2)    # Ohren
    d.polygon([(56, 26), (52, 4), (38, 16)], fill=fur, outline=line, width=2)
    d.rounded_rectangle([6, 14, 58, 56], radius=16, fill=fur, outline=line, width=3)
    d.ellipse([18, 28, 25, 35], fill=line)                                     # Augen
    d.ellipse([39, 28, 46, 35], fill=line)
    d.arc([24, 36, 40, 48], start=20, end=160, fill=line, width=3)             # Mund
    d.ellipse([40, 40, 63, 63], fill=COLORS[state] + (255,), outline=(255, 255, 255, 255), width=3)
    return img


def _message_box(text, title="Cat Printer"):
    ctypes.windll.user32.MessageBoxW(None, text, title, 0x10)


class TrayApp:
    def __init__(self, save_jobs_dir=None):
        self.save_jobs_dir = save_jobs_dir
        self.state = "ready"
        self.detail = ""
        self.volts = None
        self.low_battery_warned = False
        self.httpd = self.service = None
        self.icon = pystray.Icon("CatPrinter", make_icon("ready"), "Cat Printer", self._menu())

    # ------------------------------------------------------------ Server

    def start_server(self):
        self.cfg = load_config()
        self.httpd, self.service = serve(self.cfg, self.save_jobs_dir)
        self.service.listeners.append(self.on_event)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def stop_server(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.service.stop()
            self.httpd = self.service = None

    def restart(self):
        log.info("Server wird neu gestartet (Einstellungen neu laden)")
        self.stop_server()
        try:
            self.start_server()
        except OSError as e:
            self.set_state("error", f"Port belegt: {e}")
            self.icon.notify("Server konnte nicht neu starten – Port belegt.", "Cat Printer")
            return
        self.set_state("ready", "")
        self.icon.notify("Einstellungen neu geladen.", "Cat Printer")

    # ------------------------------------------------------------ Ereignisse

    def on_event(self, event, **data):
        if event == "job_started":
            self.set_state("printing", data["job"].name)
        elif event == "job_done":
            self.update_battery(data.get("status") or {})
            self.set_state("ready", "")
        elif event == "job_failed":
            self.set_state("error", data["error"])
            self.icon.notify(f"„{data['job'].name}“ wurde nicht gedruckt.\n{_short(data['error'])}",
                             "Druck fehlgeschlagen")
        elif event == "status":
            self.update_battery(data["status"])
            self.set_state("ready", "")
            self.icon.notify(f"Akku: {self.battery_text(short=True)}", "Cat Printer")
        elif event == "status_failed":
            self.set_state("error", data["error"])
            self.icon.notify(_short(data["error"]), "Drucker nicht erreichbar")

    def update_battery(self, status):
        volts = battery_volts(status)
        if volts is None:
            return
        self.volts = volts
        if volts < LOW_BATTERY_VOLTS and not self.low_battery_warned:
            self.low_battery_warned = True
            self.icon.notify(f"Akku schwach ({volts:.2f} V) – Drucke werden blasser. "
                             "Bitte per USB laden.", "Cat Printer")
        elif volts >= LOW_BATTERY_VOLTS + 0.1:
            self.low_battery_warned = False

    def set_state(self, state, detail):
        self.state, self.detail = state, detail
        self.icon.icon = make_icon(state)
        self.icon.title = f"Cat Printer – {LABELS[state]} · Akku {self.battery_text(short=True)}"[:127]
        self.icon.update_menu()

    # ------------------------------------------------------------ Menü

    def battery_text(self, short=False):
        if self.volts is None:
            return "unbekannt" if short else "Akku: unbekannt (wird beim Drucken gemessen)"
        text = f"{self.volts:.2f} V".replace(".", ",")
        return text if short else f"Akku: {text}"

    def status_text(self):
        text = f"Status: {LABELS[self.state]}"
        if self.detail:
            text += f" – {_short(self.detail, 60)}"
        return text

    def _menu(self):
        Item = pystray.MenuItem
        return pystray.Menu(
            Item(lambda _i: self.status_text(), None, enabled=False),
            Item(lambda _i: self.battery_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item("Testseite drucken", self._test_page),
            Item("Akkustand prüfen", lambda: self.service and self.service.refresh_status()),
            pystray.Menu.SEPARATOR,
            Item("Statusseite öffnen", self._open_status, default=True),
            Item("Log öffnen", lambda: _notepad(LOG_FILE)),
            Item("Einstellungen bearbeiten", lambda: _notepad(CONFIG_FILE)),
            Item("Server neu starten", lambda: threading.Thread(target=self.restart, daemon=True).start()),
            pystray.Menu.SEPARATOR,
            Item("Beenden", self._quit),
        )

    def _test_page(self):
        if not self.service:
            return
        info = f"Akku {self.battery_text(short=True)}" if self.volts else ""
        self.service.print_image("Testseite", short_test_page(info))

    def _open_status(self):
        webbrowser.open(f"http://{self.cfg['http_host']}:{self.cfg['http_port']}/")

    def _quit(self):
        self.stop_server()
        self.icon.stop()

    # ------------------------------------------------------------ Start

    def run(self):
        try:
            self.start_server()
        except OSError:
            _message_box("Der Cat-Printer-Server läuft bereits (Port belegt).\n"
                         "Das Symbol findest du im Infobereich der Taskleiste.")
            return 1
        log.info("Tray gestartet")
        self.icon.run()
        return 0


def _short(text, limit=120):
    text = str(text).replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _notepad(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "a", encoding="utf-8").close()
    subprocess.Popen(["notepad.exe", path])
