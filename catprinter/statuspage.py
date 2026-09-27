"""Statusseite (http://127.0.0.1:631/) und ihre JSON-Daten."""
import time

from .printer import battery_volts

STATE_KEYS = {3: "pending", 5: "printing", 7: "canceled", 8: "failed", 9: "done"}


def status_dict(service):
    """Aktueller Zustand für /status.json."""
    cfg = service.cfg
    error = service.last_error if service.last_error and time.time() - service.last_error[0] < 120 else None
    state = ("cooling" if service.cooling else "printing") if service.active else ("error" if error else "ready")
    jobs = sorted(list(service.jobs.values()), key=lambda j: -j.id)[:20]
    return {
        "name": cfg.get("printer_name", "Cat Printer"),
        "state": state,
        "error": error[1] if error else None,
        "port": service.printer.port,
        "volts": battery_volts(service.status),
        "battery": service.battery,
        "firmware": service.status.get("SV"),
        "checking": service.checking,
        "settings": {
            "density": cfg.get("density"),
            "image_mode": cfg.get("image_mode", "auto"),
            "rotate_180": cfg.get("rotate_180", True),
            "trim_bottom": cfg.get("trim_bottom", True),
            "feed_mm": cfg.get("feed_mm"),
            "com_port": cfg.get("com_port") or "",
            "bluetooth_name": cfg.get("bluetooth_name", "YHK-"),
            "keep_history": bool(cfg.get("keep_history", False)),
            "share_network": bool(cfg.get("share_network", False)),
            "match_windows_tone": bool(cfg.get("match_windows_tone", True)),
            "photo_brightness": int(cfg.get("photo_brightness", 0)),
            "battery_check_minutes": int(cfg.get("battery_check_minutes", 30)),
            "battery_warn_percent": int(cfg.get("battery_warn_percent", 15)),
        },
        "network": dict(service.net_status, enabled=bool(cfg.get("share_network", False)),
                        port=cfg["http_port"]),
        "url": f"ipp://{cfg['http_host']}:{cfg['http_port']}/ipp/print",
        "uptime": service.uptime(),
        "printed": service.printed,
        "jobs": [{
            "id": j.id,
            "name": j.name,
            "state": STATE_KEYS.get(j.state, "pending"),
            "pages": j.pages,
            "created": j.created,
            "message": j.message,
        } for j in jobs],
    }


