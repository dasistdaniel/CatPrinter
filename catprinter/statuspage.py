"""Statusseite (http://127.0.0.1:631/) und ihre JSON-Daten."""
import time

from .printer import battery_volts

STATE_KEYS = {3: "pending", 5: "printing", 7: "canceled", 8: "failed", 9: "done"}


def status_dict(service):
    """Aktueller Zustand für /status.json."""
    cfg = service.cfg
    error = service.last_error if service.last_error and time.time() - service.last_error[0] < 120 else None
    state = "printing" if service.active else ("error" if error else "ready")
    jobs = sorted(list(service.jobs.values()), key=lambda j: -j.id)[:20]
    return {
        "name": cfg.get("printer_name", "Cat Printer"),
        "state": state,
        "error": error[1] if error else None,
        "port": service.printer.port,
        "volts": battery_volts(service.status),
        "firmware": service.status.get("SV"),
        "checking": service.checking,
        "density": cfg.get("density"),
        "image_mode": cfg.get("image_mode", "auto"),
        "rotate": cfg.get("rotate_180", True),
        "feed_mm": cfg.get("feed_mm"),
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
.pill {
  margin-left: auto; display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 14px; border-radius: 999px; font-weight: 600; font-size: 14px; white-space: nowrap;
}
.pill::before { content: ""; width: 9px; height: 9px; border-radius: 50%; background: currentColor; }
.pill.ready { color: var(--ok); background: var(--ok-bg); }
.pill.printing { color: var(--busy); background: var(--busy-bg); }
.pill.printing::before { animation: pulse 1s ease-in-out infinite; }
.pill.error { color: var(--err); background: var(--err-bg); }
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
dl { display: grid; grid-template-columns: max-content 1fr; gap: 6px 16px; margin: 0; font-size: 14px; }
dt { color: var(--muted); }
dd { margin: 0; overflow-wrap: anywhere; }
footer { color: var(--muted); font-size: 12px; margin-top: 24px; text-align: center; }
@media (max-width: 600px) {
  .grid { grid-template-columns: 1fr; }
  header { flex-wrap: wrap; }
  .pill { margin-left: 0; }
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
      <div class="sub">Bluetooth-Thermodrucker · 58 mm</div>
    </div>
    <span id="pill" class="pill offline">Verbinde …</span>
  </header>

  <div id="alert" class="alert" hidden></div>

  <div class="grid">
    <div class="card">
      <div class="label">Akku</div>
      <div class="value" id="volts">–</div>
      <div class="hint" id="volts-hint">wird beim Drucken gemessen</div>
    </div>
    <div class="card">
      <div class="label">Verbindung</div>
      <div class="value" id="port">–</div>
      <div class="hint" id="firmware">Bluetooth (seriell)</div>
    </div>
    <div class="card">
      <div class="label">Gedruckt</div>
      <div class="value" id="count">0</div>
      <div class="hint" id="uptime">seit dem Start</div>
    </div>
  </div>

  <div class="actions">
    <button class="primary" id="btn-test">Testseite drucken</button>
    <button id="btn-battery">Akku prüfen</button>
  </div>

  <h2>Druckaufträge</h2>
  <div class="card jobs" id="jobs"><div class="empty">Noch keine Aufträge</div></div>

  <h2 style="margin-top:24px">Einstellungen</h2>
  <div class="card">
    <dl>
      <dt>Druckdichte</dt><dd id="density">–</dd>
      <dt>Bildmodus</dt><dd id="mode">–</dd>
      <dt>Ausrichtung</dt><dd id="rotate">–</dd>
      <dt>Vorschub</dt><dd id="feed">–</dd>
      <dt>Druckeradresse</dt><dd id="url">–</dd>
    </dl>
  </div>

  <footer>CatPrinterDriver · aktualisiert sich automatisch · Einstellungen über das Tray-Symbol bearbeiten</footer>
</main>
<script>
const $ = (id) => document.getElementById(id);
const STATE = { ready: "Bereit", printing: "Druckt …", error: "Fehler" };
const JOB = { done: "Gedruckt", printing: "Druckt", pending: "Wartet", failed: "Fehlgeschlagen", canceled: "Abgebrochen" };
const MODE = { auto: "Automatisch (Text scharf, Fotos gerastert)", text: "Text (harte Schwelle)", photo: "Foto (alles gerastert)" };
const LOW_VOLTS = 6.8;

function fmtTime(epoch) {
  const d = new Date(epoch * 1000), now = new Date();
  const t = d.toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  return d.toDateString() === now.toDateString() ? t : d.toLocaleDateString("de-DE") + " " + t;
}
function fmtUptime(s) {
  if (s < 3600) return Math.max(1, Math.round(s / 60)) + " Min.";
  if (s < 86400) return Math.round(s / 3600) + " Std.";
  return Math.round(s / 86400) + " Tagen";
}
function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

function render(s) {
  $("name").textContent = s.name;
  document.title = s.name + " – " + STATE[s.state];
  const pill = $("pill");
  pill.className = "pill " + s.state;
  pill.textContent = STATE[s.state];
  $("alert").hidden = !s.error;
  $("alert").textContent = s.error ? "Letzter Fehler: " + s.error : "";

  if (s.volts) {
    $("volts").textContent = s.volts.toFixed(2).replace(".", ",") + " V";
    $("volts").classList.toggle("low", s.volts < LOW_VOLTS);
    $("volts-hint").textContent = s.volts < LOW_VOLTS ? "schwach – bitte per USB laden" : "zuletzt gemessen";
  }
  if (s.checking) $("volts-hint").textContent = "wird gemessen …";
  $("port").textContent = s.port || "Automatisch";
  $("firmware").textContent = s.firmware ? "Firmware " + s.firmware
    : (s.port ? "Bluetooth (seriell)" : "COM-Port wird beim ersten Druck gesucht");
  $("count").textContent = s.printed;
  $("uptime").textContent = "seit " + fmtUptime(s.uptime);

  $("density").textContent = s.density;
  $("mode").textContent = MODE[s.image_mode] || s.image_mode;
  $("rotate").textContent = s.rotate ? "180° gedreht (vom Druckergesicht aus lesbar)" : "ungedreht";
  $("feed").textContent = s.feed_mm + " mm";
  $("url").textContent = s.url;

  const list = $("jobs");
  list.replaceChildren();
  if (!s.jobs.length) list.append(el("div", "empty", "Noch keine Aufträge"));
  for (const j of s.jobs) {
    const row = el("div", "job");
    const info = el("div", "name");
    info.append(el("div", "title", j.name));
    const pages = j.pages ? " · " + j.pages + (j.pages === 1 ? " Seite" : " Seiten") : "";
    info.append(el("div", "meta", "#" + j.id + " · " + fmtTime(j.created) + pages));
    if (j.message) info.append(el("div", "msg", j.message));
    row.append(info, el("span", "badge " + j.state, JOB[j.state]));
    list.append(row);
  }
  $("btn-battery").disabled = s.checking;
}

async function refresh() {
  try {
    const r = await fetch("status.json", { cache: "no-store" });
    render(await r.json());
  } catch {
    $("pill").className = "pill offline";
    $("pill").textContent = "Server nicht erreichbar";
  }
}

async function action(name, button) {
  button.disabled = true;
  try {
    await fetch("action/" + name, { method: "POST", headers: { "X-CatPrinter": "1" } });
  } finally {
    setTimeout(() => { button.disabled = false; refresh(); }, 600);
  }
}
$("btn-test").onclick = (e) => action("test", e.currentTarget);
$("btn-battery").onclick = (e) => action("battery", e.currentTarget);

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>
"""
