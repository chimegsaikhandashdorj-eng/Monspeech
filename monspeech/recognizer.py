"""Танигчийн залгуур: нийтлэг интерфейс ба сонголт.

Апп нэг л зүйл мэднэ — «дуу өгөхөд хувилбарууд буцаадаг объект». Түүний ард
Google байна уу, хэрэглэгчийн өөрийн үйлчилгээ байна уу гэдэг нь энэ файлаас
цааш харагдахгүй.

Яагаад залгуур хэрэгтэй вэ: анхны утга болох Google-ийн эндпойнт нь албан ёсны
биш, SLA байхгүй, бүх хэрэглэгч нэг задгай түлхүүр дээр сууна. Ганц хэрэглэгчид
хангалттай ч олон хүнд тараавал хязгаарлалт бүгдэд нь зэрэг цохино. Тэр өдөр
аппыг бүхэлд нь дахин бичихгүйн тулд солих цэгийг эхнээс нь энд гаргав.

Шинэ танигч нэмэх: `Provider`-оос удамшуулж `recognize()`-ыг бичээд `PROVIDERS`
бүртгэлд нэг мөр нэмнэ. Өөр хаана ч засах шаардлагагүй — цонхны цэс, анхны утга
руу буцах, тохиргооны нэр бүгд тэр бүртгэлээс уншина.
"""

from __future__ import annotations

import http.client
import logging
import threading
import time
from collections.abc import Callable, Mapping
from typing import Any

# Сүлжээний давхаргаас гарах алдаанууд — `OSError`-той хамт барина.
HTTP_ERRORS = http.client.HTTPException

# Түр зуурын гэж үзэх хариунууд: ачаалал ихдэх, сервер талын түр саатал.
# 401/403 нь энд байхгүй — түлхүүр татгалзсан бол дахин оролдох нь утгагүй.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# Оролдлого хоорондын хүлээлт. Нийт нэмэгдэх саатал 1.4 секундээс хэтрэхгүй.
# Санаатай богино: ажлын thread нэг ээлжтэй тул энд удвал араас нь ирсэн
# өгүүлбэрүүд цувж, саатал улам хуримтлагдана.
RETRY_DELAYS = (0.4, 1.0)

TIMEOUT = 15.0


class RecognitionError(Exception):
    """Хэрэглэгчид харуулах алдаа."""


# Танигч бүрт ижил утгатай статусууд. Тусгайлан бичихгүй бол эдгээр хүчинтэй.
COMMON_ERRORS: Mapping[int, str] = {
    429: "Хэт олон хүсэлт — түр хүлээнэ үү (429).",
}


def request(
    send: Callable[[int], tuple[int, bytes]],
    *,
    log: logging.Logger,
    errors: Mapping[int, str] = {},
    on_network_error: Callable[[], None] | None = None,
) -> bytes:
    """Нэг хүсэлтийг дахин оролдлоготойгоор явуулж, амжилттай биеийг буцаана.

    Танигч бүр зөвхөн `send(оролдлогын дугаар) -> (статус, бие)` гэсэн нэг
    хаалт бичнэ; дахин оролдох бодлого, хүлээлт, статусыг хэрэглэгчийн хэлээр
    алдаа болгох нь бүхэлдээ энд төвлөрнө. Ингэснээр шинэ танигч нэмэхэд
    сүлжээний зан төлөв автоматаар ижил байна.

    `errors` нь тухайн танигчид л онцгой статусууд (жишээ нь 404 хаяг олдсонгүй);
    `COMMON_ERRORS`-той нийлж, давхцвал `errors` нь дийлнэ. Жагсаагаагүй бүх
    200-аас өөр статус ерөнхий мэдэгдэл болно.

    `on_network_error` нь сүлжээ тасрахад дуудагдана — хадгалсан холболтоо
    хаяхад хэрэгтэй.

    Сүлжээ эсвэл статусын алдаанд `RecognitionError` шиднэ.
    """
    attempts = len(RETRY_DELAYS) + 1
    status, body = 0, b""
    for attempt in range(attempts):
        try:
            status, body = send(attempt)
        except (OSError, HTTP_ERRORS) as exc:
            if on_network_error is not None:
                on_network_error()
            if attempt == attempts - 1:
                raise RecognitionError(f"Сүлжээний алдаа: {exc}") from exc
            log.warning("сүлжээний алдаа (%d/%d): %s", attempt + 1, attempts, exc)
            time.sleep(RETRY_DELAYS[attempt])
            continue

        if status not in RETRY_STATUSES or attempt == attempts - 1:
            break
        log.warning(
            "үйлчилгээ %d хариу өглөө (%d/%d) — дахин оролдож байна",
            status, attempt + 1, attempts,
        )
        time.sleep(RETRY_DELAYS[attempt])

    if status == 200:
        return body
    message = errors.get(status) or COMMON_ERRORS.get(status)
    raise RecognitionError(message or f"Таних үйлчилгээ {status} хариу өглөө.")


