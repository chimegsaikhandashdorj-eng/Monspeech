"""OpenAI-нийцтэй танигч — хэрэглэгчийн өөрийн үйлчилгээ, өөрийн түлхүүрээр.

Яагаад яг энэ хэлбэр вэ: `POST /v1/audio/transcriptions` (multipart, `file` +
`model`) гэсэн бичиглэлийг олон үйлчилгээ, мөн өөрийн компьютер дээр
ажиллуулдаг серверүүд дэмждэг. Тиймээс НЭГ л танигч бичээд, хэрэглэгч зөвхөн
хаяг, загвар, түлхүүрээ солиод өөр өөр ард талд холбогдох боломжтой болно.

Аппыг үнэгүй хэвээр үлдээх загвар: сервер, дундын түлхүүр байхгүй — хүсвэл
хэрэглэгч өөрийн үнэгүй хязгаарын түлхүүрээ хийнэ, хүсэхгүй бол Google дээрээ
үлдэнэ.

⚠️ Түлхүүр нь `config.json` дотор Windows DPAPI-гаар шифрлэгдэн хадгалагдана
(санах ойд болон UI-д ил текст; файлыг нээхэд `dpapi:…` гэж харагдана).
Хуваалцсан компьютер дээр үүнийг анхаарна уу.

Google-ээс хоёр ялгаа:
  * **Хувилбар нэг** — энэ бичиглэл олон хувилбар буцаадаггүй тул толиор
    сонгох (`textproc.choose_alternative`) энд ажиллах зүйлгүй.
  * **Итгэлцэл байхгүй** — үйлчилгээ өгөхгүй бол `None` буцаана. Өөрөөр хэлбэл
    «Итгэлцлийн босго» шүүлт хийхгүй, бас төгс итгэлцэл гэж худал үзэхгүй.
  * **Auto хэл** — `lang="auto"` үед `language` талбарыг огт илгээхгүй;
    multilingual model өөрөө хэлээ болон code-switch хэсгийг танина.
"""

from __future__ import annotations

import http.client
import io
import json
import threading
import urllib.parse
import uuid
import wave

from .logging_setup import get as get_logger
from .recognizer import (
    TIMEOUT,
    Provider,
    ProviderCapabilities,
    RecognitionError,
    RecognitionResult,
    request,
)

log = get_logger("stt.openai")

# Дуу илгээх хугацаа Google-ийнхээс урт байж болно (загвар нь бүтэн бичлэгийг
# нэг дор боловсруулдаг), тиймээс арай өгөөмөр.
UPLOAD_TIMEOUT = max(TIMEOUT, 30.0)

# Энэ танигчид л онцгой статусууд. 429 ба ерөнхий тохиолдол `recognizer`-т.
ERRORS = {
    401: "Танигч түлхүүрийг хүлээж авсангүй (401).",
    403: "Танигч түлхүүрийг хүлээж авсангүй (403).",
    404: "Танигчийн хаяг олдсонгүй (404) — хаягаа шалгана уу.",
}


def _wav(pcm: bytes, rate: int) -> bytes:
    """Түүхий PCM-ийг WAV болгоно — энэ бичиглэл файлын толгой шаарддаг."""
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)  # 16 бит
        handle.setframerate(rate)
        handle.writeframes(pcm)
    return buffer.getvalue()


def _multipart(fields: dict[str, str], audio: bytes) -> tuple[bytes, str]:
    """`multipart/form-data` бие ба түүний Content-Type-ыг бүтээнэ."""
    boundary = uuid.uuid4().hex
    parts: list[bytes] = []
    for key, value in fields.items():
        if not value:
            continue
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{key}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )
    parts.append(
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="file"; filename="audio.wav"\r\n'
        "Content-Type: audio/wav\r\n\r\n".encode("utf-8")
    )
    parts.append(audio)
    parts.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), f"multipart/form-data; boundary={boundary}"


