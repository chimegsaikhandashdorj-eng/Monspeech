"""Микрофоноос шууд дуу авах.

Хөтөч ашиглахгүй — PyAudio-гоор 16 кГц, моно, 16 бит PCM цуглуулж,
чимээгүй завсраар нь өгүүлбэр болгон тасалж дамжуулна.
"""

from __future__ import annotations

import array
import math
import threading
import time
from collections import deque

try:  # Python 3.13-д стандарт сангаас хасагдсан
    import audioop
except ImportError:  # pragma: no cover - хувилбараас хамаарна
    audioop = None

from . import mics, vad
from .logging_setup import get as get_logger
from .mics import Mic

# Аль PyAudio ашиглахыг `mics` шийднэ (loopback дэмждэг хувилбар байвал тэр).
pyaudio = mics.pyaudio

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
# Товч суллах агшинд микрофоны буферт унших гараагүй хэсэг үлддэг (`read()` нь
# CHUNK бүрдэх хүртэл хүлээдэг тул үргэлж 1-2 хэсэг хоцордог). Тэр нь яг
# хэлсэн зүйлийн сүүлчийн үе байдаг учир хаявал «…юм», «…уу» алга болно.
# Тиймээс суллагдсаны дараа буферийг соруулж, дээр нь жаахан хүлээж авна.
FINAL_DRAIN_SECONDS = 0.35
# Товч дарахаас өмнөх дууг ийм удаан хугацаагаар санана. Хүн товчоо дармагц
# ярьдаггүй — эсрэгээрээ ярьж эхлээд дарах нь элбэг. Хэт урт болговол товч
# дарахаас нэлээд өмнөх (өөр хүнтэй ярьсан) яриа орж ирэх эрсдэлтэй.
PREROLL_SECONDS = 0.6
NOISE_SAMPLE = 0.25  # эхний хэсгээр орчны чимээг хэмжинэ
MIN_THRESHOLD = 320.0
# Орчны чимээний хэмжилтээс гарах босгын дээд хязгаар. Хэрэглэгч товч дармагцаа
# ярьж эхэлбэл хэмжилт нь ЯРИАН дээр тохирч, босго асар өндөр болоод бүх яриаг
# "чимээгүй" гэж үзэн чимээгүйгээр хаядаг байсан.
NOISE_CEILING = 2500.0
# Буруу хэмжилтийг өөрөө засах: ийм удаан яриа олдохгүй байвал босгыг буулгана
RECALIBRATE_AFTER = 1.4
RECALIBRATE_RATIO = 0.35

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
SAMPLE_MAX = 32767
SAMPLE_MIN = -32768


def _from_bytes(raw: bytes) -> array.array:
    out = array.array("h")
    out.frombytes(raw)
    return out


def _remove_dc_python(samples: array.array) -> array.array:
    mean = sum(samples) / len(samples)
    if abs(mean) < 1:
        return samples
    shift = int(round(mean))
    return array.array(
        "h", (max(SAMPLE_MIN, min(SAMPLE_MAX, value - shift)) for value in samples)
    )


def _remove_dc_audioop(samples: array.array) -> array.array:
    raw = samples.tobytes()
    shift = audioop.avg(raw, BYTES_PER_SAMPLE)
    if abs(shift) < 1:
        return samples
    # `audioop.bias` нь халихдаа КЛИП хийхгүй, тойрч эргэдэг: +32767 дээр
    # нэмэхэд -32768 болно — сонсогдохоор шаржигнуур үүснэ. Тиймээс эргэлт
    # үүсэх боломжгүй нь батлагдсан үед л ашиглана.
    if audioop.max(raw, BYTES_PER_SAMPLE) + abs(shift) <= SAMPLE_MAX:
        return _from_bytes(audioop.bias(raw, BYTES_PER_SAMPLE, -shift))
    return _remove_dc_python(samples)


def remove_dc(samples: array.array) -> array.array:
    """Тогтмол хазайлтыг арилгана."""
    if not samples:
        return samples
    return _remove_dc(samples)


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


