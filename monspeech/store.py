"""Түүх ба хэрэглээний тоо баримтыг диск дээр хадгалах.

Түүх нь аппыг хаагаад нээхэд алга болдог байсан. Одоо мөр бүрийг JSONL
файлд нэмж бичнэ — хайх, статистик гаргах боломжтой.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import date, datetime

from .config import CONFIG_DIR
from .logging_setup import get as get_logger

log = get_logger("store")

HISTORY_PATH = CONFIG_DIR / "history.jsonl"
STATS_PATH = CONFIG_DIR / "stats.json"
MAX_ENTRIES = 2000


class TranscriptStore:
    """Шивсэн текстүүдийг санаж, хайх боломж өгнө."""

    def __init__(self, path=None, limit: int = MAX_ENTRIES) -> None:
        self.path = path or HISTORY_PATH
        self.limit = limit
        self._lock = threading.Lock()
        self.entries: list[dict] = []
        self.load()

    def load(self) -> None:
        entries: list[dict] = []
        try:
            with open(self.path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict) and item.get("text"):
                        entries.append(item)
        except OSError:
            pass
        self.entries = entries[-self.limit :]

    def add(self, text: str, lang: str = "", seconds: float = 0.0) -> dict:
        entry = {
            "text": text.strip(),
            "lang": lang,
            "at": datetime.now().isoformat(timespec="seconds"),
            "sec": round(seconds, 2),
        }
        if not entry["text"]:
            return entry
        with self._lock:
            self.entries.append(entry)
            if len(self.entries) > self.limit:
                self.entries = self.entries[-self.limit :]
                self._rewrite()
            else:
                self._append(entry)
        return entry

    def _append(self, entry: dict) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("түүх хадгалагдсангүй: %s", exc)

    def _rewrite(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "w", encoding="utf-8") as handle:
                for item in self.entries:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("түүх дахин бичигдсэнгүй: %s", exc)

    def search(self, query: str, limit: int = 200) -> list[dict]:
        """Хайлт — үгийн хэсэг таарвал болно.

        Ажлын thread шинэ мөр нэмж байх зуур цонх хайлт хийж болох тул
        жагсаалтыг түгжээ дор уншина.
        """
        query = query.strip().lower()
        with self._lock:
            if not query:
                return list(reversed(self.entries[-limit:]))
            found = [e for e in self.entries if query in e["text"].lower()]
        return list(reversed(found[-limit:]))

    def replace(self, entry: dict, text: str) -> None:
        """Түүхийн мөрийг засна (алдаатай таньсныг залруулахад)."""
        with self._lock:
            for item in self.entries:
                if item is entry:
                    item["text"] = text.strip()
                    break
            self._rewrite()

    def clear(self) -> None:
        with self._lock:
            self.entries = []
            self._rewrite()


class UsageStats:
    """Хичнээн үг шивсэн, хэр хурдан болохыг тоолно."""

    def __init__(self, path=None) -> None:
        self.path = path or STATS_PATH
        self._lock = threading.Lock()
        self.data = {
            "words": 0,
            "utterances": 0,
            "seconds_spoken": 0.0,
            "recognise_ms": 0.0,
            "days": {},  # "2026-08-08": үгийн тоо
            "since": date.today().isoformat(),
        }
        self.load()
        self._dirty = False
        self._last_save = time.monotonic()

    def load(self) -> None:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in self.data and isinstance(value, type(self.data[key])):
                    self.data[key] = value

    def record(self, text: str, seconds: float, recognise_ms: float) -> None:
        words = len([w for w in text.split() if w.strip()])
        if not words:
            return
        today = date.today().isoformat()
        with self._lock:
            self.data["words"] += words
            self.data["utterances"] += 1
            self.data["seconds_spoken"] += seconds
            self.data["recognise_ms"] += recognise_ms
            self.data["days"][today] = self.data["days"].get(today, 0) + words
            # Зөвхөн сүүлийн 90 өдрийг хадгална
            if len(self.data["days"]) > 90:
                for key in sorted(self.data["days"])[:-90]:
                    self.data["days"].pop(key, None)
            self._dirty = True

    def save(self, force: bool = False) -> None:
        """Хэт олон бичихээс сэргийлж 30 секунд тутам хадгална."""
        if not self._dirty:
            return
        if not force and time.monotonic() - self._last_save < 30:
            return
        with self._lock:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(
                    json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                self._dirty = False
                self._last_save = time.monotonic()
            except OSError as exc:
                log.warning("статистик хадгалагдсангүй: %s", exc)

    # ------------------------------------------------------------------
    @property
    def today_words(self) -> int:
        return self.data["days"].get(date.today().isoformat(), 0)

    @property
    def average_ms(self) -> float:
        count = self.data["utterances"]
        return self.data["recognise_ms"] / count if count else 0.0

    def summary(self) -> str:
        """Цонхонд харуулах нэг мөр."""
        total = self.data["words"]
        if not total:
            return "Хараахан шивээгүй байна"
        parts = [f"Өнөөдөр {self.today_words:,} үг", f"нийт {total:,} үг"]
        if self.data["utterances"]:
            parts.append(f"дунджаар {self.average_ms:,.0f} мс")
        # Гараар бичихээс хэдэн минут хожсоныг барагцаална (40 үг/мин)
        saved = total / 40 - self.data["seconds_spoken"] / 60
        if saved > 1:
            parts.append(f"~{saved:,.0f} минут хэмнэсэн")
        return " · ".join(parts).replace(",", " ")
