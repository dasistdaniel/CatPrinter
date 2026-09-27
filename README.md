# CatPrinterDriver

Use a cheap Bluetooth "cat printer" (YHK-series mini thermal printer, normally
used with the **WalkPrint** phone app) as a regular Windows 11 printer – it
shows up in the print dialog of every application.

🇩🇪 [Deutsche Anleitung](README.de.md) · 🔧 [Protocol & technical notes](docs/PROTOCOL.md)

> [!NOTE]
> **This project was programmed with AI.** The code, the protocol analysis and
> this documentation were written by an AI assistant (Anthropic's Claude, via
> Claude Code) in a guided session, and tested by a human on real hardware
> (a `YHK-…` printer on Windows 11). It works for that setup, but it has not
> been reviewed line by line by an experienced developer. Use at your own risk.

## How it works

No kernel driver and no driver signing are involved. The project runs a tiny
local **IPP printer server**; Windows connects to it with its built-in
*Microsoft IPP Class Driver*, exactly as it would to a network printer.

```
Any application
  → Windows print dialog
  → Microsoft IPP Class Driver   (renders each page to PWG raster, 203 dpi, grayscale)
  → catprinter IPP server        (http://127.0.0.1:631/ipp/print)
      scales to 384 dots · text/photo-aware dithering · trims blank space · rotates
  → ESC/POS raster commands
  → Bluetooth serial port (SPP, e.g. COM13)
  → printer
```

## Supported hardware

Tested with a printer that advertises itself as **`YHK-XXXXXXXX`** over
Bluetooth (cat/bear-shaped case, 58 mm paper, 48 mm / 384 dots print width,
203 dpi, firmware `V1.01`). It uses *Classic* Bluetooth (serial port profile)
and speaks ESC/POS.

Other "cat printers" (GB01/GB02/MX…, MXW01, …) use completely different BLE
protocols and are **not** supported. Quick check: if your printer, once paired
in Windows, gets a *"Standard Serial over Bluetooth link (COMx)"* port, it may
work.

## Requirements