def _gain_for(peak: int) -> float:
    """Дээд цэгийг зорилтот түвшинд хүргэх өсгөлт (1.0 бол хөндөх шаардлагагүй)."""
    if peak == 0:
        return 1.0
    gain = min(MAX_GAIN, TARGET_PEAK / peak)
    return gain if gain > 1.05 else 1.0  # аль хэдийн хангалттай чанга


def _normalize_python(samples: array.array) -> array.array:
    gain = _gain_for(max(abs(value) for value in samples))
    if gain == 1.0:
        return samples
    return array.array(
        "h", (max(SAMPLE_MIN, min(SAMPLE_MAX, int(value * gain))) for value in samples)
    )


def _normalize_audioop(samples: array.array) -> array.array:
    raw = samples.tobytes()
    gain = _gain_for(audioop.max(raw, BYTES_PER_SAMPLE))
    if gain == 1.0:
        return samples
    # `mul` нь `bias`-аас ялгаатай нь халилтыг клип хийдэг. Гэхдээ өсгөлтийг
    # дээд цэгээр нь тооцсон тул халилт үүсэхгүй ч байх ёстой.
    return _from_bytes(audioop.mul(raw, BYTES_PER_SAMPLE, gain))


def normalize(samples: array.array) -> array.array:
    """Хамгийн чанга цэгийг зорилтот түвшинд хүргэж өсгөнө."""
    if not samples:
        return samples
    return _normalize(samples)


# `rms`-ийн адил: C хувилбар байвал түүнийг, эс бөгөөс цэвэр Python-ыг.
# Хэмжсэн ялгаа нь жижиг биш — 10 секундын дуунд `normalize` ганцаараа
# ~90 мс иддэг байсан бол C дээр нэг мс хүрэхгүй. Энэ хугацаа бүхэлдээ
# хэрэглэгчийн товч суллахаас текст гарах хүртэлх хүлээлт дээр нэмэгддэг.
_remove_dc = _remove_dc_audioop if audioop is not None else _remove_dc_python
_normalize = _normalize_audioop if audioop is not None else _normalize_python


#: Доод давтамжийн шүүлтүүрийн зогсоох давтамж (Гц). Хүний яриа ~85 Гц-ээс
#: эхэлдэг; сэнс, кондиционер, ширээний цохилт, салхи нь үүнээс доогуур.
HIGHPASS_HZ = 90.0
#: Чимээний түвшинг ийм хэсгээс (хамгийн намуухан 20%) хэмжинэ.
NOISE_FLOOR_RATIO = 0.2
#: Чимээ гэж үзэх хязгаар: түвшин нь чимээний түвшний ийм дахинаас доогуур
#: хэсгийг сулруулна. Хэт өндөр болговол намуухан үг иднэ.
GATE_RATIO = 1.6
#: Сулруулах хэмжээ (0 = бүрэн чимээгүй). Бүрэн таслахгүй: танигч огт
#: чимээгүй хэсгийг «хугарсан бичлэг» гэж үзэх эрсдэлтэй.
GATE_FLOOR = 0.25
#: Гэнэт унтраахгүй, ийм олон хэсэгт жигд шилжинэ (зөөлөн шилжилт).
GATE_FRAME = 160  # 10 мс @ 16 кГц
#: Хүрээ хооронд ямар хурдтай шилжих вэ (1.0 = тэр дороо). Хэт хурдан бол
#: үгийн эхлэл тайрагдана, хэт удаан бол чимээ нэвтэрнэ.
GATE_SLEW = 0.35


