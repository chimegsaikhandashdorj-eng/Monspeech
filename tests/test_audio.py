"""Дуу таслах логикийн тест (микрофон хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_audio.py
"""

import array
import math
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import audio as audio_module, mics
from monspeech.audio import (
    CHANNELS,
    CHUNK,
    MIN_THRESHOLD,
    NOISE_CEILING,
    RATE,
    Recorder,
    Segmenter,
    highpass,
    noise_gate,
    normalize,
    prepare_segment,
    remove_dc,
    rms,
    trim_silence,
)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


def silence() -> bytes:
    return b"\x00\x00" * CHUNK


def speech(amplitude: int = 8000) -> bytes:
    samples = array.array(
        "h", (int(amplitude * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(CHUNK))
    )
    return samples.tobytes()


CHUNK_SECONDS = CHUNK / RATE
print(f"нэг хэсэг = {CHUNK_SECONDS*1000:.0f} мс")

check("чимээгүйн түвшин", rms(silence()), 0.0)
check("дууны түвшин ойролцоо", round(rms(speech()) / 1000), 6)  # 8000/√2 ≈ 5657

# --- энгийн өгүүлбэр: дуу → чимээгүй → сегмент гарна
seg = Segmenter()
segments = []
for _ in range(4):  # орчны чимээ хэмжих хугацаа
    segments.append(seg.feed(silence()))
for _ in range(8):  # ~0.5 сек яриа
    segments.append(seg.feed(speech()))
for _ in range(12):  # ~0.77 сек чимээгүй
    segments.append(seg.feed(silence()))
produced = [s for s in segments if s]
check("нэг сегмент гарсан", len(produced), 1)
check("сегмент дуутай хэсгийг агуулсан", len(produced[0]) >= 8 * CHUNK * 2, True)

# --- хэт богино чимээ сегмент болохгүй
seg2 = Segmenter()
out = []
for _ in range(4):
    out.append(seg2.feed(silence()))
for _ in range(2):  # ~0.13 сек — MIN_SPEECH-ээс богино
    out.append(seg2.feed(speech()))
for _ in range(15):
    out.append(seg2.feed(silence()))
check("богино чимээг алгасна", [s for s in out if s], [])
check("flush ч хоосон", seg2.flush(), None)

# --- зогсоох үед үлдсэн яриаг гаргана
seg3 = Segmenter()
for _ in range(4):
    seg3.feed(silence())
for _ in range(10):
    seg3.feed(speech())
tail = seg3.flush()
check("зогсоход үлдсэн хэсэг гарна", tail is not None and len(tail) > 0, True)

# --- хэт урт бичлэгийг албаар тасална
seg4 = Segmenter(max_segment=1.0)
cut = None
for _ in range(4):
    seg4.feed(silence())
for _ in range(20):  # ~1.3 сек тасралтгүй яриа
    result = seg4.feed(speech())
    if result:
        cut = result
        break
check("урт яриаг тасална", cut is not None, True)

# --- чанга орчинд босго өснө
seg5 = Segmenter()
for _ in range(4):
    seg5.feed(speech(2000))  # орчны чимээ өндөр
check("босго дасан зохицсон", seg5.threshold > 320.0, True)

# --- сүүлчийн богино үг алдагдахгүй ---
# Товч суллах үед хэрэглэгч санаатай дуусгасан тул "уу", "юм" гэх мэт
# богино үгийг ч илгээх ёстой. Өмнө нь эдгээр чимээгүйгээр хаягддаг байв.
tail = Segmenter()
for _ in range(4):
    tail.feed(silence())
for _ in range(16):
    tail.feed(speech())        # ~1 сек яриа
for _ in range(13):
    tail.feed(silence())       # завсарлага → сегмент гарна
for _ in range(4):
    tail.feed(speech())        # 0.26 сек богино сүүлчийн үг
check("богино сүүлчийн үг үлдэнэ", tail.flush(final=True) is not None, True)

only_short = Segmenter()
for _ in range(4):
    only_short.feed(silence())
for _ in range(4):
    only_short.feed(speech())  # зөвхөн 0.26 сек
check("зөвхөн богино үг ч гарна", only_short.flush(final=True) is not None, True)

quiet_only = Segmenter()
for _ in range(20):
    quiet_only.feed(silence())
check("чимээгүйг илгээхгүй", quiet_only.flush(final=True), None)

# --- намуухан дуугаар төгссөн үгийг тайрахгүй ---
soft_tail = array.array("h")
soft_tail.extend(int(9000 * math.sin(2 * math.pi * 200 * i / RATE)) for i in range(RATE))
soft_tail.extend(int(400 * math.sin(2 * math.pi * 200 * i / RATE)) for i in range(RATE // 2))
kept = trim_silence(soft_tail, RATE, MIN_THRESHOLD)
check("намуухан сүүл үлдэнэ", len(kept) > RATE * 1.2, True)

# --- товч дармагцаа ярьсан ч яриа алдагдахгүй ---
# Орчны чимээг эхний хэсгээр хэмждэг тул тэр үед яриа сонсогдвол босго
# хэт өндөр тогтож, БҮХ яриаг чимээгүйгээр хаядаг байсан.
instant = Segmenter()
produced = []
for _ in range(10):  # эхнээсээ шууд яриа
    produced.append(instant.feed(speech()))
for _ in range(12):
    produced.append(instant.feed(silence()))
check("шууд ярьсан ч сегмент гарна", len([s for s in produced if s]), 1)
check("босго дээд хязгаараас хэтрэхгүй", instant.threshold <= NOISE_CEILING, True)

# --- буруу тогтсон босгыг өөрөө засна ---
recal = Segmenter()
recal.feed(silence())
recal._threshold = 20000.0  # хэт өндөр босго албаар тавина
recal._noise_done = True
for _ in range(30):  # ~1.9 сек тасралтгүй яриа
    recal.feed(speech())
check("босго өөрөө буурсан", recal.threshold < 20000.0, True)
check("яриа дахин тоологдсон", recal._speech_seconds > 0.3, True)

# --- үнэхээр чимээгүй бол босгыг хөндөхгүй ---
quiet_seg = Segmenter()
for _ in range(30):
    quiet_seg.feed(silence())
check("чимээгүй үед босго хэвээр", quiet_seg.threshold, 320.0)
check("чимээгүйд сегмент гарахгүй", quiet_seg.flush(), None)

# --- хэт урт бичлэгийг чимээгүй цэг дээр тасална ---
seg6 = Segmenter(max_segment=1.2)
cut = None
for _ in range(4):
    seg6.feed(silence())
for index in range(24):
    # 10 дахь хэсэгт бага зэрэг тайван болно — таслалт тэнд таарах ёстой
    chunk = speech(900) if index in (9, 10) else speech()
    result = seg6.feed(chunk)
    if result:
        cut = result
        break
check("урт яриаг тасална", cut is not None, True)
check("тасалсны дараа үргэлжилнэ", len(seg6._frames) > 0, True)

# --- дуу цэгцлэх ---
check("DC хазайлт арилна", max(remove_dc(array.array("h", [1000] * 100))), 0)

quiet = array.array("h", [int(300 * math.sin(2 * math.pi * i / 40)) for i in range(4000)])
louder = normalize(quiet)
check("сул дууг чангаруулна", max(louder) > 4 * max(quiet), True)
check("хэт өсгөхгүй", max(louder) <= 32767, True)

loud = array.array("h", [int(30000 * math.sin(2 * math.pi * i / 40)) for i in range(4000)])
check("аль хэдийн чанга бол хөндөхгүй", normalize(loud) is loud, True)

# --- C (audioop) ба цэвэр Python зам ЯГ ижил үр дүн өгөх ёстой ---
# Хурдны төлөө C рүү шилжсэн ч Python 3.13-д `audioop` байхгүй тул хоёр зам
# зэрэг ажиллана. Зөрвөл зарим хэрэглэгчид өөр дуу илгээгдэнэ.
check(
    "чангаруулалт хоёр замд ижил",
    audio_module._normalize_python(quiet).tolist(),
    audio_module._normalize_audioop(quiet).tolist(),
)
check(
    "DC арилгалт хоёр замд ижил",
    audio_module._remove_dc_python(array.array("h", [1000] * 100)).tolist(),
    audio_module._remove_dc_audioop(array.array("h", [1000] * 100)).tolist(),
)
# `audioop.bias` халихдаа тойрч эргэдэг тул эргэлт үүсэх дуун дээр C зам нь
# Python руу буцах ёстой — эс бөгөөс дээд цэг дээр шаржигнуур гарна
clipping = array.array("h", [32767, -32768, 32000, 1000])
check(
    "халих дуун дээр Python зам руу буцна",
    audio_module._remove_dc_audioop(clipping).tolist(),
    audio_module._remove_dc_python(clipping).tolist(),
)

# Эхэн, төгсгөлд нь чимээгүйтэй дуу → тайрагдана
padded = array.array("h", [0] * RATE)  # 1 сек чимээгүй
padded.extend(int(9000 * math.sin(2 * math.pi * 220 * i / RATE)) for i in range(RATE // 2))
padded.extend([0] * RATE)
trimmed = trim_silence(padded, RATE, MIN_THRESHOLD)
check("чимээгүйг тайрна", len(trimmed) < len(padded), True)
check("яриаг үлдээнэ", len(trimmed) >= RATE // 2, True)

prepared = prepare_segment(padded.tobytes(), RATE)
check("бүрэн боловсруулалт богиносгоно", 0 < len(prepared) < len(padded) * 2, True)
check("хоосон оролт", prepare_segment(b"", RATE), b"")

# --- алдааны мессеж ---
# -9998 бол «сонсох суваггүй төхөөрөмж рүү хандлаа» — техникийн текстээр нь
# хэрэглэгчийг тарчлаахгүй
friendly = Recorder._friendly_error(OSError(-9998, "Invalid number of channels"))
check("-9998 ойлгомжтой болно", friendly.startswith("Микрофон олдсонгүй"), True)
check(
    "танихгүй алдааг нуухгүй",
    Recorder._friendly_error(OSError("Something odd")),
    "Микрофон нээгдсэнгүй: Something odd",
)

# Бичлэгийн суваг ба төхөөрөмж шалгах суваг салж явбал сонсдог төхөөрөмжийг
# «сонсдоггүй» гэж хаяна (mics модуль эргэлдсэн импортоос болж тусдаа тоотой)
check("суваг тоо нийцнэ", CHANNELS, mics.MIN_CHANNELS)


# --- урсгал нээх нөөц зам (микрофон хэрэггүй) ---
class FakeStream:
    def read(self, frames, exception_on_overflow=True):
        return b"\x00\x00" * frames

    def get_read_available(self):
        return 0

    def stop_stream(self):
        pass

    def close(self):
        pass


class FakePyAudio:
    """PortAudio-ийн зан төлөв: сонсох суваггүй дугаар руу хандвал -9998.

    Энэ нь таамаг биш — бодит төхөөрөмж дээр хэмжсэн зан төлөв.
    """

    def __init__(self, devices, refuse=()):
        self.devices = devices  # [(нэр, сонсох суваг), ...]
        self.refuse = refuse  # жагсаалт зөв мөртлөө нээгдэхгүй дугаарууд
        self.opened = []

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        if index < 0 or index >= len(self.devices):
            raise OSError("Invalid device index")
        name, channels = self.devices[index]
        return {"name": name, "maxInputChannels": channels}

    def _default_input(self):
        for index, (_name, channels) in enumerate(self.devices):
            if channels >= CHANNELS:
                return index
        return None

    def open(self, input_device_index=None, channels=CHANNELS, **_kw):
        target = input_device_index
        if target is None:
            target = self._default_input()
        if target is None or self.devices[target][1] < channels or target in self.refuse:
            raise OSError(-9998, "Invalid number of channels")
        self.opened.append(input_device_index)
        return FakeStream()


def record_with(devices, mic, refuse=()):
    """Хуурамч төхөөрөмжийн хүснэгт дээр нэг удаа бичиж үзнэ."""
    fake = FakePyAudio(devices, refuse)
    original = audio_module._new_pyaudio
    audio_module._new_pyaudio = lambda: fake
    try:
        recorder = audio_module.Recorder(
            on_segment=lambda pcm, final: None, mic=mic, keep_open_seconds=0.0
        )
        error = recorder.start()
        recorder.stop()
        recorder.close()
        return error, recorder.active_index
    finally:
        audio_module._new_pyaudio = original


MAPPER = ("Microsoft Sound Mapper - Input", 2)
HEADSET = ("Headset (AWEI)", 1)
SPEAKERS = ("Speakers", 0)
headset_mic = mics.Mic(1, "Headset (AWEI)")

# Дугаар шилжсэн: хадгалсан №1 нь одоо чанга яригч, чихэвч №2 дээр
error, opened = record_with([MAPPER, SPEAKERS, HEADSET], headset_mic)
check("шилжсэн дугаараас сэргэнэ", (error, opened), (None, 2))

# Жагсаалт зөв мөртлөө нээлт бүтсэнгүй → системийн үндсэнээр дахин оролдоно
error, opened = record_with([MAPPER, HEADSET, SPEAKERS], headset_mic, refuse=(1,))
check("нээлт унавал үндсэнээр", (error, opened), (None, None))

# Сонсох төхөөрөмж огт үлдээгүй: бичих боломжгүй ч мессеж нь ойлгомжтой байх ёстой
error, opened = record_with([("Sound Mapper", 0), SPEAKERS], headset_mic)
check("төхөөрөмжгүй бол ойлгомжтой алдаа", error.startswith("Микрофон олдсонгүй"), True)
check("төхөөрөмжгүй бол нээгдээгүй", opened, None)

# --- товч суллах үед буферт хоцорсон сүүлчийн үе алдагдахгүй ---
# `read()` нь CHUNK бүрдэх хүртэл хүлээдэг тул суллах агшинд микрофоны буферт
# унших гараагүй хэсэг үлддэг. Өмнө нь тэр хэсэг хаягддаг байсан — яг тэнд
# хэлсэн зүйлийн сүүлчийн үе («…юм», «…уу») байдаг.
class TailStream:
    """Буферт хэдэн хэсэг хоцорсон микрофоныг дуурайна."""

    def __init__(self, pending):
        self.pending = list(pending)
        self.reads = 0

    def get_read_available(self):
        return CHUNK * len(self.pending)

    def read(self, frames, exception_on_overflow=True):
        self.reads += 1
        return self.pending.pop(0) if self.pending else silence()

    def stop_stream(self):
        pass

    def close(self):
        pass


collected = []
rec = audio_module.Recorder(
    on_segment=lambda pcm, final: collected.append((pcm, final)), keep_open_seconds=0.0
)
rec._stream = TailStream([speech()] * 3)  # буферт хоцорсон 3 хэсэг
rec._capturing.set()
rec._finishing.set()
for _ in range(4):
    rec.segmenter.feed(silence())  # орчны чимээ
for _ in range(8):
    rec.segmenter.feed(speech())  # аль хэдийн уншсан яриа
rec._finish_capture()

check("сүүлчийн сегмент илгээгдсэн", len(collected), 1)
check("«эцсийн» гэж тэмдэглэгдсэн", collected[0][1], True)
# 12 уншсан + буферийн 3 + саатлын төлөө нэмж уншсан 1 = 16
check("буферт хоцорсон хэсгүүд орсон", len(collected[0][0]), 16 * CHUNK * 2)
check("бичих төлөв хаагдсан", rec.active, False)

# Соруулж дуусахаас өмнө дахин бичиж эхэлбэл шинэ бичлэгийг таслахгүй
restarted = []
rec2 = audio_module.Recorder(
    on_segment=lambda pcm, final: restarted.append((pcm, final)), keep_open_seconds=0.0
)
rec2._stream = FakeStream()
rec2._capturing.set()
rec2._finishing.clear()  # `start()` дохиог цуцалсан гэж үзье
rec2._finish_capture()
check("цуцлагдсан төгсгөл сегмент илгээхгүй", restarted, [])
check("шинэ бичлэг үргэлжилнэ", rec2.active, True)

# --- Сорох ажил дуусаагүй байхад дахин товч дарвал бичлэг ЭХЛЭХ ёстой ---
# `stop()` нь хүлээхгүй буцдаг тул тэр үед `_capturing` асаалттай хэвээр
# байна. `start()` зөвхөн түүнийг харвал «аль хэдийн бичиж байна» гэж
# андуурч юу ч хийхгүй өнгөрөх ба дараа нь `_finish_capture` төлвийг хааж,
# хэрэглэгчийн хэлсэн зүйл бүхэлдээ чимээгүй алга болно.
rec3 = audio_module.Recorder(on_segment=lambda pcm, final: None, keep_open_seconds=45.0)
rec3._stream = FakeStream()
# Урсгал нээлттэй (унших thread амьд) гэж үзүүлнэ — «дулаан» зам руу орно,
# эс бөгөөс `start()` жинхэнэ төхөөрөмж нээхийг оролдоно
_idle = threading.Event()
_reader = threading.Thread(target=_idle.wait, daemon=True)
_reader.start()
rec3._thread = _reader
rec3._capturing.set()
rec3._finishing.set()  # `stop()` дуудагдаад төгсгөл нь хараахан дуусаагүй
check("төгсгөл дуусаагүй ч дахин эхэлнэ", rec3.start(), None)
check("дохио цуцлагдсан", rec3._finishing.is_set(), False)
rec3._finish_capture()  # хожуу ирсэн төгсгөл шинэ бичлэгийг таслах ёсгүй
check("шинэ бичлэг таслагдаагүй", rec3.active, True)
_idle.set()


# ----------------------------------------------------------------------
# Урьдчилсан буфер: товч дарахаас өмнөх дуу
# ----------------------------------------------------------------------
pre = Recorder(on_segment=lambda pcm, final: None, preroll_seconds=0.5)
limit = pre._preroll_limit()
check("багтаамж секундээс тооцогдоно", limit, int(0.5 * RATE / CHUNK))

for _ in range(limit + 5):
    pre._remember_preroll(silence())
check("хязгаараас хэтрэхгүй", len(pre._preroll), limit)

# Унтраасан үед огт хураахгүй
off = Recorder(on_segment=lambda pcm, final: None, preroll_seconds=0.0)
off._remember_preroll(speech())
check("унтраалттай бол хоосон", len(off._preroll), 0)

# Хураасан дуу сегментчлэгч рүү орно: 3 хэсэг чимээгүй + 3 хэсэг яриа өгвөл
# сегмент хараахан гарахгүй (яриа үргэлжилж байна) ч буфер нь хоосорно
pre2 = Recorder(on_segment=lambda pcm, final: None, preroll_seconds=0.5)
for _ in range(3):
    pre2._remember_preroll(silence())
for _ in range(3):
    pre2._remember_preroll(speech())
check("залгахад сегмент гараагүй", pre2._inject_preroll(), None)
check("залгасны дараа буфер хоосон", len(pre2._preroll), 0)
check("сегментчлэгчид хэсгүүд орсон", len(pre2.segmenter._frames), 6)

# Бичлэг дуусахад буфер цэвэрлэгдэнэ — сая бичсэн зүйл дахин орох ёсгүй
pre3 = Recorder(on_segment=lambda pcm, final: None, preroll_seconds=0.5)
pre3._remember_preroll(speech())
pre3._finishing.set()
pre3._capturing.set()
pre3._finish_capture()
check("бичлэг дуусахад цэвэрлэгдэв", len(pre3._preroll), 0)


# ----------------------------------------------------------------------
# Чимээ дарах
# ----------------------------------------------------------------------
import math as _math  # noqa: E402 - зөвхөн энэ хэсэгт хэрэгтэй


def tone(hz, amplitude=8000, seconds=1.0):
    count = int(RATE * seconds)
    return array.array(
        "h",
        [int(amplitude * _math.sin(2 * _math.pi * hz * i / RATE)) for i in range(count)],
    )


# Доод давтамжийг дарж, ярианы давтамжийг бараг хөндөхгүй
low = tone(50)
speech = tone(1000)
low_before, low_after = rms(low.tobytes()), rms(highpass(low, RATE).tobytes())
speech_before, speech_after = rms(speech.tobytes()), rms(highpass(speech, RATE).tobytes())
check("50 Гц гүнгэнээ дарагдав", low_after < low_before * 0.35, True)
check("1 кГц яриа хэвээр", speech_after > speech_before * 0.9, True)
check("урт өөрчлөгдөхгүй", len(highpass(low, RATE)), len(low))
check("хоосон дуу", len(highpass(array.array("h"), RATE)), 0)

# Чимээт завсрыг сулруулж, яриаг хөндөхгүй
mixed = tone(200, 300, seconds=2.0)
for index in range(8000, 20000):
    mixed[index] = max(-32768, min(32767, mixed[index] + int(9000 * _math.sin(
        2 * _math.pi * 500 * index / RATE))))
gated = noise_gate(mixed)
check("завсрын чимээ сулрав", rms(gated[:6000].tobytes()) < rms(mixed[:6000].tobytes()) * 0.5, True)
check(
    "яриа хэвээр үлдэв",
    rms(gated[9000:19000].tobytes()) > rms(mixed[9000:19000].tobytes()) * 0.95,
    True,
)
check("урт хэвээр", len(gated), len(mixed))
check("богино дууг хөндөхгүй", len(noise_gate(tone(300, seconds=0.02))), int(RATE * 0.02))

# Бүхэлдээ жигд дуу — юу ч сулруулахгүй (таних шат өөрөө шийднэ)
flat = tone(300, 5000)
check("жигд дууг хөндөхгүй", noise_gate(flat) == flat, True)

# `prepare_segment` нь зөвхөн хүсэхэд л чимээ дарна
noisy = tone(60, 2000, seconds=1.0).tobytes()
check(
    "унтраалттай бол хөндөхгүй",
    rms(prepare_segment(noisy, RATE)) > rms(prepare_segment(noisy, RATE, denoise=True)),
    True,
)


# ----------------------------------------------------------------------
# Системийн дуу: эх формат ба хөрвүүлэлт
# ----------------------------------------------------------------------
class FakeDevices:
    """`get_device_info_by_index`-ийг л дуурайна."""

    def __init__(self, devices):
        self.devices = devices

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        return self.devices[index]


recorder = Recorder(on_segment=lambda pcm, final: None)
recorder._pa = FakeDevices(
    [
        {"name": "Headset", "maxInputChannels": 1, "defaultSampleRate": 44100.0},
        {
            "name": "Speakers [Loopback]",
            "maxInputChannels": 2,
            "defaultSampleRate": 48000.0,
            "isLoopbackDevice": True,
        },
    ]
)
check("энгийн микрофон 16 кГц моно", recorder._device_format(0), (1, RATE))
check("системийн дуу эх форматаар", recorder._device_format(1), (2, 48000))
check("үндсэн төхөөрөмж", recorder._device_format(None), (1, RATE))

# 48 кГц стерео → 16 кГц моно
recorder._source_channels = 2
recorder._source_rate = 48000
recorder._resample_state = None
stereo = array.array("h")
for index in range(4800):  # 0.1 сек @ 48 кГц
    value = int(6000 * math.sin(2 * math.pi * 300 * index / 48000))
    stereo.extend((value, value))
converted = recorder._to_pipeline_format(stereo.tobytes())
check("гуравны нэг болов", abs(len(converted) - 1600 * 2) <= 8, True)
check("дуу алдагдаагүй", rms(converted) > 3000, True)

# Ердийн микрофоны хэсгийг хөндөхгүй
recorder._source_channels = 1
recorder._source_rate = RATE
plain = b"\x01\x02" * 100
check("хөрвүүлэх шаардлагагүй", recorder._to_pipeline_format(plain), plain)
check("хоосон хэсэг", recorder._to_pipeline_format(b""), b"")


print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
