"""Tests ohne Drucker: python -m unittest discover tests"""
import http.client
import io
import json
import os
import random
import socket
import tempfile
import threading
import time
import unittest
import unittest.mock

from PIL import Image, ImageChops

from catprinter import ipp, pwg, server
from catprinter.printer import WIDTH, build_job, prepare


def noisy_image(w, h, seed=1):
    rnd = random.Random(seed)
    img = Image.new("L", (w, h), 255)
    px = img.load()
    for y in range(h):
        for x in range(w):
            r = rnd.random()
            # Mischung aus Läufen und Rauschen, damit beide Kodierungen vorkommen
            px[x, y] = 0 if (x // 7 + y // 5) % 3 == 0 else (int(r * 255) if r > 0.7 else 255)
    return img


class PwgTest(unittest.TestCase):
    def test_roundtrip_gray(self):
        img = noisy_image(383, 97)
        (hdr, out), = pwg.decode(pwg.encode(img, gray=True))
        self.assertEqual((hdr.width, hdr.height, hdr.bits_per_pixel), (383, 97, 8))
        self.assertIsNone(ImageChops.difference(img, out).getbbox())

    def test_roundtrip_black1(self):
        img = noisy_image(383, 60).convert("1")
        (hdr, out), = pwg.decode(pwg.encode(img, gray=False))
        self.assertEqual(hdr.bits_per_pixel, 1)
        self.assertIsNone(ImageChops.difference(img.convert("L"), out.convert("L")).getbbox())

    def test_repeated_and_white_lines(self):
        img = Image.new("L", (500, 600), 255)
        img.paste(0, (10, 10, 490, 300))
        (_h, out), = pwg.decode(pwg.encode(img))
        self.assertIsNone(ImageChops.difference(img, out).getbbox())


class IppTest(unittest.TestCase):
    def test_roundtrip_with_collection(self):
        msg = ipp.Message((2, 0), ipp.GET_PRINTER_ATTRIBUTES, 42, [
            (ipp.OPERATION, [("attributes-charset", ipp.CHARSET, ["utf-8"]),
                             ("requested-attributes", ipp.KEYWORD, ["all", "media-col-database"])]),
            (ipp.JOB, [("media-col", ipp.BEGIN_COLLECTION, [[
                ("media-size", ipp.BEGIN_COLLECTION, [[("x-dimension", ipp.INTEGER, [4800]),
                                                       ("y-dimension", ipp.INTEGER, [8000])]]),
                ("media-type", ipp.KEYWORD, ["stationery"])]]),
                ("copies", ipp.INTEGER, [2])]),
        ])
        dec, doc = ipp.decode(ipp.encode(msg) + b"DOC")
        self.assertEqual(doc, b"DOC")
        self.assertEqual(dec.request_id, 42)
        self.assertEqual(dec.get_all("requested-attributes"), ["all", "media-col-database"])
        self.assertEqual(dec.get("copies"), 2)
        media = dec.get("media-col")
        self.assertEqual(media[0][0], "media-size")
        self.assertEqual(media[0][2][0][1][2], [8000])


class PrinterJobTest(unittest.TestCase):
    def test_prepare_and_build(self):
        bw = prepare(noisy_image(1680, 400))
        self.assertEqual(bw.width, WIDTH)
        job = build_job([bw], feed_mm=15, density=25)
        # Kein ESC @ (würde den Rest eines noch druckenden Auftrags verwerfen),
        # nur Dichte und genau ein GS-v-0-Block inkl. Vorschub
        self.assertTrue(job.startswith(b"\x1d\x49\xf0\x19\x1d\x76\x30\x00\x30\x00"))
        self.assertNotIn(b"\x1b\x40", job[:4])
        rows = int.from_bytes(job[10:12], "little")
        self.assertEqual(rows, bw.height + round(15 * 203 / 25.4))
        self.assertEqual(len(job), 12 + rows * 48)

    def test_modes(self):
        # Gleichmäßige Graufläche mit schwarzem Balken darüber
        img = Image.new("L", (WIDTH, 200), 255)
        img.paste(0, (0, 0, WIDTH, 40))
        img.paste(100, (0, 80, WIDTH, 160))
        gray_area = (20, 100, WIDTH - 20, 140)

        def black_share(bw, box):
            region = bw.convert("L").crop(box)
            return region.histogram()[0] / (region.width * region.height)

        text = prepare(img, trim=False, mode="text")
        self.assertEqual(black_share(text, gray_area), 1.0)  # Schwelle: Grau 100 -> schwarz
        for mode in ("auto", "photo"):
            share = black_share(prepare(img, trim=False, mode=mode), gray_area)
            self.assertTrue(0.4 < share < 0.8, (mode, share))  # gerastert
        self.assertEqual(black_share(prepare(img, trim=False, mode="auto"), (0, 0, WIDTH, 40)), 1.0)

    def test_photo_detection(self):
        from catprinter.printer import _is_photo
        self.assertFalse(_is_photo(Image.new("L", (WIDTH, 100), 255)))
        gradient = Image.linear_gradient("L").resize((WIDTH, 300))
        self.assertTrue(_is_photo(gradient))

    def test_quality_mapping(self):
        self.assertEqual(server.image_mode(3), "text")
        self.assertEqual(server.image_mode(4), "auto")
        self.assertEqual(server.image_mode(None, "photo"), "photo")
        self.assertEqual(server.image_mode(5, "text"), "photo")

    def test_rotate_after_trim(self):
        img = Image.new("L", (WIDTH, 1000), 255)
        img.paste(0, (0, 0, WIDTH, 100))  # schwarzer Block oben, viel Weiß darunter
        bw = prepare(img, rotate=True)
        self.assertLess(bw.height, 120)  # Weißraum wurde vor dem Drehen entfernt
        px = bw.convert("L").load()
        self.assertEqual(px[0, bw.height - 1], 0)  # Block liegt nach dem Drehen unten
        self.assertEqual(px[0, 0], 255)

    def test_trim(self):
        img = Image.new("L", (WIDTH, 1000), 255)
        img.paste(0, (0, 0, WIDTH, 100))
        self.assertLess(prepare(img).height, 120)


class FakeSerial:
    """Simulierter Drucker-Port: DLE EOT 3 meldet 'heiß', bis hot_replies aufgebraucht sind."""

    def __init__(self, hot_replies=0, stall_after=None, stall_seconds=0, hot_after_bytes=None):
        self.hot_replies = hot_replies
        self.hot_after_bytes = hot_after_bytes
        self.stall_after = stall_after
        self.stall_seconds = stall_seconds
        self.buffer = b""
        self.written = 0
        self.is_open = True
        self.closed = 0
        self.dead = False  # simuliert eine tote alte Verbindung (keine Antworten)

    def close(self):
        self.is_open = False
        self.closed += 1

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    @property
    def in_waiting(self):
        return len(self.buffer)

    def read(self, n):
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def reset_input_buffer(self):
        self.buffer = b""

    def flush(self):
        pass

    def write(self, data):
        if self.dead:
            return
        if data == b"\x10\x04\x03":
            hot = self.hot_replies > 0 or (self.hot_after_bytes is not None and self.written > self.hot_after_bytes)
            self.hot_replies -= 1
            self.buffer += b"\x52" if hot else b"\x12"
        elif data == b"\x1e\x47\x03":
            self.buffer += b"HV=H1.0,SV=V1.01,VOLT=7500mv,DPI=384,\x00"
        else:
            self.written += len(data)
            if self.stall_after is not None and self.written > self.stall_after:
                time.sleep(self.stall_seconds)
                self.stall_after = None


class HeatTest(unittest.TestCase):
    def make_printer(self, fake):
        from catprinter import printer as pr
        p = pr.Printer("COM99")
        p._open = lambda: fake
        p.chunk_delay = 0
        self.addCleanup(setattr, pr, "COOL_POLL", pr.COOL_POLL)
        self.addCleanup(setattr, pr, "STALL_SECONDS", pr.STALL_SECONDS)
        pr.COOL_POLL, pr.STALL_SECONDS = 0.01, 0.2
        return p

    def run_job(self, p):
        from catprinter import printer as pr
        events = []
        real_sleep = time.sleep  # lange Wartezeiten (z. B. 2 s Nachlauf) im Test überspringen
        with unittest.mock.patch.object(pr.time, "sleep", lambda s: None if s >= 1 else real_sleep(s)):
            p.print_images([Image.new("1", (WIDTH, 40), 0)], feed_mm=1, notify=events.append)
        return events

    def test_waits_until_cool_before_printing(self):
        fake = FakeSerial(hot_replies=3)
        events = self.run_job(self.make_printer(fake))
        self.assertEqual(events, ["cooling", "cooled"])
        self.assertGreater(fake.written, 0)

    def test_cold_printer_prints_directly(self):
        p = self.make_printer(FakeSerial())
        self.assertEqual(self.run_job(p), [])
        self.assertFalse(p.last_hot)
        self.assertEqual(p.last_status["VOLT"], "7500mv")

    def test_pause_in_the_middle_is_reported(self):
        events = self.run_job(self.make_printer(FakeSerial(stall_after=1000, stall_seconds=0.4)))
        self.assertEqual(events, ["paused_hot"])

    def test_full_buffer_is_not_a_heat_alarm(self):
        # Kurzes Blockieren = Puffer voll (Bluetooth bremst) – kein "zu heiß"
        events = self.run_job(self.make_printer(FakeSerial(stall_after=1000, stall_seconds=0.05)))
        self.assertEqual(events, [])

    def test_hot_after_job_is_reported(self):
        p = self.make_printer(FakeSerial(hot_after_bytes=1000))
        self.assertEqual(self.run_job(p), ["paused_hot"])
        self.assertTrue(p.last_hot)

    def test_connection_kept_between_jobs(self):
        # Neu verbinden, während der Drucker noch druckt, schneidet das Ende ab – also wiederverwenden
        fake = FakeSerial()
        p = self.make_printer(fake)
        opened = []
        p._open = lambda: opened.append(1) or fake
        self.run_job(p)
        self.run_job(p)
        self.assertEqual(len(opened), 1)
        self.assertEqual(fake.closed, 0)
        p.close()
        self.assertEqual(fake.closed, 1)

    def test_dead_connection_is_replaced(self):
        old, new = FakeSerial(), FakeSerial()
        p = self.make_printer(old)
        self.run_job(p)
        old.dead = True  # z. B. Drucker zwischendurch aus- und wieder eingeschaltet
        p._open = lambda: new
        self.run_job(p)
        self.assertEqual(old.closed, 1)
        self.assertGreater(new.written, 0)

    def test_service_shows_cooling(self):
        svc = server.PrintService(dict(server.DEFAULT_CONFIG, uuid="x"))
        self.addCleanup(svc.stop)
        svc.printer = FakePrinter(heat=True)
        events = []
        svc.listeners.append(lambda e, **d: events.append(e))
        svc.print_image("Test", Image.new("L", (WIDTH, 50), 0))
        for _ in range(100):
            if "job_done" in events:
                break
            time.sleep(0.02)
        self.assertEqual([e for e in events if e in ("hot", "cooled", "job_done")], ["hot", "cooled", "job_done"])
        self.assertFalse(svc.cooling)


class NetshareTest(unittest.TestCase):
    def test_address_rules(self):
        from catprinter import netshare
        for ip in ("192.168.178.20", "10.0.0.5", "172.16.1.1", "fe80::1", "::ffff:192.168.1.2"):
            self.assertTrue(netshare.is_lan(ip), ip)
        for ip in ("8.8.8.8", "127.0.0.1", "::1", "unsinn"):
            self.assertFalse(netshare.is_lan(ip), ip)
        me = socket.gethostname()
        for host in ("192.168.178.147:631", f"{me}:631", f"{me.lower()}.local:631", "[fe80::1]:631"):
            self.assertTrue(netshare.lan_host_ok(host), host)
        for host in ("evil.example:631", "evil.example", "printer.attacker.com:631"):
            self.assertFalse(netshare.lan_host_ok(host), host)


class NetworkAccessTest(unittest.TestCase):
    """Server mit Netzwerkfreigabe, angesprochen über die echte LAN-Adresse dieses PCs."""

    def setUp(self):
        from catprinter import netshare
        addrs = netshare.lan_addresses()
        if not addrs:
            self.skipTest("keine Heimnetz-Adresse")
        self.lan_ip = addrs[0]
        cfg = dict(server.DEFAULT_CONFIG, http_port=0, uuid="x", share_network=True)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.httpd, self.svc = server.serve(cfg, config_file=os.path.join(tmp.name, "config.json"))
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.addCleanup(self.httpd.server_close)
        self.addCleanup(self.httpd.shutdown)

    def request(self, method, path, body=None, host=None, ctype=None):
        conn = http.client.HTTPConnection(self.lan_ip, self.port, timeout=10)
        headers = {"Host": host or f"{self.lan_ip}:{self.port}"}
        if ctype:
            headers["Content-Type"] = ctype
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        data = resp.read()
        conn.close()
        return resp.status, data

    def ipp_attrs(self, host=None):
        msg = ipp.Message((2, 0), ipp.GET_PRINTER_ATTRIBUTES, 1, [(ipp.OPERATION, [
            ("attributes-charset", ipp.CHARSET, ["utf-8"]),
            ("attributes-natural-language", ipp.LANGUAGE, ["en"]),
            ("printer-uri", ipp.URI, [f"ipp://{self.lan_ip}:{self.port}/ipp/print"])])])
        return self.request("POST", "/ipp/print", ipp.encode(msg), host, "application/ipp")

    def test_lan_can_print_but_not_see_status(self):
        status, body = self.ipp_attrs()
        self.assertEqual(status, 200)
        resp, _ = ipp.decode(body)
        self.assertIn(self.lan_ip, resp.get("printer-uri-supported"))
        self.assertEqual(self.request("GET", "/")[0], 403)
        self.assertEqual(self.request("GET", "/status.json")[0], 403)
        self.assertEqual(self.request("GET", "/history.json")[0], 403)
        self.assertEqual(self.request("POST", "/action/test", b"{}", ctype="application/json")[0], 403)

    def test_lan_rebinding_host_rejected(self):
        self.assertEqual(self.ipp_attrs(host=f"evil.example:{self.port}")[0], 403)

    def test_share_off_blocks_lan(self):
        self.svc.cfg["share_network"] = False
        self.assertEqual(self.ipp_attrs()[0], 403)


class HistoryTest(unittest.TestCase):
    def test_limit_and_ids(self):
        from catprinter.history import History
        with tempfile.TemporaryDirectory() as tmp:
            h = History(tmp, limit=3)
            ids = [h.add(f"Auftrag {i}", [Image.new("L", (WIDTH, 50), 200)], 4) for i in range(5)]
            self.assertEqual([e["name"] for e in h.list()], ["Auftrag 4", "Auftrag 3", "Auftrag 2"])
            self.assertEqual(h.pages(ids[-1])[0].size, (WIDTH, 50))
            h.set_state(ids[-1], "done")
            self.assertEqual(h.meta(ids[-1])["state"], "done")
            for bad in ("../x", "..", "1234", ids[-1] + "/../.."):
                with self.assertRaises(KeyError):
                    h.meta(bad)
            h.clear()
            self.assertEqual(h.list(), [])


class FakePrinter:
    def __init__(self, fail=False, heat=False):
        self.printed = []
        self.port = "FAKE"
        self.fail = fail
        self.heat = heat
        self.seen_cooling = False
        self.last_status = {"VOLT": "7100mv"}

    def print_images(self, images, feed_mm=15, density=25, notify=None):
        if self.heat and notify:
            notify("cooling")
            self.seen_cooling = True
            notify("cooled")
        if self.fail:
            from catprinter.printer import PrinterError
            raise PrinterError("COM99 lässt sich nicht öffnen")
        self.printed.append(images)

    def status(self):
        return self.last_status

    def close(self, linger=0):
        pass


class ServiceTest(unittest.TestCase):
    def make_service(self, fail=False):
        svc = server.PrintService(dict(server.DEFAULT_CONFIG, uuid="x"))
        svc.printer = FakePrinter(fail)
        events = []
        svc.listeners.append(lambda event, **data: events.append((event, data)))
        self.addCleanup(svc.stop)
        return svc, events

    def wait_for(self, events, name):
        for _ in range(100):
            if any(e == name for e, _d in events):
                return dict(events)[name]
            time.sleep(0.02)
        self.fail(f"Ereignis {name} kam nicht: {events}")

    def test_print_image_emits_done_with_battery(self):
        from catprinter.pages import short_test_page
        svc, events = self.make_service()
        job = svc.print_image("Testseite", short_test_page("Akku 7,10 V"))
        data = self.wait_for(events, "job_done")
        self.assertIs(data["job"], job)
        self.assertEqual(data["status"], {"VOLT": "7100mv"})
        self.assertEqual(svc.printer.printed[0][0].width, WIDTH)
        self.assertEqual(events[0][0], "job_started")

    def test_failure_emits_job_failed(self):
        svc, events = self.make_service(fail=True)
        job = svc.print_image("Test", Image.new("L", (WIDTH, 50), 0))
        data = self.wait_for(events, "job_failed")
        self.assertIn("COM99", data["error"])
        self.assertEqual(job.state, server.ABORTED)

    def test_refresh_status(self):
        svc, events = self.make_service()
        svc.refresh_status()
        self.assertEqual(self.wait_for(events, "status")["status"], {"VOLT": "7100mv"})

    def test_windows_tone_only_for_network_photos(self):
        from catprinter.printer import _WINDOWS_LUT
        self.assertEqual((_WINDOWS_LUT[0], _WINDOWS_LUT[255]), (66, 255))
        self.assertEqual(_WINDOWS_LUT, sorted(_WINDOWS_LUT))  # monoton, keine Tonwertumkehr
        svc, _events = self.make_service()
        photo = Image.linear_gradient("L").resize((WIDTH, 300))   # viele Grautöne = Foto
        graphic = Image.new("L", (WIDTH, 300), 255)
        graphic.paste(0, (0, 0, WIDTH, 100))                      # Logo mit Schwarzfläche
        self.assertIs(svc._tone(photo, "photo", False), photo)    # vom PC: unverändert
        self.assertEqual(svc._tone(photo, "auto", True).getpixel((0, 0)), 66)  # Handy-Foto: aufgehellt
        self.assertIs(svc._tone(graphic, "auto", True), graphic)  # Handy-Grafik: bleibt schwarz
        svc.cfg["match_windows_tone"] = False
        self.assertIs(svc._tone(photo, "photo", True), photo)
        # Foto-Helligkeit: Mitteltöne heller, Schwarz/Weiß bleiben, Grafik unverändert
        svc.cfg["photo_brightness"] = 20
        bright = svc._tone(photo, "photo", False)
        self.assertGreater(bright.getpixel((0, 150)), photo.getpixel((0, 150)))
        self.assertEqual((bright.getpixel((0, 0)), bright.getpixel((0, 299))), (0, 255))
        self.assertIs(svc._tone(graphic, "auto", False), graphic)
        with self.assertRaises(ValueError):
            server.validate_settings({"photo_brightness": 99})

    def test_battery_percent(self):
        from catprinter.printer import battery_percent
        self.assertEqual(battery_percent(8.42), 100)   # voll geladen gemessen
        self.assertEqual(battery_percent(6.5), 0)
        self.assertIsNone(battery_percent(None))
        values = [battery_percent(v / 100) for v in range(660, 845, 5)]
        self.assertEqual(values, sorted(values))        # steigt mit der Spannung
        self.assertTrue(10 <= battery_percent(7.25) <= 20)

    def test_battery_warnings_once_per_level(self):
        svc, events = self.make_service()
        battery = lambda: [(e, d.get("level")) for e, d in events if e.startswith("battery")]
        for volts in ("8100", "7280", "7260", "7050", "7000"):
            svc._update_battery({"VOLT": volts + "mv"})
        self.assertEqual(battery(), [("battery", "low"), ("battery", "critical")])
        self.assertEqual(svc.battery["level"], "critical")
        svc._update_battery({"VOLT": "8420mv"})           # geladen
        self.assertEqual(battery()[-1], ("battery_full", None))
        svc._update_battery({"VOLT": "7200mv"})           # entlädt sich wieder (10 %): erneut warnen
        self.assertEqual(battery()[-1], ("battery", "low"))

    def test_quiet_check_stays_silent_when_printer_off(self):
        svc, events = self.make_service()
        def offline():
            from catprinter.printer import PrinterError
            raise PrinterError("COM13 lässt sich nicht öffnen")
        svc.printer.status = offline
        svc.refresh_status(quiet=True)
        time.sleep(0.2)
        self.assertIsNone(svc.last_error)
        self.assertNotIn("status_failed", [e for e, _d in events])
        svc.refresh_status()                              # manuell: Fehler anzeigen
        self.wait_for(events, "status_failed")
        self.assertIsNotNone(svc.last_error)

    def test_battery_volts(self):
        from catprinter.printer import battery_volts
        self.assertEqual(battery_volts({"VOLT": "7180mv"}), 7.18)
        self.assertIsNone(battery_volts({}))

    def test_tray_icon_image(self):
        from catprinter.tray import make_icon
        for state in ("ready", "printing", "error"):
            self.assertEqual(make_icon(state).size, (64, 64))


class ServerTest(unittest.TestCase):
    def setUp(self):
        cfg = dict(server.DEFAULT_CONFIG, http_port=0, uuid="00000000-0000-0000-0000-000000000001")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.config_file = os.path.join(tmp.name, "config.json")  # nie die echte config.json anfassen
        self.httpd, self.svc = server.serve(cfg, config_file=self.config_file)
        self.svc.printer = FakePrinter()
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()

    def call(self, op, attrs, job_attrs=None, doc=b"", chunked=False):
        groups = [(ipp.OPERATION, [("attributes-charset", ipp.CHARSET, ["utf-8"]),
                                   ("attributes-natural-language", ipp.LANGUAGE, ["en"]),
                                   ("printer-uri", ipp.URI, [f"ipp://127.0.0.1:{self.port}/ipp/print"])] + attrs)]
        if job_attrs:
            groups.append((ipp.JOB, job_attrs))
        body = ipp.encode(ipp.Message((2, 0), op, 7, groups)) + doc
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        if chunked:
            conn.putrequest("POST", "/ipp/print")
            conn.putheader("Content-Type", "application/ipp")
            conn.putheader("Transfer-Encoding", "chunked")
            conn.endheaders()
            for i in range(0, len(body), 1000):
                part = body[i:i + 1000]
                conn.send(b"%x\r\n" % len(part) + part + b"\r\n")
            conn.send(b"0\r\n\r\n")
        else:
            conn.request("POST", "/ipp/print", body, {"Content-Type": "application/ipp"})
        resp = conn.getresponse()
        self.assertEqual(resp.status, 200)
        msg, _ = ipp.decode(resp.read())
        conn.close()
        return msg

    def test_printer_attributes(self):
        resp = self.call(ipp.GET_PRINTER_ATTRIBUTES, [("requested-attributes", ipp.KEYWORD, ["all"])])
        self.assertEqual(resp.code, ipp.OK)
        self.assertEqual(resp.request_id, 7)
        self.assertIn("image/pwg-raster", resp.get_all("document-format-supported"))
        self.assertEqual(len(resp.get_all("media-col-database")), len(server.MEDIA))

    def test_create_job_send_document_chunked(self):
        resp = self.call(ipp.CREATE_JOB, [("job-name", ipp.NAME, ["Test"])])
        job_id = resp.get("job-id")
        self.assertIsNotNone(job_id)
        doc = pwg.encode(noisy_image(384, 200))
        resp = self.call(ipp.SEND_DOCUMENT, [("job-id", ipp.INTEGER, [job_id]),
                                             ("document-format", ipp.MIME, ["image/pwg-raster"]),
                                             ("last-document", ipp.BOOLEAN, [True])], doc=doc, chunked=True)
        self.assertEqual(resp.code, ipp.OK)
        for _ in range(50):
            state = self.call(ipp.GET_JOB_ATTRIBUTES, [("job-id", ipp.INTEGER, [job_id])]).get("job-state")
            if state == server.COMPLETED:
                break
            time.sleep(0.05)
        self.assertEqual(state, server.COMPLETED)
        self.assertEqual(self.svc.printer.printed[0][0].width, WIDTH)

    def http(self, method, path, headers=None, body=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        body = resp.read()
        conn.close()
        return resp.status, body

    def test_status_page_and_json(self):
        status, body = self.http("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn(b"status.json", body)
        status, body = self.http("GET", "/status.json")
        data = json.loads(body)
        self.assertEqual((data["state"], data["printed"], data["jobs"]), ("ready", 0, []))

    def test_actions_need_header(self):
        self.assertEqual(self.http("POST", "/action/test")[0], 403)  # z. B. von fremder Webseite
        self.assertEqual(self.http("POST", "/action/test", {"X-CatPrinter": "1"})[0], 202)
        for _ in range(100):
            if self.svc.printer.printed:
                break
            time.sleep(0.02)
        self.assertEqual(len(self.svc.printer.printed), 1)
        data = json.loads(self.http("GET", "/status.json")[1])
        self.assertEqual((data["printed"], data["jobs"][0]["state"]), (1, "done"))

    def post_json(self, action, data, header=True):
        headers = {"Content-Type": "application/json"}
        if header:
            headers["X-CatPrinter"] = "1"
        status, body = self.http("POST", "/action/" + action, headers, json.dumps(data))
        return status, json.loads(body) if body.startswith(b"{") else body

    def test_settings_saved_and_applied(self):
        status, body = self.post_json("settings", {"density": 30, "image_mode": "text",
                                                   "rotate_180": False, "com_port": "com7"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["applied"]["com_port"], "COM7")
        self.assertEqual((self.svc.cfg["density"], self.svc.printer.port), (30, "COM7"))
        with open(self.config_file, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["image_mode"], "text")
        data = json.loads(self.http("GET", "/status.json")[1])
        self.assertEqual(data["settings"]["density"], 30)
        # Leerer Port = wieder automatisch suchen
        self.post_json("settings", {"com_port": ""})
        self.assertIsNone(self.svc.printer.port)

    def test_settings_rejected(self):
        for bad in ({"density": 500}, {"density": "40"}, {"image_mode": "x"}, {"http_port": 80},
                    {"com_port": "LPT1"}, {"rotate_180": "ja"}):
            status, body = self.post_json("settings", bad)
            self.assertEqual(status, 400, bad)
            self.assertIn("error", body)
        self.assertEqual(self.svc.cfg["density"], server.DEFAULT_CONFIG["density"])
        self.assertFalse(os.path.exists(self.config_file))
        self.assertEqual(self.post_json("settings", {"density": 30}, header=False)[0], 403)

    def test_calibrate_uses_own_density(self):
        printed = []
        self.svc.printer.print_images = lambda images, feed, density, **_kw: printed.append(density)
        self.assertEqual(self.post_json("calibrate", {"density": 55})[0], 202)
        for _ in range(100):
            if printed:
                break
            time.sleep(0.02)
        self.assertEqual(printed, [55])
        self.assertEqual(self.svc.cfg["density"], server.DEFAULT_CONFIG["density"])

    def wait_until(self, cond):
        for _ in range(150):
            if cond():
                return
            time.sleep(0.02)
        self.fail("Bedingung nicht erreicht")

    def ipp_print(self, name="Einkaufsliste"):
        doc = pwg.encode(noisy_image(384, 120))
        resp = self.call(ipp.PRINT_JOB, [("job-name", ipp.NAME, [name]),
                                         ("document-format", ipp.MIME, ["image/pwg-raster"])], doc=doc)
        self.assertEqual(resp.code, ipp.OK)

    def test_history_off_by_default(self):
        self.ipp_print()
        self.wait_until(lambda: self.svc.printer.printed)
        data = json.loads(self.http("GET", "/history.json")[1])
        self.assertEqual(data, {"enabled": False, "entries": []})
        self.assertFalse(os.path.exists(self.svc.history.directory))

    def test_history_view_reprint_and_disable(self):
        self.post_json("settings", {"keep_history": True})
        self.ipp_print("Einkaufsliste")
        self.wait_until(lambda: self.svc.printer.printed)
        entries = json.loads(self.http("GET", "/history.json")[1])["entries"]
        self.assertEqual([(e["name"], e["pages"]) for e in entries], [("Einkaufsliste", 1)])
        hid = entries[0]["id"]
        self.wait_until(lambda: self.svc.history.meta(hid)["state"] == "done")

        status, png = self.http("GET", f"/history/{hid}/1.png")
        self.assertEqual(status, 200)
        self.assertEqual(Image.open(io.BytesIO(png)).width, WIDTH)
        self.assertEqual(self.http("GET", f"/history/{hid}/9.png")[0], 404)
        self.assertEqual(self.http("GET", "/history/..%2F..%2Fconfig.json/1.png")[0], 404)

        self.assertEqual(self.post_json("reprint", {"id": hid})[0], 202)
        self.wait_until(lambda: len(self.svc.printer.printed) == 2)
        # Nachdrucke landen nicht nochmal im Verlauf
        self.assertEqual(len(self.svc.history.list()), 1)
        self.assertEqual(self.post_json("reprint", {"id": "1234"})[0], 404)

        self.post_json("settings", {"keep_history": False})
        self.assertFalse(os.path.exists(self.svc.history.directory))  # ausschalten löscht alles

    def test_quit_action_emits_event(self):
        events = []
        self.svc.listeners.append(lambda event, **_d: events.append(event))
        self.assertEqual(self.post_json("quit", {})[0], 202)
        self.wait_until(lambda: "quit" in events)

    def test_foreign_host_rejected(self):
        # DNS-Rebinding: fremde Domain, die auf 127.0.0.1 zeigt
        headers = {"Host": f"evil.example:{self.port}"}
        self.assertEqual(self.http("GET", "/status.json", headers)[0], 403)
        self.assertEqual(self.http("GET", "/history.json", headers)[0], 403)
        headers["X-CatPrinter"] = "1"
        self.assertEqual(self.http("POST", "/action/test", headers)[0], 403)
        self.assertEqual(self.http("GET", "/status.json", {"Host": f"localhost:{self.port}"})[0], 200)

    def test_unknown_operation(self):
        self.assertEqual(self.call(0x0033, []).code, ipp.OPERATION_NOT_SUPPORTED)


if __name__ == "__main__":
    unittest.main()
