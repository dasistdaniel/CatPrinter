"""Optionaler Verlauf gedruckter Aufträge (nur wenn in den Einstellungen eingeschaltet).

Pro Auftrag ein Ordner mit meta.json und den Seiten als Graustufen-PNG in
Druckbreite (384 Punkte) – genug, um erneut zu drucken, aber ohne das
Originaldokument aufzubewahren.
"""
import json
import os
import re
import shutil
import threading
import time
import uuid

from PIL import Image

HISTORY_LIMIT = 30
_ID = re.compile(r"^[0-9]{13}-[0-9a-f]{6}$")


class History:
    def __init__(self, directory, limit=HISTORY_LIMIT):
        self.directory = directory
        self.limit = limit
        self.lock = threading.Lock()

    def _path(self, hid, *parts):
        if not _ID.match(str(hid)):
            raise KeyError(hid)  # schützt auch vor Pfadangaben wie ../
        return os.path.join(self.directory, hid, *parts)

    def add(self, name, pages, quality=None):
        """Speichert die Seiten (PIL-Bilder in Druckbreite). Gibt die Verlaufs-ID zurück."""
        hid = f"{int(time.time() * 1000):013d}-{uuid.uuid4().hex[:6]}"
        with self.lock:
            tmp = os.path.join(self.directory, hid + ".tmp")
            os.makedirs(tmp, exist_ok=True)
            for i, page in enumerate(pages, 1):
                page.convert("L").save(os.path.join(tmp, f"page-{i}.png"), optimize=True)
            meta = {"id": hid, "name": name, "created": int(time.time()), "pages": len(pages),
                    "quality": quality, "state": "pending"}
            with open(os.path.join(tmp, "meta.json"), "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.replace(tmp, os.path.join(self.directory, hid))
            self._prune()
        return hid

    def set_state(self, hid, state):
        with self.lock:
            path = self._path(hid, "meta.json")
            try:
                with open(path, encoding="utf-8") as f:
                    meta = json.load(f)
            except FileNotFoundError:
                return  # inzwischen gelöscht
            meta["state"] = state
            with open(path + ".tmp", "w", encoding="utf-8") as f:
                json.dump(meta, f)
            os.replace(path + ".tmp", path)

    def list(self):
        entries = []
        if not os.path.isdir(self.directory):
            return entries
        for hid in sorted(os.listdir(self.directory), reverse=True):
            if not _ID.match(hid):
                continue
            try:
                with open(self._path(hid, "meta.json"), encoding="utf-8") as f:
                    entries.append(json.load(f))
            except (OSError, ValueError):
                continue
        return entries

    def meta(self, hid):
        with open(self._path(hid, "meta.json"), encoding="utf-8") as f:
            return json.load(f)

    def page(self, hid, number):
        path = self._path(hid, f"page-{int(number)}.png")
        with Image.open(path) as img:
            return img.copy()

    def pages(self, hid):
        return [self.page(hid, n) for n in range(1, self.meta(hid)["pages"] + 1)]

    def delete(self, hid):
        with self.lock:
            shutil.rmtree(self._path(hid), ignore_errors=True)

    def clear(self):
        with self.lock:
            shutil.rmtree(self.directory, ignore_errors=True)

    def _prune(self):
        ids = sorted(h for h in os.listdir(self.directory) if _ID.match(h))
        for hid in ids[:-self.limit] if len(ids) > self.limit else []:
            shutil.rmtree(os.path.join(self.directory, hid), ignore_errors=True)
