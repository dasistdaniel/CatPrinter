"""Texte für Tray-Symbol, Benachrichtigungen, Fehlermeldungen, Installer und Testseiten.

Sprache: Einstellung "language" = "auto" (Windows-Sprache), "de" oder "en".
Log-Meldungen bleiben deutsch (Fehlersuche).
"""
import ctypes
import locale

LANGUAGES = ("auto", "de", "en")

TEXTS = {
    # ------------------------------------------------------------ Drucker
    "page_too_long": ("Seite zu lang ({rows} Zeilen, maximal {max})",
                      "Page too long ({rows} rows, max. {max})"),
    "no_printer": ("Kein gekoppelter Drucker '{prefix}*' mit COM-Port gefunden",
                   "No paired printer '{prefix}*' with a COM port found"),
    "port_open_failed": ("{port} lässt sich nicht öffnen (Drucker aus oder mit dem Handy verbunden?): {err}",
                         "Can't open {port} (printer off or connected to the phone?): {err}"),
    "connection_lost": ("Verbindung zum Drucker verloren: {err}", "Lost connection to the printer: {err}"),
    "no_connection": ("Keine Verbindung zum Drucker: {err}", "No connection to the printer: {err}"),
    "connection_broken": ("Verbindung während des Drucks abgebrochen: {err}",
                          "Connection lost while printing: {err}"),
    # ------------------------------------------------------------ Einstellungen (Server)
    "density_range": ("Druckdichte muss eine ganze Zahl von 5 bis 80 sein",
                      "Print density must be a whole number from 5 to 80"),
    "feed_range": ("Vorschub muss eine ganze Zahl von 0 bis 50 mm sein",
                   "Paper feed must be a whole number from 0 to 50 mm"),
    "battery_check_range": ("Akkuprüfung: 0 (aus) bis 240 Minuten", "Battery check: 0 (off) to 240 minutes"),
    "battery_warn_range": ("Akkuwarnung: 5 bis 50 Prozent", "Battery warning: 5 to 50 percent"),
    "brightness_range": ("Foto-Helligkeit muss eine ganze Zahl von -30 bis 50 sein",
                         "Photo brightness must be a whole number from -30 to 50"),
    "unknown_mode": ("Unbekannter Bildmodus", "Unknown image mode"),
    "unknown_language": ("Unbekannte Sprache", "Unknown language"),
    "must_bool": ("{key} muss true oder false sein", "{key} must be true or false"),
    "com_port_format": ("COM-Port muss wie COM13 aussehen oder leer sein (automatisch)",
                        "COM port must look like COM13 or be empty (automatic)"),
    "bt_name_empty": ("Bluetooth-Name darf nicht leer sein", "Bluetooth name must not be empty"),
    "not_editable": ("Einstellung {key} kann hier nicht geändert werden", "Setting {key} can't be changed here"),
    "invalid_data": ("Ungültige Daten: {err}", "Invalid data: {err}"),
    "json_object": ("JSON-Objekt erwartet", "JSON object expected"),
    "entry_not_found": ("Eintrag nicht gefunden", "Entry not found"),
    "format_unsupported": ("Format {fmt} nicht unterstützt", "Format {fmt} not supported"),
    "job_not_found": ("Auftrag nicht gefunden", "Job not found"),
    "job_not_cancelable": ("Auftrag kann nicht mehr abgebrochen werden", "Job can no longer be canceled"),
    # ------------------------------------------------------------ Druckerstatus für Windows
    "state_ready": ("Bereit", "Ready"),
    "state_printing": ("Druckt", "Printing"),
    "state_cooling": ("Drucker zu heiß – kühlt ab, druckt dann weiter", "Printer too hot – cooling down, then continues"),
    "state_charged": ("Akku voll (am Ladekabel)", "Battery full (on the charger)"),
    "state_charging": ("Akku wird geladen", "Battery charging"),
    "state_battery_critical": ("Akku fast leer ({percent} %) – bitte per USB laden",
                               "Battery almost empty ({percent} %) – please charge via USB"),
    "state_battery_low": ("Akku schwach ({percent} %) – bitte per USB laden",
                          "Battery low ({percent} %) – please charge via USB"),
    # ------------------------------------------------------------ Tray: Zustände und Menü
    "label_ready": ("Bereit", "Ready"),
    "label_printing": ("Druckt …", "Printing …"),
    "label_cooling": ("Zu heiß – kühlt ab …", "Too hot – cooling down …"),
    "label_error": ("Fehler", "Error"),
    "battery": ("Akku", "Battery"),
    "status": ("Status", "Status"),
    "battery_unknown": ("unbekannt", "unknown"),
    "battery_not_measured": ("noch nicht gemessen", "not measured yet"),
    "battery_charging": ("lädt …", "charging …"),
    "battery_charged": ("voll (am Ladekabel)", "full (on the charger)"),
    "battery_almost_empty": ("fast leer!", "almost empty!"),
    "battery_low_suffix": ("schwach", "low"),
    "menu_test_page": ("Testseite drucken", "Print test page"),
    "menu_check_battery": ("Akkustand prüfen", "Check battery"),
    "menu_status_page": ("Statusseite öffnen", "Open status page"),
    "menu_log": ("Log öffnen", "Open log"),
    "menu_settings": ("Einstellungen bearbeiten", "Edit settings"),
    "menu_restart": ("Server neu starten", "Restart server"),
    "menu_setup_printer": ("Windows-Drucker einrichten …", "Set up Windows printer …"),
    "menu_language": ("Sprache / Language", "Language / Sprache"),
    "menu_language_auto": ("Automatisch (Windows)", "Automatic (Windows)"),
    "menu_quit": ("Beenden", "Quit"),
    # ------------------------------------------------------------ Tray: Benachrichtigungen
    "restart_failed": ("Server konnte nicht neu starten – Port belegt.", "Server couldn't restart – port in use."),
    "settings_reloaded": ("Einstellungen neu geladen.", "Settings reloaded."),
    "firewall_failed": ("Firewall-Regel wurde nicht angelegt (Adminrechte abgelehnt?) – "
                        "Handys erreichen den Drucker dann nicht.",
                        "Firewall rule was not added (admin rights declined?) – phones can't reach the printer."),
    "shared_on": ("Im Heimnetz freigegeben – auf dem Handy als „{name}“ wählbar.",
                  "Shared on the home network – choose “{name}” on your phone."),
    "shared_off": ("Netzwerkfreigabe ausgeschaltet.", "Network sharing turned off."),
    "hot_title": ("Cat Printer kühlt ab", "Cat Printer is cooling down"),
    "hot_text": ("Der Druckkopf ist zu heiß (viele dunkle Flächen am Stück). ",
                 "The print head is too hot (many dark areas in a row). "),
    "hot_waiting": ("Der nächste Druck startet, sobald er abgekühlt ist – meist nach 1–2 Minuten.",
                    "The next print starts once it has cooled down – usually after 1–2 minutes."),
    "hot_paused": ("Der Drucker pausiert kurz und druckt dann von selbst weiter.",
                   "The printer pauses briefly and then continues by itself."),
    "print_failed_title": ("Druck fehlgeschlagen", "Print failed"),
    "print_failed": ("„{name}“ wurde nicht gedruckt.\n{err}", "“{name}” was not printed.\n{err}"),
    "unreachable_title": ("Drucker nicht erreichbar", "Printer not reachable"),
    "battery_critical_title": ("Cat Printer: Akku fast leer", "Cat Printer: battery almost empty"),
    "battery_critical_text": ("Akku fast leer ({percent} %) – bitte jetzt per USB laden. "
                              "Drucke werden blass, der Drucker kann sich bald abschalten.",
                              "Battery almost empty ({percent} %) – please charge via USB now. "
                              "Prints get faint and the printer may switch off soon."),
    "battery_low_title": ("Cat Printer: Akku schwach", "Cat Printer: battery low"),
    "battery_low_text": ("Akku schwach ({percent} %) – bitte bald per USB laden, sonst werden Drucke blasser.",
                         "Battery low ({percent} %) – please charge via USB soon, otherwise prints get fainter."),
    "battery_full_text": ("Der Akku ist voll geladen – das USB-Kabel kann ab.",
                          "The battery is fully charged – you can unplug the USB cable."),
    "printer_missing": ("Der Windows-Drucker „Cat Printer“ fehlt noch – ohne ihn taucht der Drucker nicht im "
                        "Druckdialog auf.\n\nJetzt anlegen? Windows fragt dafür nach Adminrechten.",
                        "The Windows printer “Cat Printer” is missing – without it the printer doesn't appear in "
                        "print dialogs.\n\nAdd it now? Windows will ask for admin rights."),
    "printer_missing_later": ("\n\n(Später geht das auch über das Tray-Menü.)",
                              "\n\n(You can also do this later from the tray menu.)"),
    "printer_added": ("Drucker „Cat Printer“ ist eingerichtet.", "Printer “Cat Printer” has been set up."),
    "printer_not_added": ("Drucker wurde nicht angelegt (Adminrechte abgelehnt?).",
                          "Printer was not added (admin rights declined?)."),
    "port_in_use": ("Port {port} ist von einem anderen Programm belegt.\nDer Cat-Printer-Server kann nicht starten.",
                    "Port {port} is used by another program.\nThe Cat Printer server can't start."),
    "language_changed": ("Sprache: Deutsch", "Language: English"),
    # ------------------------------------------------------------ Installer
    "install_question": ("Cat Printer {version} installieren?", "Install Cat Printer {version}?"),
    "update_question": ("Cat Printer {version} aktualisieren?", "Update Cat Printer {version}?"),
    "install_steps": ("• Programm nach {dir}\n• Start bei der Anmeldung (Symbol im Infobereich)\n"
                      "• Eintrag im Startmenü und unter „Apps & Features“\n",
                      "• Program to {dir}\n• Starts at logon (icon in the notification area)\n"
                      "• Entry in the Start menu and in “Apps & Features”\n"),
    "install_step_printer": ("• Drucker „Cat Printer“ in Windows anlegen (Windows fragt nach Adminrechten)\n",
                             "• Add the printer “Cat Printer” to Windows (Windows asks for admin rights)\n"),
    "install_choice": ("\nJa = installieren\nNein = ohne Installation starten (nur jetzt, kein Autostart)\n"
                       "Abbrechen = nichts tun",
                       "\nYes = install\nNo = run without installing (just now, no autostart)\nCancel = do nothing"),
    "server_not_started": ("\n\nDer Server ist nicht gestartet – siehe Log in {dir}",
                           "\n\nThe server did not start – see the log in {dir}"),
    "printer_add_failed": ("\n\nDer Drucker konnte nicht angelegt werden (Adminrechte abgelehnt?). "
                           "Starte die Installation erneut, um es nochmal zu versuchen.",
                           "\n\nThe printer could not be added (admin rights declined?). "
                           "Run the installation again to retry."),
    "installed": ("Cat Printer ist installiert.", "Cat Printer is installed."),
    "updated": ("Cat Printer ist aktualisiert.", "Cat Printer has been updated."),
    "installed_hint": ("\n\nWähle im Druckdialog eines beliebigen Programms „Cat Printer“. "
                       "Das Katzen-Symbol im Infobereich zeigt Status und Akku.",
                       "\n\nChoose “Cat Printer” in the print dialog of any program. "
                       "The cat icon in the notification area shows status and battery."),
    "uninstall_question": ("Cat Printer deinstallieren?\n\nDer Drucker „Cat Printer“ (und ggf. die Firewall-Regeln "
                           "der Netzwerkfreigabe) werden aus Windows entfernt – Windows fragt nach Adminrechten.",
                           "Uninstall Cat Printer?\n\nThe printer “Cat Printer” (and the firewall rules for network "
                           "sharing, if any) will be removed from Windows – Windows asks for admin rights."),
    "delete_settings_question": ("Auch Einstellungen, Log und Verlauf löschen?\n{dir}",
                                 "Also delete settings, log and history?\n{dir}"),
    "uninstalled": ("Cat Printer wurde deinstalliert.", "Cat Printer has been uninstalled."),
    "printer_not_removed": ("\n\nDer Drucker „Cat Printer“ konnte nicht entfernt werden.",
                            "\n\nThe printer “Cat Printer” could not be removed."),
    "portable_no_install": ("Das ist die portable Variante – sie wird nicht installiert.\n"
                            "Zum Installieren die Datei „portable“ neben der exe entfernen bzw. die exe umbenennen.",
                            "This is the portable version – it is not installed.\n"
                            "To install, remove the file “portable” next to the exe or rename the exe."),
    "install_error": ("Fehler bei der Installation:\n{err}\n\nDetails im Log: {dir}",
                      "Installation failed:\n{err}\n\nDetails in the log: {dir}"),
    "uninstall_error": ("Fehler bei der Deinstallation:\n{err}\n\nDetails im Log: {dir}",
                        "Uninstall failed:\n{err}\n\nDetails in the log: {dir}"),
    # ------------------------------------------------------------ Gedruckte Testseiten
    "test_page": ("Testseite", "Test page"),
    "test_line": ("Zeile {n:02d}: Das ist ein langer Testdruck", "Line {n:02d}: this is a long test print"),
    "test_end": ("ENDE", "END"),
    "test_page_short": ("Testseite %d.%m.%Y %H:%M", "Test page %Y-%m-%d %H:%M"),
    "density_label": ("Dichte {d}", "Density {d}"),
    "battery_info": ("Akku {v}", "Battery {v}"),
    "sample_job": ("Probedruck Dichte {d}", "Sample density {d}"),
}

_setting = "auto"


def system_language():
    """Windows-Anzeigesprache: Deutsch -> "de", sonst "en"."""
    try:
        langid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        return "de" if langid & 0x3FF == 0x07 else "en"
    except (AttributeError, OSError):
        loc = (locale.getlocale()[0] or "").lower()
        return "de" if loc.startswith(("de", "german")) else "en"


def set_language(value):
    global _setting
    _setting = value if value in LANGUAGES else "auto"


def current():
    return system_language() if _setting == "auto" else _setting


def t(text_id, /, **kwargs):
    texts = TEXTS.get(text_id)
    if texts is None:
        return text_id
    text = texts[0] if current() == "de" else texts[1]
    return text.format(**kwargs) if kwargs else text


def volts(value):
    """7.18 -> "7,18 V" bzw. "7.18 V"."""
    text = f"{value:.2f} V"
    return text.replace(".", ",") if current() == "de" else text
