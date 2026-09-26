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
- Drucker in *Einstellungen → Bluetooth und Geräte* gekoppelt
- Nur für die Python-Variante: Python 3.10+

## Installation (Windows-Programm)

1. `CatPrinter.exe` besorgen – von der Seite
   [Releases](https://github.com/dasistdaniel/CatPrinterDriver/releases), falls vorhanden,
   oder selbst bauen (siehe *exe bauen*).
2. Doppelklicken und **Installieren** bestätigen. Das Programm
   - kopiert sich nach `%LOCALAPPDATA%\Programs\CatPrinter` (ohne Adminrechte),
   - startet bei jeder Anmeldung (Tray-Symbol) und bekommt einen Startmenü-Eintrag,
   - legt den Drucker **„Cat Printer“** in Windows an, falls er noch fehlt –
     nur dafür fragt Windows nach Adminrechten,
   - erscheint unter *Einstellungen → Apps* zum Deinstallieren.
3. In jedem Programm auf „Cat Printer“ drucken.

**Aktualisieren:** einfach eine neuere `CatPrinter.exe` starten – sie ersetzt
die installierte; Einstellungen, Verlauf und der Windows-Drucker bleiben.
**Deinstallieren:** *Einstellungen → Apps → Cat Printer (CatPrinterDriver)*.
Entfernt den Drucker (Adminabfrage) und fragt, ob Einstellungen, Log und
Verlauf gelöscht werden sollen.

### Ohne Installation (portabel)

- **Einfach nur starten:** Im Installationsdialog **Nein** wählen – die exe
  läuft dann von ihrem Ort aus, ohne Autostart, Startmenü-Eintrag oder Kopie.
  Einstellungen liegen wie gewohnt in `%APPDATA%\CatPrinterDriver`.
- **Voll portabel** (z. B. auf einem USB-Stick): eine leere Datei namens
  `portable` neben die exe legen oder die exe z. B. `CatPrinter-portable.exe`
  nennen. Dann fragt sie nie nach Installation und speichert Einstellungen,
  Log und Verlauf im Ordner `CatPrinterData` neben der exe – auf dem PC wird
  nichts eingetragen.

Für den Druck aus anderen Programmen braucht es trotzdem den Windows-Drucker
„Cat Printer“. Fehlt er, bietet die portable exe beim Start an, ihn anzulegen
(Adminabfrage), und zeigt im Tray-Menü *Windows-Drucker einrichten*. Ist Cat
Printer auf dem PC auch installiert, nutzt die portable Kopie denselben
Drucker. Entfernen: Ordner löschen und – falls der Drucker angelegt wurde –
als Administrator `Remove-Printer "Cat Printer"` ausführen.

> [!WARNING]
> Die exe ist **nicht signiert**. Nach dem Herunterladen zeigt Windows
> SmartScreen eventuell *„Der Computer wurde durch Windows geschützt“* –
> *Weitere Informationen → Trotzdem ausführen* klicken. Manche Virenscanner
> melden mit PyInstaller gebaute Programme fälschlich. Wer das nicht möchte,
> baut die exe selbst oder nutzt die Python-Variante.

## Python-Variante (aus dem Quellcode)

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
4. **Bei jeder Anmeldung automatisch starten** (optional, ohne Adminrechte):
   ```powershell
   .\autostart.ps1            # Verknüpfung im Autostart-Ordner: Server + Tray-Symbol, ohne Konsolenfenster
   .\autostart.ps1 -Remove    # wieder entfernen
   ```
   Log: `%APPDATA%\CatPrinterDriver\server.log`. Wird der Projektordner
   verschoben, `autostart.ps1` einfach erneut ausführen. (Nicht zusammen mit
   der installierten exe nutzen – beide verwenden denselben Autostart-Eintrag.)

## Tray-Symbol

Die installierte exe (oder `python -m catprinter tray`) führt den
Druckserver zusammen mit einem Katzen-Symbol im Infobereich der Taskleiste
aus. Der Punkt zeigt den Zustand: 🟢 bereit · 🔵 druckt · 🔴 Fehler.

Rechtsklick-Menü: Status und Akkuspannung (wird nach jedem Druck gemessen),
*Testseite drucken*, *Akkustand prüfen*, *Statusseite öffnen* (auch per
Doppelklick), *Log öffnen*, *Einstellungen bearbeiten*, *Server neu starten*
(lädt `config.json` neu), *Beenden*.

Windows-Benachrichtigungen erscheinen, wenn ein Druck fehlschlägt (z. B.
Drucker aus) und wenn der Akku unter 6,8 V fällt.

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

## Verlauf (optional, standardmäßig aus)

Aus Datenschutzgründen werden gedruckte Seiten **nicht** gespeichert, solange
du den *Verlauf* nicht in den Einstellungen auf der Statusseite einschaltest.
Ist er an, wird von jeder gedruckten Seite eine Kopie (Graustufen in
Druckbreite, nicht das Originaldokument) in `%APPDATA%\CatPrinterDriver\history`
aufbewahrt – höchstens die letzten 30 Aufträge. Die Statusseite zeigt sie mit
Vorschaubild; per Klick siehst du, wie sie gedruckt aussehen, und kannst sie
*nochmal drucken* (auch fehlgeschlagene, z. B. weil der Drucker aus war).
Einträge lassen sich einzeln oder alle auf einmal löschen. **Beim Ausschalten
wird der gesamte Verlauf sofort gelöscht.**

Statusseite und Verlauf werden nur für Anfragen an `127.0.0.1`/`localhost`
ausgeliefert (Schutz vor DNS-Rebinding), Aktionen brauchen eine eigene
Kennung – fremde Webseiten können also weder mitlesen noch drucken.

## Befehle

| Befehl | Zweck |
|---|---|
| `python -m catprinter serve` | IPP-Druckserver in der Konsole starten (Standard) |
| `python -m catprinter tray` | Druckserver mit Tray-Symbol starten (Log in `%APPDATA%\CatPrinterDriver\server.log`) |
| `python -m catprinter serve -v --save-jobs ORDNER` | Ausführliches Log, empfangene Aufträge speichern |
| `python -m catprinter status` | Firmware, Akkuspannung, COM-Port anzeigen |
| `python -m catprinter test` | Testseite direkt drucken (ohne Windows) |
| `python -m catprinter image bild.png` | Bild direkt drucken |
| `python -m catprinter calibrate 15 25 40` | Schwarzfelder mit verschiedenen Druckdichten drucken |
| http://127.0.0.1:631/ | Statusseite: Zustand, Akku, letzte Aufträge, änderbare Einstellungen, Knöpfe für Testseite und Akkuprüfung (aktualisiert sich live, hell/dunkel) |

Optionen: `--port COMx`, `--density N`, `--mode auto|text|photo`, `--log-file DATEI`.

## Einstellungen

Am einfachsten über die **Statusseite** (http://127.0.0.1:631/ oder
Doppelklick auf das Tray-Symbol): Dort lassen sich Druckdichte, Bildmodus,
Drehung, Vorschub, Zuschnitt und Verbindung ändern. Änderungen gelten sofort
ab dem nächsten Druck und werden gespeichert. *Probe drucken* druckt ein
Testfeld mit der Dichte vom Schieberegler, damit du Werte vor dem Speichern
ausprobieren kannst.

Alle Einstellungen stehen in `%APPDATA%\CatPrinterDriver\config.json` (wird
beim ersten Start angelegt; nach Änderungen von Hand im Tray-Menü *Server neu
starten* wählen):

| Schlüssel | Standard | Bedeutung |
|---|---|---|
| `com_port` | `null` | fester COM-Port, z. B. `"COM13"`; `null` = automatisch über den Bluetooth-Namen |
| `bluetooth_name` | `"YHK-"` | Namensanfang für die automatische Suche |
| `density` | `40` | Druckdichte/Heizstärke (`1D 49 F0 n`); WalkPrint nutzt 25, 40 sah im Test am besten aus |
| `feed_mm` | `15` | Papiervorschub nach dem Druck (bis über die Abreißkante) |
| `trim_bottom` | `true` | Weißraum am Seitenende abschneiden |
| `rotate_180` | `true` | Ausdruck um 180° drehen |
| `image_mode` | `"auto"` | Modus bei Druckqualität „Normal“: `auto`, `text` oder `photo` |
| `keep_history` | `false` | Kopien gedruckter Seiten zum Ansehen/Nachdrucken aufbewahren (siehe *Verlauf*) |
| `http_host` / `http_port` | `127.0.0.1` / `631` | Adresse des IPP-Servers |
| `printer_name` | `"Cat Printer"` | Name gegenüber Windows |
| `uuid` | zufällig | Identität des Druckers – nicht ändern, sonst hält Windows ihn für ein neues Gerät |

## Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| Auftrag bricht nach ca. 20 s ab | Drucker aus, Akku leer oder mit dem Handy verbunden (nur eine Bluetooth-Verbindung möglich). Die Warteschlange bleibt nicht hängen. |
| Aufträge hängen dauerhaft | Server läuft nicht (kein Katzen-Symbol im Infobereich) – starten oder Autostart einrichten. |
| `Add-Printer`: Zugriff verweigert | PowerShell als Administrator starten. |
| Druck zu blass | Akku laden; `density` erhöhen (mit `calibrate` testen). |
| Dünne hellere Linien in großen, komplett schwarzen Flächen | Zeilen, in denen alle 384 Punkte schwarz sind, bekommen im Akkubetrieb etwas weniger Heizleistung. Solche Bilder mit angestecktem USB-Kabel (Laden) drucken – im Test waren die Linien dann weg. Text und normale Bilder sind nicht betroffen. |
| „Unbekanntes USB-Gerät“ beim Anstecken | Normal: Der USB-Anschluss lädt nur, er hat keine Datenverbindung. Drucken geht nur über Bluetooth. |
| Alles entfernen | exe: über *Einstellungen → Apps* deinstallieren. Python-Variante: `Remove-Printer "Cat Printer"` (als Admin), `.\autostart.ps1 -Remove`, Ordner `%APPDATA%\CatPrinterDriver` löschen. |

## exe bauen

```powershell
pip install -r requirements.txt pyinstaller
.\build.ps1
```

Führt die Tests aus, erzeugt das Symbol und baut mit PyInstaller
`dist\CatPrinter.exe` (eine Datei, ca. 28 MB, ohne Konsolenfenster). Ein
Doppelklick außerhalb des Installationsordners startet die Installation, die
installierte Kopie startet das Tray-Symbol. `CatPrinter.exe install` bzw.
`CatPrinter.exe uninstall` machen dasselbe ausdrücklich.

## Tests

```powershell
python -m unittest discover tests
```

Laufen ohne Drucker (IPP-Codec, PWG-Raster, ESC/POS-Aufbau, kompletter
IPP-Druckauftrag gegen den Server mit Attrappe).

## Lizenz

[MIT](LICENSE)