def highpass(
    samples: array.array, rate: int, cutoff: float = HIGHPASS_HZ, stages: int = 2
) -> array.array:
    """Доод давтамж таслах шүүлтүүр (нэг туйлт, `stages` удаа дараалуулсан).

    Сэнс, кондиционерын гүнгэнээ нь ярианы давтамжид ордоггүй ч түвшин
    хэмжилтийг гажуудуулж, танигчид ч саад болдог. Хоёр шат нь 50 Гц-ийг
    ~12 дБ-ээр дарж, 1 кГц-ийг бараг хөндөхгүй (хэмжсэн). Хоёр шатыг НЭГ
    дамжуулалтад хийнэ — 1 секунд дуунд ~7 мс.
    """
    if not samples or rate <= 0 or stages < 1:
        return samples
    # y[n] = a * (y[n-1] + x[n] - x[n-1])
    alpha = 1.0 / (1.0 + (2.0 * math.pi * cutoff / rate))
    out = array.array("h", bytes(len(samples) * 2))
    previous_in = [0.0] * stages
    previous_out = [0.0] * stages
    for index, value in enumerate(samples):
        current = float(value)
        for stage in range(stages):
            filtered = alpha * (previous_out[stage] + current - previous_in[stage])
            previous_in[stage] = current
            previous_out[stage] = filtered
            current = filtered
        out[index] = _clip(current)
    return out


def _clip(value: float) -> int:
    if value > 32767:
        return 32767
    if value < -32768:
        return -32768
    return int(value)


def noise_gate(
    samples: array.array,
    frame: int = GATE_FRAME,
    ratio: float = GATE_RATIO,
    floor: float = GATE_FLOOR,
) -> array.array:
    """Ярианы хооронд үлдэх тогтмол хишиг, шуугианыг сулруулна.

    Чимээний түвшинг бичлэгийн ХАМГИЙН НАМУУХАН хэсгүүдээс хэмжинэ — ингэснээр
    орчин бүрд өөрөө тохирно. Босгоос доогуур хэсгийг бүрэн таслахгүй, зөвхөн
    сулруулна: бүтэн чимээгүй хэсэг нь зарим танигчид «тасарсан» мэт харагддаг.
    """
    if len(samples) < frame * 3:
        return samples
    raw = samples.tobytes()
    step = frame * BYTES_PER_SAMPLE
    chunks = [raw[i : i + step] for i in range(0, len(raw) - step + 1, step)]
    tail = raw[len(chunks) * step :]
    levels = [rms(chunk) for chunk in chunks]
    quiet = sorted(levels)[: max(1, int(len(levels) * NOISE_FLOOR_RATIO))]
    noise = sum(quiet) / len(quiet)
    if noise <= 0:
        return samples
    threshold = noise * ratio
    if threshold >= max(levels):
        return samples  # бүхэлдээ чимээ — таних шат нь өөрөө шийднэ

    # Хүрээ хоорондоо жигд шилжинэ («товшилт» гаргахгүй), хүрээ ДОТОР нь
    # тогтмол — ингэснээр үржүүлэлт бүрийг `audioop` C хурдаар хийнэ.
    pieces = []
    gain = 1.0
    for chunk, level in zip(chunks, levels, strict=True):
        target = 1.0 if level >= threshold else floor
        gain += (target - gain) * GATE_SLEW
        pieces.append(_scale(chunk, gain))
    out = array.array("h")
    out.frombytes(b"".join(pieces) + tail)
    return out


def _scale(chunk: bytes, gain: float) -> bytes:
    """Хэсгийн түвшинг өөрчилнө (`audioop` байвал C хурдаар)."""
    if gain >= 0.999:
        return chunk
    if audioop is not None:
        return audioop.mul(chunk, BYTES_PER_SAMPLE, gain)
    scaled = array.array("h")
    scaled.frombytes(chunk)
    for index, value in enumerate(scaled):
        scaled[index] = _clip(value * gain)
    return scaled.tobytes()


