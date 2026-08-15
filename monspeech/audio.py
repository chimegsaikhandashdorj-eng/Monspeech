"""Микрофоноос шууд дуу авах.

Хөтөч ашиглахгүй — PyAudio-гоор 16 кГц, моно, 16 бит PCM цуглуулж,
чимээгүй завсраар нь өгүүлбэр болгон тасалж дамжуулна.
"""

from __future__ import annotations

import array
import math
import threading
import time

try:  # Python 3.13-д стандарт сангаас хасагдсан
    import audioop
except ImportError:  # pragma: no cover - хувилбараас хамаарна
    audioop = None

import pyaudio

from .logging_setup import get as get_logger

log = get_logger("audio")

RATE = 16000
CHUNK = 1024  # ~64 мс
CHANNELS = 1
FORMAT = pyaudio.paInt16
BYTES_PER_SAMPLE = 2

# Сегмент таслах хэмжүүрүүд
SILENCE_HOLD = 0.7  # ийм удаан чимээгүй бол өгүүлбэр дууссан гэж үзнэ
MIN_SPEECH = 0.22  # үүнээс богино дуутай хэсгийг илгээхгүй
# Товч суллах үед хэрэглэгч санаатай дуусгасан тул хамаагүй богино үгийг ч
# илгээнэ. Эс бөгөөс "уу", "юм" зэрэг богино сүүлчийн үг чимээгүй алга болно.
FINAL_MIN_SPEECH = 0.10
MAX_SEGMENT = 45.0  # хэт урт бичлэгийг албаар тасална
NOISE_SAMPLE = 0.25  # эхний хэсгээр орчны чимээг хэмжинэ
MIN_THRESHOLD = 320.0
# Орчны чимээний хэмжилтээс гарах босгын дээд хязгаар. Хэрэглэгч товч дармагцаа
# ярьж эхэлбэл хэмжилт нь ЯРИАН дээр тохирч, босго асар өндөр болоод бүх яриаг
# "чимээгүй" гэж үзэн чимээгүйгээр хаядаг байсан.
NOISE_CEILING = 2500.0
# Буруу хэмжилтийг өөрөө засах: ийм удаан яриа олдохгүй байвал босгыг буулгана
RECALIBRATE_AFTER = 1.4
RECALIBRATE_RATIO = 0.35


# ----------------------------------------------------------------------
# Төхөөрөмж сонгох
# ----------------------------------------------------------------------
def _input_channels(pa, index: int) -> int:
    """Тухайн дугаарын төхөөрөмж хэдэн сувгаар СОНСОЖ чадахыг буцаана."""
    try:
        info = pa.get_device_info_by_index(index)
    except Exception:  # noqa: BLE001 - дугаар хүрээнээс гарсан бол PyAudio шиднэ
        return 0
    try:
        return int(info.get("maxInputChannels", 0))
    except (TypeError, ValueError):
        return 0


def _device_name(pa, index: int) -> str:
    try:
        return str(pa.get_device_info_by_index(index).get("name", ""))
    except Exception:  # noqa: BLE001
        return ""


def resolve_input_device(pa, index: int | None, name: str = "") -> int | None:
    """Хадгалсан дугаарыг ОДООГИЙН төхөөрөмжийн жагсаалттай тааруулна.

    PyAudio-ийн дугаар нь тогтвортой биш: чихэвч салгаж холбоход жагсаалт
    шинэчлэгдэж, өчигдрийн «1» өнөөдөр өөр төхөөрөмж — эсвэл огт сонсдоггүй
    чанга яригч — болно. Тэр дугаараар нээхэд PortAudio нь «Invalid number of
    channels» (-9998) гэж шиднэ: сонсох суваг нь тэг учраас. Хэрэглэгчийн хувьд
    энэ нь «микрофон гэнэт ажиллахаа больсон» гэсэн үг.

    Иймд нэрээр нь дахин олно, олдохгүй бол системийн үндсэн микрофон руу
    (`None`) буцна — ажиллахгүй байхаас өөр микрофоноор ажилласан нь дээр.
    """
    if index is None or index < 0:
        return None
    if _input_channels(pa, index) >= CHANNELS and (
        not name or _device_name(pa, index) == name
    ):
        return index

    if name:
        try:
            count = pa.get_device_count()
        except Exception:  # noqa: BLE001
            count = 0
        for i in range(count):
            if _input_channels(pa, i) >= CHANNELS and _device_name(pa, i) == name:
                return i
    return None


