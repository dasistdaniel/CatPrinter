"""Freigabe im Heimnetz: Drucken vom Handy (Android-Standarddruckdienst, iOS/AirPrint-fähige Apps).

- Bekanntgabe per mDNS/DNS-SD als IPP-Drucker (_ipp._tcp), damit Geräte ihn finden
- Firewall-Regeln für private Netzwerke (einmalig mit Adminrechten)
- Nur Drucken ist aus dem Netz erreichbar; Statusseite und Verlauf bleiben lokal
"""
import ipaddress
import logging
import socket
import subprocess

log = logging.getLogger("netshare")

FIREWALL_RULES = (
    ("Cat Printer (IPP)", "TCP", 631),
    ("Cat Printer (mDNS)", "UDP", 5353),
)


def is_loopback(ip):
    try:
        return ipaddress.ip_address(ip.split("%")[0]).is_loopback
    except ValueError:
        return False


def is_lan(ip):
    """Private/Link-Local-Adresse (Heimnetz) – nie Adressen aus dem Internet."""
    try:
        addr = ipaddress.ip_address(ip.split("%")[0])
    except ValueError:
        return False
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped:
        addr = addr.ipv4_mapped
    return (addr.is_private or addr.is_link_local) and not addr.is_loopback


def lan_host_ok(host):
    """Host-Header für Anfragen aus dem Netz: IP-Adresse oder der Name dieses PCs.

    Verhindert DNS-Rebinding über die Netzwerkadresse (fremde Domain -> Rechner-IP).
    """
    name = host.rsplit(":", 1)[0] if host.count(":") == 1 or host.startswith("[") else host
    name = name.strip("[]").lower().rstrip(".")
    try:
        ipaddress.ip_address(name)
        return True
    except ValueError:
        pass
    me = socket.gethostname().lower()
    return name in (me, me + ".local", "localhost")


def lan_addresses():
    """IPv4-Adressen dieses PCs im Heimnetz (Anzeige und mDNS-Bekanntgabe).

    Ohne 169.254.x.x: Diese Notfalladressen haben Adapter ohne echte Verbindung –
    ein Handy würde dort vergeblich anfragen.
    """
    addrs = set()
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if is_lan(ip) and not ipaddress.ip_address(ip).is_link_local:
                addrs.add(ip)
    except OSError:
        pass
    return sorted(addrs)


def _ps(script, timeout=30):
    return subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, text=True,
                          timeout=timeout, creationflags=subprocess.CREATE_NO_WINDOW).stdout.strip()


def firewall_ok():
    names = ",".join(f"'{n}'" for n, _p, _port in FIREWALL_RULES)
    out = _ps(f"@(Get-NetFirewallRule -DisplayName {names} -ErrorAction SilentlyContinue |"
              " Where-Object Enabled -eq 'True').Count")
    return out == str(len(FIREWALL_RULES))


def firewall_any():
    names = ",".join(f"'{n}'" for n, _p, _port in FIREWALL_RULES)
    return _ps(f"@(Get-NetFirewallRule -DisplayName {names} -ErrorAction SilentlyContinue).Count") not in ("", "0")


def firewall_script(remove=False):
    lines = [f"Remove-NetFirewallRule -DisplayName '{n}' -ErrorAction SilentlyContinue"
             for n, _p, _port in FIREWALL_RULES]
    if not remove:
        lines += [f"New-NetFirewallRule -DisplayName '{n}' -Direction Inbound -Protocol {p} -LocalPort {port}"
                  " -Profile Private -Action Allow | Out-Null" for n, p, port in FIREWALL_RULES]
    return "; ".join(lines)


def network_profiles():
    """Kategorie der aktiven Netzwerke, z. B. {'Ethernet': 'Private'}."""
    out = _ps("Get-NetConnectionProfile | ForEach-Object { $_.InterfaceAlias + '=' + $_.NetworkCategory }")
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


class Advertiser:
    """Gibt den Drucker per mDNS im Netz bekannt (wie ein Netzwerkdrucker)."""

    def __init__(self, cfg, port):
        self.cfg = cfg
        self.port = port
        self.zc = None
        self.infos = []

    def start(self):
        from zeroconf import IPVersion, ServiceInfo, Zeroconf

        host = socket.gethostname()
        name = f"{self.cfg.get('printer_name', 'Cat Printer')} @ {host}"
        addrs = [socket.inet_aton(ip) for ip in lan_addresses()]
        if not addrs:
            log.warning("Keine Heimnetz-Adresse gefunden – mDNS-Bekanntgabe übersprungen")
            return
        txt = {
            "txtvers": "1", "qtotal": "1", "rp": "ipp/print",
            "ty": "YHK Cat Printer", "product": "(YHK Cat Printer)", "note": host,
            "pdl": "image/pwg-raster,application/octet-stream",
            "UUID": self.cfg["uuid"], "Color": "F", "Duplex": "F", "Copies": "T",
            "kind": "roll", "PaperMax": "<legal-A4", "priority": "50",
        }
        self.zc = Zeroconf(ip_version=IPVersion.V4Only)
        info = ServiceInfo("_ipp._tcp.local.", f"{name}._ipp._tcp.local.", addresses=addrs, port=self.port,
                           properties=txt, server=f"{host}.local.")
        self.zc.register_service(info, allow_name_change=True)
        self.infos = [info]
        log.info("Im Netzwerk bekannt gegeben: %s (%s:%d)", name, ", ".join(lan_addresses()), self.port)

    def stop(self):
        if self.zc:
            for info in self.infos:
                try:
                    self.zc.unregister_service(info)
                except Exception:  # noqa: BLE001
                    pass
            self.zc.close()
            self.zc = None
