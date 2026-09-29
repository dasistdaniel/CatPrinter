<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="docs/logo/catprinter-horizontal-on-dark.svg">
    <img src="docs/logo/catprinter-horizontal.svg" alt="Cat Printer" width="420">
  </picture>
</p>

# CatPrinter (Deutsch)

[![Tests](https://github.com/dasistdaniel/CatPrinter/actions/workflows/tests.yml/badge.svg)](https://github.com/dasistdaniel/CatPrinter/actions/workflows/tests.yml)

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
   [Releases](https://github.com/dasistdaniel/CatPrinter/releases), falls vorhanden,
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
git clone https://github.com/dasistdaniel/CatPrinter.git
cd CatPrinter
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
aus. Der Punkt zeigt den Zustand: 🟢 bereit · 🔵 druckt · 🟠 zu heiß, kühlt ab ·
🔴 Fehler.

Rechtsklick-Menü: Status und Akkustand, *Testseite drucken*, *Akkustand
prüfen*, *Statusseite öffnen* (auch per Doppelklick), *Log öffnen*,
*Einstellungen bearbeiten*, *Sprache*, *Server neu starten* (lädt
`config.json` neu), *Beenden*.

Windows-Benachrichtigungen erscheinen, wenn ein Druck fehlschlägt (z. B.
Drucker aus), wenn der Druckkopf zu heiß ist und beim Akku (siehe unten).

**Sprache:** Tray-Symbol, Benachrichtigungen, Statusseite, Fehlermeldungen,
Installer und gedruckte Testseiten gibt es auf **Deutsch und Englisch**.
Standardmäßig richtet sich die Sprache nach Windows; umstellen lässt sie sich
im Tray-Menü (*Sprache*), mit dem DE | EN-Schalter auf der Statusseite oder in
deren Einstellungen. (Die Log-Datei bleibt deutsch.)

### Akkuwarnung

Der Ladestand wird nach jedem Druck gemessen und, solange nichts gedruckt
wird, **automatisch alle 30 Minuten** (auf der Statusseite einstellbar, 0 =
aus; ist der Drucker aus, passiert nichts). Der Prozentwert ist aus der
Spannung des zweizelligen Li-Ionen-Akkus geschätzt (8,4 V = voll) und steht
im Tray-Tooltip und auf der Statusseite. Benachrichtigungen: einmal bei
*schwach* (15 %, einstellbar), einmal bei *fast leer* (5 %) und *voll
geladen*.

**Laden:** Am USB-Kabel meldet der Drucker die Ladespannung mit, die Prozente
wären dann zu hoch. Der Treiber erkennt das Laden an einem Sprung um
≥ 0,15 V zwischen zwei Messungen in Ruhe (gemessen beim Anstecken:
7,32 → 7,54 V), zeigt dann *„lädt …“* statt einer Prozentzahl, setzt die
Warnungen aus und prüft alle 5 Minuten. Ist die Ladespannung zweimal
hintereinander oben angekommen (≥ 8,35 V), meldet er *voll geladen*. Das
Abstecken erkennt er am erneuten Abfall der Spannung. Der letzte Messwert steht
in `battery.json`, damit das auch über einen Neustart hinweg funktioniert.

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

## Drucken vom Handy (optional, standardmäßig aus)

In den Einstellungen auf der Statusseite **„Im Heimnetz freigeben“**
einschalten. Der PC gibt den Drucker dann im WLAN als **„Cat Printer @
<PC-Name>“** bekannt (mDNS/Bonjour, wie ein Netzwerkdrucker), und Handys
können ohne zusätzliche App darauf drucken:

- **Android:** *Einstellungen → Verbundene Geräte → Verbindungseinstellungen →
  Drucken → Standard-Druckdienst* muss an sein. Dann aus einer beliebigen App
  drucken (z. B. Google Fotos: ⋮ → Drucken), *Alle Drucker* wählen und
  „Cat Printer @ …“ auswählen. Eines der 48-mm-Papierformate einstellen.
- iOS/AirPrint ist nicht getestet.

Hinweise:

- Beim ersten Einschalten fragt Windows nach Adminrechten für zwei
  Firewall-Regeln (TCP 631, UDP 5353) – **nur für private Netzwerke**. Ist das
  Netzwerk als *öffentlich* eingestuft, erreichen Handys den PC nicht; die
  Statusseite warnt dann.
- Aus dem Netz ist **nur Drucken** möglich, und nur von privaten Adressen.
  Statusseite, Einstellungen und Verlauf bleiben auf diesem PC. Solange die
  Freigabe an ist, kann jeder im Heimnetz drucken.
- Der PC muss laufen und Cat Printer gestartet sein.
- Windows 11 richtet den bekannt gegebenen Drucker eventuell automatisch als
  zweiten Netzwerkdrucker ein. Der kann gelöscht werden – „Cat Printer“ ist
  derselbe Drucker.
- **Fotos vom Handy** kommen originalgetreu an, Windows hellt dagegen beim
  Drucken die Schatten von Fotos deutlich auf. Handy-Fotos würden also
  dunkler gedruckt; *„Fotos vom Handy aufhellen wie am PC“* (standardmäßig an)
  wendet dieselbe Tonwertkurve an. *„Foto-Helligkeit“* hellt zusätzlich die
  Mitteltöne aller Fotos auf (Thermopunkte laufen etwas aus, Fotos wirken
  daher oft dunkler als am Bildschirm). Text und Grafik werden nie verändert.

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
| http://127.0.0.1:631/ | Statusseite: Zustand, Akku, letzte Aufträge, änderbare Einstellungen, Knöpfe für Testseite und Akkuprüfung (aktualisiert sich live, hell/dunkel, Umschalter **Deutsch / Englisch** oben rechts) |

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
| `share_network` | `false` | Im Heimnetz freigeben, um vom Handy zu drucken (siehe *Drucken vom Handy*) |
| `match_windows_tone` | `true` | Schatten von Handy-Fotos aufhellen wie Windows |
| `photo_brightness` | `0` | Foto-Helligkeit in Prozent (−30 … +50), nur Fotos |
| `battery_check_minutes` | `30` | Akku alle N Minuten automatisch prüfen, wenn nichts gedruckt wird (0 = aus) |
| `battery_warn_percent` | `15` | Ab diesem Ladestand warnen |
| `language` | `"auto"` | `auto` (wie Windows), `de` oder `en` |
| `http_host` / `http_port` | `127.0.0.1` / `631` | Adresse des IPP-Servers |
| `printer_name` | `"Cat Printer"` | Name gegenüber Windows |
| `uuid` | zufällig | Identität des Druckers – nicht ändern, sonst hält Windows ihn für ein neues Gerät |

## Fehlersuche

| Problem | Ursache / Lösung |
|---|---|
| Auftrag bricht nach ca. 20 s ab | Drucker aus, Akku leer oder mit dem Handy verbunden (nur eine Bluetooth-Verbindung möglich). Die Warteschlange bleibt nicht hängen. |
| WalkPrint-App verbindet sich direkt nach einem Druck nicht | Cat Printer hält die Bluetooth-Verbindung nach dem letzten Druck 90 Sekunden offen (ein neuer Verbindungsaufbau während des Drucks würde das Ende abschneiden). Kurz warten oder Cat Printer über das Tray-Menü beenden. |
| Aufträge hängen dauerhaft | Server läuft nicht (kein Katzen-Symbol im Infobereich) – starten oder Autostart einrichten. |
| `Add-Printer`: Zugriff verweigert | PowerShell als Administrator starten. |
| Druck zu blass | Akku laden; `density` erhöhen (mit `calibrate` testen). |
| Drucker hält mitten im Druck an, Status „Zu heiß – kühlt ab“ | Hitzeschutz nach vielen dunklen Drucken am Stück. Der Drucker pausiert etwa 1–2 Minuten und macht dann von selbst weiter; vor dem nächsten Auftrag wartet der Treiber, bis er abgekühlt ist. Es geht nichts verloren. |
| Fotos zu dunkel | *„Foto-Helligkeit“* auf der Statusseite erhöhen (z. B. +20 %) und mit *„Nochmal drucken“* im Verlauf vergleichen. |
| Handy findet den Drucker nicht | Freigabe an? Gleiches WLAN? Netzwerkprofil *Privat*? Firewall-Regel vorhanden (Statusseite zeigt Warnungen)? Unter Android muss der *Standard-Druckdienst* an sein. |
| Dünne hellere Linien in großen, komplett schwarzen Flächen | Zeilen, in denen alle 384 Punkte schwarz sind, bekommen im Akkubetrieb etwas weniger Heizleistung. Solche Bilder mit angestecktem USB-Kabel (Laden) drucken – im Test waren die Linien dann weg. Text und normale Bilder sind nicht betroffen. |
| „Unbekanntes USB-Gerät“ beim Anstecken | Normal: Der USB-Anschluss lädt nur, er hat keine Datenverbindung. Drucken geht nur über Bluetooth. |
| Alles entfernen | exe: über *Einstellungen → Apps* deinstallieren (entfernt auch die Firewall-Regeln). Python-Variante: `Remove-Printer "Cat Printer"` (als Admin), `.\autostart.ps1 -Remove`, Ordner `%APPDATA%\CatPrinterDriver` löschen. |

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

GitHub Actions (`.github/workflows/tests.yml`) führt sie bei jedem Push und
Pull Request unter Windows mit Python 3.12 und 3.14 aus, baut danach mit
`build.ps1` die exe und hält sie 14 Tage lang zum Herunterladen bereit.

## Lizenz

[MIT](LICENSE)
