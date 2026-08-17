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
            # Цэвэрлэгээний шийдвэр нь заавал биш: дуудагч өгөөгүй бол
            # ерөнхий тохиргоог хэрэглэнэ.
            pcm, lang, *rest = item
            self._handle(pcm, lang, rest[0] if rest else None)

    def _retry_other_language(
        self, pcm: bytes, lang: str, alternatives: list[str], confidence: float
    ) -> tuple[list[str], float, str]:
        """Буруу хэлээр сонссон бололтой бол хоёрдогч хэлээр нэг л удаа дахин асууна.

        Гурван нөхцөл ЗЭРЭГ таарвал л дахин хүсэлт явна:

        * танилт амжилттай боловч итгэлцэл нь хэрэглэгчийн босгоос доогуур,
        * буцаасан текст нь үсгээрээ гадаад (кирилл биш),
        * хоёрдогч хэл нь одоогийнхоос өөр.

        Итгэлцэл өндөр байхад хөндөхгүй, кирилл гарсан бол хөндөхгүй — өөрөөр
        хэлбэл ТОДОРХОЙГҮЙ тохиолдолд л хоёр дахь хүсэлт явна. Тиймээс дундаж
        зардал бараг нэмэгдэхгүй. Дахилт бүтэлгүйтвэл анхны үр дүн хэвээр
        үлдэнэ — нэмэлт онцлогоос болж танилт бүхэлдээ уначихгүй.
        """
        if not alternatives or not self.cfg["detect_language"]:
            return alternatives, confidence, lang
        if confidence >= float(self.cfg["min_confidence"]):
            return alternatives, confidence, lang
        if not textproc.looks_foreign(alternatives[0]):
            return alternatives, confidence, lang
        other = str(self.cfg["lang_alt"] or "")
        if not other or other == lang:
            return alternatives, confidence, lang

        log.info("итгэлцэл бага, кирилл биш — %s хэлээр дахин оролдож байна", other)
        try:
            retry_alternatives, retry_confidence = self.recognizer.recognize(
                pcm, RATE, other
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("хэл сэжиглэх дахилт бүтсэнгүй: %s", exc)
            return alternatives, confidence, lang

        if retry_alternatives and retry_confidence > confidence:
            log.info("%s хэлний үр дүн илүү итгэлтэй байлаа", other)
            return retry_alternatives, retry_confidence, other
        return alternatives, confidence, lang

    def _handle(self, pcm: bytes, lang: str, clean: bool | None = None) -> None:
        if clean is None:
            clean = bool(self.cfg["clean_speech"])
        started = time.monotonic()
        spoken_seconds = len(pcm) / (RATE * BYTES_PER_SAMPLE)
        try:
            cleaned = prepare_segment(pcm, RATE)
            alternatives, confidence = self.recognizer.recognize(cleaned, RATE, lang)
            alternatives, confidence, lang = self._retry_other_language(
                cleaned, lang, alternatives, confidence
            )
        except Exception as exc:  # noqa: BLE001
            # Хүлээлтийн тоог эхлээд бууруулна — эс бөгөөс төлөв шинэчлэгдэж,
            # алдааны мессежийг тэр дороо дарж орхино.
            self.events.put(("pending", -1))
            message = str(exc) if isinstance(exc, RecognitionError) else f"Таних алдаа: {exc}"
            log.error("таних алдаа: %s", exc)
            self.events.put(("error", message))
            return

        # Үйлчилгээ хэд хэдэн хувилбар буцаадаг; хэрэглэгчийн үгсийн санд
        # нийцэхийг нь сонгоно (хариунд аль хэдийн ирсэн тул саатал нэмэгдэхгүй).
        raw = self.formatter.choose(alternatives)

        elapsed_ms = (time.monotonic() - started) * 1000
        log.info(
            "таньсан: %.1f сек дуу → %d тэмдэгт, %d хувилбар, итгэлцэл %.2f, %.0f мс",
            spoken_seconds, len(raw), len(alternatives), confidence, elapsed_ms,
        )
        if raw and raw != alternatives[0]:
            # Текстийг лог руу бичихгүй — зөвхөн хэд дэх хувилбарыг сонгосныг.
            log.info("толиор %d дэх хувилбарыг сонголоо", alternatives.index(raw) + 1)
        self.events.put(("pending", -1))

        if not raw:
            self.events.put(("empty", "unrecognized"))
            return
        # Итгэлцлийн шүүлт цэвэрлэгээнээс ӨМНӨ: итгэлцэл багатай чимээ
        # цэвэрлэгээгээр хоосорвол хэрэглэгчид «зөвхөн чигчлүүр сонсогдлоо»
        # гэж буруу шалтгаан харагдана.
        if confidence < float(self.cfg["min_confidence"]):
            log.info("итгэлцэл бага тул алгаслаа (%.2f)", confidence)
            self.events.put(("empty", "low_confidence"))
            return
        if clean:
            # Дуут командыг («буцаа») цэвэрлэгээ хөндөхгүй: тэдгээр нь
            # чигчлүүрийн жагсаалтад байхгүй тул бүтнээрээ үлдэнэ.
            cleaned_raw = textproc.clean_speech(raw)
            if not cleaned_raw:
                self.events.put(("empty", "filler"))
                return
            raw = cleaned_raw
        if self.cfg["voice_numbers"]:
            # Цэвэрлэгээний ДАРАА: чигчлүүр хасагдсанаар тооны үгс зэрэгцэж,
            # «хорин ааа гурван» гэх мэт нь ч нэг тоо болж уншигдана.
            raw = textproc.spell_numbers(raw)

        if textproc.match_action(raw) == "undo":
            self.events.put(("undo", None))
            return

        text, backspaces = self.formatter.format(raw)
        if not text and not backspaces:
            return
        shown = text.strip() or raw
        self.stats.record(shown, spoken_seconds, elapsed_ms)
        # Батлагдсан текст — дараагийн хувилбар сонголтод жин болно.
        self.formatter.remember(shown)
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
