"""Монгол–англи автомат хэл сонголт.

Provider хэлээ өөрөө таньдаг бол нэг auto хүсэлт ашиглана. Үгүй бол монгол,
англи үр дүнг тэнцвэртэй (эргэлзсэн үед дахин) эсвэл нарийвчлалын (хоёуланг
зэрэг) горимоор авч, бичиг + үгийн сан + бодит итгэлцэл + өмнөх хэлний дохиог
нийлүүлэн сонгоно.
"""

from __future__ import annotations

import re
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from typing import Callable

from .logging_setup import get as get_logger
from .recognizer import Provider, ProviderCapabilities, RecognitionResult, coerce_result

log = get_logger("language")

#: 16 бит PCM. `audio`-г импортлохгүй (тэр нь PyAudio татдаг) — энэ модуль
#: benchmark-аас ч дуудагддаг тул хамаарлаа хөнгөн байлгана.
BYTES_PER_SAMPLE = 2

_CYRILLIC = re.compile(r"[А-Яа-яЁёӨөҮү]")
_LATIN = re.compile(r"[A-Za-z]")
_STRIP = " \t\r\n.,!?;:…()[]{}\"'“”‘’«»-—_"

# Эдгээр нь бүрэн хэлний загвар биш. Богино, эргэлзээтэй өгүүлбэрт бичгийн
# дохиог батлах жижиг жагсаалт; гол шийдвэр нь provider-ийн хоёр transcript.
_MN_WORDS = frozenset({
    "би", "чи", "та", "бид", "энэ", "тэр", "мөн", "биш", "байна", "байсан",
    "болно", "хийх", "хий", "маргааш", "өнөөдөр", "өглөө", "орой", "цаг",
    "минут", "уулзъя", "явна", "ирнэ", "сайн", "уу", "тийм", "үгүй", "гэж",
    "дээр", "доор", "ажил", "хурал", "бич", "өг", "ав", "шинэ", "хоёр", "нэг",
    "гурав", "дөрөв", "тав",
})
_EN_WORDS = frozenset({
    "i", "you", "we", "they", "this", "that", "is", "are", "was", "will", "do",
    "make", "today", "tomorrow", "morning", "evening", "meeting", "standup", "code",
    "function", "deployment", "deploy", "refactor", "test", "file", "new", "line",
    "hello", "world", "please", "copy", "stop", "undo", "repeat", "the", "a", "an",
    "to", "in", "on", "for",
})


def script_counts(text: str) -> tuple[int, int]:
    """`(кирилл, латин)` үсгийн тоо."""

    return len(_CYRILLIC.findall(text)), len(_LATIN.findall(text))


def infer_text_language(text: str) -> str:
    """Бичгээс `mn-MN`, `en-US`, `mixed`, эсвэл хоосон утга сэжиглэнэ."""

    cyrillic, latin = script_counts(text)
    total = cyrillic + latin
    if not total:
        return ""
    if cyrillic >= 2 and latin >= 2 and min(cyrillic, latin) / total >= 0.15:
        return "mixed"
    return "mn-MN" if cyrillic >= latin else "en-US"


def script_fit(text: str, language: str) -> float:
    """Текстийн бичиг хүссэн хэлтэй 0..1 хэмжээнд хэр нийцэж байна."""

    cyrillic, latin = script_counts(text)
    total = cyrillic + latin
    if not total:
        return 0.5
    if language.lower().startswith("mn"):
        return cyrillic / total
    if language.lower().startswith("en"):
        return latin / total
    return 0.5


def _words(text: str) -> list[str]:
    return [word.strip(_STRIP).lower() for word in text.split() if word.strip(_STRIP)]


def lexical_fit(text: str, language: str) -> float:
    words = _words(text)
    if not words:
        return 0.0
    vocabulary = _MN_WORDS if language.lower().startswith("mn") else _EN_WORDS
    return sum(word in vocabulary for word in words) / len(words)


