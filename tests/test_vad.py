"""Ярианы илрүүлэгч (VAD) ба түүнийг ашигласан сегментчилэл.

Илрүүлэгчийн ЛОГИКийг хуурамч илрүүлэгчээр шалгана — жинхэнэ `webrtcvad`
суугаагүй машин дээр ч энэ тест бүрэн ажиллах ёстой. Жинхэнэ сангийн тестүүд
нь суусан үед л нэмэгдэнэ.
"""

import array
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401

from monspeech import vad
from monspeech.audio import CHUNK, MIN_THRESHOLD, RATE, Recorder, Segmenter, rms

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


class FakeDetector:
    """Заасан хариуг дараалан буцаана. `None` = «мэдэхгүй»."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.index = 0
        self.resets = 0

    def feed(self, chunk):
        if self.index < len(self.answers):
            answer = self.answers[self.index]
        else:
            answer = self.answers[-1] if self.answers else None
        self.index += 1
        return answer

    def reset(self):
        self.resets += 1


# --- Сегментчилэл: илрүүлэгч түвшингийн шийдвэрийг ОРЛОНО ---------------

# Аяархан хэлсэн үг: түвшин нь босгоос доогуур тул хуучин зам огт сонсохгүй.
QUIET = speech(200)
check("аяархан үг босгоос доогуур", rms(QUIET) < MIN_THRESHOLD, True)

quiet = Segmenter(detector=FakeDetector([True]))
produced = []
for _ in range(4):
    produced.append(quiet.feed(silence()))
for _ in range(8):
    produced.append(quiet.feed(QUIET))
quiet.detector.answers = [False]
quiet.detector.index = 0
for _ in range(12):
    produced.append(quiet.feed(silence()))
check("аяархан үг сегмент болно", len([s for s in produced if s]), 1)

deaf = Segmenter()
for _ in range(4):
    deaf.feed(silence())
for _ in range(8):
    deaf.feed(QUIET)
check("илрүүлэгчгүй бол аяархан үг алдагдана", deaf.flush(), None)

# Чанга ч ярианы бус чимээ (гар товчлуурын товшилт) сегментийг НЭЭХГҮЙ.
clack = Segmenter(detector=FakeDetector([False]))
for _ in range(4):
    clack.feed(silence())
for _ in range(10):
    clack.feed(speech())
check("чанга чимээ яриа болохгүй", clack.flush(), None)

# «Мэдэхгүй» гэсэн хариу түвшингийн зам руу унана.
unsure = Segmenter(detector=FakeDetector([None]))
for _ in range(4):
    unsure.feed(silence())
for _ in range(10):
    unsure.feed(speech())
check("мэдэхгүй бол түвшин шийднэ", unsure.flush() is not None, True)

# Илрүүлэгчтэй үед босгын дахин тохируулга ажиллах ёсгүй.
recal = Segmenter(detector=FakeDetector([False]))
recal.feed(silence())
recal._threshold = 20000.0
recal._noise_done = True
for _ in range(30):
    recal.feed(speech())
check("илрүүлэгчтэй үед босго хөндөгдөхгүй", recal.threshold, 20000.0)

# Сегмент солигдоход илрүүлэгчийн хагас фрэйм цэвэрлэгдэнэ.
tracked = FakeDetector([True])
tidy = Segmenter(detector=tracked)
before = tracked.resets
tidy.reset()
check("reset илрүүлэгчид дамжина", tracked.resets, before + 1)

# --- create(): байхгүй бол чимээгүй `None` -----------------------------
check("унтраасан бол илрүүлэгчгүй", vad.create(enabled=False), None)
check("дэмжигдэхгүй давтамжид уначихгүй", vad.create(rate=44100), None)

# --- Recorder дээрх шууд асаах/унтраах ---------------------------------
rec = Recorder(on_segment=lambda *a: None, vad_enabled=False)
check("унтраалттай эхэлбэл илрүүлэгчгүй", rec.segmenter.detector, None)
rec.set_vad(True)
check("асаахад тэр дороо үйлчилнэ", rec.segmenter.detector is not None, vad.available())
rec.set_vad(False)
check("буцааж унтраана", rec.segmenter.detector, None)

# --- Жинхэнэ webrtcvad (суусан үед) ------------------------------------
if vad.available():
    real = vad.create()
    check("жинхэнэ илрүүлэгч үүснэ", real is not None, True)
    check("чимээгүй нь яриа биш", real.feed(silence()), False)
    real.reset()
    check("дуутай нь яриа мөн", real.feed(speech(9000)), True)
    # WebRTC өмнөх ярианы дараа хэсэг хугацаанд «яриа» гэсээр байдаг
    # (hangover) — сүүлийн үе тайрагдахгүй байх зориудын зан төлөв.
    # Тиймээс фрэймийн тоололыг цэвэр төлөвтэй илрүүлэгч дээр шалгана.
    fresh = vad.create()
    # 20 мс = 320 сэмпл. 10 мс өгвөл фрэйм бүрдэхгүй тул «мэдэхгүй».
    check("бүтэн фрэйм бүрдээгүй бол мэдэхгүй", fresh.feed(b"\x00\x00" * 160), None)
    # Үлдэгдэл нь хаягдахгүй — дараагийн 10 мс-тэй нийлж бүтэн фрэйм болно.
    check("үлдэгдэл дараагийнхтай нийлнэ", fresh.feed(b"\x00\x00" * 160), False)
else:
    print("алгаслаа (webrtcvad суугаагүй)")

print()
if fails:
    print("FAILED:")
    for line in fails:
        print(" ", line)
    raise SystemExit(1)
print("ALL PASS")
