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
from .language_router import LanguageRouter
from .logging_setup import get as get_logger
from .recognizer import RecognitionError

log = get_logger("pipeline")

#: Товчоор ээлжлүүлж болох хувилбарын дээд тоо. Танигч 5-аас олныг ховор
#: буцаадаг ба олон болох тусам зөв нь холдоно.
MAX_VARIANTS = 5


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
        provider_factory=None,
        samples=None,
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
        # Хэцүү тохиолдлын дууг хураагч (`samples.HardSampleStore`). `None`
        # бол огт цуглуулахгүй — тест, файл хөрвүүлэлт зэрэгт хэрэггүй.
        self.samples = samples
        self.router = LanguageRouter(
            recognizer,
            factory=provider_factory,
            chooser=formatter.choose,
            # Тооллыг router хийнэ: нэг таналт нэг хүсэлт биш (хоёр хэл зэрэг,
            # эсвэл зөрүүтэй үеийн дахилт) тул эндээс тоолвол дутуу гарна.
            on_request=stats.record_usage,
        )
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

    def set_recognizer(self, provider, provider_factory=None) -> None:
        """Танигч солигдоход auto хэлний нэмэлт provider-уудыг шинэчилнэ."""

        self.recognizer = provider
        self.router.replace_provider(provider, provider_factory)

    def prewarm_languages(self, hint: str, automatic: bool) -> None:
        self.router.prewarm(
            hint,
            list(self.cfg.get("auto_languages") or []),
            automatic=automatic,
            accuracy=bool(self.cfg.get("language_accuracy_mode", False)),
        )

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while True:
            item = self.segments.get()
            if item is None:
                self.router.close_extras()
                return
            # Цэвэрлэгээний шийдвэр нь заавал биш: дуудагч өгөөгүй бол
            # ерөнхий тохиргоог хэрэглэнэ.
            pcm, lang, *rest = item
            self._handle(
                pcm,
                lang,
                rest[0] if len(rest) > 0 else None,
                rest[1] if len(rest) > 1 else None,
                rest[2] if len(rest) > 2 else None,
                rest[3] if len(rest) > 3 else None,
            )

    def _prepare_alternative(self, alternative: str, clean: bool) -> str:
        """Хувилбарыг эхнийхтэй ЯГ ижил дүрмээр цэгцэлнэ (харьцуулах боломжтой)."""
        text = alternative
        if clean:
            text = textproc.clean_speech(text)
            if not text:
                return ""
        if self.cfg["voice_numbers"]:
            text = textproc.spell_numbers(text)
        return text

    def _variants(
        self, alternatives: list[str], clean: bool, end_sentence: bool
    ) -> list[str]:
        """Танигчийн бүх хувилбарыг оруулахад бэлэн текст болгоно.

        Эхний утга нь ҮРГЭЛЖ жинхэнэ оруулах текст — хэрэглэгч товчоор
        ээлжлүүлэхэд эндээс л эхэлнэ. Хоосон ба давхардсаныг хаяна.
        `preview` нь төлөв хөндөхгүй тул жинхэнэ `format`-ын өмнө дуудна.
        """
        variants: list[str] = []
        for alternative in alternatives[:MAX_VARIANTS]:
            prepared = self._prepare_alternative(alternative, clean)
            if not prepared:
                continue
            text, _ = self.formatter.preview(prepared, end_sentence=end_sentence)
            if text and text not in variants:
                variants.append(text)
        return variants

    def _handle(
        self,
        pcm: bytes,
        lang: str,
        clean: bool | None = None,
        automatic: bool | None = None,
        verbatim: bool | None = None,
        command: bool | None = None,
    ) -> None:
        if clean is None:
            clean = bool(self.cfg["clean_speech"])
        if automatic is None:
            automatic = bool(self.cfg.get("detect_language", False))
        if verbatim is None:
            verbatim = bool(self.cfg.get("verbatim_mode", False))
        if verbatim:
            clean = False
        command = bool(command)
        if command:
            # Команд горимд юу ч бичихгүй тул цэгцлэх, хэл сэжиглэх хэрэггүй
            clean = False
            verbatim = False
        started = time.monotonic()
        spoken_seconds = len(pcm) / (RATE * BYTES_PER_SAMPLE)
        try:
            cleaned = prepare_segment(
                pcm, RATE, denoise=bool(self.cfg.get("noise_suppression"))
            )
            result = self.router.recognize(
                cleaned,
                RATE,
                hint=lang,
                configured=list(
                    self.cfg.get("auto_languages")
                    or [self.cfg.get("lang", "mn-MN"), self.cfg.get("lang_alt", "en-US")]
                ),
                automatic=automatic,
                accuracy=bool(self.cfg.get("language_accuracy_mode", False)),
                minimum_confidence=float(self.cfg["min_confidence"]),
                margin=float(self.cfg.get("language_margin", 0.08)),
                choose_alternatives=not verbatim,
            )
        except Exception as exc:  # noqa: BLE001
            # Хүлээлтийн тоог эхлээд бууруулна — эс бөгөөс төлөв шинэчлэгдэж,
            # алдааны мессежийг тэр дороо дарж орхино.
            self.events.put(("pending", -1))
            message = str(exc) if isinstance(exc, RecognitionError) else f"Таних алдаа: {exc}"
            log.error("таних алдаа: %s", exc)
            self.events.put(("error", message))
            return

        alternatives = result.alternatives
        confidence = result.confidence
        detected_lang = result.language or lang
        # Router цэгцэлсэн горимд толийн хувилбарыг аль хэдийн эхэнд тавьсан.
        # Үгчлэн горимд provider-ийн ЯГ эхний хувилбар хэвээр.
        raw = alternatives[0] if alternatives else ""
        source_raw = result.raw_text or raw

        elapsed_ms = (time.monotonic() - started) * 1000
        log.info(
            "таньсан: %.1f сек дуу → %d тэмдэгт, %d хувилбар, хэл %s, итгэлцэл %s, %.0f мс",
            spoken_seconds,
            len(raw),
            len(alternatives),
            detected_lang,
            "—" if confidence is None else f"{confidence:.2f}",
            elapsed_ms,
        )
        self.events.put(("pending", -1))

        if not raw:
            self._keep_hard(cleaned, "unrecognized", language=detected_lang)
            self.events.put(("empty", "unrecognized"))
            return
        # Итгэлцлийн шүүлт цэвэрлэгээнээс ӨМНӨ: итгэлцэл багатай чимээ
        # цэвэрлэгээгээр хоосорвол хэрэглэгчид «зөвхөн чигчлүүр сонсогдлоо»
        # гэж буруу шалтгаан харагдана.
        if confidence is not None and confidence < float(self.cfg["min_confidence"]):
            log.info("итгэлцэл бага тул алгаслаа (%.2f)", confidence)
            self._keep_hard(
                cleaned,
                "low_confidence",
                heard=raw,
                language=detected_lang,
                confidence=confidence,
                provider=result.provider,
            )
            self.events.put(("empty", "low_confidence"))
            return
        if command:
            # Тусгай товчлуураар хэлсэн зүйл — ЗӨВХӨН үйлдэл. Танихгүй бол
            # чимээгүй өнгөрөхгүй: юу сонссоноо хэлж, хэрэглэгч дахин
            # оролдох эсвэл толиндоо нэмэх боломжтой болно.
            action = textproc.match_action(raw, self.cfg.get("actions"), command=True)
            if action:
                name, argument = action
                log.info("команд: %s", name)
                self.events.put((name, argument))
            else:
                self.events.put(("command_missed", raw))
            return

        if clean:
            # Дуут командыг («буцаа») цэвэрлэгээ хөндөхгүй: тэдгээр нь
            # чигчлүүрийн жагсаалтад байхгүй тул бүтнээрээ үлдэнэ.
            cleaned_raw = textproc.clean_speech(raw)
            if not cleaned_raw:
                self.events.put(("empty", "filler"))
                return
            raw = cleaned_raw
        if not verbatim and self.cfg["voice_numbers"]:
            # Цэвэрлэгээний ДАРАА: чигчлүүр хасагдсанаар тооны үгс зэрэгцэж,
            # «хорин ааа гурван» гэх мэт нь ч нэг тоо болж уншигдана.
            raw = textproc.spell_numbers(raw)

        # Дуут үйлдэл (буцаа, давт, хуул, зогс) — текст оруулахгүй, эвент болно.
        # Үйлдлийн НЭР нь шууд эвентийн нэр: шинэ үйлдэл нэмэхэд `textproc`-д
        # нэг мөр, `app._handlers()`-д нэг мөр л хангалттай.
        if not verbatim:
            action = textproc.match_action(raw, self.cfg.get("actions"))
            if action:
                name, argument = action
                self.events.put((name, argument))
                return

        end_sentence = bool(self.cfg.get("auto_period"))
        # Үгчлэн горимд хувилбар сонгох утгагүй: хэлснийг нь ЯГ буулгах ёстой.
        variants = (
            [] if verbatim else self._variants(alternatives, clean, end_sentence)
        )
        if verbatim:
            text, backspaces = self.formatter.format_verbatim(raw)
        else:
            text, backspaces = self.formatter.format(raw, end_sentence=end_sentence)
        if not text and not backspaces:
            return
        shown = text.strip() or raw
        self.stats.record(shown, spoken_seconds, elapsed_ms)
        # Батлагдсан текст — дараагийн хувилбар сонголтод жин болно.
        if not verbatim:
            self.formatter.remember(shown)
        entry = self.transcripts.add(
            shown,
            detected_lang,
            spoken_seconds,
            raw_text=source_raw,
            provider=result.provider,
            confidence=confidence,
            requested_lang=lang,
            mode="verbatim" if verbatim else "polished",
        )
        # Дууг санах ойд барина: хэрэглэгч энэ таналтыг хожим засвал тэр
        # агшинд «дуу + зөв текст» гэсэн бүрэн хос үүснэ.
        if self.samples is not None:
            self.samples.remember(cleaned, entry)
        self.events.put(("recognized", (shown, entry, variants)))
        self.deliver(text, backspaces)

    def _keep_hard(self, pcm: bytes, reason: str, **meta) -> None:
        """Бүтэлгүй танилтын дууг хадгална (хураагч байхгүй бол юу ч хийхгүй).

        Зөв хариу нь мэдэгдэхгүй тул manifest-д гараар бичих мөр болж очно —
        гэхдээ яг эдгээр нь хамгийн хэцүү, хамгийн үнэ цэнэтэй жишээнүүд.
        """
        if self.samples is None:
            return
        try:
            self.samples.capture(pcm, reason, **meta)
        except Exception as exc:  # noqa: BLE001 - оношийн зүйл танилтыг унагаах ёсгүй
            log.warning("хэцүү жишээ хадгалагдсангүй: %s", exc)

    def deliver(self, text: str, backspaces: int, remember: bool = True) -> None:
        """Текстийг зорилтот цонхонд оруулна (энэ thread дээр л дуудна)."""
        try:
            # Зорилтот цонх идэвхжсэнгүй бол буулгахгүй. Энэ бол цөөн боловч
            # хамгийн үнэтэй алдаа: текст ӨӨР цонхны (чат, код, нууц үг оруулах
            # талбар) курсор дээр очно. Ялангуяа сүлжээ удааширч, хэрэглэгч
            # энэ хооронд өөр цонх руу шилжсэн үед тохиолддог.
            if not self.target.ensure() and self.target.known():
                log.warning("зорилтот цонх идэвхжсэнгүй — текстийг оруулсангүй")
                self.events.put(("misdirected", text))
                return
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
