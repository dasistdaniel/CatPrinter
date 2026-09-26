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
- Python 3.10+ ([python.org](https://www.python.org/))
- The printer paired in *Settings → Bluetooth & devices*

## Installation

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
4. **Start the server automatically at logon** (optional, no admin needed):
   ```powershell
   .\autostart.ps1            # creates a shortcut in the Startup folder (runs hidden via pythonw)
   .\autostart.ps1 -Remove    # removes it again
   ```
   The log file is then `%APPDATA%\CatPrinterDriver\server.log`.

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

## Command line

| Command | Purpose |
|---|---|
| `python -m catprinter serve` | Run the IPP print server (default command) |
| `python -m catprinter serve -v --save-jobs DIR` | Verbose log, keep received jobs for debugging |
| `python -m catprinter status` | Show firmware, battery voltage and COM port |
| `python -m catprinter test` | Print a test page directly (bypasses Windows) |
| `python -m catprinter image picture.png` | Print an image file directly |
| `python -m catprinter calibrate 15 25 40` | Print black test blocks at several density levels |
| http://127.0.0.1:631/ | Status page with the latest jobs |

Options: `--port COMx` (skip auto-detection), `--density N`, `--mode auto|text|photo`,
`--log-file FILE`.

## Configuration

`%APPDATA%\CatPrinterDriver\config.json` is created on first start.
Restart the server after changing it.

| Key | Default | Meaning |
|---|---|---|
| `com_port` | `null` | Fixed COM port, e.g. `"COM13"`; `null` = find it via the Bluetooth name |
| `bluetooth_name` | `"YHK-"` | Name prefix used for auto-detection |
| `density` | `40` | Print density / heat (`1D 49 F0 n`). WalkPrint uses 25; 40 looked best in tests. Try values with `calibrate` |
| `feed_mm` | `15` | Paper feed after printing, so the end clears the tear-off edge |
| `trim_bottom` | `true` | Cut blank space at the end of each page |
| `rotate_180` | `true` | Rotate output 180° (readable from the printer's face side) |
| `image_mode` | `"auto"` | Mode used for print quality "Normal": `auto`, `text` or `photo` |
| `http_host` / `http_port` | `127.0.0.1` / `631` | Address of the IPP server |
| `printer_name` | `"Cat Printer"` | Name reported to Windows |
| `uuid` | random | Printer identity – don't change it, or Windows sees a new device |

## Troubleshooting

| Problem | Cause / fix |
|---|---|
| Job fails after ~20 s | Printer is off, battery empty, or connected to the phone (Bluetooth serial allows only one connection). The job is aborted and doesn't block the queue. |
| Jobs stay "printing" forever | The server isn't running – start it or set up the autostart. |
| `Add-Printer`: access denied | Run PowerShell as Administrator. |
| Output too light | Charge the battery; raise `density` (see `calibrate`). |
| Thin lighter lines in large all-black areas | Hardware limit: rows where all 384 dots are black get slightly less heat on battery power. Text and normal images are not affected. |
| Remove everything | `Remove-Printer "Cat Printer"` (as admin), `.\autostart.ps1 -Remove`, delete `%APPDATA%\CatPrinterDriver`. |

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
| `catprinter/server.py` | IPP server, printer/job attributes, job queue |
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
