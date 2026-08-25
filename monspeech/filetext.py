"""Аудио/видео файлыг текст болгох.

Микрофоны дамжлагатай ижил танигчийг ашиглана — ялгаа нь эх сурвалж:
бичлэг хийхийн оронд дискнээс уншина. Хурлын бичлэг, лекц, дуут тэмдэглэлийг
хөрвүүлэхэд хэрэглэнэ.

**WAV нь нэмэлт хэрэгсэлгүй** ажиллана (стандарт `wave` сан). MP3, M4A, MP4
зэрэг нь `ffmpeg` шаардана — байхгүй бол ойлгомжтой мессеж буцаана.

Урт бичлэгийг НЭГ хүсэлтээр илгээхгүй: ярианы завсраар нь хэсэглээд дараалан
илгээнэ. Ингэснээр (1) үйлчилгээний хэмжээ/хугацааны хязгаарт багтана,
(2) явцыг харуулах боломжтой, (3) нэг хэсэг унасан ч бусад нь үлдэнэ.
"""

from __future__ import annotations

import array
import shutil
import subprocess
import wave
from collections.abc import Callable
from pathlib import Path

try:  # Python 3.13-д стандарт сангаас хасагдсан
    import audioop
except ImportError:  # pragma: no cover - хувилбараас хамаарна
    audioop = None

from .audio import BYTES_PER_SAMPLE, MAX_SEGMENT, RATE, Segmenter
from .logging_setup import get as get_logger
from .recognizer import RecognitionError

log = get_logger("filetext")

#: `wave`-ээр шууд уншиж чадах өргөтгөлүүд.
NATIVE_SUFFIXES = {".wav", ".wave"}

#: ffmpeg-ээр дамжуулж уншиж болох (алдартай) өргөтгөлүүд. Жагсаалт нь зөвхөн
#: цонхны файл сонгогчид зориулсан — ffmpeg эдгээрээс олныг уншина.
FFMPEG_SUFFIXES = {".mp3", ".m4a", ".aac", ".ogg", ".opus", ".flac", ".mp4", ".mkv", ".mov", ".webm"}

#: Нэг хүсэлтэд илгээх дууны дээд урт (секунд). Сегментчлэгч чимээгүй
#: завсраар таслах ба энэ нь зөвхөн ДЭЭД хязгаар.
CHUNK_SECONDS = MAX_SEGMENT

#: ffmpeg хэр удаан ажиллаж болох вэ (секунд). Урт видео ч энэ дотор багтана.
FFMPEG_TIMEOUT = 900


class FileError(Exception):
    """Файлыг уншиж чадсангүй (хэрэглэгчид харуулах мессежтэй)."""


def ffmpeg_path() -> str:
    """Системд суусан ffmpeg-ийн зам (олдохгүй бол хоосон)."""
    return shutil.which("ffmpeg") or ""


def load_pcm(path: str | Path) -> bytes:
    """Файлыг 16 кГц, моно, 16 бит PCM болгож уншина."""
    source = Path(path)
    if not source.exists():
        raise FileError(f"«{source.name}» олдсонгүй.")
    if source.suffix.lower() in NATIVE_SUFFIXES:
        return _load_wav(source)
    return _load_ffmpeg(source)