def language_score(
    result: RecognitionResult,
    language: str,
    *,
    prior: str = "",
    recent: str = "",
) -> float:
    """Өөр provider-ийн итгэлцлийг дангаар харьцуулахгүй нийлмэл оноо."""

    if not result.text:
        return -1.0
    confidence = result.confidence if result.confidence is not None else 0.5
    score = 0.42 * max(0.0, min(1.0, confidence))
    score += 0.43 * script_fit(result.text, language)
    score += 0.10 * lexical_fit(result.text, language)
    if language == prior:
        score += 0.04
    if language == recent:
        score += 0.02
    return score


def _strong_mn(word: str) -> bool:
    core = word.strip(_STRIP).lower()
    return bool(core) and ("ө" in core or "ү" in core or core in _MN_WORDS)


def _strong_en(word: str) -> bool:
    core = word.strip(_STRIP).lower()
    return bool(core) and bool(_LATIN.search(core)) and core in _EN_WORDS


def merge_code_switch(mongolian: str, english: str) -> str:
    """Ижил хэмнэлтэй хоёр transcript-ийг болгоомжтой токеноор нэгтгэнэ.

    Timestamp байхгүй provider дээр зөвхөн үгийн тоо ижил, хоёр талаас хүчтэй
    нотолгоо олдсон үед үр дүн гаргана. Эргэлзвэл хоосон буцааж, бүтэн нэг
    transcript сонгох хуучин аюулгүй замдаа үлдэнэ.
    """

    mn_words, en_words = mongolian.split(), english.split()
    if len(mn_words) != len(en_words) or not 2 <= len(mn_words) <= 40:
        return ""
    merged: list[str] = []
    used_mn = used_en = False
    for mn_word, en_word in zip(mn_words, en_words, strict=True):
        if mn_word.strip(_STRIP).lower() == en_word.strip(_STRIP).lower():
            merged.append(mn_word)
            continue
        mn_strong, en_strong = _strong_mn(mn_word), _strong_en(en_word)
        if mn_strong and not en_strong:
            merged.append(mn_word)
            used_mn = True
        elif en_strong and not mn_strong:
            merged.append(en_word)
            used_en = True
        else:
            # Нотолгоогүй токеныг монгол хувилбараас авна: энэ аппын үндсэн
            # хэрэглээ монгол бөгөөд санамсаргүй эвлүүлэг хийхгүй байх нь чухал.
            merged.append(mn_word)
    text = " ".join(merged)
    return text if used_mn and used_en and infer_text_language(text) == "mixed" else ""


