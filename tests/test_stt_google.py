"""Таних хариуг задлах логикийн тест (сүлжээ хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_recognizer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


import monspeech.recognizer as recognizer_module
from monspeech.recognizer import RecognitionError, RecognitionResult
from monspeech.stt_google import GoogleWebSpeech

fails = []


def check(label, got, want):
    if isinstance(got, RecognitionResult):
        got = (got.alternatives, got.confidence)
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


parse = GoogleWebSpeech._parse

check("хоосон хариу", parse('{"result":[]}\n'), ([], None))
check(
    "энгийн хариу",
    parse('{"result":[]}\n'
          '{"result":[{"alternative":[{"transcript":"сайн байна уу","confidence":0.94}]}],'
          '"result_index":0}\n'),
    (["сайн байна уу"], 0.94),
)
check(
    "бүх хувилбарыг эрэмбээр нь буцаана",
    parse('{"result":[{"alternative":[{"transcript":"нэг","confidence":0.8},'
          '{"transcript":"хоёр"},{"transcript":"гурав"}]}]}'),
    (["нэг", "хоёр", "гурав"], 0.8),
)
check(
    "итгэлцлийг зөвхөн эхний хувилбараас авна",
    parse('{"result":[{"alternative":[{"transcript":"нэг","confidence":0.8},'
          '{"transcript":"хоёр","confidence":0.99}]}]}'),
    (["нэг", "хоёр"], 0.8),
)
check(
    "итгэлцэл өгөөгүй бол 1.0",
    parse('{"result":[{"alternative":[{"transcript":"утга"}]}]}'),
    (["утга"], None),
)
check(
    "хоосон transcript алгасна",
    parse('{"result":[{"alternative":[{"transcript":"   "}]}]}\n'
          '{"result":[{"alternative":[{"transcript":"утга","confidence":0.5}]}]}'),
    (["утга"], 0.5),
)
check(
    "хоосон хувилбарыг завсраас нь хаяна",
    parse('{"result":[{"alternative":[{"transcript":"нэг","confidence":0.7},'
          '{"transcript":""},{"transcript":"гурав"}]}]}'),
    (["нэг", "гурав"], 0.7),
)
check("эвдэрсэн JSON", parse("{нэг хоёр\n"), ([], None))
check("огт хоосон", parse(""), ([], None))


# ----------------------------------------------------------------------
# Түр зуурын алдаанд дахин оролдох (сүлжээнд хандахгүй — `_post`-ыг сольсон)
# ----------------------------------------------------------------------
OK_BODY = (
    '{"result":[{"alternative":[{"transcript":"тест","confidence":0.9}]}]}\n'
).encode("utf-8")
PCM = b"\x00\x10" * 100


def build(responses):
    """Өгсөн хариунуудыг дараалан буцаах танигч. `(status, body)` эсвэл алдаа."""
    recognizer = GoogleWebSpeech()
    calls = []
    slept = []

    def fake_post(pcm, rate, reuse, lang):
        calls.append(reuse)
        answer = responses[len(calls) - 1]
        if isinstance(answer, Exception):
            raise answer
        return answer, OK_BODY

    recognizer._post = fake_post
    # Хүлээлтийг бодитоор хийхгүй. Дахин оролдох давталт `recognizer.request`-т
    # төвлөрсөн тул хүлээлтийг ч тэндээс хаана.
    recognizer_module.time.sleep = slept.append
    return recognizer, calls, slept


real_sleep = recognizer_module.time.sleep
try:
    # 429 хоёр удаа гараад гурав дахьд амжилттай
    rec, calls, slept = build([429, 429, 200])
    check("гурав дахь оролдлогод танив", rec.recognize(PCM), (["тест"], 0.9))
    check("гурван удаа оролдсон", len(calls), 3)
    check("эхнийх нь холболтоо ашигласан", calls, [True, False, False])
    check("хүлээлтийн дараалал", slept, [0.4, 1.0])

    # 503 ч мөн адил түр зуурынх
    rec, calls, slept = build([503, 200])
    check("503-ын дараа танив", rec.recognize(PCM), (["тест"], 0.9))
    check("хоёр удаа оролдсон", len(calls), 2)

    # 403 нь өөрөө засрахгүй — дахин оролдохгүй
    rec, calls, slept = build([403, 200])
    try:
        rec.recognize(PCM)
        check("403 алдаа шидсэн", False, True)
    except RecognitionError as exc:
        check("403 алдаа шидсэн", "403" in str(exc), True)
    check("403-д дахин оролдоогүй", len(calls), 1)

    # Бүх оролдлого 429 бол эцэст нь алдаа
    rec, calls, slept = build([429, 429, 429])
    try:
        rec.recognize(PCM)
        check("тасралтгүй 429 алдаа болсон", False, True)
    except RecognitionError as exc:
        check("тасралтгүй 429 алдаа болсон", "429" in str(exc), True)
    check("хязгаартаа хүрч зогссон", len(calls), 3)

    # Сүлжээний тасалдал ч дахин оролдоно
    rec, calls, slept = build([OSError("холболт тасарлаа"), 200])
    check("тасалдлын дараа танив", rec.recognize(PCM), (["тест"], 0.9))
    check("тасалдалд дахин оролдсон", len(calls), 2)

    # Бүх оролдлого тасалдвал сүлжээний алдаа
    rec, calls, slept = build([OSError("а"), OSError("б"), OSError("в")])
    try:
        rec.recognize(PCM)
        check("тасралтгүй тасалдал алдаа болсон", False, True)
    except RecognitionError as exc:
        check("тасралтгүй тасалдал алдаа болсон", "Сүлжээний алдаа" in str(exc), True)

    # Хоосон дуунд огт хандахгүй
    rec, calls, slept = build([200])
    check("хоосон дуу", rec.recognize(b""), ([], None))
    check("хоосон дуунд хандаагүй", len(calls), 0)
finally:
    recognizer_module.time.sleep = real_sleep

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
