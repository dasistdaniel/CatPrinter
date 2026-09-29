"""Installation/Deinstallation der exe (ohne Adminrechte, außer fürs Anlegen des Druckers).

- kopiert die exe nach %LOCALAPPDATA%\\Programs\\CatPrinter
- Autostart- und Startmenü-Verknüpfung
- Eintrag unter "Apps & Features" (HKCU) zum Deinstallieren
- legt den Drucker "Cat Printer" an, falls er fehlt (eine UAC-Abfrage)
"""
import ctypes
import json
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import winreg

from . import __version__, i18n, netshare
from .i18n import t
from .server import CONFIG_DIR, load_config

log = logging.getLogger("installer")

APP_NAME = "Cat Printer"
PRINTER_NAME = "Cat Printer"
INSTALL_DIR = os.path.join(os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "Programs", "CatPrinter")
INSTALLED_EXE = os.path.join(INSTALL_DIR, "CatPrinter.exe")
# Gleicher Name wie bei autostart.ps1 – ersetzt einen alten Python-Autostart statt ihn zu verdoppeln
STARTUP_LNK = "Cat Printer Server.lnk"
STARTMENU_LNK = "Cat Printer.lnk"
UNINSTALL_KEY = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\CatPrinterDriver"

MB_YESNO, MB_YESNOCANCEL, MB_ICONINFO, MB_ICONQUESTION, MB_ICONWARNING = 0x4, 0x3, 0x40, 0x20, 0x30
IDYES, IDNO = 6, 7
RUN_WITHOUT_INSTALL = "run"  # Rückgabe von install(): Nutzer will ohne Installation starten


def _box(text, flags=MB_ICONINFO):
    return ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, flags)


def _ps(script, timeout=60):
    """PowerShell ohne Fenster ausführen, Ausgabe zurückgeben."""
    result = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                            capture_output=True, text=True, timeout=timeout,
                            creationflags=subprocess.CREATE_NO_WINDOW)
    return result.stdout.strip()


def _q(text):
    return "'" + str(text).replace("'", "''") + "'"


def _special(folder):
    return _ps(f"[Environment]::GetFolderPath('{folder}')")


def is_installed_copy():
    return os.path.normcase(os.path.abspath(sys.executable)) == os.path.normcase(INSTALLED_EXE)


# ---------------------------------------------------------------- laufende Instanz

def _base_url():
    cfg = load_config()
    return f"http://{cfg['http_host']}:{cfg['http_port']}/", cfg["http_port"]


def _port_owner(port):
    out = _ps(f"(Get-NetTCPConnection -State Listen -LocalPort {port} -ErrorAction SilentlyContinue |"
              " Select-Object -First 1).OwningProcess")
    return int(out) if out.isdigit() else None


