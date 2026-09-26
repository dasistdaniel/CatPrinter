"""Tests ohne Drucker: python -m unittest discover tests"""
import http.client
import random
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


class FakePrinter:
    def __init__(self):
        self.printed = []
        self.port = "FAKE"

    def print_images(self, images, feed_mm=15, density=25):
        self.printed.append(images)


class ServerTest(unittest.TestCase):
    def setUp(self):
        cfg = dict(server.DEFAULT_CONFIG, http_port=0, uuid="00000000-0000-0000-0000-000000000001")
        self.httpd, self.svc = server.serve(cfg)
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

    def test_unknown_operation(self):
        self.assertEqual(self.call(0x0033, []).code, ipp.OPERATION_NOT_SUPPORTED)


if __name__ == "__main__":
    unittest.main()