class LanguageRouter:
    """Provider-уудыг удирдаж, нэг эцсийн `RecognitionResult` сонгоно."""

    def __init__(
        self,
        provider: Provider,
        factory: Callable[[str], Provider] | None = None,
        chooser: Callable[[list[str]], str] | None = None,
        on_request: Callable[[str, float], None] | None = None,
    ) -> None:
        self.provider = provider
        self.factory = factory
        self.chooser = chooser
        # Хэрэглээний тоолуур. Нэг таналт нэг хүсэлт ГЭСЭН ҮГ БИШ: нарийвчлалын
        # горимд хоёр хэл зэрэг, энгийн горимд зөрүүтэй үед хоёр дахь хүсэлт
        # явдаг. Тиймээс тоолол нь дамжлагад биш, ЭНД — хүсэлт бүрд нэг удаа.
        self.on_request = on_request
        self._extra: dict[str, Provider] = {}
        self.last_language = ""
        self._recent_languages: deque[str] = deque(maxlen=5)

    def replace_provider(
        self, provider: Provider, factory: Callable[[str], Provider] | None = None
    ) -> None:
        self.close_extras()
        self.provider = provider
        if factory is not None:
            self.factory = factory
        self.last_language = ""
        self._recent_languages.clear()

    def set_vocabulary(self, hint: str) -> None:
        """Толь солигдоход үндсэн ба нэмэлт танигч БҮГДЭД дохиог тарааана."""
        self.provider.set_vocabulary(hint)
        for provider in self._extra.values():
            provider.set_vocabulary(hint)

    def confirm_language(self, language: str) -> None:
        """Автомат сонголт эсвэл хэрэглэгчийн засварыг session prior-д санана."""

        if language and language != "mixed":
            self._recent_languages.append(language)
            self.last_language = language

    def _recent_preference(self) -> str:
        if not self._recent_languages:
            return ""
        items = list(self._recent_languages)
        # Давтамж дийлнэ; тэнцвэл хамгийн сүүлийнх.
        return max(set(items), key=lambda lang: (items.count(lang), items[::-1].index(lang) * -1))

    def close_extras(self) -> None:
        for provider in self._extra.values():
            try:
                provider.close()
            except Exception:  # noqa: BLE001 - хаах алдаа аппыг унагахгүй
                pass
        self._extra.clear()

    def prewarm(
        self,
        hint: str,
        configured: list[str] | tuple[str, ...],
        *,
        automatic: bool,
        accuracy: bool,
    ) -> None:
        """Нарийвчлалын горимын хоёр дахь TLS холболтыг ярих зуур нээнэ."""

        if not automatic or not accuracy or self.factory is None:
            return
        capabilities = getattr(self.provider, "capabilities", ProviderCapabilities())
        if capabilities.auto_language:
            return
        for language in self._candidates(hint, configured)[:2]:
            self._provider_for(language).prewarm_async()

    def _provider_for(self, language: str) -> Provider:
        if language == getattr(self.provider, "lang", language) or self.factory is None:
            return self.provider
        if language not in self._extra:
            self._extra[language] = self.factory(language)
        return self._extra[language]

    def _count(self, provider: Provider, pcm: bytes, rate: int) -> None:
        """Явуулсан НЭГ хүсэлтийг бүртгэнэ (амжилттай хариу ирсний дараа)."""
        if self.on_request is None or rate <= 0:
            return
        try:
            self.on_request(
                getattr(provider, "name", ""), len(pcm) / (rate * BYTES_PER_SAMPLE)
            )
        except Exception as exc:  # noqa: BLE001 - тоолуур танилтыг унагахгүй
            log.warning("хэрэглээг бүртгэж чадсангүй: %s", exc)

    def _one(self, pcm: bytes, rate: int, language: str) -> RecognitionResult:
        provider = self._provider_for(language)
        value = provider.recognize(pcm, rate, language)
        self._count(provider, pcm, rate)
        return coerce_result(
            value,
            language=language,
            provider=getattr(provider, "name", ""),
        )

    def _selected_alternative(self, result: RecognitionResult) -> RecognitionResult:
        if not result.alternatives or self.chooser is None:
            return result
        selected = self.chooser(result.alternatives)
        if not selected or selected == result.alternatives[0]:
            return result
        alternatives = [selected] + [item for item in result.alternatives if item != selected]
        return replace(result, alternatives=alternatives)

    def _maybe_selected(
        self, result: RecognitionResult, choose_alternatives: bool
    ) -> RecognitionResult:
        return self._selected_alternative(result) if choose_alternatives else result

    @staticmethod
    def _candidates(hint: str, configured: list[str] | tuple[str, ...]) -> list[str]:
        candidates: list[str] = []
        for language in (hint, *configured):
            language = str(language or "")
            if language and language not in candidates:
                candidates.append(language)
        return candidates or ["mn-MN", "en-US"]

    @staticmethod
    def _needs_second(result: RecognitionResult, language: str, minimum: float) -> bool:
        if not result.text:
            return True
        # Бичиг зөрвөл confidence өндөр байсан ч шалгана — хуучин механизмын
        # хамгийн том цоорхой энэ байсан.
        if script_fit(result.text, language) < 0.60:
            return True
        return result.confidence is not None and result.confidence < minimum

    def recognize(
        self,
        pcm: bytes,
        rate: int,
        *,
        hint: str,
        configured: list[str] | tuple[str, ...],
        automatic: bool,
        accuracy: bool,
        minimum_confidence: float,
        margin: float = 0.08,
        choose_alternatives: bool = True,
    ) -> RecognitionResult:
        if not automatic:
            result = self._maybe_selected(
                self._one(pcm, rate, hint), choose_alternatives
            )
            if result.text:
                self.confirm_language(hint)
            return result

        # Multilingual model өөрөө хэлээ таньдаг бол forced language өгөхгүй.
        capabilities = getattr(self.provider, "capabilities", ProviderCapabilities())
        if capabilities.auto_language:
            value = self.provider.recognize(pcm, rate, "auto")
            self._count(self.provider, pcm, rate)
            result = coerce_result(
                value,
                provider=getattr(self.provider, "name", ""),
            )
            result = self._maybe_selected(result, choose_alternatives)
            inferred = infer_text_language(result.text)
            language = "mixed" if inferred == "mixed" else (result.language or inferred or hint)
            result.language = language
            if language and language != "mixed":
                self.confirm_language(language)
            return result

        languages = self._candidates(hint, configured)[:2]
        results: dict[str, RecognitionResult] = {}
        errors: list[Exception] = []

        if accuracy and len(languages) > 1 and self.factory is not None:
            # Тусдаа provider instance-ууд тул Google-ийн connection lock
            # хүсэлтүүдийг цувруулахгүй — үнэхээр зэрэг явна.
            with ThreadPoolExecutor(max_workers=len(languages)) as pool:
                futures = {pool.submit(self._one, pcm, rate, lang): lang for lang in languages}
                for future in as_completed(futures):
                    language = futures[future]
                    try:
                        results[language] = self._maybe_selected(
                            future.result(), choose_alternatives
                        )
                    except Exception as exc:  # noqa: BLE001
                        errors.append(exc)
        else:
            first = languages[0]
            first_result = self._maybe_selected(
                self._one(pcm, rate, first), choose_alternatives
            )
            results[first] = first_result
            if len(languages) > 1 and self._needs_second(
                first_result, first, minimum_confidence
            ):
                try:
                    second = languages[1]
                    results[second] = self._maybe_selected(
                        self._one(pcm, rate, second), choose_alternatives
                    )
                except Exception as exc:  # noqa: BLE001
                    log.warning("хоёр дахь хэлний танилт бүтсэнгүй: %s", exc)

        if not results and errors:
            raise errors[0]
        if not results:
            return RecognitionResult(language=hint)

        scores = {
            language: language_score(
                result, language, prior=hint, recent=self._recent_preference()
            )
            for language, result in results.items()
        }
        ranked = sorted(scores, key=scores.get, reverse=True)
        chosen_language = ranked[0]
        if len(ranked) > 1 and scores[ranked[0]] - scores[ranked[1]] < margin:
            if hint in results:
                chosen_language = hint
            elif self.last_language in results:
                chosen_language = self.last_language

        # Timestamp-гүй Google дээрх хязгаарлагдмал code-switch нэгтгэл.
        if "mn-MN" in results and "en-US" in results:
            mixed = merge_code_switch(results["mn-MN"].text, results["en-US"].text)
            if mixed:
                base = results[chosen_language]
                return RecognitionResult(
                    [mixed],
                    base.confidence,
                    "mixed",
                    f"{base.provider}+merge",
                )

        chosen = results[chosen_language]
        chosen.language = chosen_language
        if chosen.text:
            self.confirm_language(chosen_language)
        log.info(
            "хэл сонгов: %s (%s)",
            chosen_language,
            ", ".join(f"{lang}={scores[lang]:.2f}" for lang in ranked),
        )
        return chosen
