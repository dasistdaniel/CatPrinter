# Protocol & technical notes

What was learned while building this project – about the printer, and about
the Windows IPP client. Everything below was observed on one `YHK-…` printer
(hardware `H1.0`, firmware `V1.01`) and Windows 11 (build 26200). Other firmware
versions may behave differently.

*(Written with AI assistance, see the note in the [README](../README.md).)*

## 1. Transport

- **Classic Bluetooth, Serial Port Profile (SPP)** – not BLE/GATT like most
  other "cat printers". After pairing, Windows creates a
  *Standard Serial over Bluetooth link* COM port.
- The COM port's hardware ID contains the printer's Bluetooth MAC address:
  `BTHENUM\{00001101-…}_LOCALMFG&005D\…&<MAC>_C00000000`.
  The paired device itself appears as `BTHENUM\DEV_<MAC>` with the friendly
  name `YHK-…`. `find_port()` joins the two to find the port automatically.
- The baud rate setting is irrelevant for Bluetooth serial ports (115200 used).
- **Only one connection at a time.** If the phone app is connected, opening
  the port fails.
- **Reconnect delay:** right after the port is closed, the printer refuses a
  new connection for a few seconds (`OSError 22 / 1167 "device not connected"`).
  The driver retries 3× with 3 s pause.
- **Printer off:** opening the port fails after ~5 s with
  `OSError 22 / 121 "semaphore timeout"`.
- RFCOMM has its own credit-based flow control. Sending a 24 KB job without
  any pauses took 0.3 s and printed correctly. The driver still paces writes
  (256 bytes / 30 ms ≈ 8 KB/s) as a precaution for very long jobs.

## 2. Commands (ESC/POS dialect)

| Bytes | Meaning | Notes |
|---|---|---|
| `1B 40` | `ESC @` initialize | **Discards everything still in the print buffer.** Only send it once at the start of a connection – concatenating jobs that each start with `ESC @` silently drops all but the last one. |
| `1D 49 F0 n` | Print density / heat | Sent by WalkPrint with `n = 0x19` (25). Visible difference between 15 and 60; 40 looked best. |
| `1D 76 30 00 xL xH yL yH d…` | `GS v 0` raster image | `x` = bytes per row (48 for 384 dots), `y` = rows (16 bit). 1 bit per dot, MSB = leftmost, **1 = black**. |
| `0A` | Line feed | Works; the driver feeds with blank raster rows instead. |
| `1E 47 03` | Status query | Reply: `HV=H1.0,SV=V1.01,VOLT=7260mv,DPI=384,\0` (`DPI` is actually the dot width). |
| `1D 67 39` | Serial number query | Reply: `sn:<serial>.\0` |
| `1D 67 69` | Product info query | Reply: `public id:0202.\0` |

### Job layout used by the driver

```
1B 40                      init (once)
1D 49 F0 <density>         density
1D 76 30 00 30 00 <rows>   one GS v 0 block per page:
<rows × 48 bytes>          page bitmap + blank rows for the paper feed (last page)
```

- **Send each page as one `GS v 0` block.** Splitting a page into bands of
  128 rows produced visible light stripes at every band boundary.
- **Paper feed:** 4 line feeds were not enough to move the end of the print
  past the tear-off edge; 15 mm of blank rows (≈ 120 rows) appended to the
  last page works.
- **Orientation:** the first row sent comes out first, i.e. farthest from the
  printer. Seen from the printer's "face", unrotated output is upside down,
  so the driver rotates by 180° by default (and reverses page order).

### Hardware limits

- **Power limit on fully black rows:** rows in which (almost) all 384 dots are
  black print slightly lighter than rows with ≤ 70 % coverage – visible as
  thin light lines inside large black areas. The raster data is correct; this
  is the battery/head not delivering enough heat. Pacing and block layout
  made no difference.
- Battery voltage drops noticeably during long sessions (7.28 V → 6.98 V in
  ~20 minutes of testing), and prints get lighter with it.

## 3. Windows side (IPP)

- `Add-Printer -Name … -IppURL http://127.0.0.1:631/ipp/print` creates a
  queue with the **Microsoft IPP Class Driver** (port `WSD-<guid>`). It needs
  an **elevated** PowerShell ("access denied" otherwise).
- Bind the server to `127.0.0.1` and use that in the URL (not `localhost`,
  which may resolve to `::1`).
- Windows 11 asks for these formats and prefers **`image/pwg-raster`** when
  it is the only raster format offered (no PDF, no URF). It then sends
  `sgray_8`, 203×203 dpi, one PWG page per document page, e.g. 383×639 px
  for the 48×80 mm media (48 mm @ 203 dpi = 383.6 dots → 383, padded to 384).
- Operation sequence per print job:
  `Get-Printer-Attributes` (several) → `Validate-Job` → `Create-Job` →
  `Send-Document` (with `last-document=true`, body usually **chunked**) →
  `Get-Job-Attributes` polled about once per second until the job state is
  `completed` (9) or `aborted` (8).
- Job attributes sent by Windows: `media-col` (e.g. `x-dimension=4800`,
  `y-dimension=7999` – note the rounding), `print-color-mode=monochrome`,
  `print-quality=4`, `print-scaling=fit`.
- Attributes Windows requests (all answered by `server.py`):
  document formats, `media-col-database`, margins, `printer-resolution-*`,
  `pwg-raster-document-*`, `finishings-*`, `number-up-*`,
  `multiple-document-handling-*`, `media-source-default`, `printer-firmware-*`,
  `printer-uuid`, `mopria-certified` (not answered – not needed).
- **Keep `printer-uuid` stable** across restarts; it is stored in `config.json`.
- An aborted job ends up as *"Error, Complete"* in the Windows queue and does
  not block later jobs.

### Media sizes offered

| Keyword | Size | Note |
|---|---|---|
| `om_roll-40_48x40mm` … `om_roll-300_48x300mm` | 48 × 40/80/150/300 mm | Default: 48 × 80 mm, zero margins |
| `iso_a6_105x148mm`, `iso_a4_210x297mm`, `na_letter_8.5x11in` | | Scaled down to 48 mm width |

## 4. PWG raster decoding

Per page: 1796-byte header (big-endian; width @372, height @376,
bits-per-pixel @388, bytes-per-line @392, color space @400), then per line
group: 1 byte *line repeat count − 1*, followed by pixel runs until the line
is full:

- `0x00–0x7F`: next pixel repeated `n + 1` times
- `0x81–0xFF`: `257 − n` literal pixels follow
- `0x80`: fill the rest of the line with white

For bit depths below 8 the "pixel" unit is one byte. White is `0xFF` for
`sgray`/`srgb`, but `0x00` for `black_1` (color space 3).
