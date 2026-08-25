"""Файлаас хөрвүүлэх логикийн тест (сүлжээ, ffmpeg шаардахгүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_filetext.py
"""

import array
import math
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import filetext
from monspeech.audio import RATE
from monspeech.recognizer import RecognitionError, RecognitionResult

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


TEMP = Path(tempfile.mkdtemp())


def tone(hz=300, amplitude=9000, seconds=1.0, rate=RATE):
    count = int(rate * seconds)
    return array.array(
        "h", [int(amplitude * math.sin(2 * math.pi * hz * i / rate)) for i in range(count)]
    )


def write_wav(name, samples, channels=1, width=2, rate=RATE):
    path = TEMP / name
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(width)
        handle.setframerate(rate)
        handle.writeframes(samples.tobytes())
    return path


# ----------------------------------------------------------------------
# Файл унших
# ----------------------------------------------------------------------
mono = write_wav("mono.wav", tone(seconds=0.5))
pcm = filetext.load_pcm(mono)
check("моно WAV уншигдав", len(pcm), int(RATE * 0.5) * 2)
check("үргэлжлэх хугацаа", round(filetext.duration_seconds(pcm), 2), 0.5)

# Стерео ба өөр давтамжийг өөрөө хөрвүүлнэ
stereo = array.array("h")
for value in tone(seconds=0.5, rate=8000):
    stereo.extend((value, value))
converted = filetext.load_pcm(write_wav("stereo.wav", stereo, channels=2, rate=8000))
# Дахин түүвэрлэхэд нэг хоёр түүвэр зөрж болно — урт нь ойролцоо байвал зөв
check(
    "стерео 8 кГц → моно 16 кГц",
    abs(len(converted) - int(RATE * 0.5) * 2) <= 8,
    True,
)

try:
    filetext.load_pcm(TEMP / "байхгүй.wav")
    check("байхгүй файл", "алдаа гараагүй", "FileError")
except filetext.FileError as exc:
    check("байхгүй файлыг хэлнэ", "олдсонгүй" in str(exc), True)

# ffmpeg шаардах өргөтгөл — хэрэгсэл байхгүй бол ойлгомжтой мессеж
if not filetext.ffmpeg_path():
    fake_mp3 = TEMP / "яриа.mp3"
    fake_mp3.write_bytes(b"not really an mp3")
    try:
        filetext.load_pcm(fake_mp3)
        check("ffmpeg шаардлага", "алдаа гараагүй", "FileError")
    except filetext.FileError as exc:
        check("ffmpeg хэрэгтэйг хэлнэ", "ffmpeg" in str(exc), True)


# ----------------------------------------------------------------------
# Хэсэглэх
# ----------------------------------------------------------------------
# Яриа — чимээгүй — яриа: хоёр хэсэг болно
speech = tone(seconds=0.6)
silence = array.array("h", [0] * int(RATE * 1.2))
mixed = array.array("h")
mixed.extend(silence[: int(RATE * 0.3)])
mixed.extend(speech)
mixed.extend(silence)
mixed.extend(speech)
chunks = filetext.split_chunks(mixed.tobytes())
check("хоёр хэсэг гарав", len(chunks), 2)
check("хэсэг бүр яриатай", all(len(chunk) > RATE for chunk in chunks), True)
check("хоосон дуу", filetext.split_chunks(b""), [])


# ----------------------------------------------------------------------
# Хөрвүүлэх
# ----------------------------------------------------------------------
class FakeRecognizer:
    def __init__(self, answers):
        self.answers = list(answers)
        self.calls = 0

    def recognize(self, pcm, rate, lang):
        self.calls += 1
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return RecognitionResult(alternatives=[answer], provider="fake")


progress = []
recognizer = FakeRecognizer(["эхний хэсэг", "хоёр дахь хэсэг"])
text = filetext.transcribe(
    write_wav("яриа.wav", mixed),
    recognizer,
    on_progress=lambda index, total: progress.append((index, total)),
)
check("хоёр мөр нийлэв", text, "эхний хэсэг\nхоёр дахь хэсэг")
check("явц мэдэгдэв", progress, [(1, 2), (2, 2)])

# Нэг хэсэг унасан ч бусад нь үлдэнэ
recognizer = FakeRecognizer([RecognitionError("сүлжээ"), "үлдсэн хэсэг"])
check(
    "унасан хэсгийг алгасна",
    filetext.transcribe(write_wav("яриа2.wav", mixed), recognizer),
    "үлдсэн хэсэг",
)

# Зогсоох хүсэлтийг дагана
recognizer = FakeRecognizer(["нэг", "хоёр"])
check(
    "зогсоохыг дагана",
    filetext.transcribe(write_wav("яриа3.wav", mixed), recognizer, should_stop=lambda: True),
    "",
)

# Яриагүй файл
try:
    filetext.transcribe(write_wav("чимээгүй.wav", array.array("h", [0] * RATE)), FakeRecognizer([]))
    check("яриагүй файл", "алдаа гараагүй", "FileError")
except filetext.FileError as exc:
    check("яриагүйг хэлнэ", "яриа олдсонгүй" in str(exc), True)


# ----------------------------------------------------------------------
# Хадгалах
# ----------------------------------------------------------------------
source = write_wav("хадгалах.wav", speech)
saved = filetext.save_text(source, "нэг мөр")
check("текст хадгалагдав", saved.read_text(encoding="utf-8"), "нэг мөр")
check("нэр нь эх файлаас", saved.name, "хадгалах.txt")
again = filetext.save_text(source, "хоёр дахь")
check("хуучныг дарж бичихгүй", again.name, "хадгалах (2).txt")


print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