- Windows 11 (Windows 10 might work, untested)
- The printer paired in *Settings → Bluetooth & devices*
- Only for running from source: Python 3.10+ ([python.org](https://www.python.org/))

## Installation (Windows program)

1. Get `CatPrinter.exe` – from the [Releases](https://github.com/dasistdaniel/CatPrinterDriver/releases)
   page if available, or build it yourself (see *Building the exe*).
2. Double-click it and confirm **Install**. It
   - copies itself to `%LOCALAPPDATA%\Programs\CatPrinter` (no admin rights needed),
   - starts automatically at logon (tray icon) and adds a Start menu entry,
   - adds the printer **"Cat Printer"** to Windows if it doesn't exist yet –
     this is the only step that asks for administrator rights,
   - registers itself under *Settings → Apps* for uninstalling.
3. Print from any program to "Cat Printer".

To **update**, simply run a newer `CatPrinter.exe` – it replaces the installed
copy; settings, history and the Windows printer are kept.
To **uninstall**, use *Settings → Apps → Cat Printer (CatPrinterDriver)*. It
removes the printer (admin prompt) and asks whether to delete settings,
log and history.

### Without installing (portable)

- **Just run it once:** in the install dialog choose **No** – the exe starts
  from where it is, without autostart, Start menu entry or copying itself.
  Settings are stored in `%APPDATA%\CatPrinterDriver` as usual.
- **Fully portable** (e.g. on a USB stick): put an empty file named
  `portable` next to the exe, or name the exe e.g. `CatPrinter-portable.exe`.
  It then never asks to install and keeps settings, log and history in a
  `CatPrinterData` folder next to the exe – nothing is registered on the PC.

The Windows printer "Cat Printer" is still needed to print from other
programs. If it is missing, the portable exe offers to add it on start
(admin prompt) and shows *Set up Windows printer* in the tray menu. On a PC
where Cat Printer is also installed, the portable copy reuses the installed
printer. To remove a portable copy, delete its folder and, if you added the
printer, run `Remove-Printer "Cat Printer"` as administrator.

> [!WARNING]
> The exe is **not code-signed**. When you download it, Windows SmartScreen
> may show *"Windows protected your PC"* – click *More info → Run anyway*.
> Some antivirus programs also flag PyInstaller-built executables by mistake.
> If you prefer, build the exe yourself or run from source.

## Running from source (Python)

```powershell
git clone https://github.com/dasistdaniel/CatPrinterDriver.git
cd CatPrinterDriver
pip install -r requirements.txt
```

1. **Test the connection** (printer switched on, *not* connected to the phone app):
   ```powershell
   python -m catprinter status   # firmware, battery voltage, COM port
   python -m catprinter test     # prints a test page directly
   ```
2. **Start the print server** (keep the window open for now):
   ```powershell
   python -m catprinter serve
   ```
3. **Add the printer to Windows** – once, in a PowerShell **run as Administrator**:
   ```powershell
   Add-Printer -Name "Cat Printer" -IppURL "http://127.0.0.1:631/ipp/print"
   ```
4. **Start automatically at logon** (optional, no admin needed):
   ```powershell
   .\autostart.ps1            # shortcut in the Startup folder: server + tray icon, no console window
   .\autostart.ps1 -Remove    # removes it again
   ```
   The log file is then `%APPDATA%\CatPrinterDriver\server.log`.
   (Don't combine this with the installed exe – both use the same autostart entry.)

## Tray icon

The installed exe (or `python -m catprinter tray`) runs the print server
together with a cat icon in the notification area. The dot shows the state:
🟢 ready · 🔵 printing · 🟠 too hot, cooling down · 🔴 error.

Right-click menu: status and battery level, *Print test page*, *Check
battery*, *Open status page* (also on double-click), *Open log*, *Edit
settings*, *Language*, *Restart server* (reloads `config.json`), *Quit*.

Windows notifications appear when a print fails (e.g. printer off), when the
print head is too hot, and for the battery (see below).

**Language:** tray icon, notifications, status page, error messages, installer
and printed test pages are available in **German and English**. By default
the language follows Windows; switch it in the tray menu (*Language*), with
the DE | EN switch on the status page or in its settings. (The log file stays
German.)

### Battery warning

The battery level is measured after every print and, while nothing is
printing, **automatically every 30 minutes** (adjustable on the status page,
0 = off; if the printer is off, nothing happens). The percentage is estimated
from the voltage of the two-cell Li-ion battery (8.4 V = full) and shown in
the tray tooltip and on the status page. Notifications: once at *low*
(15 %, adjustable), once at *almost empty* (5 %), and *fully charged*.

**Charging:** while the USB cable is plugged in, the printer reports the
charging voltage, so the percentage would look too high. The driver detects
charging from a jump of ≥ 0.15 V between two idle readings (measured when
plugging in: 7.32 → 7.54 V) and then shows *„lädt …“* instead of a percentage,
pauses the warnings and checks every 5 minutes. When the charging voltage has
reached the top (≥ 8.35 V) twice in a row, it reports *fully charged*.
Unplugging is detected from the voltage dropping again. The last reading is
kept in `battery.json`, so this also works across a restart.

## Printing

- Choose **"Cat Printer"** in any print dialog.
- **Paper size:** pick one of the roll sizes `48 x 40 / 80 / 150 / 300 mm`.
  A4, A6 and Letter are accepted too, but are scaled down to 48 mm width (tiny).
- **Margins:** set them to 0 / minimum. Default margins (e.g. 2.5 cm in Word)
  don't fit on 48 mm paper.
- **Print quality** (in the print dialog / printer preferences) selects how
  gray tones are converted to black-and-white dots:

  | Quality | Mode | Result |
  |---|---|---|
  | Draft | `text` | Hard threshold – everything crisp, gray areas become solid black or white |
  | **Normal** (default) | `auto` | Photos are dithered; for text and graphics, edges stay crisp (no frayed anti-aliased text) and only flat gray areas (fills, gradients) are dithered |
  | High | `photo` | Everything dithered (Floyd–Steinberg) |

  *Auto* treats a page as a photo when it uses many different gray levels.
  Classic Windows (GDI) programs always send "Normal".
- Blank space at the end of a page is cut off automatically to save paper.
- By default the output is rotated by 180° so it reads correctly when you look
  at the printer from its "face" side (the end of the page comes out first).

## Printing from your phone (optional, off by default)

Switch on **„Im Heimnetz freigeben“** (share on home network) in the settings on the status page. The
PC then announces the printer in your Wi-Fi as **"Cat Printer @ <PC name>"**
(mDNS/Bonjour, like a network printer), and phones can print to it without
any extra app:

- **Android:** make sure *Settings → Connected devices → Connection
  preferences → Printing → Default Print Service* is on. Then print from any
  app (e.g. Google Photos: ⋮ → Print), choose *All printers* and pick
  "Cat Printer @ …". Select one of the 48 mm paper sizes.
- iOS/AirPrint was not tested.

Notes:

- The first time you switch it on, Windows asks for admin rights to add two
  firewall rules (TCP 631, UDP 5353) – **private networks only**. If your
  network is set to *Public*, phones can't reach the PC; the status page warns
  about that.
- From the network **only printing** is possible, only from private
  addresses. The status page, settings and history stay on this PC.
  Anyone on your home network can print while sharing is on.
- The PC must be running with Cat Printer started.
- Windows 11 may automatically add the announced printer as a second,
  network printer queue. You can delete it – "Cat Printer" is the same printer.
- **Photos from phones** arrive with faithful tones, whereas Windows lightens
  photo shadows noticeably when printing. So phone photos would print darker;
  *„Fotos vom Handy aufhellen wie am PC“* (on by default) applies the same tone
  curve. *„Foto-Helligkeit“* (photo brightness) additionally lightens the mid-tones of all photos
  (thermal dots spread a little, so photos tend to look darker than on
  screen). Text and graphics are never changed.

## History (optional, off by default)

For privacy, printed pages are **not** stored unless you switch on
*History* in the settings on the status page. When enabled, a copy of every
printed page (grayscale at print width, not the original document) is kept in
`%APPDATA%\CatPrinterDriver\history` – at most the last 30 jobs. The status
page then lists them with thumbnails; click one to see how it prints, and use
*Print again* (also for jobs that failed, e.g. because the printer was off).
Entries can be deleted one by one or all at once. **Switching the history off
deletes all stored pages immediately.**

The status page and history are only served to requests addressed to
`127.0.0.1`/`localhost` (protection against DNS rebinding), and actions
require a custom header, so other websites can neither read them nor print.

## Command line

| Command | Purpose |
|---|---|
| `python -m catprinter serve` | Run the IPP print server in the console (default command) |
| `python -m catprinter tray` | Run the print server with tray icon (logs to `%APPDATA%\CatPrinterDriver\server.log`) |
| `python -m catprinter serve -v --save-jobs DIR` | Verbose log, keep received jobs for debugging |
| `python -m catprinter status` | Show firmware, battery voltage and COM port |
| `python -m catprinter test` | Print a test page directly (bypasses Windows) |
| `python -m catprinter image picture.png` | Print an image file directly |
| `python -m catprinter calibrate 15 25 40` | Print black test blocks at several density levels |
| http://127.0.0.1:631/ | Status page: state, battery, recent jobs, editable settings, buttons for test page and battery check (updates live, light/dark mode, **German / English** switch top right) |

Options: `--port COMx` (skip auto-detection), `--density N`, `--mode auto|text|photo`,
`--log-file FILE`.

## Configuration

The easiest way: open the **status page** (http://127.0.0.1:631/, or
double-click the tray icon). Density, image mode, rotation, feed, trimming
and the connection can be changed there; changes apply to the next print
immediately and are saved. *Print sample* prints a test block with the
density on the slider, so you can try values before saving.

All settings live in `%APPDATA%\CatPrinterDriver\config.json` (created on
first start). If you edit the file by hand, choose *Restart server* in the
tray menu afterwards.

| Key | Default | Meaning |
|---|---|---|
| `com_port` | `null` | Fixed COM port, e.g. `"COM13"`; `null` = find it via the Bluetooth name |
| `bluetooth_name` | `"YHK-"` | Name prefix used for auto-detection |
| `density` | `40` | Print density / heat (`1D 49 F0 n`). WalkPrint uses 25; 40 looked best in tests. Try values with `calibrate` |
| `feed_mm` | `15` | Paper feed after printing, so the end clears the tear-off edge |
| `trim_bottom` | `true` | Cut blank space at the end of each page |
| `rotate_180` | `true` | Rotate output 180° (readable from the printer's face side) |
| `image_mode` | `"auto"` | Mode used for print quality "Normal": `auto`, `text` or `photo` |
| `keep_history` | `false` | Keep copies of printed pages for viewing / printing again (see *History*) |
| `share_network` | `false` | Share on the home network for printing from phones (see *Printing from your phone*) |
| `match_windows_tone` | `true` | Lighten photo shadows of phone prints like Windows does |
| `photo_brightness` | `0` | Photo brightness in percent (−30 … +50), photos only |
| `battery_check_minutes` | `30` | Check the battery automatically every N minutes while idle (0 = off) |
| `battery_warn_percent` | `15` | Warn when the battery drops to this level |
| `language` | `"auto"` | `auto` (like Windows), `de` or `en` |
| `http_host` / `http_port` | `127.0.0.1` / `631` | Address of the IPP server |
| `printer_name` | `"Cat Printer"` | Name reported to Windows |
| `uuid` | random | Printer identity – don't change it, or Windows sees a new device |

## Troubleshooting

| Problem | Cause / fix |
|---|---|
| Job fails after ~20 s | Printer is off, battery empty, or connected to the phone (Bluetooth serial allows only one connection). The job is aborted and doesn't block the queue. |
| WalkPrint app can't connect right after a print | Cat Printer keeps the Bluetooth connection open for 90 s after the last print (reconnecting while it prints would cut off the end). Wait a moment or quit Cat Printer from the tray menu. |
| Jobs stay "printing" forever | The server isn't running (no cat icon in the notification area) – start it or set up the autostart. |
| `Add-Printer`: access denied | Run PowerShell as Administrator. |
| Output too light | Charge the battery; raise `density` (see `calibrate`). |
| Printer stops in the middle of a print, status "Zu heiß – kühlt ab" | Overheat protection after many dark prints in a row. The printer pauses about 1–2 minutes and then continues by itself; before the next job the driver waits until it has cooled down. Nothing is lost. |
| Photos too dark | Raise *„Foto-Helligkeit“* on the status page (try +20 %) and compare with *„Nochmal drucken“* (print again) in the history. |
| Phone doesn't find the printer | Sharing on? Same Wi-Fi? Network profile *Private*? Firewall rule present (status page shows warnings)? On Android, the *Default Print Service* must be enabled. |
| Thin lighter lines in large all-black areas | Rows where all 384 dots are black get slightly less heat on battery power. Print such images with the USB cable plugged in (charging) – in our test the lines disappeared. Text and normal images are not affected. |
| "Unknown USB device" when plugged in | Normal: the USB port only charges the printer, it has no data connection. Printing works only via Bluetooth. |
| Remove everything | exe: uninstall via *Settings → Apps* (also removes the firewall rules). Source version: `Remove-Printer "Cat Printer"` (as admin), `.\autostart.ps1 -Remove`, delete `%APPDATA%\CatPrinterDriver`. |

## Building the exe

```powershell
pip install -r requirements.txt pyinstaller
.\build.ps1
```

Runs the tests, generates the icon and builds `dist\CatPrinter.exe` (a single
file, ~28 MB, no console window) with PyInstaller. Double-clicking it outside
the install folder starts the installer; the installed copy starts the tray.
`CatPrinter.exe install` / `CatPrinter.exe uninstall` do the same explicitly.

## Development

```powershell
python -m unittest discover tests
```

The tests need no printer: they cover the IPP codec, the PWG raster decoder
(round trip), the ESC/POS job builder and a full IPP print job against the
server with a fake printer.

| File | Content |
|---|---|
| `catprinter/ipp.py` | Minimal IPP/1.1–2.0 message encoder/decoder (RFC 8010) |
| `catprinter/pwg.py` | PWG raster decoder (+ encoder for tests) |
| `catprinter/printer.py` | Image preparation, ESC/POS job builder, serial transport, port detection |
| `catprinter/server.py` | IPP server, printer/job attributes, job queue, events |
| `catprinter/tray.py` | Tray icon, menu and notifications |
| `catprinter/pages.py` | Test and calibration pages |
| `catprinter/statuspage.py` | Status page (HTML) and its JSON data |
| `catprinter/history.py` | Optional history of printed jobs |
| `catprinter/installer.py` | Install/update/uninstall of the exe |
| `catprinter/netshare.py` | Home network sharing: access rules, mDNS announcement, firewall |
| `packaging/`, `build.ps1` | exe entry point, icon generator, build script |
| `catprinter/__main__.py` | Command line interface |
| `autostart.ps1` | Startup-folder shortcut |
| `docs/PROTOCOL.md` | What was learned about the printer and the Windows IPP client |

## Credits

The printer protocol was identified with the help of these projects:

- [abhigkar/YHK-Cat-Thermal-Printer](https://github.com/abhigkar/YHK-Cat-Thermal-Printer) – YHK printers over Classic Bluetooth
- [Dejniel/TiMini-Print](https://github.com/Dejniel/TiMini-Print) – density command `1D 49 F0 n`
- [Josh McArthur – YHK Mini Printer notes](https://www.joshmcarthur.com/case-studies/yhk-mini-printer/)

## License

[MIT](LICENSE)
