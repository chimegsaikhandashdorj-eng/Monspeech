"""Дуу → текст → курсор гэсэн дамжлагын ажлын thread.

Микрофоны thread нь сегмент илгээж, энэ thread тэдгээрийг ирсэн дарааллаар нь
таниж, цэгцэлж, идэвхтэй цонхонд буулгана. Цонхтой холбоотой бүх зүйл (төлөв,
мэдэгдэл) `events` дараалалаар л явна — Tk-г өөр thread-ээс хөндөх аюулгүй арга.
"""

from __future__ import annotations

import queue
import threading
import time

from . import injector, textproc
from .audio import BYTES_PER_SAMPLE, RATE, prepare_segment
from .logging_setup import get as get_logger
from .recognizer import RecognitionError

log = get_logger("pipeline")


class RecognitionWorker:
    """Сегментүүдийг текст болгож буулгана. `stop()` хүртэл ажиллана."""

    def __init__(
        self,
        *,
        segments: queue.Queue,
        events: queue.Queue,
        cfg,
        recognizer,
        formatter,
        stats,
        transcripts,
        insertions,
        target,
        insert_mode,
    ) -> None:
        self.segments = segments
        self.events = events
        self.cfg = cfg
        self.recognizer = recognizer
        self.formatter = formatter
        self.stats = stats
        self.transcripts = transcripts
        self.insertions = insertions
        self.target = target
        self.insert_mode = insert_mode
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self._thread:
            return
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.segments.put(None)
        self._thread = None

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            item = self.segments.get()
            if item is None:
                return
            pcm, lang = item
            self._handle(pcm, lang)

    def _handle(self, pcm: bytes, lang: str) -> None:
        started = time.monotonic()
        spoken_seconds = len(pcm) / (RATE * BYTES_PER_SAMPLE)
        try:
            cleaned = prepare_segment(pcm, RATE)
            raw, confidence = self.recognizer.recognize(cleaned, RATE, lang)
        except Exception as exc:  # noqa: BLE001
            # Хүлээлтийн тоог эхлээд бууруулна — эс бөгөөс төлөв шинэчлэгдэж,
            # алдааны мессежийг тэр дороо дарж орхино.
            self.events.put(("pending", -1))
            message = str(exc) if isinstance(exc, RecognitionError) else f"Таних алдаа: {exc}"
            log.error("таних алдаа: %s", exc)
            self.events.put(("error", message))
            return

        elapsed_ms = (time.monotonic() - started) * 1000
        log.info(
            "таньсан: %.1f сек дуу → %d тэмдэгт, итгэлцэл %.2f, %.0f мс",
            spoken_seconds, len(raw), confidence, elapsed_ms,
        )
        self.events.put(("pending", -1))

        if not raw:
            self.events.put(("empty", "unrecognized"))
            return
        if confidence < float(self.cfg["min_confidence"]):
            log.info("итгэлцэл бага тул алгаслаа (%.2f)", confidence)
            self.events.put(("empty", "low_confidence"))
            return

        if textproc.match_action(raw) == "undo":
            self.events.put(("undo", None))
            return

        text, backspaces = self.formatter.format(raw)
        if not text and not backspaces:
            return
        shown = text.strip() or raw
        self.stats.record(shown, spoken_seconds, elapsed_ms)
        entry = self.transcripts.add(shown, lang, spoken_seconds)
        self.events.put(("recognized", (shown, entry)))
        self.deliver(text, backspaces)

    def deliver(self, text: str, backspaces: int, remember: bool = True) -> None:
        """Текстийг зорилтот цонхонд оруулна (энэ thread дээр л дуудна)."""
        try:
            self.target.ensure()
            injector.insert_text(
                text,
                bool(self.cfg["restore_clipboard"]),
                backspaces,
                self.insert_mode(),
            )
            if remember and text:
                self.insertions.record(text)
        except Exception as exc:  # noqa: BLE001
            log.error("текст оруулж чадсангүй: %s", exc)
