# CatPrinterDriver (Deutsch)

Macht einen günstigen Bluetooth-„Cat Printer“ (YHK-Mini-Thermodrucker, sonst
mit der Handy-App **WalkPrint** benutzt) zu einem normalen Windows-11-Drucker,
der in jedem Programm im Druckdialog auftaucht.

🇬🇧 [English guide](README.md) · 🔧 [Protokoll & technische Notizen (englisch)](docs/PROTOCOL.md)

> [!NOTE]
> **Dieses Projekt wurde mit KI programmiert.** Code, Protokollanalyse und
> Dokumentation stammen von einem KI-Assistenten (Claude von Anthropic, über
> Claude Code) in einer angeleiteten Sitzung und wurden von einem Menschen mit
> echter Hardware getestet (`YHK-…`-Drucker unter Windows 11). Für diesen Aufbau
> funktioniert es, der Code wurde aber nicht Zeile für Zeile von einem
> erfahrenen Entwickler geprüft. Nutzung auf eigene Gefahr.

## Funktionsweise

Es wird kein Kernel-Treiber installiert und nichts signiert. Ein kleiner
lokaler **IPP-Druckserver** läuft im Hintergrund; Windows verbindet sich mit
seinem eingebauten *Microsoft IPP Class Driver* – wie mit einem Netzwerkdrucker.

```
Programm → Windows-Druckdialog → Microsoft IPP Class Driver (PWG-Raster, 203 dpi)
  → catprinter-IPP-Server (127.0.0.1:631) → 384 Punkte, Text-/Foto-Rasterung, Zuschnitt, Drehung
  → ESC/POS → Bluetooth-COM-Port → Drucker
```

## Unterstützte Hardware

Getestet mit einem Drucker, der sich per Bluetooth als **`YHK-XXXXXXXX`**
meldet (58-mm-Papier, 48 mm / 384 Punkte Druckbreite, 203 dpi, Firmware
`V1.01`). Er nutzt *klassisches* Bluetooth (serielles Profil) und ESC/POS.
Andere „Cat Printer“ (GB01/GB02/MX…, MXW01 …) sprechen ganz andere
BLE-Protokolle und werden **nicht** unterstützt. Faustregel: Bekommt der
gekoppelte Drucker in Windows einen Port *„Standardmäßige Seriell-über-Bluetooth-Verbindung (COMx)“*, stehen die Chancen gut.

## Voraussetzungen

- Windows 11 (Windows 10 evtl., ungetestet)
- Python 3.10+
- Drucker in *Einstellungen → Bluetooth und Geräte* gekoppelt

## Einrichtung

```powershell
git clone https://github.com/dasistdaniel/CatPrinterDriver.git
cd CatPrinterDriver
pip install -r requirements.txt
```

1. **Verbindung testen** (Drucker an, *nicht* mit dem Handy verbunden):
   ```powershell
   python -m catprinter status   # Firmware, Akkuspannung, COM-Port
   python -m catprinter test     # Testseite direkt drucken
   ```
2. **Druckserver starten** (Fenster vorerst offen lassen):
   ```powershell
   python -m catprinter serve
   ```
3. **Drucker einmalig in Windows anlegen** – PowerShell **als Administrator**:
   ```powershell
   Add-Printer -Name "Cat Printer" -IppURL "http://127.0.0.1:631/ipp/print"
   ```
4. **Server bei jeder Anmeldung automatisch starten** (optional, ohne Adminrechte):
   ```powershell
   .\autostart.ps1            # Verknüpfung im Autostart-Ordner (läuft unsichtbar per pythonw)
   .\autostart.ps1 -Remove    # wieder entfernen
   ```
   Log: `%APPDATA%\CatPrinterDriver\server.log`. Wird der Projektordner
   verschoben, `autostart.ps1` einfach erneut ausführen.

## Drucken

- Im Druckdialog **„Cat Printer“** wählen.
- **Papierformat:** eines der Rollenformate `48 x 40 / 80 / 150 / 300 mm`.
  A4/A6/Letter gehen auch, werden aber auf 48 mm Breite verkleinert (sehr klein).
- **Ränder** auf 0 bzw. minimal stellen – Standardränder (z. B. 2,5 cm in Word)
  passen nicht auf 48 mm.
