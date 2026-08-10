"""Дуу таслах логикийн тест (микрофон хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_audio.py
"""

import array
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech.audio import (
    CHUNK,
    MIN_THRESHOLD,
    NOISE_CEILING,
    RATE,
    Segmenter,
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

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