PAGE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Cat Printer</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Cpath d='M8 26 12 4l14 12M56 26 52 4 38 16' fill='%23fff' stroke='%23333' stroke-width='3' stroke-linejoin='round'/%3E%3Crect x='6' y='14' width='52' height='42' rx='16' fill='%23fff' stroke='%23333' stroke-width='3'/%3E%3Ccircle cx='21' cy='32' r='3.5' fill='%23333'/%3E%3Ccircle cx='43' cy='32' r='3.5' fill='%23333'/%3E%3Cpath d='M26 42q6 5 12 0' fill='none' stroke='%23333' stroke-width='3' stroke-linecap='round'/%3E%3C/svg%3E">
<style>
:root {
  --bg: #f5f3f0; --card: #ffffff; --text: #1f1d1a; --muted: #6b665f; --line: #e6e1da;
  --accent: #c94f68; --on-accent: #ffffff; --ok: #2e9e4f; --busy: #2f6fdb; --err: #d33b37; --wait: #a0772a;
  --ok-bg: #e5f4e9; --busy-bg: #e3ecfb; --err-bg: #fbe6e5; --wait-bg: #f7eedb; --neutral-bg: #eeebe6;
  --shadow: 0 1px 2px rgba(0,0,0,.05), 0 4px 16px rgba(0,0,0,.05);
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #171614; --card: #221f1c; --text: #eeeae4; --muted: #a39d94; --line: #36322d;
    --accent: #ec8a9c; --on-accent: #2a1015; --ok: #5cc97b; --busy: #6c9cf0; --err: #f07470; --wait: #d6aa55;
    --ok-bg: #1c3223; --busy-bg: #1c2a44; --err-bg: #3e1f1d; --wait-bg: #3a2f19; --neutral-bg: #2d2925;
    --shadow: none;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--text);
  font: 15px/1.5 "Segoe UI", system-ui, -apple-system, sans-serif;
}
main { max-width: 760px; margin: 0 auto; padding: 32px 16px 48px; }
header { display: flex; align-items: center; gap: 16px; margin-bottom: 24px; }
header svg { width: 56px; height: 56px; flex: none; }
h1 { font-size: 24px; margin: 0; line-height: 1.2; }
.sub { color: var(--muted); font-size: 13px; margin-top: 2px; }
.head-right { margin-left: auto; display: flex; align-items: center; gap: 10px; }
.lang { display: inline-flex; border: 1px solid var(--line); border-radius: 8px; overflow: hidden; }
.lang button {
  border: 0; border-radius: 0; padding: 4px 9px; font-size: 12px; font-weight: 600;
  background: transparent; color: var(--muted);
}
.lang button.active { background: var(--neutral-bg); color: var(--text); }
.pill {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 14px; border-radius: 999px; font-weight: 600; font-size: 14px; white-space: nowrap;
}
.pill::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: currentColor; }
.pill.ready { color: var(--ok); background: var(--ok-bg); }
.pill.printing { color: var(--busy); background: var(--busy-bg); }
.pill.printing::before { animation: pulse 1s ease-in-out infinite; }
.pill.error { color: var(--err); background: var(--err-bg); }
.pill.cooling { color: var(--wait); background: var(--wait-bg); }
.pill.cooling::before { animation: pulse 1.6s ease-in-out infinite; }
.pill.offline { color: var(--muted); background: var(--neutral-bg); }
@keyframes pulse { 50% { opacity: .25; } }
.alert {
  background: var(--err-bg); color: var(--err); border-radius: 12px;
  padding: 12px 16px; margin-bottom: 16px; font-size: 14px;
}
.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.card { background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 16px; box-shadow: var(--shadow); }
.label { color: var(--muted); font-size: 12px; text-transform: uppercase; letter-spacing: .06em; }
.value { font-size: 22px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
.hint { color: var(--muted); font-size: 13px; }
.low { color: var(--err); }
.warnlow { color: var(--wait); }
.battery-bar { height: 6px; border-radius: 3px; background: var(--neutral-bg); margin: 6px 0 4px; overflow: hidden; }
.battery-bar div { height: 100%; width: 0; background: var(--ok); border-radius: 3px; transition: width .3s; }
.battery-bar div.warnlow { background: var(--wait); }
.battery-bar div.low { background: var(--err); }
.battery-bar div.charging {
  width: 100%;
  background: repeating-linear-gradient(-45deg, var(--ok) 0 8px, transparent 8px 16px);
  background-size: 22.6px 100%; animation: charge 1s linear infinite; opacity: .7;
}
@keyframes charge { to { background-position: 22.6px 0; } }
.netinfo {
  background: var(--busy-bg); color: var(--text); border-radius: 12px;
  padding: 10px 16px; margin-bottom: 16px; font-size: 14px;
}
.netinfo strong { color: var(--busy); }
.net-warn { color: var(--err); margin-top: 4px; }
.actions { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 24px; }
button {
  font: inherit; font-weight: 600; font-size: 14px; cursor: pointer;
  border: 1px solid var(--line); background: var(--card); color: var(--text);
  padding: 8px 16px; border-radius: 10px;
}
button.primary { background: var(--accent); border-color: var(--accent); color: var(--on-accent); }
button:disabled { opacity: .5; cursor: default; }
button:not(:disabled):hover { filter: brightness(.96); }
h2 { font-size: 16px; margin: 0 0 12px; }
.jobs { padding: 4px 0; }
.job { display: flex; align-items: center; gap: 12px; padding: 10px 16px; border-top: 1px solid var(--line); }
.job:first-child { border-top: 0; }
.job .name { flex: 1; min-width: 0; }
.job .title { font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job .meta { color: var(--muted); font-size: 13px; }
.job .msg { color: var(--err); font-size: 13px; }
.badge { font-size: 12px; font-weight: 600; padding: 2px 10px; border-radius: 999px; white-space: nowrap; }
.badge.done { color: var(--ok); background: var(--ok-bg); }
.badge.printing { color: var(--busy); background: var(--busy-bg); }
.badge.pending { color: var(--wait); background: var(--wait-bg); }
.badge.failed { color: var(--err); background: var(--err-bg); }
.badge.canceled { color: var(--muted); background: var(--neutral-bg); }
.empty { color: var(--muted); padding: 24px 16px; text-align: center; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin: 24px 0 12px; }
.section-head h2 { margin: 0; }
button.small { padding: 4px 12px; font-size: 13px; }
button.link { border: 0; background: none; color: var(--accent); padding: 4px 0; margin-top: 6px; }
button.link:hover { text-decoration: underline; }
button.icon { border: 0; background: none; font-size: 16px; padding: 4px 8px; color: var(--muted); }
button.danger { color: var(--err); }
.hist { display: flex; align-items: center; gap: 14px; padding: 12px 16px; border-top: 1px solid var(--line); }
.hist:first-child { border-top: 0; }
.thumb {
  width: 56px; height: 72px; flex: none; padding: 0; overflow: hidden; cursor: zoom-in;
  background: #fff; border: 1px solid var(--line); border-radius: 6px;
}
.thumb img { width: 100%; height: 100%; object-fit: cover; object-position: top; display: block; }
.hist .name { flex: 1; min-width: 0; }
.hist .buttons { display: flex; gap: 6px; flex-wrap: wrap; justify-content: flex-end; }
dialog {
  width: min(480px, calc(100vw - 32px)); max-height: calc(100vh - 48px); padding: 0;
  border: 1px solid var(--line); border-radius: 14px; background: var(--card); color: var(--text);
  box-shadow: 0 12px 48px rgba(0,0,0,.25);
}
dialog[open] { display: flex; flex-direction: column; }
dialog::backdrop { background: rgba(0,0,0,.45); }
.viewer-head, .viewer-foot { display: flex; align-items: center; gap: 12px; padding: 12px 16px; }
.viewer-head { border-bottom: 1px solid var(--line); justify-content: space-between; }
.viewer-foot { border-top: 1px solid var(--line); justify-content: space-between; }
.viewer-head .title { font-weight: 600; }
.viewer-head .meta, .viewer-foot .hint { color: var(--muted); font-size: 13px; }
.viewer-pages { overflow: auto; padding: 16px; display: grid; gap: 12px; justify-items: center; background: var(--bg); }
.viewer-pages img {
  width: 100%; max-width: 384px; background: #fff; image-rendering: pixelated;
  box-shadow: 0 1px 4px rgba(0,0,0,.15);
}
.section { margin-top: 24px; }
.section > summary {
  display: flex; align-items: baseline; gap: 10px; list-style: none;
  cursor: pointer; margin-bottom: 12px; user-select: none;
}
.section > summary::-webkit-details-marker { display: none; }
.section > summary::before {
  content: ""; width: 7px; height: 7px; flex: none; align-self: center;
  border-right: 2px solid var(--muted); border-bottom: 2px solid var(--muted);
  transform: rotate(-45deg); transition: transform .15s;
}
.section[open] > summary::before { transform: rotate(45deg); }
.section > summary h2 { margin: 0; }
.summary-hint { color: var(--muted); font-size: 13px; }
.section[open] .summary-hint { display: none; }
.settings { padding: 4px 16px; }
.field { padding: 14px 0; border-top: 1px solid var(--line); }
.field:first-child { border-top: 0; }
.field > label, .twocol label { display: block; font-weight: 600; font-size: 14px; margin-bottom: 6px; }
.control { display: flex; align-items: center; gap: 12px; }
.help { color: var(--muted); font-size: 13px; margin: 6px 0 0; }
input[type=range] { flex: 1; min-width: 0; accent-color: var(--accent); }
output { font-weight: 600; font-variant-numeric: tabular-nums; min-width: 2ch; }
input[type=number], input[type=text], select {
  font: inherit; color: var(--text); background: var(--bg);
  border: 1px solid var(--line); border-radius: 8px; padding: 7px 10px;
}
select { width: 100%; }
input[type=number] { width: 90px; }
input[type=text] { width: 100%; }
input:focus-visible, select:focus-visible, button:focus-visible, summary:focus-visible {
  outline: 2px solid var(--accent); outline-offset: 2px;
}
.unit { color: var(--muted); }
.checks { display: grid; gap: 10px; }
.check { display: flex; align-items: center; gap: 10px; font-size: 14px; cursor: pointer; }
.check input { width: 18px; height: 18px; accent-color: var(--accent); margin: 0; }
summary { font-weight: 600; font-size: 14px; cursor: pointer; }
details[open] summary { margin-bottom: 10px; }
.twocol { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
code { font-family: Consolas, ui-monospace, monospace; font-size: 12px; overflow-wrap: anywhere; }
.save-row { display: flex; align-items: center; justify-content: flex-end; gap: 8px; padding: 14px 0; border-top: 1px solid var(--line); }
.save-msg { margin-right: auto; font-size: 13px; color: var(--muted); }
.save-msg.ok { color: var(--ok); }
.save-msg.err { color: var(--err); }
footer { color: var(--muted); font-size: 12px; margin-top: 24px; text-align: center; }
@media (max-width: 600px) {
  .grid, .twocol { grid-template-columns: 1fr; }
  header { flex-wrap: wrap; }
  .head-right { margin-left: 0; }
}
</style>
</head>
<body>
<main>
  <header>
    <svg viewBox="0 0 64 64" aria-hidden="true">
      <path d="M8 26 12 4l14 12M56 26 52 4 38 16" fill="var(--card)" stroke="var(--text)" stroke-width="2.5" stroke-linejoin="round"/>
      <rect x="6" y="14" width="52" height="42" rx="16" fill="var(--card)" stroke="var(--text)" stroke-width="2.5"/>
      <circle cx="21" cy="32" r="3.5" fill="var(--text)"/><circle cx="43" cy="32" r="3.5" fill="var(--text)"/>
      <ellipse cx="15" cy="40" rx="4" ry="2.5" fill="var(--accent)" opacity=".5"/>
      <ellipse cx="49" cy="40" rx="4" ry="2.5" fill="var(--accent)" opacity=".5"/>
      <path d="M26 42q6 5 12 0" fill="none" stroke="var(--text)" stroke-width="2.5" stroke-linecap="round"/>
    </svg>
    <div>
      <h1 id="name">Cat Printer</h1>
      <div class="sub" data-i18n="subtitle"></div>
    </div>
    <div class="head-right">
      <span id="pill" class="pill offline" data-i18n="connecting"></span>
      <div class="lang" role="group" aria-label="Sprache / Language">
        <button type="button" data-lang="de">DE</button><button type="button" data-lang="en">EN</button>
      </div>
    </div>
  </header>

  <div id="alert" class="alert" hidden></div>

  <div class="grid">
    <div class="card">
      <div class="label" data-i18n="battery"></div>
      <div class="value" id="volts">–</div>
      <div class="battery-bar"><div id="battery-fill"></div></div>
      <div class="hint" id="volts-hint" data-i18n="notMeasured"></div>
    </div>
    <div class="card">
      <div class="label" data-i18n="connection"></div>
      <div class="value" id="port">–</div>
      <div class="hint" id="firmware"></div>
    </div>
    <div class="card">
      <div class="label" data-i18n="printed"></div>
      <div class="value" id="count">0</div>
      <div class="hint" id="uptime"></div>
    </div>
  </div>

  <div class="netinfo" id="netinfo" hidden>
    <strong data-i18n="sharedOnNetwork"></strong> <span id="net-text"></span>
    <div class="net-warn" id="net-warn" hidden></div>
  </div>

  <div class="actions">
    <button class="primary" id="btn-test" data-i18n="printTestPage"></button>
    <button id="btn-battery" data-i18n="checkBattery"></button>
  </div>

  <h2 data-i18n="jobs"></h2>
  <div class="card jobs" id="jobs"></div>

  <div class="section-head">
    <h2 data-i18n="history"></h2>
    <button type="button" class="small" id="btn-clear" hidden data-i18n="deleteAll"></button>
  </div>
  <div class="card" id="history"></div>

  <dialog id="viewer">
    <div class="viewer-head">
      <div><div class="title" id="viewer-title"></div><div class="meta" id="viewer-meta"></div></div>
      <button type="button" class="icon" id="viewer-close" data-i18n-aria="close">✕</button>
    </div>
    <div class="viewer-pages" id="viewer-pages"></div>
    <div class="viewer-foot">
      <span class="hint" data-i18n="previewHint"></span>
      <button type="button" class="primary" id="viewer-reprint" data-i18n="printAgain"></button>
    </div>
  </dialog>

  <details class="section" id="settings-section">
  <summary><h2 data-i18n="settings"></h2><span class="summary-hint" data-i18n="settingsHint"></span></summary>
  <form class="card settings" id="settings" autocomplete="off">
    <div class="field">
      <label for="f-density" data-i18n="density"></label>
      <div class="control">
        <input type="range" id="f-density" name="density" min="5" max="80" step="1">
        <output id="density-out">–</output>
        <button type="button" id="btn-calibrate" data-i18n="printSample"></button>
      </div>
      <p class="help" data-i18n="densityHelp"></p>
    </div>
    <div class="field">
      <label for="f-mode" data-i18n="imageMode"></label>
      <select id="f-mode" name="image_mode">
        <option value="auto" data-i18n="modeAuto"></option>
        <option value="text" data-i18n="modeText"></option>
        <option value="photo" data-i18n="modePhoto"></option>
      </select>
      <p class="help" data-i18n="imageModeHelp"></p>
    </div>
    <div class="field">
      <label for="f-bright" data-i18n="photoBrightness"></label>
      <div class="control">
        <input type="range" id="f-bright" name="photo_brightness" min="-30" max="50" step="5">
        <output id="bright-out">0</output>
      </div>
      <p class="help" data-i18n="photoBrightnessHelp"></p>
    </div>
    <div class="field">
      <label for="f-feed" data-i18n="feed"></label>
      <div class="control">
        <input type="number" id="f-feed" name="feed_mm" min="0" max="50" step="1"><span class="unit">mm</span>
      </div>
      <p class="help" data-i18n="feedHelp"></p>
    </div>
    <div class="field">
      <label for="f-battery-check" data-i18n="batteryCheck"></label>
      <div class="control">
        <select id="f-battery-check" name="battery_check_minutes" style="width:auto">
          <option value="0" data-i18n="off"></option>
          <option value="15" data-i18n="every15"></option>
          <option value="30" data-i18n="every30"></option>
          <option value="60" data-i18n="every60"></option>
          <option value="120" data-i18n="every120"></option>
        </select>
        <span class="unit" data-i18n="warnFrom"></span>
        <input type="number" id="f-battery-warn" name="battery_warn_percent" min="5" max="50" step="5"><span class="unit">%</span>
      </div>
      <p class="help" data-i18n="batteryCheckHelp"></p>
    </div>
    <div class="field checks">
      <label class="check"><input type="checkbox" id="f-rotate" name="rotate_180"> <span data-i18n="rotate"></span></label>
      <label class="check"><input type="checkbox" id="f-trim" name="trim_bottom"> <span data-i18n="trim"></span></label>
    </div>
    <div class="field">
      <label class="check"><input type="checkbox" id="f-history" name="keep_history"> <span data-i18n="keepHistory"></span></label>
      <p class="help" data-i18n-html="keepHistoryHelp"></p>
    </div>
    <div class="field">
      <label class="check"><input type="checkbox" id="f-share" name="share_network"> <span data-i18n="shareNetwork"></span></label>
      <p class="help" data-i18n="shareNetworkHelp"></p>
      <label class="check" style="margin-top:10px"><input type="checkbox" id="f-tone" name="match_windows_tone"> <span data-i18n="matchTone"></span></label>
      <p class="help" data-i18n="matchToneHelp"></p>
    </div>
    <details class="field">
      <summary data-i18n="connection"></summary>
      <div class="twocol">
        <div>
          <label for="f-port" data-i18n="comPort"></label>
          <input type="text" id="f-port" name="com_port" data-i18n-placeholder="automatic">
        </div>
        <div>
          <label for="f-btname" data-i18n="btName"></label>
          <input type="text" id="f-btname" name="bluetooth_name">
        </div>
      </div>
      <p class="help"><span data-i18n="connectionHelp"></span> <code id="url">–</code></p>
    </details>
    <div class="save-row">
      <span id="save-msg" class="save-msg" role="status"></span>
      <button type="button" id="btn-reset" data-i18n="discard"></button>
      <button type="submit" class="primary" id="btn-save" data-i18n="save"></button>
    </div>
  </form>
  </details>

  <footer data-i18n="footer"></footer>
</main>
<script>
const $ = (id) => document.getElementById(id);

// ---------------------------------------------------------------- Texte (Deutsch / English)
const I18N = {
  de: {
    subtitle: "Bluetooth-Thermodrucker · 58 mm", connecting: "Verbinde …", serverDown: "Server nicht erreichbar",
    ready: "Bereit", printing: "Druckt …", cooling: "Zu heiß – kühlt ab …", error: "Fehler",
    jobDone: "Gedruckt", jobPrinting: "Druckt", jobPending: "Wartet", jobFailed: "Fehlgeschlagen", jobCanceled: "Abgebrochen",
    battery: "Akku", connection: "Verbindung", printed: "Gedruckt", notMeasured: "noch nicht gemessen",
    measuring: "wird gemessen …", measuredAt: "gemessen {0}", battCritical: "fast leer – jetzt per USB laden ({0})",
    battLow: "schwach – bitte bald laden ({0})", charging: "lädt …", full: "voll", atCharger: "am Ladekabel · ",
    chargingVoltage: "Ladespannung {0} · ", automaticPort: "Automatisch", bluetoothSerial: "Bluetooth (seriell)",
    portSearched: "COM-Port wird beim ersten Druck gesucht", since: "seit {0}", minutes: "{0} Min.",
    hours: "{0} Std.", days: "{0} Tagen", lastError: "Letzter Fehler: {0}",
    sharedOnNetwork: "Im Heimnetz freigegeben", netSetup: "– wird eingerichtet …",
    netHow: "· Handy im selben WLAN → Drucken → Drucker „{0}“ wählen · {1}", netNoAddr: "· keine Heimnetz-Adresse gefunden",
    netFirewall: "Firewall-Regel fehlt – im Einstellungsbereich die Freigabe aus- und wieder einschalten.",
    netPublic: "Ein Netzwerk ist als „öffentlich“ eingestuft – dort erreichen Handys den Drucker nicht (Windows: Netzwerkprofil „Privat“).",
    netAdvert: "Bekanntgabe im Netz fehlgeschlagen: {0}", unknown: "unbekannt",
    printTestPage: "Testseite drucken", checkBattery: "Akku prüfen", jobs: "Druckaufträge", noJobs: "Noch keine Aufträge",
    page: "Seite", pages: "Seiten", history: "Verlauf", deleteAll: "Alle löschen", close: "Schließen",
    previewHint: "Vorschau mit den aktuellen Einstellungen", printAgain: "Nochmal drucken", delete: "Löschen",
    view: "Ansehen", preview: "Vorschau", historyOff: "Der Verlauf ist ausgeschaltet – gedruckte Aufträge werden nicht gespeichert.",
    enableInSettings: "In den Einstellungen einschalten", historyEmpty: "Noch nichts gespeichert – der nächste Druck erscheint hier.",
    confirmClear: "Alle gespeicherten Aufträge löschen?",
    confirmHistoryOff: "Verlauf ausschalten? Alle {0} gespeicherten Aufträge werden gelöscht.",
    settings: "Einstellungen", settingsHint: "Dichte, Bildmodus, Vorschub, Akku, Verbindung",
    density: "Druckdichte", printSample: "Probe drucken",
    densityHelp: "Heizstärke. Höher = dunkler, aber feine Details laufen eher zu. Getestet: 40. WalkPrint nutzt 25.",
    imageMode: "Bildmodus", modeAuto: "Automatisch – Text scharf, Fotos gerastert",
    modeText: "Text – harte Schwelle, alles gestochen scharf", modePhoto: "Foto – alles gerastert",
    imageModeHelp: "Gilt für Druckqualität „Normal“. „Entwurf“ druckt immer als Text, „Hoch“ immer als Foto.",
    photoBrightness: "Foto-Helligkeit",
    photoBrightnessHelp: "Hellt die Mitteltöne von Fotos auf (Schwarz und Weiß bleiben). Auf Thermopapier laufen die Punkte etwas aus, deshalb wirken Fotos oft dunkler als am Bildschirm. Text und Grafik sind nicht betroffen. Mit „Nochmal drucken“ im Verlauf lässt sich der Wert gut vergleichen.",
    feed: "Vorschub nach dem Druck", feedHelp: "Damit das Ende über die Abreißkante kommt.",
    batteryCheck: "Akku automatisch prüfen", off: "aus", every15: "alle 15 Minuten", every30: "alle 30 Minuten",
    every60: "jede Stunde", every120: "alle 2 Stunden", warnFrom: "warnen ab",
    batteryCheckHelp: "Fragt den Ladestand ab, wenn gerade nichts gedruckt wird (ist der Drucker aus, passiert nichts). Nach jedem Druck wird er ohnehin gemessen. Warnt einmal bei „schwach“ und einmal bei „fast leer“ (5 %), erkennt das Laden am USB-Kabel und meldet, wenn der Akku voll ist. Der Ladestand ist aus der Spannung geschätzt.",
    rotate: "Um 180° drehen (vom Druckergesicht aus lesbar)", trim: "Weißraum am Seitenende abschneiden",
    keepHistory: "Verlauf: gedruckte Aufträge speichern",
    keepHistoryHelp: "Speichert eine Kopie jeder gedruckten Seite auf diesem PC (<code>%APPDATA%\\CatPrinterDriver\\history</code>, höchstens 30 Aufträge), damit du sie ansehen und nochmal drucken kannst. Standardmäßig aus. <strong>Beim Ausschalten wird der Verlauf gelöscht.</strong>",
    shareNetwork: "Im Heimnetz freigeben (Drucken vom Handy)",
    shareNetworkHelp: "Macht den Drucker für Handys und andere Geräte im selben WLAN sichtbar (Android: „Standard-Druckdienst“). Nur Drucken ist aus dem Netz erreichbar – Statusseite, Einstellungen und Verlauf bleiben auf diesem PC. Beim ersten Einschalten fragt Windows nach Adminrechten für die Firewall. Jeder im Heimnetz kann dann drucken.",
    matchTone: "Fotos vom Handy aufhellen wie am PC",
    matchToneHelp: "Windows hellt beim Drucken die Schatten von Fotos auf, Handys nicht – ohne Ausgleich werden Handy-Fotos deutlich dunkler. Betrifft nur Fotos, nicht Text und Grafik.",
    comPort: "COM-Port", automatic: "automatisch", btName: "Bluetooth-Name beginnt mit",
    connectionHelp: "COM-Port leer lassen, um den Drucker automatisch über seinen Bluetooth-Namen zu finden. Druckeradresse für Windows:",
    discard: "Verwerfen", save: "Speichern", unsaved: "Nicht gespeicherte Änderungen",
    saved: "Gespeichert – gilt ab dem nächsten Druck", errorCode: "Fehler {0}",
    footer: "CatPrinterDriver · aktualisiert sich automatisch · Änderungen gelten sofort und werden in config.json gespeichert",
  },
  en: {
    subtitle: "Bluetooth thermal printer · 58 mm", connecting: "Connecting …", serverDown: "Server not reachable",
    ready: "Ready", printing: "Printing …", cooling: "Too hot – cooling down …", error: "Error",
    jobDone: "Printed", jobPrinting: "Printing", jobPending: "Waiting", jobFailed: "Failed", jobCanceled: "Canceled",
    battery: "Battery", connection: "Connection", printed: "Printed", notMeasured: "not measured yet",
    measuring: "measuring …", measuredAt: "measured {0}", battCritical: "almost empty – charge via USB now ({0})",
    battLow: "low – please charge soon ({0})", charging: "charging …", full: "full", atCharger: "on the charger · ",
    chargingVoltage: "charging voltage {0} · ", automaticPort: "Automatic", bluetoothSerial: "Bluetooth (serial)",
    portSearched: "COM port is found on the first print", since: "since {0}", minutes: "{0} min",
    hours: "{0} h", days: "{0} days", lastError: "Last error: {0}",
    sharedOnNetwork: "Shared on your home network", netSetup: "– setting up …",
    netHow: "· Phone on the same Wi-Fi → Print → choose printer “{0}” · {1}", netNoAddr: "· no home network address found",
    netFirewall: "Firewall rule missing – switch sharing off and on again in the settings.",
    netPublic: "A network is set to “Public” – phones can't reach the printer there (Windows: network profile “Private”).",
    netAdvert: "Network announcement failed: {0}", unknown: "unknown",
    printTestPage: "Print test page", checkBattery: "Check battery", jobs: "Print jobs", noJobs: "No jobs yet",
    page: "page", pages: "pages", history: "History", deleteAll: "Delete all", close: "Close",
    previewHint: "Preview with the current settings", printAgain: "Print again", delete: "Delete",
    view: "View", preview: "Preview", historyOff: "History is off – printed jobs are not stored.",
    enableInSettings: "Turn it on in the settings", historyEmpty: "Nothing stored yet – the next print will appear here.",
    confirmClear: "Delete all stored jobs?",
    confirmHistoryOff: "Turn off the history? All {0} stored jobs will be deleted.",
    settings: "Settings", settingsHint: "Density, image mode, feed, battery, connection",
    density: "Print density", printSample: "Print sample",
    densityHelp: "Heat strength. Higher = darker, but fine details fill in more easily. Tested: 40. WalkPrint uses 25.",
    imageMode: "Image mode", modeAuto: "Automatic – sharp text, dithered photos",
    modeText: "Text – hard threshold, everything crisp", modePhoto: "Photo – everything dithered",
    imageModeHelp: "Applies to print quality “Normal”. “Draft” always prints as text, “High” always as photo.",
    photoBrightness: "Photo brightness",
    photoBrightnessHelp: "Lightens the mid-tones of photos (black and white stay). Thermal dots spread a little, so photos often look darker than on screen. Text and graphics are not affected. Compare values with “Print again” in the history.",
    feed: "Paper feed after printing", feedHelp: "So the end of the print clears the tear-off edge.",
    batteryCheck: "Check battery automatically", off: "off", every15: "every 15 minutes", every30: "every 30 minutes",
    every60: "every hour", every120: "every 2 hours", warnFrom: "warn at",
    batteryCheckHelp: "Reads the battery level while nothing is printing (if the printer is off, nothing happens). It is measured after every print anyway. Warns once at “low” and once at “almost empty” (5 %), detects charging via USB and reports when the battery is full. The level is estimated from the voltage.",
    rotate: "Rotate 180° (readable from the printer's face)", trim: "Trim blank space at the end of the page",
    keepHistory: "History: keep printed jobs",
    keepHistoryHelp: "Stores a copy of every printed page on this PC (<code>%APPDATA%\\CatPrinterDriver\\history</code>, up to 30 jobs) so you can view and print them again. Off by default. <strong>Turning it off deletes the history.</strong>",
    shareNetwork: "Share on home network (print from phones)",
    shareNetworkHelp: "Makes the printer visible to phones and other devices on the same Wi-Fi (Android: “Default Print Service”). Only printing is reachable from the network – status page, settings and history stay on this PC. The first time, Windows asks for admin rights for the firewall. Anyone on your home network can then print.",
    matchTone: "Lighten phone photos like on the PC",
    matchToneHelp: "Windows lightens photo shadows when printing, phones don't – without this, phone photos come out noticeably darker. Only affects photos, not text and graphics.",
    comPort: "COM port", automatic: "automatic", btName: "Bluetooth name starts with",
    connectionHelp: "Leave the COM port empty to find the printer automatically by its Bluetooth name. Printer address for Windows:",
    discard: "Discard", save: "Save", unsaved: "Unsaved changes",
    saved: "Saved – applies from the next print", errorCode: "Error {0}",
    footer: "CatPrinterDriver · updates automatically · changes apply immediately and are saved in config.json",
  },
};

function pickLang() {
  try {
    const stored = localStorage.getItem("catprinter-lang");
    if (stored === "de" || stored === "en") return stored;
  } catch { /* Speicher nicht verfügbar */ }
  return (navigator.language || "en").toLowerCase().startsWith("de") ? "de" : "en";
}
let lang = pickLang();

function t(key, ...args) {
  const text = (I18N[lang] && I18N[lang][key]) ?? I18N.de[key] ?? key;
  return text.replace(/\{(\d)\}/g, (_m, i) => args[Number(i)] ?? "");
}
function locale() { return lang === "de" ? "de-DE" : "en-GB"; }
function num(v, digits) {
  return Number(v).toLocaleString(locale(), { minimumFractionDigits: digits, maximumFractionDigits: digits });
}

function applyStatic() {
  document.documentElement.lang = lang;
  document.querySelectorAll("[data-i18n]").forEach((e) => { e.textContent = t(e.dataset.i18n); });
  document.querySelectorAll("[data-i18n-html]").forEach((e) => { e.innerHTML = t(e.dataset.i18nHtml); });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((e) => { e.placeholder = t(e.dataset.i18nPlaceholder); });
  document.querySelectorAll("[data-i18n-aria]").forEach((e) => { e.setAttribute("aria-label", t(e.dataset.i18nAria)); });
  document.querySelectorAll(".lang button").forEach((b) => b.classList.toggle("active", b.dataset.lang === lang));
}
function setLang(l) {
  lang = l;
  try { localStorage.setItem("catprinter-lang", l); } catch { /* egal */ }
  applyStatic();
  historyKey = "";  // Verlauf in der neuen Sprache neu zeichnen
  if (lastStatus) render(lastStatus);
  if (lastHistory) renderHistory(lastHistory);
  if (dirty) setMsg(t("unsaved"));
}
document.querySelectorAll(".lang button").forEach((b) => { b.onclick = () => setLang(b.dataset.lang); });

const JOB = { done: "jobDone", printing: "jobPrinting", pending: "jobPending", failed: "jobFailed", canceled: "jobCanceled" };
let saved = null;   // Einstellungen laut Server
let dirty = false;  // ungespeicherte Änderungen im Formular?
let lastStatus = null, lastHistory = null;

function fillForm(s) {
  $("f-density").value = s.density;
  $("density-out").textContent = s.density;
  $("f-mode").value = s.image_mode;
  $("f-feed").value = s.feed_mm;
  $("f-rotate").checked = s.rotate_180;
  $("f-trim").checked = s.trim_bottom;
  $("f-port").value = s.com_port;
  $("f-btname").value = s.bluetooth_name;
  $("f-history").checked = s.keep_history;
  $("f-share").checked = s.share_network;
  $("f-tone").checked = s.match_windows_tone;
  $("f-bright").value = s.photo_brightness;
  $("f-battery-check").value = String(s.battery_check_minutes);
  $("f-battery-warn").value = s.battery_warn_percent;
  $("bright-out").textContent = fmtPercent(s.photo_brightness);
}
function fmtPercent(v) { v = Number(v); return (v > 0 ? "+" : "") + v + " %"; }
function readForm() {
  return {
    density: Number($("f-density").value),
    image_mode: $("f-mode").value,
    feed_mm: Number($("f-feed").value),
    rotate_180: $("f-rotate").checked,
    trim_bottom: $("f-trim").checked,
    com_port: $("f-port").value.trim(),
    bluetooth_name: $("f-btname").value.trim(),
    keep_history: $("f-history").checked,
    share_network: $("f-share").checked,
    match_windows_tone: $("f-tone").checked,
    photo_brightness: Number($("f-bright").value),
    battery_check_minutes: Number($("f-battery-check").value),
    battery_warn_percent: Number($("f-battery-warn").value),
  };
}
function changes() {
  const form = readForm(), out = {};
  for (const k in form) if (!saved || form[k] !== saved[k]) out[k] = form[k];
  return out;
}
function setMsg(text, cls) {
  const m = $("save-msg");
  m.textContent = text;
  m.className = "save-msg " + (cls || "");
}
function updateDirty() {
  dirty = Object.keys(changes()).length > 0;
  $("btn-save").disabled = $("btn-reset").disabled = !dirty;
  if (dirty) setMsg(t("unsaved"));
}
async function post(name, data) {
  const r = await fetch("action/" + name, {
    method: "POST",
    headers: { "X-CatPrinter": "1", "Content-Type": "application/json" },
    body: JSON.stringify(data || {}),
  });
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.error || t("errorCode", r.status));
  return body;
}

function fmtTime(epoch) {
  const d = new Date(epoch * 1000), now = new Date();
  const time = d.toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString() ? time : d.toLocaleDateString(locale()) + " " + time;
}
function fmtUptime(s) {
  if (s < 3600) return t("minutes", Math.max(1, Math.round(s / 60)));
  if (s < 86400) return t("hours", Math.round(s / 3600));
  return t("days", Math.round(s / 86400));
}
function pagesText(n) { return n + " " + (n === 1 ? t("page") : t("pages")); }
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function renderNetwork(n, name) {
  $("netinfo").hidden = !n.enabled;
  if (!n.enabled) return;
  if (!n.addresses) {
    $("net-text").textContent = t("netSetup");
    $("net-warn").hidden = true;
    return;
  }
  $("net-text").textContent = n.addresses.length
    ? t("netHow", n.name || name, n.addresses.join(", ") + ":" + n.port)
    : t("netNoAddr");
  const warn = [];
  if (n.firewall === false) warn.push(t("netFirewall"));
  if (n.profiles && Object.values(n.profiles).includes("Public")) warn.push(t("netPublic"));
  if (n.advertised === false) warn.push(t("netAdvert", n.error || t("unknown")));
  $("net-warn").textContent = warn.join(" ");
  $("net-warn").hidden = !warn.length;
}

function renderBattery(b, checking) {
  if (b.percent !== undefined) {
    const cls = b.level === "critical" ? "low" : b.level === "low" ? "warnlow" : "";
    const when = new Date(b.time * 1000).toLocaleTimeString(locale(), { hour: "2-digit", minute: "2-digit" });
    const volts = num(b.volts, 2) + " V";
    $("volts").textContent = b.percent + " %";
    $("volts").className = "value " + cls;
    $("battery-fill").style.width = b.percent + "%";
    $("battery-fill").className = cls;
    $("volts-hint").textContent =
      b.level === "critical" ? t("battCritical", volts) :
      b.level === "low" ? t("battLow", volts) :
      volts + " · " + t("measuredAt", when);
    if (b.charging) {
      // Am Kabel misst der Drucker die Ladespannung mit – keine (geschönte) Prozentzahl zeigen
      $("volts").textContent = b.full ? t("full") : t("charging");
      $("volts").className = "value";
      $("battery-fill").style.width = b.full ? "100%" : "";
      $("battery-fill").className = b.full ? "" : "charging";
      $("volts-hint").textContent = (b.full ? t("atCharger") : t("chargingVoltage", volts)) + t("measuredAt", when);
    }
  } else {
    $("volts-hint").textContent = t("notMeasured");
  }
  if (checking) $("volts-hint").textContent = t("measuring");
}

function render(s) {
  lastStatus = s;
  $("name").textContent = s.name;
  document.title = s.name + " – " + t(s.state);
  const pill = $("pill");
  pill.className = "pill " + s.state;
  pill.textContent = t(s.state);
  $("alert").hidden = !s.error;
  $("alert").textContent = s.error ? t("lastError", s.error) : "";

  renderBattery(s.battery || {}, s.checking);
  $("port").textContent = s.port || t("automaticPort");
  $("firmware").textContent = s.firmware ? "Firmware " + s.firmware
    : (s.port ? t("bluetoothSerial") : t("portSearched"));
  $("count").textContent = s.printed;
  $("uptime").textContent = t("since", fmtUptime(s.uptime));

  $("url").textContent = s.url;
  renderNetwork(s.network, s.name);
  saved = s.settings;
  if (!dirty) fillForm(saved);

  const list = $("jobs");
  list.replaceChildren();
  if (!s.jobs.length) list.append(el("div", "empty", t("noJobs")));
  for (const j of s.jobs) {
    const row = el("div", "job");
    const info = el("div", "name");
    info.append(el("div", "title", j.name));
    info.append(el("div", "meta", "#" + j.id + " · " + fmtTime(j.created) + (j.pages ? " · " + pagesText(j.pages) : "")));
    if (j.message) info.append(el("div", "msg", j.message));
    row.append(info, el("span", "badge " + j.state, t(JOB[j.state])));
    list.append(row);
  }
  $("btn-battery").disabled = s.checking;
}

let historyKey = "";   // zuletzt gezeichneter Verlauf (nur neu zeichnen, wenn er sich ändert)
let historyEntries = [];
let viewing = null;

function renderHistory(h) {
  lastHistory = h;
  const key = JSON.stringify(h);
  if (key === historyKey) return;
  historyKey = key;
  historyEntries = h.entries;
  const box = $("history");
  $("btn-clear").hidden = !h.enabled || !h.entries.length;
  box.replaceChildren();
  if (!h.enabled) {
    const empty = el("div", "empty", t("historyOff"));
    const link = el("button", "link", t("enableInSettings"));
    link.type = "button";
    link.onclick = openHistorySetting;
    empty.append(document.createElement("br"), link);
    box.append(empty);
    return;
  }
  if (!h.entries.length) {
    box.append(el("div", "empty", t("historyEmpty")));
    return;
  }
  for (const e of h.entries) {
    const row = el("div", "hist");
    const thumb = el("button", "thumb");
    thumb.type = "button";
    thumb.title = t("view");
    const img = el("img");
    img.alt = t("preview") + " " + e.name;
    img.loading = "lazy";
    img.src = "history/" + e.id + "/1.png?thumb=1";
    thumb.append(img);
    thumb.onclick = () => openViewer(e);
    const info = el("div", "name");
    info.append(el("div", "title", e.name));
    info.append(el("div", "meta", fmtTime(e.created) + " · " + pagesText(e.pages)));
    const buttons = el("div", "buttons");
    const again = el("button", "small", t("printAgain"));
    again.type = "button";
    again.onclick = () => reprint(e.id, again);
    const del = el("button", "small danger", t("delete"));
    del.type = "button";
    del.onclick = () => removeEntry(e.id, del);
    buttons.append(again, del);
    const badgeState = e.state === "failed" ? "failed" : e.state === "done" ? "done" : "pending";
    row.append(thumb, info, el("span", "badge " + badgeState, t(JOB[badgeState])), buttons);
    box.append(row);
  }
}

async function loadHistory() {
  try {
    const r = await fetch("history.json", { cache: "no-store" });
    renderHistory(await r.json());
  } catch { /* Server kurz weg – nächster Versuch beim nächsten Refresh */ }
}

function openViewer(e) {
  viewing = e;
  $("viewer-title").textContent = e.name;
  $("viewer-meta").textContent = fmtTime(e.created) + " · " + pagesText(e.pages);
  const pages = $("viewer-pages");
  pages.replaceChildren();
  for (let n = 1; n <= e.pages; n++) {
    const img = el("img");
    img.alt = t("page") + " " + n;
    img.src = "history/" + e.id + "/" + n + ".png?t=" + Date.now();
    pages.append(img);
  }
  $("viewer").showModal();
}
$("viewer-close").onclick = () => $("viewer").close();
$("viewer").addEventListener("click", (ev) => { if (ev.target === $("viewer")) $("viewer").close(); });
$("viewer-reprint").onclick = (ev) => { if (viewing) reprint(viewing.id, ev.currentTarget); };

async function reprint(id, button) {
  button.disabled = true;
  try {
    await post("reprint", { id });
    if ($("viewer").open) $("viewer").close();
  } catch (err) {
    alert(err.message);
  } finally {
    setTimeout(() => { button.disabled = false; refresh(); }, 600);
  }
}
async function removeEntry(id, button) {
  button.disabled = true;
  try { await post("history-delete", { id }); } finally { loadHistory(); }
}
$("btn-clear").onclick = async () => {
  if (!confirm(t("confirmClear"))) return;
  await post("history-clear");
  loadHistory();
};
function openHistorySetting() {
  $("settings-section").open = true;
  $("f-history").focus();
  $("f-history").scrollIntoView({ block: "center", behavior: "smooth" });
}

async function refresh() {
  loadHistory();
  try {
    const r = await fetch("status.json", { cache: "no-store" });
    render(await r.json());
  } catch {
    $("pill").className = "pill offline";
    $("pill").textContent = t("serverDown");
  }
}

async function action(name, button, data) {
  button.disabled = true;
  try {
    await post(name, data);
  } catch (err) {
    setMsg(err.message, "err");
  } finally {
    setTimeout(() => { button.disabled = false; refresh(); }, 600);
  }
}
$("btn-test").onclick = (e) => action("test", e.currentTarget);
$("btn-battery").onclick = (e) => action("battery", e.currentTarget);
$("btn-calibrate").onclick = (e) =>
  action("calibrate", e.currentTarget, { density: Number($("f-density").value) });

$("settings").addEventListener("input", (e) => {
  if (e.target.id === "f-density") $("density-out").textContent = e.target.value;
  if (e.target.id === "f-bright") $("bright-out").textContent = fmtPercent(e.target.value);
  updateDirty();
});
$("btn-reset").onclick = () => { fillForm(saved); updateDirty(); setMsg(""); };
$("settings").onsubmit = async (e) => {
  e.preventDefault();
  const diff = changes();
  if (!Object.keys(diff).length) return;
  if (diff.keep_history === false && historyEntries.length &&
      !confirm(t("confirmHistoryOff", historyEntries.length))) return;
  $("btn-save").disabled = true;
  try {
    await post("settings", diff);
    dirty = false;
    await refresh();
    updateDirty();
    setMsg(t("saved"), "ok");
  } catch (err) {
    setMsg(err.message, "err");
    $("btn-save").disabled = false;
  }
};
$("btn-save").disabled = $("btn-reset").disabled = true;

applyStatic();
$("jobs").append(el("div", "empty", t("noJobs")));
refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""
