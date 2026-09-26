"""Tests ohne Drucker: python -m unittest discover tests"""
import http.client
import io
import json
import os
import random
import tempfile
import threading
import time
import unittest

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
        # Init, Dichte, dann genau ein GS-v-0-Block inkl. Vorschub
        self.assertTrue(job.startswith(b"\x1b\x40\x1d\x49\xf0\x19\x1d\x76\x30\x00\x30\x00"))
        rows = int.from_bytes(job[12:14], "little")
        self.assertEqual(rows, bw.height + round(15 * 203 / 25.4))
        self.assertEqual(len(job), 14 + rows * 48)

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
    def __init__(self, fail=False):
        self.printed = []
        self.port = "FAKE"
        self.fail = fail
        self.last_status = {"VOLT": "7100mv"}

    def print_images(self, images, feed_mm=15, density=25):
        if self.fail:
            from catprinter.printer import PrinterError
            raise PrinterError("COM99 lässt sich nicht öffnen")
        self.printed.append(images)

    def status(self):
        return self.last_status


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
        self.svc.printer.print_images = lambda images, feed, density: printed.append(density)
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