def prepare_segment(
    pcm: bytes,
    rate: int = RATE,
    threshold: float = MIN_THRESHOLD,
    denoise: bool = False,
) -> bytes:
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
    if denoise:
        # Дараалал нь чухал: эхлээд гүнгэнээг авна (түвшин хэмжилт цэвэрших),
        # дараа нь чимээг сулруулна, эцэст нь ердийн тайралт, жигдрүүлэлт.
        samples = highpass(samples, rate)
        samples = noise_gate(samples)
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
        detector=None,
    ) -> None:
        self.rate = rate
        self.silence_hold = silence_hold
        self.min_speech = min_speech
        self.max_segment = max_segment
        # Ярианы илрүүлэгч (`vad.create()`). `None` бол түвшингийн зам —
        # энэ ангийн бусад бүх логик (чимээгүйн хүлээлт, богиныг хаях, урт
        # сегментийг таслах) хоёр тохиолдолд ЯГ ижил ажиллана: илрүүлэгч нь
        # зөвхөн «энэ уншилт дуутай юу» гэсэн НЭГ асуултыг орлоно.
        self.detector = detector
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
        if self.detector is not None:
            # Дуусаагүй фрэйм өмнөх сегментээс дараагийнх руу дуслахгүй
            self.detector.reset()

    @property
    def threshold(self) -> float:
        return self._threshold

    def _chunk_seconds(self, chunk: bytes) -> float:
        return len(chunk) / (self.rate * BYTES_PER_SAMPLE)

    def _voiced(self, chunk: bytes, level: float) -> bool:
        """Уншилт дуутай эсэх — илрүүлэгч байвал түүнээр, эс бөгөөс түвшингээр.

        Илрүүлэгч `None` буцаах нь «мэдэхгүй» (бүтэн фрэйм бүрдээгүй) гэсэн
        үг тул тэр үед ч түвшин рүү унана — шийдвэргүй уншилт байх ёсгүй.
        """
        if self.detector is not None:
            voiced = self.detector.feed(chunk)
            if voiced is not None:
                return voiced
        return level >= self._threshold

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

        if self._voiced(chunk, level):
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
        if self.detector is not None:
            # Дахин тохируулга нь БУРУУ тогтсон түвшингийн босгыг засах арга.
            # Илрүүлэгч босго огт хэрэглэдэггүй тул энд засах зүйл байхгүй —
            # харин ч чимээг «яриа» болгож дэвшүүлэх эрсдэлтэй.
            return
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
        for level, chunk in zip(rest_levels, rest, strict=True):
            seconds = self._chunk_seconds(chunk)
            self._segment_seconds += seconds
            if self._voiced(chunk, level):
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


