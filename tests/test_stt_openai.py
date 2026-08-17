"""OpenAI-нийцтэй танигчийн тест — хүсэлт бүрдүүлэлт, хариу задлалт.

Сүлжээнд хандахгүй: `_post`-ыг хуурмагаар солино.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_stt_openai.py
"""

import io
import sys
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


import monspeech.recognizer as recognizer_module
from monspeech.recognizer import RecognitionError
from monspeech.stt_openai import OpenAICompatible, _multipart, _wav

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


PCM = b"\x00\x10" * 8000  # 1 секунд @ 16 кГц

# ----------------------------------------------------------------------
# WAV бүрдүүлэлт — эдгээр үйлчилгээ түүхий PCM биш, файлын толгой шаарддаг
# ----------------------------------------------------------------------
data = _wav(PCM, 16000)
check("WAV толгойтой", data[:4], b"RIFF")
with wave.open(io.BytesIO(data), "rb") as handle:
    check("нэг суваг", handle.getnchannels(), 1)
    check("16 бит", handle.getsampwidth(), 2)
    check("16 кГц", handle.getframerate(), 16000)
    check("дуу бүтнээрээ", handle.readframes(handle.getnframes()), PCM)

# ----------------------------------------------------------------------
# multipart — талбарууд болон дуу нэг биед багтана
# ----------------------------------------------------------------------
body, content_type = _multipart({"model": "whisper-1", "language": "mn"}, b"AUDIO")
check("хилийн мөр зарлагдсан", "boundary=" in content_type, True)
check("загвар орсон", b'name="model"' in body and b"whisper-1" in body, True)
check("хэл орсон", b'name="language"' in body and b"mn" in body, True)
check("файл орсон", b'filename="audio.wav"' in body and b"AUDIO" in body, True)
check(
    "хоосон талбар оруулахгүй",
    b'name="language"' in _multipart({"language": ""}, b"A")[0],
    False,
)

# ----------------------------------------------------------------------
# Хариу задлах
# ----------------------------------------------------------------------
parse = OpenAICompatible._parse
check("энгийн хариу", parse('{"text": "сайн байна уу"}'), (["сайн байна уу"], 1.0))
check("зайг тайрна", parse('{"text": "  тест  "}'), (["тест"], 1.0))
check("хоосон текст", parse('{"text": ""}'), ([], 0.0))
check("текст талбаргүй", parse('{"task": "transcribe"}'), ([], 0.0))
check("эвдэрсэн JSON", parse("{"), ([], 0.0))
check("жагсаалт ирвэл", parse("[1, 2]"), ([], 0.0))

# ----------------------------------------------------------------------
# Тохиргоо дутуу бол шулуухан хэлнэ (чимээгүй бүтэлгүйтэхгүй)
# ----------------------------------------------------------------------
def expect_error(label, provider, fragment, pcm=PCM):
    try:
        provider.recognize(pcm)
        check(label, "алдаа гараагүй", fragment)
    except RecognitionError as exc:
        check(label, fragment in str(exc), True)


expect_error("хаяггүй", OpenAICompatible(url="", model="m"), "хаяг")
expect_error(
    "загваргүй",
    OpenAICompatible(url="https://example.test/v1/audio/transcriptions", model=""),
    "загвар",
)
expect_error(
    "хаяг буруу",
    OpenAICompatible(url="хачин-хаяг", model="m"),
    "хаяг буруу",
)
check(
    "хоосон дуунд хандахгүй",
    OpenAICompatible(url="https://example.test/x", model="m").recognize(b""),
    ([], 0.0),
)

# ----------------------------------------------------------------------
# Статусын боловсруулалт ба дахин оролдлого
# ----------------------------------------------------------------------
OK_BODY = '{"text": "тест"}'.encode("utf-8")


def build(responses):
    provider = OpenAICompatible(
        url="https://example.test/v1/audio/transcriptions", model="whisper-1", key="k"
    )
    calls = []
    slept = []

    def fake_post(pcm, rate, lang):
        calls.append(lang)
        answer = responses[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer, OK_BODY

    provider._post = fake_post
    # Дахин оролдох давталт `recognizer.request`-т төвлөрсөн.
    recognizer_module.time.sleep = slept.append
    return provider, calls, slept


real_sleep = recognizer_module.time.sleep
try:
    provider, calls, slept = build([200])
    check("амжилттай", provider.recognize(PCM), (["тест"], 1.0))
    check("хэл дамжсан", calls, ["mn-MN"])  # ISO болгох нь `_post` дотор

    provider, calls, slept = build([429, 429, 200])
    check("429-ийн дараа танив", provider.recognize(PCM), (["тест"], 1.0))
    check("гурван оролдлого", len(calls), 3)
    check("хүлээлтийн дараалал", slept, [0.4, 1.0])

    provider, calls, slept = build([503, 200])
    check("503 бол дахин оролдоно", provider.recognize(PCM), (["тест"], 1.0))

    for status, fragment in ((401, "түлхүүр"), (403, "түлхүүр"), (404, "хаяг олдсонгүй")):
        provider, calls, slept = build([status, 200])
        expect_error(f"{status} алдаа", provider, fragment)
        check(f"{status}-д дахин оролдоогүй", len(calls), 1)

    provider, calls, slept = build([OSError("тасарлаа"), 200])
    check("тасалдлын дараа танив", provider.recognize(PCM), (["тест"], 1.0))

    provider, calls, slept = build([OSError("а"), OSError("б"), OSError("в")])
    expect_error("тасралтгүй тасалдал", provider, "Сүлжээний алдаа")
finally:
    recognizer_module.time.sleep = real_sleep

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