def _load_wav(source: Path) -> bytes:
    try:
        with wave.open(str(source), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            rate = handle.getframerate()
            raw = handle.readframes(handle.getnframes())
    except (OSError, wave.Error) as exc:
        # Зарим «wav» нь үнэндээ шахсан бичиглэлтэй байдаг — ffmpeg-ээр оролдоно
        log.info("WAV шууд уншигдсангүй (%s) — ffmpeg-ээр оролдож байна", exc)
        return _load_ffmpeg(source)
    return _to_mono_16k(raw, channels, width, rate)


def _to_mono_16k(raw: bytes, channels: int, width: int, rate: int) -> bytes:
    """Дурын PCM-ийг таних дамжлагын хүлээдэг хэлбэрт оруулна."""
    if not raw:
        return b""
    if audioop is None:  # pragma: no cover - зөвхөн шинэ Python дээр
        if (channels, width, rate) != (1, BYTES_PER_SAMPLE, RATE):
            raise FileError(
                "Энэ Python хувилбарт дууг хөрвүүлэх сан алга — 16 кГц, моно WAV хэрэгтэй."
            )
        return raw
    if width != BYTES_PER_SAMPLE:
        raw = audioop.lin2lin(raw, width, BYTES_PER_SAMPLE)
    if channels > 1:
        raw = audioop.tomono(raw, BYTES_PER_SAMPLE, 0.5, 0.5)
    if rate != RATE:
        raw, _ = audioop.ratecv(raw, BYTES_PER_SAMPLE, 1, rate, RATE, None)
    return raw


def _load_ffmpeg(source: Path) -> bytes:
    tool = ffmpeg_path()
    if not tool:
        raise FileError(
            f"«{source.suffix or 'энэ'}» файлыг уншихад ffmpeg хэрэгтэй. "
            "WAV файл бол шууд ажиллана."
        )
    command = [
        tool, "-nostdin", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-vn", "-ac", "1", "-ar", str(RATE), "-f", "s16le", "-",
    ]
    try:
        done = subprocess.run(  # noqa: S603 - зам нь `shutil.which`-ээс
            command, capture_output=True, timeout=FFMPEG_TIMEOUT, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise FileError(f"ffmpeg ажиллуулж чадсангүй: {exc}") from exc
    if done.returncode != 0 or not done.stdout:
        message = (done.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        detail = message[-1] if message else "тодорхойгүй алдаа"
        raise FileError(f"«{source.name}»-г уншиж чадсангүй: {detail}")
    return done.stdout


def split_chunks(pcm: bytes, rate: int = RATE, limit: float = CHUNK_SECONDS) -> list[bytes]:
    """Дууг ярианы завсраар нь хэсэглэнэ (шаардвал албаар таслана)."""
    if not pcm:
        return []
    segmenter = Segmenter(rate=rate, max_segment=limit)
    step = int(rate * 0.064) * BYTES_PER_SAMPLE  # ~64 мс, микрофонтой ижил
    chunks: list[bytes] = []
    for start in range(0, len(pcm), step):
        segment = segmenter.feed(pcm[start : start + step])
        if segment:
            chunks.append(segment)
    final = segmenter.flush(final=True)
    if final:
        chunks.append(final)
    return chunks


def transcribe(
    path: str | Path,
    recognizer,
    lang: str = "mn-MN",
    on_progress: Callable[[int, int], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> str:
    """Файлыг текст болгож, мөр мөрөөр нь нийлүүлж буцаана.

    Нэг хэсэг унасан ч бусдыг үргэлжлүүлнэ: урт бичлэгийн дунд сүлжээ
    ганц удаа тасарснаас болж бүх ажил үрэгдэх ёсгүй.
    """
    pcm = load_pcm(path)
    chunks = split_chunks(pcm)
    if not chunks:
        raise FileError("Файлаас яриа олдсонгүй.")
    lines: list[str] = []
    for index, chunk in enumerate(chunks, start=1):
        if should_stop and should_stop():
            log.info("хөрвүүлэлт зогсоов (%d/%d)", index, len(chunks))
            break
        if on_progress:
            on_progress(index, len(chunks))
        try:
            result = recognizer.recognize(chunk, RATE, lang)
        except (RecognitionError, Exception) as exc:  # noqa: BLE001
            log.warning("%d дэх хэсэг танигдсангүй: %s", index, exc)
            continue
        text = (getattr(result, "text", "") or "").strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def save_text(source: str | Path, text: str) -> Path:
    """Хөрвүүлсэн текстийг эх файлын хажууд `.txt` болгож хадгална."""
    target = Path(source).with_suffix(".txt")
    if target.exists():
        # Хуучин үр дүнг дарж бичихгүй — дугаар нэмнэ
        stem = target.stem
        index = 2
        while target.exists():
            target = target.with_name(f"{stem} ({index}).txt")
            index += 1
    target.write_text(text, encoding="utf-8")
    return target


def duration_seconds(pcm: bytes, rate: int = RATE) -> float:
    return len(pcm) / (rate * BYTES_PER_SAMPLE) if rate else 0.0


def _samples(pcm: bytes) -> array.array:  # pragma: no cover - туслах
    out = array.array("h")
    out.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    return out