def _new_pyaudio():
    """PyAudio үүсгэх ЦОРЫН ГАНЦ газар.

    Тест энд өөрийн хуурамчийг тавьж, микрофонгүйгээр нөөц замыг (сонголт
    олдохгүй → үндсэн рүү) шалгана. Эс бөгөөс тэр зам зөвхөн жинхэнэ чихэвч
    салгаж байж шалгагдана — өөрөөр хэлбэл хэзээ ч шалгагдахгүй.
    """
    return pyaudio.PyAudio()


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
        mic: Mic = mics.SYSTEM,
        max_seconds: float = 300.0,
        silence_hold: float = SILENCE_HOLD,
        keep_open_seconds: float = 45.0,
        preroll_seconds: float = PREROLL_SECONDS,
        vad_enabled: bool = True,
    ) -> None:
        self.on_segment = on_segment
        self.on_level = on_level
        self.on_error = on_error
        self.mic = mic
        # Хамгийн сүүлд нээхээр оролдсон дугаар (`None` = системийн үндсэн).
        # Урсгал нээлттэй үед л утга нь үнэн — `stream_open`-той хамт уншина.
        self.active_index: int | None = None
        self.max_seconds = max_seconds
        self.keep_open_seconds = keep_open_seconds
        # Товч дарахаас ӨМНӨХ хэдэн зуун мс. Микрофон бэлэн байх зуур уншсан
        # хэсгүүдийг хаялгүй энд хураана — товч дарж амжаагүй эхэлсэн үг
        # ингэснээр аврагдана.
        self.preroll_seconds = preroll_seconds
        self._preroll: deque[bytes] = deque()
        self._pa: pyaudio.PyAudio | None = None
        self._stream = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._capturing = threading.Event()
        # «Товч суллагдсан, үлдсэн дууг цуглуулж дуусга» гэсэн дохио. Унших
        # thread үүнийг хараад өөрөө төгсгөнө — `stop()` хүлээхгүй.
        self._finishing = threading.Event()
        self._seg_lock = threading.Lock()
        # Унших thread гарах шийдвэр ба `start()`-ын "дулаан уу" шалгалтыг
        # хооронд нь оруулахгүй байлгах түгжээ
        self._state_lock = threading.Lock()
        self._exiting = False
        self._idle_since = 0.0
        # Эх төхөөрөмжийн формат (loopback нь 48 кГц стерео байдаг). Уншсаны
        # дараа дамжлагын 16 кГц моно руу өөрсдөө хөрвүүлнэ.
        self._source_channels = CHANNELS
        self._source_rate = RATE
        self._resample_state = None
        # Уншсаныг ҮРГЭЛЖ 16 кГц моно болгодог (`_to_pipeline_format`) тул
        # илрүүлэгчид өгөх давтамж нь төхөөрөмжийнхөөс үл хамаарна.
        self.segmenter = Segmenter(
            silence_hold=silence_hold, detector=vad.create(RATE, vad_enabled)
        )
        self.started_at = 0.0
        self.session_peak = 0.0

    def set_vad(self, enabled: bool) -> None:
        """Илрүүлэгчийг ажиллаж байх зуур асаах/унтраана.

        Чагт бүр тэр дороо үйлчлэх ёстой тул аппыг дахин эхлүүлэх шалтгаан
        болгож болохгүй. Сегментийн түгжээн дор солино — унших thread яг тэр
        агшинд хагас солигдсон илрүүлэгч рүү хандахгүй.
        """
        with self._seg_lock:
            self.segmenter.detector = vad.create(RATE, enabled)

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
        # «number of channels» нь -9998: сонсох суваггүй төхөөрөмж рүү хандсан
        # — чихэвч салсан эсвэл жагсаалт хоосон гэсэн үг, өөрөөр хэлбэл
        # микрофон олдоогүйн бас нэг дүр.
        if (
            "no default input" in text
            or "invalid input device" in text
            or "number of channels" in text
        ):
            return "Микрофон олдсонгүй — чихэвч/микрофоноо холбоод дахин оролдоно уу."
        if "device unavailable" in text or "invalid device" in text:
            return "Сонгосон микрофон боломжгүй байна — Тохиргооноос өөрийг сонгоно уу."
        if "access" in text or "denied" in text:
            return "Микрофон ашиглах зөвшөөрөл алга — Windows-ийн Нууцлалын тохиргоог шалгана уу."
        return f"Микрофон нээгдсэнгүй: {exc}"

    def _device_format(self, index: int | None) -> tuple[int, int]:
        """Тухайн төхөөрөмжийг ЯМАР давтамж, суваггаар нээх вэ.

        Ердийн микрофоныг 16 кГц моногоор шууд нээнэ. Харин WASAPI loopback
        (системийн дуу) нь чанга яригчийн ЯГ тэр форматаар л нээгддэг —
        ихэвчлэн 48 кГц, стерео. Тэгвэл уншсаны дараа өөрсдөө хөрвүүлнэ.
        """
        if index is None:
            return CHANNELS, RATE
        info = mics.describe(self._pa, index)
        if not mics.is_loopback_info(info):
            return CHANNELS, RATE
        channels = max(1, min(2, int(info.get("maxInputChannels") or 1)))
        rate = int(info.get("defaultSampleRate") or RATE)
        return channels, rate

    def _open_device(self, index: int | None):
        channels, rate = self._device_format(index)
        self._source_channels = channels
        self._source_rate = rate
        self._resample_state = None
        if (channels, rate) != (CHANNELS, RATE):
            log.info("төхөөрөмжийн формат: %d суваг, %d Гц — хөрвүүлнэ", channels, rate)
        return self._pa.open(
            format=FORMAT,
            channels=channels,
            rate=rate,
            input=True,
            frames_per_buffer=CHUNK,
            input_device_index=index,
        )

    def _to_pipeline_format(self, chunk: bytes) -> bytes:
        """Уншсан хэсгийг дамжлагын хүлээдэг 16 кГц моно болгоно."""
        if not chunk:
            return chunk
        if self._source_channels > 1:
            if audioop is None:  # pragma: no cover - зөвхөн шинэ Python дээр
                return chunk
            chunk = audioop.tomono(chunk, BYTES_PER_SAMPLE, 0.5, 0.5)
        if self._source_rate != RATE:
            if audioop is None:  # pragma: no cover
                return chunk
            chunk, self._resample_state = audioop.ratecv(
                chunk, BYTES_PER_SAMPLE, 1, self._source_rate, RATE, self._resample_state
            )
        return chunk

    def _open_stream(self) -> str | None:
        try:
            self._pa = _new_pyaudio()
        except Exception as exc:  # noqa: BLE001 - PyAudio янз бүрийн алдаа шиднэ
            self._cleanup()
            return self._friendly_error(exc)

        index = mics.resolve(self._pa, self.mic)
        self.active_index = index
        if not self.mic.is_default and index != self.mic.index:
            if index is None:
                log.warning(
                    "сонгосон микрофон («%s», №%s) олдсонгүй — системийн үндсэн рүү",
                    self.mic.name,
                    self.mic.index,
                )
            else:
                # Олдсон. Зөвхөн дугаар нь шилжсэн — «олдсонгүй» гэж бичвэл
                # дараагийн удаа логыг уншиж буй хүнийг төөрөгдүүлнэ.
                log.info(
                    "«%s» микрофон №%s → №%s болж шилжжээ",
                    self.mic.name,
                    self.mic.index,
                    index,
                )
        try:
            self._stream = self._open_device(index)
        except Exception as exc:  # noqa: BLE001
            if index is None:
                self.active_index = None
                self._cleanup()
                return self._friendly_error(exc)
            # Жагсаалт зөв мэдээлсэн ч нээлт бүтсэнгүй: системийн үндсэнээр
            # сүүлчийн оролдлого хийнэ — огт бичихгүй байхаас арай дээр.
            log.warning("микрофон %s нээгдсэнгүй (%s) — үндсэнээр оролдож байна", index, exc)
            try:
                self._stream = self._open_device(None)
            except Exception:  # noqa: BLE001
                self.active_index = None
                self._cleanup()
                return self._friendly_error(exc)
            self.active_index = None
        return None

    def start(self) -> str | None:
        """Бичиж эхэлнэ. Алдаа гарвал мессежийг буцаана."""
        # Өмнөх бичлэгийн ТӨГСГӨЛ хараахан дуусаагүй байж болно: `stop()` нь
        # хүлээлгүй буцдаг тул тэр үед `_capturing` асаалттай хэвээр байна.
        # Зөвхөн `active`-ийг харвал «аль хэдийн бичиж байна» гэж андуурч
        # чимээгүй юу ч хийхгүй өнгөрнө — дараа нь `_finish_capture` төлвийг
        # хааж, хэрэглэгчийн хэлсэн зүйл бүхэлдээ алга болно.
        if self.active and not self._finishing.is_set():
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
            # Өмнөх бичлэгийн төгсгөл хараахан дуусаагүй байж болно. Дохиог
            # цуцлавал тэр нь шинэ бичлэгийг таслахгүйгээр өнгөрнө.
            self._finishing.clear()
            # Урьдчилсан дууг `_capturing`-аас ӨМНӨ залгана — эс бөгөөс унших
            # thread шинэ хэсгийг түрүүлж оруулж, дараалал холилдоно.
            stray = self._inject_preroll() if warm else None
            self._capturing.set()
            if not warm:
                self._exiting = False
        if stray:
            # Урьдчилсан буферт бүтэн өгүүлбэр багтсан байна (яриа + чимээгүй
            # завсар). Товч дарахаас өмнө ДУУССАН яриа тул энэ бичлэгт
            # хамаарахгүй — хаяна, эс бөгөөс хэрэглэгчийн хэлээгүй зүйл орно.
            log.info("урьдчилсан буферээс өмнөх яриа олдсон тул хаялаа")
        if warm:
            log.info("бичлэг эхэллээ (төхөөрөмж=%s, бэлэн=True)", self.active_index)
            return None

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
        """Бичихээ болино. Үлдсэн хэсгийг сүүлчийн өгүүлбэр болгож илгээнэ.

        Энэ дуудлага Tk-ийн үндсэн thread дээрээс ирдэг тул **хүлээхгүй**:
        буферт хоцорсон дууг соруулах ажлыг унших thread-д даалгаад тэр дороо
        буцна. Эс бөгөөс товч суллах бүрд цонх хэдэн зуун мс царцана.
        """
        if not self._capturing.is_set():
            return
        self._finishing.set()
        if self.stream_open:
            return  # унших thread буферээ соруулаад өөрөө төгсгөнө
        # Унших thread амьд биш бол хүлээх хүн алга — энд дуусгана
        self._finish_capture()
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
            self._finishing.clear()
        # Thread хугацаандаа гараагүй бол өөрөө цэвэрлэж амжаагүй байж болно
        self._cleanup()
        log.info("микрофон суллагдлаа")

    # ------------------------------------------------------------------
    def _preroll_limit(self) -> int:
        """Урьдчилсан буферт хэдэн хэсэг багтах вэ (0 бол унтраалттай)."""
        return max(0, int(self.preroll_seconds * RATE / CHUNK))

    def _remember_preroll(self, chunk: bytes) -> None:
        """Бичихгүй байхад уншсан хэсгийг цагираг буферт хийнэ."""
        limit = self._preroll_limit()
        if limit <= 0:
            if self._preroll:
                self._preroll.clear()
            return
        self._preroll.append(chunk)
        while len(self._preroll) > limit:
            self._preroll.popleft()

    def _inject_preroll(self) -> bytes | None:
        """Хураасан хэсгүүдийг сегментчлэгчид өгнө. Гарсан сегментийг буцаана.

        Хэсэг бүрийг ТУСАД нь өгнө: сегментчлэгч эхний 0.25 секундээр орчны
        чимээг хэмждэг тул нэг том хэсэг болгож нийлүүлбэл хэмжилт эвдэрнэ.
        Эхэнд нь чимээгүй байх нь ХЭРЭГТЭЙ — тэр л жинхэнэ орчны чимээ.
        """
        # `list()` + `clear()` хийвэл яг тэр хормын унших thread-ийн `append`
        # алдагдана. `popleft` нь атомик тул юу ч гээхгүй соруулна.
        chunks: list[bytes] = []
        while True:
            try:
                chunks.append(self._preroll.popleft())
            except IndexError:
                break
        if not chunks:
            return None
        stray = None
        with self._seg_lock:
            for chunk in chunks:
                segment = self.segmenter.feed(chunk)
                if segment:
                    stray = segment
        return stray

    def _fail(self, message: str) -> None:
        log.error("%s", message)
        if self.on_error:
            self.on_error(message)

    def _read_chunk(self) -> bytes | None:
        """Хэсэг уншина. Төхөөрөмж салсан бол нэг удаа дахин нээхийг оролдоно."""
        try:
            return self._to_pipeline_format(
                self._stream.read(CHUNK, exception_on_overflow=False)
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("микрофон уншилт тасарлаа: %s — дахин нээж байна", exc)
            self._cleanup()
            if self._open_stream() is None:
                try:
                    return self._to_pipeline_format(
                        self._stream.read(CHUNK, exception_on_overflow=False)
                    )
                except Exception:  # noqa: BLE001
                    pass
            # Бичихгүй байхад төхөөрөмж салсан бол чимээгүй хаана — хэрэглэгчийг
            # хамаагүй анхааруулга харуулж төвөг удахгүй
            if self._capturing.is_set():
                self._fail("Микрофонтой холбоо тасарлаа. Төхөөрөмжөө шалгана уу.")
            else:
                log.info("сул зогсолтын үед микрофон салсан тул хаалаа")
            return None

    def _consume(self, chunk: bytes) -> None:
        """Нэг хэсгийг түвшин заалт ба сегментчлэлд дамжуулна."""
        level = rms(chunk)
        self.session_peak = max(self.session_peak, level)
        if self.on_level:
            self.on_level(level)
        with self._seg_lock:
            segment = self.segmenter.feed(chunk)
        if segment:
            self.on_segment(segment, False)

    def _drain_buffer(self) -> None:
        """Микрофоны буферт хоцорсон хэсгүүдийг сорж авна.

        Эхлээд бэлэн байгаа бүхнийг, дараа нь нэг хэсгийг НЭМЖ хүлээж уншина:
        төхөөрөмжийн саатлаас болж хамгийн сүүлчийн үе буферт хараахан
        бичигдээгүй байж болно. Нэмэлт саатал нь ~64 мс — алдагдсан үгийг
        буцааж авахын төлөө төлөх зохистой үнэ.
        """
        stream = self._stream
        if stream is None:
            return
        deadline = time.monotonic() + FINAL_DRAIN_SECONDS
        lingered = False
        while time.monotonic() < deadline:
            try:
                if stream.get_read_available() < CHUNK:
                    if lingered:
                        return
                    lingered = True  # нэг удаа хүлээж үзнэ
                chunk = self._to_pipeline_format(
                    stream.read(CHUNK, exception_on_overflow=False)
                )
            except Exception as exc:  # noqa: BLE001
                # Энд дахин нээх гэж оролдохгүй: төгсгөлийн хэдэн мс төдийд
                # төхөөрөмж сэргэхгүй, харин хэрэглэгч хүлээнэ.
                log.warning("сүүлчийн хэсгийг уншиж чадсангүй: %s", exc)
                return
            self._consume(chunk)

    def _finish_capture(self) -> None:
        """Буферээ соруулаад бичлэгийн төлөвийг хааж, сүүлчийн өгүүлбэрийг илгээнэ."""
        self._drain_buffer()
        with self._state_lock:
            if not self._finishing.is_set():
                # Энэ хооронд дахин бичиж эхэлсэн — шинэ бичлэгийг таслахгүй.
                # Соруулсан хэсэг нь шинэ сегментийн эхэнд үлдэнэ.
                return
            self._finishing.clear()
            self._capturing.clear()
        self._idle_since = time.monotonic()
        self._preroll.clear()
        with self._seg_lock:
            final = self.segmenter.flush(final=True)
        if final:
            self.on_segment(final, True)
        log.info("бичлэг зогслоо (%.1f сек)", time.monotonic() - self.started_at)

    def _loop(self) -> None:
        try:
            while not self._stop.is_set():
                chunk = self._read_chunk()
                if chunk is None:
                    return  # алдааг аль хэдийн мэдэгдсэн

                if not self._capturing.is_set():
                    # Бичихгүй байгаа ч урсгалыг сорсоор байна: буфер цэвэр
                    # байж, дараагийн бичлэг тэр дор нь эхэлнэ. Уншсан хэсгийг
                    # хаялгүй урьдчилсан буферт хураана.
                    self._remember_preroll(chunk)
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

                self._consume(chunk)
                if self._finishing.is_set():
                    # Товч суллагдсан. Буферт хоцорсон сүүлчийн үеийг соруулж
                    # авах ажил ЭНД л хийгдэнэ — `stop()` хүлээхгүй буцсан.
                    self._finish_capture()
                    if self.keep_open_seconds <= 0:
                        # Гарахаа сул зогсолтын замтай ижилхэн зарлана: эс
                        # бөгөөс яг энэ хормын `start()` нь «урсгал нээлттэй»
                        # гэж үзээд дулаан замаар буцах ба урсгал нь тэр дороо
                        # хаагдаж, дараагийн бичлэг чимээгүй хоосон гарна.
                        with self._state_lock:
                            if self._capturing.is_set():
                                continue  # яг одоо дахин эхэлчихлээ
                            self._exiting = True
                        return  # `finally` дотор урсгал хаагдана
                    continue
                if time.monotonic() - self.started_at > self.max_seconds:
                    self._finishing.set()
                    self._finish_capture()
                    self._fail(
                        f"Бичлэг {int(self.max_seconds / 60)} минут үргэлжилсэн тул зогслоо."
                    )
                    return
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        self._preroll.clear()
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