class OpenAICompatible(Provider):
    """`/v1/audio/transcriptions` бичиглэлтэй дурын үйлчилгээ."""

    name = "openai"
    title = "Өөрийн үйлчилгээ (OpenAI-нийцтэй)"
    capabilities = ProviderCapabilities(
        auto_language=True,
        confidence=False,
        code_switching=True,
    )

    def __init__(
        self, lang: str = "mn-MN", url: str = "", model: str = "", key: str = ""
    ) -> None:
        super().__init__(lang)
        self.url = url.strip()
        self.model = model.strip()
        self.key = key.strip()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    def _target(self) -> tuple[bool, str, int, str]:
        """Хаягийг `(https эсэх, хост, порт, зам)` болгож задална."""
        parsed = urllib.parse.urlsplit(self.url)
        if parsed.scheme not in ("http", "https") or not parsed.hostname:
            raise RecognitionError(
                "Танигчийн хаяг буруу байна — «Яриа» хуудсанаас шалгана уу."
            )
        secure = parsed.scheme == "https"
        # Localhost биш бөгөөд нууцлалгүй HTTP холболт хэрэглэж байвал анхааруулна
        if not secure and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
            log.warning(
                "аюулгүй бус HTTP холболтоор алсын сервер рүү хандаж байна (%s) — түлхүүр ба яриа ил сүлжээгээр дамжина",
                parsed.hostname,
            )
        port = parsed.port or (443 if secure else 80)
        path = parsed.path or "/"
        if parsed.query:
            path = f"{path}?{parsed.query}"
        return secure, parsed.hostname, port, path

    def _post(self, pcm: bytes, rate: int, lang: str | None) -> tuple[int, bytes]:
        secure, host, port, path = self._target()
        body, content_type = _multipart(
            {
                "model": self.model,
                # Auto үед хоосон тул `_multipart` энэ талбарыг огт илгээхгүй.
                # Тодорхой хэл бол ISO-639-1: «mn-MN» → «mn».
                "language": lang.split("-")[0] if lang else "",
                # Хэрэглэгчийн толь — Whisper-төрлийн үйлчилгээ энд өгсөн үгсийг
                # таних магадлалыг өсгөдөг. Хоосон бол `_multipart` илгээхгүй.
                "prompt": self.vocabulary,
                "response_format": "json",
            },
            _wav(pcm, rate),
        )
        headers = {"Content-Type": content_type, "Content-Length": str(len(body))}
        if self.key:
            headers["Authorization"] = f"Bearer {self.key}"

        opener = http.client.HTTPSConnection if secure else http.client.HTTPConnection
        conn = opener(host, port, timeout=UPLOAD_TIMEOUT)
        try:
            conn.request("POST", path, body=body, headers=headers)
            response = conn.getresponse()
            return response.status, response.read()
        finally:
            conn.close()

    # ------------------------------------------------------------------
    def recognize(
        self, pcm: bytes, rate: int = 16000, lang: str | None = None
    ) -> RecognitionResult:
        if not pcm:
            requested = "" if lang == "auto" else (lang or self.lang)
            return RecognitionResult(language=requested, provider=self.name)
        if not self.url or not self.model:
            raise RecognitionError(
                "Танигчийн хаяг, загвар тохируулаагүй байна — «Яриа» хуудсыг үзнэ үү."
            )

        language = None if lang == "auto" else (lang or self.lang)
        with self._lock:
            body = request(
                lambda _attempt: self._post(pcm, rate, language),
                log=log,
                errors=ERRORS,
            )

        return self._parse(body.decode("utf-8", "replace"), language or "")

    @staticmethod
    def _parse(body: str, requested_language: str = "") -> RecognitionResult:
        """`{"text": "…"}` хэлбэрийн хариунаас текстийг авна.

        Итгэлцэл ирдэггүй тул `None` — босгоор шүүхгүй. Хариу нь
        хүлээгээгүй хэлбэртэй байвал хоосон буцааж, дуудагч нь «таньсангүй»
        гэж мэдэгдэнэ (чимээгүй бүтэлгүйтэхгүй).
        """
        try:
            data = json.loads(body)
        except ValueError:
            return RecognitionResult(language=requested_language, provider="openai")
        if not isinstance(data, dict):
            return RecognitionResult(language=requested_language, provider="openai")
        text = str(data.get("text") or "").strip()
        detected = str(data.get("language") or requested_language).strip()
        # Зарим compatible сервер ISO-639-1, зарим нь бүтэн нэр буцаана.
        detected = {
            "mn": "mn-MN",
            "mongolian": "mn-MN",
            "en": "en-US",
            "english": "en-US",
        }.get(detected.lower(), detected)
        return RecognitionResult(
            [text] if text else [],
            None,
            detected,
            "openai",
        )