- Die **Druckqualität** (im Druckdialog bzw. in den Druckeinstellungen)
  bestimmt, wie Grautöne in schwarze Punkte umgewandelt werden:

  | Qualität | Modus | Ergebnis |
  |---|---|---|
  | Entwurf | `text` | Harte Schwelle – alles gestochen scharf, Grauflächen werden schwarz oder weiß |
  | **Normal** (Standard) | `auto` | Fotos werden gerastert; bei Text und Grafik bleiben Kanten scharf (keine ausgefransten geglätteten Schriften), nur gleichmäßige Grauflächen (Füllungen, Verläufe) werden gerastert |
  | Hoch | `photo` | Alles gerastert (Floyd-Steinberg) |

  *Automatisch* hält eine Seite für ein Foto, wenn sie viele verschiedene
  Grautöne enthält. Klassische Windows-Programme (GDI) schicken immer „Normal“.
- Weißraum am Seitenende wird automatisch abgeschnitten.
- Standardmäßig wird um 180° gedreht, damit der Ausdruck vom „Gesicht“ des
  Druckers aus richtig herum steht (das Seitenende kommt zuerst heraus).

## Befehle

| Befehl | Zweck |
|---|---|
| `python -m catprinter serve` | IPP-Druckserver starten (Standard) |
| `python -m catprinter serve -v --save-jobs ORDNER` | Ausführliches Log, empfangene Aufträge speichern |
| `python -m catprinter status` | Firmware, Akkuspannung, COM-Port anzeigen |
| `python -m catprinter test` | Testseite direkt drucken (ohne Windows) |
| `python -m catprinter image bild.png` | Bild direkt drucken |
| `python -m catprinter calibrate 15 25 40` | Schwarzfelder mit verschiedenen Druckdichten drucken |
| http://127.0.0.1:631/ | Statusseite mit den letzten Aufträgen |

Optionen: `--port COMx`, `--density N`, `--mode auto|text|photo`, `--log-file DATEI`.

## Einstellungen

`%APPDATA%\CatPrinterDriver\config.json` (wird beim ersten Start angelegt;
nach Änderungen Server neu starten, z. B. ab- und wieder anmelden):

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `com_port` | `null` | fester COM-Port, z. B. `"COM13"`; `null` = automatisch über den Bluetooth-Namen |
| `bluetooth_name` | `"YHK-"` | Namensanfang für die automatische Suche |
| `density` | `40` | Druckdichte/Heizstärke (`1D 49 F0 n`); WalkPrint nutzt 25, 40 sah im Test am besten aus |
| `feed_mm` | `15` | Papiervorschub nach dem Druck (bis über die Abreißkante) |
| `trim_bottom` | `true` | Weißraum am Seitenende abschneiden |
| `rotate_180` | `true` | Ausdruck um 180° drehen |
| `image_mode` | `"auto"` | Modus bei Druckqualität „Normal“: `auto`, `text` oder `photo` |
| `http_host` / `http_port` | `127.0.0.1` / `631` | Adresse des IPP-Servers |
| `printer_name` | `"Cat Printer"` | Name gegenüber Windows |
| `uuid` | zufällig | Identität des Druckers – nicht ändern, sonst hält Windows ihn für ein neues Gerät |

## Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| Auftrag bricht nach ca. 20 s ab | Drucker aus, Akku leer oder mit dem Handy verbunden (nur eine Bluetooth-Verbindung möglich). Die Warteschlange bleibt nicht hängen. |
| Aufträge hängen dauerhaft | Server läuft nicht – starten oder Autostart einrichten. |
| `Add-Printer`: Zugriff verweigert | PowerShell als Administrator starten. |
| Druck zu blass | Akku laden; `density` erhöhen (mit `calibrate` testen). |
| Dünne hellere Linien in großen, komplett schwarzen Flächen | Hardwaregrenze: Zeilen, in denen alle 384 Punkte schwarz sind, bekommen im Akkubetrieb etwas weniger Heizleistung. Text und normale Bilder sind nicht betroffen. |
| Alles entfernen | `Remove-Printer "Cat Printer"` (als Admin), `.\autostart.ps1 -Remove`, Ordner `%APPDATA%\CatPrinterDriver` löschen. |

## Tests

```powershell
python -m unittest discover tests
```

Laufen ohne Drucker (IPP-Codec, PWG-Raster, ESC/POS-Aufbau, kompletter
IPP-Druckauftrag gegen den Server mit Attrappe).

## Lizenz

[MIT](LICENSE)
