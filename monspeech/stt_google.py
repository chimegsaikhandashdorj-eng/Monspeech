"""Google Web Speech рүү шууд хандах танигч (хөтөчгүйгээр).

Chromium-ийн ашигладаг нээлттэй эндпойнт рүү түүхий PCM дуу илгээнэ.
Холболтыг урьдчилан нээж тавьдаг тул товч суллагдмагц зөвхөн дуу л явна.

⚠️ Энэ нь албан ёсоор гуравдагч талд нээсэн API биш: SLA байхгүй, түлхүүр нь
бүх хэрэглэгчид нийтлэг. Хувийн хэрэглээнд хэвийн, олон хүнд тараахад
хязгаарлалтад өртөх магадлалтай — тэр тохиолдолд «Яриа» хуудсанаас өөр танигч
сонгоно.
"""

from __future__ import annotations

import http.client
import json
import threading
import urllib.parse

from .logging_setup import get as get_logger
from .recognizer import TIMEOUT, Provider, request

log = get_logger("stt.google")

HOST = "www.google.com"
PATH = "/speech-api/v2/recognize"
# Chromium-ийн задгай түлхүүр — бүртгэл, төлбөр шаардахгүй
DEFAULT_KEY = "AIzaSyBOti4mM-6x9WDnZIjIeyEU21OpBXqWBgw"

# Хэдэн хувилбар гуйхаа. Хариу нэг л удаа ирдэг тул нэмэлт зардал үүсэхгүй;
# хэрэглэгчийн толиор эргэж сонгоход хэрэг болно (textproc.choose_alternative).
MAX_ALTERNATIVES = 3

# Энэ танигчид л онцгой статусууд. 429 ба ерөнхий тохиолдол `recognizer`-т.
ERRORS = {403: "Таних үйлчилгээ түлхүүрийг хүлээж авсангүй (403)."}


class GoogleWebSpeech(Provider):
    """Дууг текст болгоно. Thread-ээс дуудаж болно (дотроо түгжээтэй)."""

    name = "google"
    title = "Google (үнэгүй, түлхүүргүй)"

    def __init__(self, lang: str = "mn-MN", key: str = DEFAULT_KEY) -> None:
        super().__init__(lang)
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
                "maxAlternatives": MAX_ALTERNATIVES,
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
    ) -> tuple[list[str], float]:
        """Үйлчилгээ түр ачаалагдсан (429) эсвэл 5xx гарвал дахин оролдоно.

        Эс бөгөөс хэрэглэгчийн хэлсэн өгүүлбэр бүрмөсөн алдагдаж, дахин
        ярихаас өөр арга үлдэхгүй.
        """
        if not pcm:
            return [], 0.0
        language = lang or self.lang
        with self._lock:
            body = request(
                # Дахин оролдохдоо үргэлж шинэ холболтоор: хадгалсан нь
                # хуучирсан байж болно.
                lambda attempt: self._post(pcm, rate, attempt == 0, language),
                log=log,
                errors=ERRORS,
                on_network_error=self._forget_connection,
            )

        return self._parse(body.decode("utf-8", "replace"))

    def _forget_connection(self) -> None:
        self._conn = None

    @staticmethod
    def _parse(body: str) -> tuple[list[str], float]:
        """Хариу нь мөр бүрт нэг JSON — эхний утгатай үр дүнг бүхэлд нь авна.

        Нэг хэлсэн зүйлд `maxAlternatives`-ийн хэрээр хэд хэдэн хувилбар ирдэг.
        Эхнийх нь хамгийн магадлалтай нь бөгөөд итгэлцлийг зөвхөн түүнд өгдөг
        (итгэлцэл байхгүй бол 1.0 гэж үзнэ — шүүлтгүй өнгөрнө). Үлдсэнийг нь
        хаялгүй буцаана: хэрэглэгчийн толиор эргэж сонгоход хэрэг болно.
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
                texts: list[str] = []
                confidence = 1.0
                for alternative in item.get("alternative") or []:
                    text = (alternative.get("transcript") or "").strip()
                    if not text:
                        continue
                    if not texts:
                        raw = alternative.get("confidence")
                        confidence = float(raw) if isinstance(raw, (int, float)) else 1.0
                    texts.append(text)
                if texts:
                    return texts, confidence
        return [], 0.0
