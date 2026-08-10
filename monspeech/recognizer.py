"""Google Web Speech рүү шууд хандах (хөтөчгүйгээр).

Chromium-ийн ашигладаг нээлттэй эндпойнт рүү түүхий PCM дуу илгээнэ.
Холболтыг урьдчилан нээж тавьдаг тул товч суллагдмагц зөвхөн дуу л явна.
"""

from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.parse

from .logging_setup import get as get_logger

log = get_logger("recognizer")

HOST = "www.google.com"
PATH = "/speech-api/v2/recognize"
# Chromium-ийн задгай түлхүүр — бүртгэл, төлбөр шаардахгүй
DEFAULT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"

TIMEOUT = 15.0

# Түр зуурын гэж үзэх хариунууд: ачаалал ихдэх, сервер талын түр саатал.
# 403 нь энд байхгүй — түлхүүр татгалзсан бол дахин оролдох нь утгагүй.
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
# Оролдлого хоорондын хүлээлт. Нийт нэмэгдэх саатал 1.4 секундээс хэтрэхгүй.
RETRY_DELAYS = (0.4, 1.0)


class RecognitionError(Exception):
    """Хэрэглэгчид харуулах алдаа."""


class Recognizer:
    """Дууг текст болгоно. Thread-ээс дуудаж болно (дотроо түгжээтэй)."""

    def __init__(self, lang: str = "mn-MN", key: str = DEFAULT_KEY) -> None:
        self.lang = lang
        self.key = key
        self._lock = threading.Lock()
        self._conn: http.client.HTTPSConnection | None = None

    # ------------------------------------------------------------------
    def _connect(self) -> http.client.HTTPSConnection:
        conn = http.client.HTTPSConnection(HOST, timeout=TIMEOUT)
        conn.connect()
        return conn

    def prewarm(self) -> None:
        """TLS холболтыг урьдчилан нээнэ — хариу ирэх хугацааг богиносгоно."""
        with self._lock:
            if self._conn is not None:
                return
            try:
                self._conn = self._connect()
            except OSError:
                self._conn = None  # сүлжээгүй байж болно — дараа дахин оролдоно

    def prewarm_async(self) -> None:
        threading.Thread(target=self.prewarm, daemon=True).start()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                try:
                    self._conn.close()
                except OSError:
                    pass
                self._conn = None

    # ------------------------------------------------------------------
    def _post(self, pcm: bytes, rate: int, reuse: bool, lang: str) -> tuple[int, bytes]:
        if self._conn is None or not reuse:
            if self._conn is not None:
                try:
                    self._conn.close()
                except OSError:
                    pass
            self._conn = self._connect()
        query = urllib.parse.urlencode(
            {
                "output": "json",
                "lang": lang,
                "key": self.key,
                "client": "chromium",
                "maxAlternatives": 3,
                "pFilter": 0,  # үгийг од болгож далдлахгүй
            }
        )
        self._conn.request(
            "POST",
            f"{PATH}?{query}",
            body=pcm,
            headers={
                "Content-Type": f"audio/l16; rate={rate}",
                "Content-Length": str(len(pcm)),
            },
        )
        response = self._conn.getresponse()
        body = response.read()
        if response.will_close:
            self._conn.close()
            self._conn = None
        return response.status, body

    def recognize(
        self, pcm: bytes, rate: int = 16000, lang: str | None = None
    ) -> tuple[str, float]:
        """PCM дууг текст болгоно.

        `(текст, итгэлцэл)` хосыг буцаана. Юу ч танигдаагүй бол `("", 0.0)`.
        Итгэлцлийг үйлчилгээ өгөөгүй бол 1.0 гэж үзнэ.

        Үйлчилгээ түр ачаалагдсан (429) эсвэл сервер талын түр алдаа (5xx) гарвал
        богино хүлээлттэйгээр дахин оролдоно — эс бөгөөс хэрэглэгчийн хэлсэн
        өгүүлбэр бүрмөсөн алдагдаж, дахин ярихаас өөр арга үлдэхгүй.
        """
        if not pcm:
            return "", 0.0
        language = lang or self.lang
        with self._lock:
            status, body = self._post_with_retries(pcm, rate, language)

        if status == 403:
            raise RecognitionError("Таних үйлчилгээ түлхүүрийг хүлээж авсангүй (403).")
        if status == 429:
            raise RecognitionError("Хэт олон хүсэлт — түр хүлээнэ үү (429).")
        if status != 200:
            raise RecognitionError(f"Таних үйлчилгээ {status} хариу өглөө.")

        return self._parse(body.decode("utf-8", "replace"))

    def _post_with_retries(self, pcm: bytes, rate: int, lang: str) -> tuple[int, bytes]:
        """Түр зуурын алдаанд дахин оролдоно (түгжээ дотор дуудагдана).

        Хүлээлтийг санаатай богино барьсан: ажлын thread нэг ээлжтэй тул энд
        удвал араас нь ирсэн өгүүлбэрүүд цувж, саатал улам хуримтлагдана.
        """
        attempts = len(RETRY_DELAYS) + 1
        for attempt in range(attempts):
            reuse = attempt == 0  # дахин оролдохдоо үргэлж шинэ холболтоор
            try:
                status, body = self._post(pcm, rate, reuse, lang)
            except (OSError, http.client.HTTPException) as exc:
                # Хадгалсан холболт хуучирсан байж болно — дахин оролдоно
                self._conn = None
                if attempt == attempts - 1:
                    raise RecognitionError(f"Сүлжээний алдаа: {exc}") from exc
                log.warning("сүлжээний алдаа (%d/%d): %s", attempt + 1, attempts, exc)
                time.sleep(RETRY_DELAYS[attempt])
                continue

            if status not in RETRY_STATUSES or attempt == attempts - 1:
                return status, body
            log.warning(
                "үйлчилгээ %d хариу өглөө (%d/%d) — дахин оролдож байна",
                status, attempt + 1, attempts,
            )
            time.sleep(RETRY_DELAYS[attempt])
        raise AssertionError("хүрэхгүй")  # давталт үргэлж буцаана эсвэл шиднэ

    @staticmethod
    def _parse(body: str) -> tuple[str, float]:
        """Хариу нь мөр бүрт нэг JSON — эхний утгатайг нь авна.

        Эхний хувилбар нь хамгийн магадлалтай нь бөгөөд итгэлцлийг зөвхөн
        түүнд өгдөг. Итгэлцэл байхгүй бол 1.0 гэж үзнэ (шүүлтгүй өнгөрнө).
        """
        for line in body.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            for item in data.get("result", []):
                for alternative in item.get("alternative") or []:
                    text = (alternative.get("transcript") or "").strip()
                    if text:
                        raw = alternative.get("confidence")
                        confidence = float(raw) if isinstance(raw, (int, float)) else 1.0
                        return text, confidence
        return "", 0.0
