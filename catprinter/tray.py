"""Symbol im Infobereich: startet den Druckserver und zeigt Status, Akku und Menü."""
import ctypes
import json
import logging
import os
import socket
import subprocess
import threading
import urllib.request
import webbrowser

import pystray
from PIL import Image, ImageDraw

from . import netshare
from .pages import short_test_page
from .printer import battery_volts
from .server import CONFIG_DIR, CONFIG_FILE, load_config, save_config, serve

log = logging.getLogger("tray")

LOG_FILE = os.path.join(CONFIG_DIR, "server.log")
LOW_BATTERY_VOLTS = 6.8

COLORS = {"ready": (46, 160, 67), "printing": (31, 111, 235), "cooling": (224, 150, 20), "error": (218, 54, 51)}
LABELS = {"ready": "Bereit", "printing": "Druckt …", "cooling": "Zu heiß – kühlt ab …", "error": "Fehler"}


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
    def __init__(self, save_jobs_dir=None, offer_printer_setup=False):
        self.save_jobs_dir = save_jobs_dir
        self.offer_printer_setup = offer_printer_setup
        self.printer_missing = False
        self.state = "ready"
        self.detail = ""
        self.volts = None
        self.low_battery_warned = False
        self.httpd = self.service = None
        self.advertiser = None
        self.icon = pystray.Icon("CatPrinter", make_icon("ready"), "Cat Printer", self._menu())

    # ------------------------------------------------------------ Server

    def start_server(self):
        self.cfg = load_config()
        self.httpd, self.service = serve(self.cfg, self.save_jobs_dir)
        self.service.listeners.append(self.on_event)
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        if self.cfg.get("share_network"):
            threading.Thread(target=self._start_sharing, args=(self.service,), daemon=True).start()

    def _start_sharing(self, service):
        """mDNS-Bekanntgabe starten und Netzwerkstatus für die Statusseite ermitteln."""
        status = {"addresses": netshare.lan_addresses(),
                  "name": f"{self.cfg.get('printer_name', 'Cat Printer')} @ {socket.gethostname()}"}
        try:
            self.advertiser = netshare.Advertiser(self.cfg, self.cfg["http_port"])
            self.advertiser.start()
            status["advertised"] = True
        except Exception as e:  # noqa: BLE001 – Freigabe darf den Druckserver nicht verhindern
            log.exception("mDNS-Bekanntgabe fehlgeschlagen")
            status["advertised"] = False
            status["error"] = str(e)
        status["firewall"] = netshare.firewall_ok()
        status["profiles"] = netshare.network_profiles()
        service.net_status = status

    def stop_server(self):
        if self.advertiser:
            self.advertiser.stop()
            self.advertiser = None
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.service.stop()
            self.httpd = self.service = None

    def restart(self, message="Einstellungen neu geladen."):
        log.info("Server wird neu gestartet (Einstellungen neu laden)")
        self.stop_server()
        try:
            self.start_server()
        except OSError as e:
            self.set_state("error", f"Port belegt: {e}")
            self.icon.notify("Server konnte nicht neu starten – Port belegt.", "Cat Printer")
            return
        self.set_state("ready", "")
        self.icon.notify(message, "Cat Printer")

    def _share_changed(self, enabled):
        if enabled and not netshare.firewall_ok():
            from .installer import _elevated
            # Einmalig: Firewall für private Netzwerke öffnen (Windows fragt nach Adminrechten)
            _elevated(netshare.firewall_script())
            if not netshare.firewall_ok():
                self.icon.notify("Firewall-Regel wurde nicht angelegt (Adminrechte abgelehnt?) – "
                                 "Handys erreichen den Drucker dann nicht.", "Cat Printer")
        name = self.cfg.get("printer_name", "Cat Printer")
        self.restart(f"Im Heimnetz freigegeben – auf dem Handy als „{name} @ {socket.gethostname()}“ wählbar."
                     if enabled else "Netzwerkfreigabe ausgeschaltet.")

    # ------------------------------------------------------------ Ereignisse

    def on_event(self, event, **data):
        if event == "quit":
            self._quit()
        elif event == "share_changed":
            threading.Thread(target=self._share_changed, args=(data["enabled"],), daemon=True).start()
        elif event == "job_started":
            self.set_state("printing", data["job"].name)
        elif event == "hot":
            self.set_state("cooling", "Druckkopf zu heiß")
            self.icon.notify("Der Druckkopf ist zu heiß (viele dunkle Flächen am Stück). "
                             + ("Der nächste Druck startet, sobald er abgekühlt ist – meist nach 1–2 Minuten."
                                if data.get("waiting") else
                                "Der Drucker pausiert kurz und druckt dann von selbst weiter."),
                             "Cat Printer kühlt ab")
        elif event == "cooled":
            self.set_state("printing", "")
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
            Item("Windows-Drucker einrichten …", lambda: threading.Thread(
                target=self._setup_printer, daemon=True).start(), visible=lambda _i: self.printer_missing),
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

    # ------------------------------------------------------------ Drucker (portable)

    def _check_printer(self):
        """Nicht installierte exe: fehlt der Windows-Drucker, einmal anbieten, ihn anzulegen."""
        from .installer import printer_exists
        self.printer_missing = not printer_exists()
        self.icon.update_menu()
        if self.printer_missing and not self.cfg.get("printer_setup_declined"):
            self._setup_printer(first_time=True)

    def _setup_printer(self, first_time=False):
        from .installer import IDYES, MB_ICONQUESTION, MB_YESNO, _box, add_printer
        text = ("Der Windows-Drucker „Cat Printer“ fehlt noch – ohne ihn taucht der Drucker "
                "nicht im Druckdialog auf.\n\nJetzt anlegen? Windows fragt dafür nach Adminrechten.")
        if first_time:
            text += "\n\n(Später geht das auch über das Tray-Menü.)"
        if _box(text, MB_YESNO | MB_ICONQUESTION) != IDYES:
            if first_time:
                self.cfg["printer_setup_declined"] = True  # nicht bei jedem Start erneut fragen
                save_config(self.cfg, self.service.config_file)
            return
        if add_printer():
            self.printer_missing = False
            self.icon.update_menu()
            self.icon.notify("Drucker „Cat Printer“ ist eingerichtet.", "Cat Printer")
        else:
            self.icon.notify("Drucker wurde nicht angelegt (Adminrechte abgelehnt?).", "Cat Printer")

    # ------------------------------------------------------------ Start

    def run(self):
        try:
            self.start_server()
        except OSError:
            cfg = load_config()
            url = f"http://{cfg['http_host']}:{cfg['http_port']}/"
            if _server_answers(url):
                # Läuft schon (z. B. per Autostart): einfach die Statusseite öffnen
                log.info("Server läuft bereits – öffne Statusseite")
                webbrowser.open(url)
                return 0
            _message_box(f"Port {cfg['http_port']} ist von einem anderen Programm belegt.\n"
                         "Der Cat-Printer-Server kann nicht starten.")
            return 1
        log.info("Tray gestartet")

        def setup(icon):
            icon.visible = True
            if self.offer_printer_setup:
                threading.Thread(target=self._check_printer, daemon=True).start()

        self.icon.run(setup=setup)
        return 0


def _server_answers(url):
    try:
        with urllib.request.urlopen(url + "status.json", timeout=3) as resp:
            return resp.status == 200 and "state" in json.loads(resp.read())
    except (OSError, ValueError):
        return False


def _short(text, limit=120):
    text = str(text).replace("\n", " ")
    return text if len(text) <= limit else text[:limit - 1] + "…"


def _notepad(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        open(path, "a", encoding="utf-8").close()
    subprocess.Popen(["notepad.exe", path])