def input_device_name(index: int) -> str:
    """Дугаараар нь төхөөрөмжийн нэрийг олно (тохиргоонд хадгалахад)."""
    if index is None or index < 0:
        return ""
    try:
        pa = pyaudio.PyAudio()
    except Exception:  # noqa: BLE001
        return ""
    try:
        return _device_name(pa, index)
    finally:
        try:
            pa.terminate()
        except Exception:  # noqa: BLE001
            pass


# Дуу цэгцлэх
TRIM_PADDING = 0.12  # эхэнд үлдээх зай
TRIM_TAIL_PADDING = 0.30  # төгсгөлд үлдээх зай (сүүлчийн үгийг хамгаална)
TRIM_TAIL_RATIO = 0.5  # төгсгөлийг илрүүлэх босгыг ийм хувиар бууруулна
TARGET_PEAK = 23000  # ~-3 dBFS (16 битийн дээд утга 32767)
MAX_GAIN = 8.0


def _rms_python(chunk: bytes) -> float:
    """16 бит PCM хэсгийн дундаж чанга байдал (цэвэр Python)."""
    if not chunk:
        return 0.0
    samples = array.array("h")
    samples.frombytes(chunk[: len(chunk) - (len(chunk) % 2)])
    if not samples:
        return 0.0
    total = 0
    for value in samples:
        total += value * value
    return math.sqrt(total / len(samples))


