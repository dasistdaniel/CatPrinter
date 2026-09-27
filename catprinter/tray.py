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

from . import i18n, netshare
from .i18n import t
from .pages import short_test_page
from .server import CONFIG_DIR, CONFIG_FILE, load_config, save_config, serve

log = logging.getLogger("tray")

LOG_FILE = os.path.join(CONFIG_DIR, "server.log")

COLORS = {"ready": (46, 160, 67), "printing": (31, 111, 235), "cooling": (224, 150, 20), "error": (218, 54, 51)}


def label(state):
    return t("label_" + state)


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

    def restart(self, message=None):
        log.info("Server wird neu gestartet (Einstellungen neu laden)")
        self.stop_server()
        try:
            self.start_server()
        except OSError as e:
            self.set_state("error", str(e))
            self.icon.notify(t("restart_failed"), "Cat Printer")
            return
        self.set_state("ready", "")
        self.icon.notify(message or t("settings_reloaded"), "Cat Printer")

    def _share_changed(self, enabled):
        if enabled and not netshare.firewall_ok():
            from .installer import _elevated
            # Einmalig: Firewall für private Netzwerke öffnen (Windows fragt nach Adminrechten)
            _elevated(netshare.firewall_script())
            if not netshare.firewall_ok():
                self.icon.notify(t("firewall_failed"), "Cat Printer")
        name = f"{self.cfg.get('printer_name', 'Cat Printer')} @ {socket.gethostname()}"
        self.restart(t("shared_on", name=name) if enabled else t("shared_off"))

    # ------------------------------------------------------------ Ereignisse

    def on_event(self, event, **data):
        if event == "quit":
            self._quit()
        elif event == "share_changed":
            threading.Thread(target=self._share_changed, args=(data["enabled"],), daemon=True).start()
        elif event == "settings":
            if "language" in data.get("changes", {}):
                self.set_state(self.state, self.detail)  # Menü und Tooltip in der neuen Sprache
        elif event == "job_started":
            self.set_state("printing", data["job"].name)
        elif event == "hot":
            self.set_state("cooling", "")
            self.icon.notify(t("hot_text") + (t("hot_waiting") if data.get("waiting") else t("hot_paused")),
                             t("hot_title"))
        elif event == "cooled":
            self.set_state("printing", "")
        elif event == "job_done":
            self.set_state("ready", "")
        elif event == "job_failed":
            self.set_state("error", data["error"])
            self.icon.notify(t("print_failed", name=data["job"].name, err=_short(data["error"])),
                             t("print_failed_title"))
        elif event == "status":
            if data.get("quiet"):
                self.set_state(self.state, self.detail)  # nur Tooltip/Menü mit neuem Akkustand
            else:
                self.set_state("ready", "")
                self.icon.notify(f"{t('battery')}: {self.battery_text(short=True)}", "Cat Printer")
        elif event == "status_failed":
            self.set_state("error", data["error"])
            self.icon.notify(_short(data["error"]), t("unreachable_title"))
        elif event == "battery":
            self.set_state(self.state, self.detail)
            if data["level"] == "critical":
                self.icon.notify(t("battery_critical_text", percent=data["percent"]), t("battery_critical_title"))
            else:
                self.icon.notify(t("battery_low_text", percent=data["percent"]), t("battery_low_title"))
        elif event == "battery_full":
            self.set_state(self.state, self.detail)
            self.icon.notify(t("battery_full_text"), "Cat Printer")
        elif event in ("battery_charging", "battery_unplugged"):
            self.set_state(self.state, self.detail)  # Tooltip/Menü: "lädt …" bzw. wieder Prozent

    def set_state(self, state, detail):
        self.state, self.detail = state, detail
        self.icon.icon = make_icon(state)
        self.icon.title = f"Cat Printer – {label(state)} · {t('battery')} {self.battery_text(short=True)}"[:127]
        self.icon.update_menu()

    # ------------------------------------------------------------ Menü

    @property
    def volts(self):
        return (self.service.battery.get("volts") if self.service else None)

    def battery_text(self, short=False):
        b = self.service.battery if self.service else {}
        if not b:
            return t("battery_unknown") if short else f"{t('battery')}: {t('battery_not_measured')}"
        if b.get("charging"):
            text = t("battery_charged") if b.get("full") else t("battery_charging")
            return text if short else f"{t('battery')}: {text}"
        text = f"{b['percent']} % ({i18n.volts(b['volts'])})"
        if b["level"] == "critical":
            text += " – " + t("battery_almost_empty")
        elif b["level"] == "low":
            text += " – " + t("battery_low_suffix")
        return text if short else f"{t('battery')}: {text}"

    def status_text(self):
        text = f"{t('status')}: {label(self.state)}"
        if self.detail:
            text += f" – {_short(self.detail, 60)}"
        return text

    def _set_language(self, value):
        if self.service:
            self.service.update_settings({"language": value})  # meldet "settings" -> Menü neu
            self.icon.notify(t("language_changed"), "Cat Printer")

    def _menu(self):
        Item = pystray.MenuItem
        current = lambda value: (lambda _i: (self.cfg.get("language", "auto") if self.service else "auto") == value)
        language_menu = pystray.Menu(
            Item(lambda _i: t("menu_language_auto"), lambda: self._set_language("auto"),
                 checked=current("auto"), radio=True),
            Item("Deutsch", lambda: self._set_language("de"), checked=current("de"), radio=True),
            Item("English", lambda: self._set_language("en"), checked=current("en"), radio=True),
        )
        return pystray.Menu(
            Item(lambda _i: self.status_text(), None, enabled=False),
            Item(lambda _i: self.battery_text(), None, enabled=False),
            pystray.Menu.SEPARATOR,
            Item(lambda _i: t("menu_test_page"), self._test_page),
            Item(lambda _i: t("menu_check_battery"), lambda: self.service and self.service.refresh_status()),
            pystray.Menu.SEPARATOR,
            Item(lambda _i: t("menu_status_page"), self._open_status, default=True),
            Item(lambda _i: t("menu_log"), lambda: _notepad(LOG_FILE)),
            Item(lambda _i: t("menu_settings"), lambda: _notepad(CONFIG_FILE)),
            Item(lambda _i: t("menu_language"), language_menu),
            Item(lambda _i: t("menu_restart"), lambda: threading.Thread(target=self.restart, daemon=True).start()),
            Item(lambda _i: t("menu_setup_printer"), lambda: threading.Thread(
                target=self._setup_printer, daemon=True).start(), visible=lambda _i: self.printer_missing),
            pystray.Menu.SEPARATOR,
            Item(lambda _i: t("menu_quit"), self._quit),
        )

    def _test_page(self):
        if not self.service:
            return
        info = t("battery_info", v=self.battery_text(short=True)) if self.volts else ""
        self.service.print_image(t("test_page"), short_test_page(info))

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
        text = t("printer_missing") + (t("printer_missing_later") if first_time else "")
        if _box(text, MB_YESNO | MB_ICONQUESTION) != IDYES:
            if first_time:
                self.cfg["printer_setup_declined"] = True  # nicht bei jedem Start erneut fragen
                save_config(self.cfg, self.service.config_file)
            return
        if add_printer():
            self.printer_missing = False
            self.icon.update_menu()
            self.icon.notify(t("printer_added"), "Cat Printer")
        else:
            self.icon.notify(t("printer_not_added"), "Cat Printer")

    # ------------------------------------------------------------ Start

    def run(self):
        try:
            self.start_server()
        except OSError:
            cfg = load_config()
            i18n.set_language(cfg.get("language", "auto"))
            url = f"http://{cfg['http_host']}:{cfg['http_port']}/"
            if _server_answers(url):
                # Läuft schon (z. B. per Autostart): einfach die Statusseite öffnen
                log.info("Server läuft bereits – öffne Statusseite")
                webbrowser.open(url)
                return 0
            _message_box(t("port_in_use", port=cfg["http_port"]))
            return 1
        log.info("Tray gestartet")
        # Tooltip in der eingestellten Sprache (update_menu erst, wenn das Symbol läuft)
        self.icon.title = f"Cat Printer – {label('ready')} · {t('battery')} {self.battery_text(short=True)}"[:127]

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