def _wait_for_server(url, seconds=20):
    for _ in range(seconds * 2):
        try:
            with urllib.request.urlopen(url + "status.json", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except OSError:
            pass
        time.sleep(0.5)
    return False


def stop_running():
    """Beendet einen laufenden Cat-Printer-Server (neue Version per HTTP, ältere notfalls hart)."""
    url, port = _base_url()
    try:
        req = urllib.request.Request(url + "action/quit", data=b"{}", method="POST",
                                     headers={"X-CatPrinter": "1", "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=3).close()
    except OSError:
        pass
    for _ in range(20):
        if _port_owner(port) is None:
            return
        time.sleep(0.5)
    pid = _port_owner(port)
    if pid:
        name = _ps(f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue).ProcessName").lower()
        # Nur eigene Prozesse beenden (exe oder die Python-Variante), nie fremde Programme
        if name in ("catprinter", "pythonw", "python"):
            log.info("Beende alten Server (PID %s, %s)", pid, name)
            _ps(f"Stop-Process -Id {pid} -Force")
            time.sleep(1)


# ---------------------------------------------------------------- Bausteine

def _shortcut(path, target, args="", description=""):
    _ps(f"$s = (New-Object -ComObject WScript.Shell).CreateShortcut({_q(path)}); "
        f"$s.TargetPath = {_q(target)}; $s.Arguments = {_q(args)}; "
        f"$s.WorkingDirectory = {_q(os.path.dirname(target))}; $s.IconLocation = {_q(target + ',0')}; "
        f"$s.Description = {_q(description)}; $s.Save()")


def _register_uninstall():
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
        values = {
            "DisplayName": "Cat Printer (CatPrinterDriver)",
            "DisplayVersion": __version__,
            "DisplayIcon": INSTALLED_EXE,
            "Publisher": "dasistdaniel",
            "InstallLocation": INSTALL_DIR,
            "UninstallString": f'"{INSTALLED_EXE}" uninstall',
            "URLInfoAbout": "https://github.com/dasistdaniel/CatPrinter",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)
        size_kb = os.path.getsize(INSTALLED_EXE) // 1024
        winreg.SetValueEx(key, "EstimatedSize", 0, winreg.REG_DWORD, size_kb)


def printer_exists():
    return _ps(f"if (Get-Printer -Name {_q(PRINTER_NAME)} -ErrorAction SilentlyContinue) {{ 'ja' }}") == "ja"


def add_printer():
    """Legt den Windows-Drucker an (UAC). Der Server muss dabei laufen. True bei Erfolg."""
    url, _port = _base_url()
    _elevated(f"Add-Printer -Name {_q(PRINTER_NAME)} -IppURL {_q(url.rstrip('/') + '/ipp/print')}")
    return printer_exists()


def _elevated(script):
    """Führt PowerShell mit Adminrechten aus (UAC-Abfrage). False, wenn abgelehnt."""
    inner = script.replace('"', '\\"')
    out = _ps("try { Start-Process powershell -Verb RunAs -Wait -WindowStyle Hidden -ArgumentList "
              f"'-NoProfile','-Command',\"{inner}\"; 'ok' }} catch {{ 'abgelehnt' }}", timeout=300)
    return out.endswith("ok")


def _copy_self():
    os.makedirs(INSTALL_DIR, exist_ok=True)
    for _ in range(20):  # die alte exe kann nach dem Beenden noch kurz gesperrt sein
        try:
            shutil.copy2(sys.executable, INSTALLED_EXE)
            return
        except PermissionError:
            time.sleep(0.5)
    shutil.copy2(sys.executable, INSTALLED_EXE)


# ---------------------------------------------------------------- Ablauf

def _use_configured_language():
    i18n.set_language(load_config().get("language", "auto"))


def install(ask=True):
    _use_configured_language()
    update = os.path.exists(INSTALLED_EXE)
    if ask:
        text = t("update_question" if update else "install_question", version=__version__) + "\n\n"
        text += t("install_steps", dir=INSTALL_DIR)
        if not printer_exists():
            text += t("install_step_printer")
        text += t("install_choice")
        answer = _box(text, MB_YESNOCANCEL | MB_ICONQUESTION)
        if answer == IDNO:
            return RUN_WITHOUT_INSTALL
        if answer != IDYES:
            return 1

    stop_running()
    _copy_self()
    _shortcut(os.path.join(_special("Startup"), STARTUP_LNK), INSTALLED_EXE, "", "Cat Printer – Druckserver")
    _shortcut(os.path.join(_special("Programs"), STARTMENU_LNK), INSTALLED_EXE, "", "Cat Printer – Status")
    _register_uninstall()

    # Erst den installierten Server starten: Windows fragt den Drucker beim Anlegen ab
    subprocess.Popen([INSTALLED_EXE], cwd=INSTALL_DIR, close_fds=True,
                     creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP)
    url, _port = _base_url()
    running = _wait_for_server(url)

    printer_note = ""
    if not running:
        printer_note = t("server_not_started", dir=CONFIG_DIR)
    elif not printer_exists() and not add_printer():
        printer_note = t("printer_add_failed")
    log.info("Installiert: %s (%s)", INSTALLED_EXE, __version__)
    if ask:
        _box(t("updated" if update else "installed") + t("installed_hint") + printer_note)
    return 0


def uninstall(ask=True):
    _use_configured_language()
    if ask and _box(t("uninstall_question"), MB_YESNO | MB_ICONWARNING) != IDYES:
        return 1
    stop_running()
    for folder, name in (("Startup", STARTUP_LNK), ("Programs", STARTMENU_LNK)):
        try:
            os.remove(os.path.join(_special(folder), name))
        except FileNotFoundError:
            pass
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY)
    except FileNotFoundError:
        pass
    # Drucker und Firewall-Regeln der Netzwerkfreigabe mit einer einzigen Adminabfrage entfernen
    admin_steps = []
    if printer_exists():
        admin_steps.append(f"Remove-Printer -Name {_q(PRINTER_NAME)}")
    if netshare.firewall_any():
        admin_steps.append(netshare.firewall_script(remove=True))
    if admin_steps:
        _elevated("; ".join(admin_steps))

    if ask and os.path.isdir(CONFIG_DIR) and _box(
            t("delete_settings_question", dir=CONFIG_DIR), MB_YESNO | MB_ICONQUESTION) == IDYES:
        shutil.rmtree(CONFIG_DIR, ignore_errors=True)

    # Die laufende exe kann sich nicht selbst löschen: kurz warten lassen, dann Ordner entfernen
    subprocess.Popen(f'cmd /c ping 127.0.0.1 -n 4 >nul & rmdir /s /q "{INSTALL_DIR}"',
                     creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS, close_fds=True)
    if ask:
        _box(t("uninstalled") + ("" if not printer_exists() else t("printer_not_removed")))
    return 0


def status_info():
    """Für Tests/Diagnose: was ist installiert?"""
    return json.dumps({"installed_exe": os.path.exists(INSTALLED_EXE), "printer": printer_exists(),
                       "running_from_install_dir": is_installed_copy()})