class Provider:
    """Танигч бүрийн суурь. Дэд ангиуд `recognize()`-ыг бичнэ.

    `lang` нь гаднаас солигддог (хоёр дахь хэлний товчлуур) тул энгийн талбар.
    `prewarm`/`close` нь холболт барьдаг танигчид л утгатай — бусад нь юу ч
    хийхгүй өвлөнө.
    """

    def __init__(self, lang: str = "mn-MN") -> None:
        self.lang = lang

    def recognize(
        self, pcm: bytes, rate: int = 16000, lang: str | None = None
    ) -> tuple[list[str], float]:
        """PCM дууг текст болгоно.

        `(хувилбарууд, итгэлцэл)` хосыг буцаана. Хувилбарууд нь магадлалын
        дарааллаар — эхнийх нь хамгийн магадлалтай. Юу ч танигдаагүй бол
        `([], 0.0)`. Итгэлцэл өгөх боломжгүй үйлчилгээ 1.0 буцаана (шүүлтгүй
        өнгөрнө).
        """
        raise NotImplementedError

    def prewarm(self) -> None:
        """Холболтыг урьдчилан нээх боломжтой бол нээнэ."""

    def prewarm_async(self) -> None:
        threading.Thread(target=self.prewarm, daemon=True).start()

    def close(self) -> None:
        """Барьсан нөөцөө сулла."""


# Импортыг үүсгэгч дотор хийсэн: танигчид энэ файлаас `Provider`-ыг авдаг тул
# дээд түвшинд импортловол тойрог үүснэ.
def _build_google(cfg: dict[str, Any], lang: str) -> Provider:
    from .stt_google import GoogleWebSpeech

    return GoogleWebSpeech(lang=lang)


def _build_openai(cfg: dict[str, Any], lang: str) -> Provider:
    from .stt_openai import OpenAICompatible

    return OpenAICompatible(
        lang=lang,
        url=str(cfg.get("stt_url") or ""),
        model=str(cfg.get("stt_model") or ""),
        key=str(cfg.get("stt_key") or ""),
    )


#: Танигч бүр: тохиргооны нэр → (цонхонд харагдах гарчиг, үүсгэгч).
#: Шинэ танигч нэмэхэд ЗӨВХӨН энд мөр нэмнэ.
PROVIDERS: dict[str, tuple[str, Callable[[dict[str, Any], str], Provider]]] = {
    "google": ("Google (үнэгүй, түлхүүргүй)", _build_google),
    "openai": ("Өөрийн үйлчилгээ (OpenAI-нийцтэй)", _build_openai),
}

#: Танихгүй нэр таарвал энэ рүү буцна.
DEFAULT_PROVIDER = "google"


def create(cfg: dict[str, Any]) -> Provider:
    """Тохиргоонд заасан танигчийг үүсгэнэ.

    Танихгүй нэр бичигдсэн (гараар config.json засах, хуучин хувилбар) бол
    чимээгүй анхны танигч руу буцна — апп ажиллахаа болихоос дээр.
    """
    name = str(cfg.get("stt_provider") or DEFAULT_PROVIDER)
    lang = str(cfg.get("lang") or "mn-MN")
    _, build = PROVIDERS.get(name) or PROVIDERS[DEFAULT_PROVIDER]
    return build(cfg, lang)


def titles() -> list[tuple[str, str]]:
    """Цонхонд харуулах `(нэр, гарчиг)` жагсаалт."""
    return [(name, title) for name, (title, _) in PROVIDERS.items()]