def _rms_audioop(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    return float(audioop.rms(chunk[: len(chunk) - (len(chunk) % 2)], BYTES_PER_SAMPLE))


# `audioop` нь C хэл дээр бичигдсэн тул хэдэн арав дахин хурдан. Python 3.13-аас
# стандарт сангаас хасагдсан тул байхгүй бол Python хувилбар руу буцна.
rms = _rms_audioop if audioop is not None else _rms_python


# ----------------------------------------------------------------------
# Дуу цэгцлэх (цэвэр функцууд — микрофон шаардахгүй)
# ----------------------------------------------------------------------
def remove_dc(samples: array.array) -> array.array:
    """Тогтмол хазайлтыг арилгана."""
    if not samples:
        return samples
    mean = sum(samples) / len(samples)
    if abs(mean) < 1:
        return samples
    shift = int(round(mean))
    return array.array("h", (max(-32768, min(32767, value - shift)) for value in samples))


def trim_silence(samples: array.array, rate: int, threshold: float) -> array.array:
    """Эхлэл, төгсгөлийн чимээгүйг тайрна.

    Сүүл тал дээр илүү болгоомжтой: намуухан дуугаар төгсдөг үг (жишээ нь
    "…аа", "…юм") тайрагдвал сүүлчийн үг алга болно. Иймд төгсгөлд босгыг
    бууруулж, зайг нь ихэсгэсэн.
    """
    window = max(1, rate // 50)  # 20 мс
    head_padding = int(rate * TRIM_PADDING)
    tail_padding = int(rate * TRIM_TAIL_PADDING)
    tail_threshold = threshold * TRIM_TAIL_RATIO

    def level(index: int) -> float:
        block = samples[index : index + window]
        if not block:
            return 0.0
        total = 0
        for value in block:
            total += value * value
        return math.sqrt(total / len(block))

    start = 0
    while start + window < len(samples) and level(start) < threshold:
        start += window
    end = len(samples) - window
    while end > start and level(end) < tail_threshold:
        end -= window

    start = max(0, start - head_padding)
    end = min(len(samples), end + window + tail_padding)
    if end <= start:
        return samples
    return samples[start:end]


def normalize(samples: array.array) -> array.array:
    """Хамгийн чанга цэгийг зорилтот түвшинд хүргэж өсгөнө."""
    if not samples:
        return samples
    peak = max(abs(value) for value in samples)
    if peak == 0:
        return samples
    gain = min(MAX_GAIN, TARGET_PEAK / peak)
    if gain <= 1.05:  # аль хэдийн хангалттай чанга
        return samples
    return array.array(
        "h", (max(-32768, min(32767, int(value * gain))) for value in samples)
    )


def prepare_segment(pcm: bytes, rate: int = RATE, threshold: float = MIN_THRESHOLD) -> bytes:
    """Илгээхийн өмнө: хазайлт арилгах → чимээгүй тайрах → түвшин жигдрүүлэх.

    Илгээх хэмжээ багасаж, сул бичлэгийн танилт мэдэгдэхүйц сайжирдаг.
    """
    if not pcm:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    if not samples:
        return pcm
    samples = remove_dc(samples)
    samples = trim_silence(samples, rate, threshold)
    samples = normalize(samples)
    return samples.tobytes()


class Segmenter:
    """Дууны хэсгүүдийг өгүүлбэр болгон хуваана (тусад нь шалгах боломжтой)."""

    def __init__(
        self,
        rate: int = RATE,
        silence_hold: float = SILENCE_HOLD,
        min_speech: float = MIN_SPEECH,
        max_segment: float = MAX_SEGMENT,
    ) -> None:
        self.rate = rate
        self.silence_hold = silence_hold
        self.min_speech = min_speech
        self.max_segment = max_segment
        self.reset()

    def reset(self) -> None:
        self._frames: list[bytes] = []
        self._levels: list[float] = []
        self._threshold = MIN_THRESHOLD
        self._noise_frames: list[float] = []
        self._noise_done = False
        self._speech_seconds = 0.0
        self._silence_seconds = 0.0
        self._segment_seconds = 0.0

    @property
    def threshold(self) -> float:
        return self._threshold

    def _chunk_seconds(self, chunk: bytes) -> float:
        return len(chunk) / (self.rate * BYTES_PER_SAMPLE)

    def feed(self, chunk: bytes) -> bytes | None:
        """Хэсэг нэмнэ. Өгүүлбэр дуусвал түүний PCM-ийг буцаана."""
        seconds = self._chunk_seconds(chunk)
        level = rms(chunk)
        self._frames.append(chunk)
        self._levels.append(level)
        self._segment_seconds += seconds

        if not self._noise_done:
            self._noise_frames.append(level)
            if self._segment_seconds >= NOISE_SAMPLE:
                # Дунджаас илүү хамгийн намхан хэсгийг авна — яриан дунд ч
                # чимээгүй завсар олдох магадлалтай
                ambient = min(self._noise_frames)
                self._threshold = min(
                    NOISE_CEILING, max(MIN_THRESHOLD, ambient * 2.5)
                )
                self._noise_done = True

        if level >= self._threshold:
            self._speech_seconds += seconds
            self._silence_seconds = 0.0
        else:
            self._silence_seconds += seconds
            self._maybe_recalibrate()

        long_enough = self._speech_seconds >= self.min_speech
        if long_enough and self._silence_seconds >= self.silence_hold:
            return self.flush()
        if self._segment_seconds >= self.max_segment and long_enough:
            return self._cut_at_quietest()
        return None

    def _maybe_recalibrate(self) -> None:
        """Босго хэт өндөр тогтсоныг өөрөө засна.

        Хангалттай хугацаанд яриа огт олдохгүй байхад дуу нь мэдэгдэхүйц чанга
        байвал хэмжилт буруу байсан гэж үзэж, ажигласан хамгийн чанга дууны
        хувиар босгыг дахин тогтооно.
        """
        if self._speech_seconds > 0 or self._segment_seconds < RECALIBRATE_AFTER:
            return
        loudest = max(self._levels, default=0.0)
        if loudest < MIN_THRESHOLD * 1.5:
            return  # үнэхээр чимээгүй байна — хөндөх шаардлагагүй
        # Анхаар: "хамгийн чанга дуу нь босгоос доогуур" гэдэг нь яг л буруу
        # тогтсон босгын шинж тул үүнийг зогсоох болзол болгож болохгүй.
        self._threshold = max(MIN_THRESHOLD, loudest * RECALIBRATE_RATIO)
        # Хуримтлагдсан хэсгүүдийг шинэ босгоор дахин тоолно
        self._speech_seconds = 0.0
        self._silence_seconds = 0.0
        chunk_seconds = self._segment_seconds / max(1, len(self._levels))
        for level in self._levels:
            if level >= self._threshold:
                self._speech_seconds += chunk_seconds
                self._silence_seconds = 0.0
            else:
                self._silence_seconds += chunk_seconds

    def _cut_at_quietest(self) -> bytes | None:
        """Хэт урт болсныг сүүлийн секундын хамгийн чимээгүй цэг дээр тасална.

        Шууд таславал үг дундуур тасарч, хоёр хэсэг хоёулаа буруу танигдана.
        """
        chunks_per_second = max(1, int(self.rate * BYTES_PER_SAMPLE / len(self._frames[0])))
        tail = min(len(self._levels) - 1, chunks_per_second)
        if tail <= 1:
            return self.flush()
        window = self._levels[-tail:]
        quietest = min(range(len(window)), key=lambda i: window[i])
        cut = len(self._frames) - tail + quietest + 1

        head, rest = self._frames[:cut], self._frames[cut:]
        rest_levels = self._levels[cut:]
        pcm = b"".join(head)

        # Үлдсэн хэсгийг шинэ сегментийн эхлэл болгож үргэлжлүүлнэ
        threshold, noise_done = self._threshold, self._noise_done
        self.reset()
        self._threshold, self._noise_done = threshold, noise_done
        self._frames = rest
        self._levels = rest_levels
        for level, chunk in zip(rest_levels, rest):
            seconds = self._chunk_seconds(chunk)
            self._segment_seconds += seconds
            if level >= threshold:
                self._speech_seconds += seconds
                self._silence_seconds = 0.0
            else:
                self._silence_seconds += seconds
        return pcm

    def flush(self, final: bool = False) -> bytes | None:
        """Хуримтлагдсан хэсгийг гаргаж, шинээр эхэлнэ.

        `final=True` нь товч суллах үед — тэр үед богино үгийг ч хаяхгүй.
        """
        floor = FINAL_MIN_SPEECH if final else self.min_speech
        pcm = b"".join(self._frames) if self._speech_seconds >= floor else None
        threshold = self._threshold
        noise_done = self._noise_done
        self.reset()
        # Орчны чимээний хэмжилтийг дахин хийхгүй — нэг удаа хангалттай
        self._threshold = threshold
        self._noise_done = noise_done
        return pcm


class Recorder:
    """Микрофоныг асааж, өгүүлбэр бүрийг callback руу дамжуулна.

    Микрофоны урсгалыг нээснээс хойш эхний дуу ирэх хүртэл ~0.7 секунд болдог
    (ялангуяа Bluetooth чихэвч). Тиймээс бичлэг зогссоны дараа урсгалыг богино
    хугацаанд нээлттэй үлдээж, дараалсан бичилтүүд шууд эхэлдэг болгосон.
    Тэр хугацаанд Windows-ийн "микрофон ашиглаж байна" заалт асаалттай хэвээр
    байх тул хугацааг тохиргооноос багасгах, эсвэл 0 болгож огт унтраах боломжтой.
    """

    def __init__(
        self,
        on_segment,
        on_level=None,
        on_error=None,
        device_index: int | None = None,
        device_name: str = "",
        max_seconds: float = 300.0,
        silence_hold: float = SILENCE_HOLD,
        keep_open_seconds: float = 45.0,
    ) -> None:
        self.on_segment = on_segment
        self.on_level = on_level
        self.on_error = on_error
        self.device_index = device_index
        self.device_name = device_name
        # Хамгийн сүүлд ҮНЭХЭЭР нээгдсэн дугаар (лог, оношилгоонд)
        self.active_index: int | None = device_index
        self.max_seconds = max_seconds
        self.keep_open_seconds = keep_open_seconds
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._capturing = threading.Event()
        self._seg_lock = threading.Lock()
        # Унших thread гарах шийдвэр ба `start()`-ын "дулаан уу" шалгалтыг
        # хооронд нь оруулахгүй байлгах түгжээ
        self._state_lock = threading.Lock()
        self._exiting = False
        self._idle_since = 0.0
        self.segmenter = Segmenter(silence_hold=silence_hold)
        self.started_at = 0.0
        self.session_peak = 0.0

    @property
    def active(self) -> bool:
        """Яг одоо бичиж байгаа эсэх."""
        return self._capturing.is_set()

    @property
    def stream_open(self) -> bool:
        """Микрофон нээлттэй байгаа эсэх (бичиж байгаа эсэхээс үл хамааран)."""
        return bool(self._thread and self._thread.is_alive())

    # ------------------------------------------------------------------
    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        """PyAudio-ийн техникийн алдааг ойлгомжтой болгоно."""
        text = str(exc).lower()
        if "no default input" in text or "invalid input device" in text:
            return "Микрофон олдсонгүй — чихэвч/микрофоноо холбоод дахин оролдоно уу."
        if "device unavailable" in text or "invalid device" in text:
            return "Сонгосон микрофон боломжгүй байна — Тохиргооноос өөрийг сонгоно уу."
        if "access" in text or "denied" in text:
            return "Микрофон ашиглах зөвшөөрөл алга — Windows-ийн Нууцлалын тохиргоог шалгана уу."
        # -9998: сонгосон төхөөрөмж нь сонсдоггүй (чихэвч салсан, дугаар хуучирсан)
        if "number of channels" in text:
            return "Микрофон олдсонгүй — чихэвч/микрофоноо холбоод дахин оролдоно уу."
        return f"Микрофон нээгдсэнгүй: {exc}"

    def _open(self, index: int | None):
        return self._pa.open(
            format=FORMAT,
            channels=CHANNELS,
            rate=RATE,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=index,
        )

    def _open_stream(self) -> str | None:
        try:
            self._pa = pyaudio.PyAudio()
        except Exception as exc:  # noqa: BLE001 - PyAudio янз бүрийн алдаа шиднэ
            self._cleanup()
            return self._friendly_error(exc)

        index = resolve_input_device(self._pa, self.device_index, self.device_name)
        if index != self.device_index:
            log.warning(
                "сонгосон микрофон (%s «%s») олдсонгүй — %s руу шилжлээ",
                self.device_index,
                self.device_name,
                "системийн үндсэн" if index is None else index,
            )
        try:
            self._stream = self._open(index)
        except Exception as exc:  # noqa: BLE001
            if index is None:
                self._cleanup()
                return self._friendly_error(exc)
            # Жагсаалт зөв мэдээлсэн ч нээлт бүтсэнгүй: системийн үндсэнээр
            # сүүлчийн оролдлого хийнэ — огт бичихгүй байхаас арай дээр.
            log.warning("микрофон %s нээгдсэнгүй (%s) — үндсэнээр оролдож байна", index, exc)
            try:
                self._stream = self._open(None)
            except Exception:  # noqa: BLE001
                self._cleanup()
                return self._friendly_error(exc)
            index = None
        self.active_index = index
        return None

    def start(self) -> str | None:
        """Бичиж эхэлнэ. Алдаа гарвал мессежийг буцаана."""
        if self.active:
            return None
        with self._seg_lock:
            self.segmenter.reset()
        self.started_at = time.monotonic()
        self.session_peak = 0.0

        # Урсгал нээлттэй байвал шууд эхэлнэ. Гэхдээ яг энэ агшинд сул
        # зогсолтын хугацаа дуусаж, унших thread гарахаар шийдсэн байж болно.
        # Тэр шийдвэр ба энэ шалгалт нэг түгжээн дор явснаар "бичиж эхэлсэн
        # мэт харагдаад дуу огт ирэхгүй" гэсэн байдал үүсэхгүй.
        with self._state_lock:
            warm = self.stream_open and not self._exiting
            self._capturing.set()
            if warm:
                log.info("бичлэг эхэллээ (төхөөрөмж=%s, бэлэн=True)", self.active_index)
                return None
            self._exiting = False

        if self._thread:
            self.close()  # гарах шатанд байсан thread-ийг цэвэрлэнэ
            self._capturing.set()
        error = self._open_stream()
        if error:
            self._capturing.clear()
            log.warning("микрофон нээгдсэнгүй: %s", error)
            return error
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        log.info("бичлэг эхэллээ (төхөөрөмж=%s, бэлэн=False)", self.active_index)
        return None

    def stop(self) -> None:
        """Бичихээ болино. Үлдсэн хэсгийг сүүлчийн өгүүлбэр болгож илгээнэ."""
        if not self._capturing.is_set():
            return
        self._capturing.clear()
        self._idle_since = time.monotonic()
        with self._seg_lock:
            final = self.segmenter.flush(final=True)
        if final:
            self.on_segment(final, True)
        log.info("бичлэг зогслоо (%.1f сек)", time.monotonic() - self.started_at)
        if self.keep_open_seconds <= 0:
            self.close()

    def close(self) -> None:
        """Микрофоныг бүрэн суллана."""
        if not self._thread:
            return
        self._capturing.clear()
        self._stop.set()
        self._thread.join(timeout=2.0)
        self._thread = None
        with self._state_lock:
            self._exiting = False
        # Thread хугацаандаа гараагүй бол өөрөө цэвэрлэж амжаагүй байж болно
        self._cleanup()
        log.info("микрофон суллагдлаа")

    # ------------------------------------------------------------------
    def _fail(self, message: str) -> None:
        log.error("%s", message)
        if self.on_error:
            self.on_error(message)

    def _read_chunk(self) -> bytes | None:
        """Хэсэг уншина. Төхөөрөмж салсан бол нэг удаа дахин нээхийг оролдоно."""
        try:
            return self._stream.read(CHUNK, exception_on_overflow=False)
        except Exception as exc:  # noqa: BLE001
            log.warning("микрофон уншилт тасарлаа: %s — дахин нээж байна", exc)
            self._cleanup()
            if self._open_stream() is None:
                try:
                    return self._stream.read(CHUNK, exception_on_overflow=False)
                except Exception:  # noqa: BLE001
                    pass
            # Бичихгүй байхад төхөөрөмж салсан бол чимээгүй хаана — хэрэглэгчийг
            # хамаагүй анхааруулга харуулж төвөг удахгүй
            if self._capturing.is_set():
                self._fail("Микрофонтой холбоо тасарлаа. Төхөөрөмжөө шалгана уу.")
            else:
                log.info("сул зогсолтын үед микрофон салсан тул хаалаа")
            return None

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                chunk = self._read_chunk()
                if chunk is None:
                    return  # алдааг аль хэдийн мэдэгдсэн

                if not self._capturing.is_set():
                    # Бичихгүй байгаа ч урсгалыг сорсоор байна: буфер цэвэр
                    # байж, дараагийн бичлэг тэр дор нь эхэлнэ.
                    if (
                        self.keep_open_seconds > 0
                        and time.monotonic() - self._idle_since > self.keep_open_seconds
                    ):
                        with self._state_lock:
                            if self._capturing.is_set():
                                continue  # яг одоо дахин эхэлчихлээ
                            self._exiting = True
                        log.info("микрофоныг ашиглаагүй тул хаалаа")
                        return
                    continue

                level = rms(chunk)
                self.session_peak = max(self.session_peak, level)
                if self.on_level:
                    self.on_level(level)
                with self._seg_lock:
                    segment = self.segmenter.feed(chunk)
                if segment:
                    self.on_segment(segment, False)
                if time.monotonic() - self.started_at > self.max_seconds:
                    self._capturing.clear()
                    with self._seg_lock:
                        final = self.segmenter.flush(final=True)
                    if final:
                        self.on_segment(final, True)
                    self._fail(
                        f"Бичлэг {int(self.max_seconds / 60)} минут үргэлжилсэн тул зогслоо."
                    )
                    return
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:  # noqa: BLE001
                pass
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:  # noqa: BLE001
                pass
            self._pa = None
