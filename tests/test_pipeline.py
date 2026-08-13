"""Таних дамжлагын тест — сегмент ирснээс текст орох хүртэлх урсгал.

Бодит микрофон, сүлжээ, товчлуур хөндөхгүй: танигч, оруулагчийг хуурмагаар
солино.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_pipeline.py
"""

import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech import pipeline
from monspeech.audio import RATE
from monspeech.pipeline import RecognitionWorker
from monspeech.recognizer import RecognitionError
from monspeech.textproc import Formatter

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


class FakeRecognizer:
    """Урьдчилан бэлдсэн хариуг дараалан өгнө."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.langs = []

    def recognize(self, pcm, rate, lang):
        self.langs.append(lang)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


class FakeStore:
    def __init__(self):
        self.added = []

    def add(self, text, lang="", seconds=0.0):
        entry = {"text": text, "lang": lang}
        self.added.append(entry)
        return entry


class FakeStats:
    def __init__(self):
        self.records = []

    def record(self, text, seconds, ms):
        self.records.append(text)


class FakeInsertions:
    def __init__(self):
        self.items = []

    def record(self, text):
        self.items.append(text)


class FakeTarget:
    def __init__(self):
        self.ensured = 0

    def ensure(self):
        self.ensured += 1
        return True


class FakeInjector:
    """Бодит товчлуур дарахгүй — зөвхөн дуудлагыг тэмдэглэнэ."""

    def __init__(self):
        self.calls = []

    def insert_text(self, text, restore, backspaces, mode):
        self.calls.append((text, restore, backspaces, mode))


def build(answers, cfg=None, formatter=None):
    injector = FakeInjector()
    pipeline.injector = injector  # бодит оруулагчийг түр солино
    worker = RecognitionWorker(
        segments=queue.Queue(),
        events=queue.Queue(),
        cfg=cfg or {"min_confidence": 0.45, "restore_clipboard": True, "clean_speech": True},
        recognizer=FakeRecognizer(answers),
        formatter=formatter or Formatter(),
        stats=FakeStats(),
        transcripts=FakeStore(),
        insertions=FakeInsertions(),
        target=FakeTarget(),
        insert_mode=lambda: "paste",
    )
    return worker, injector


def drain(events) -> list:
    out = []
    while True:
        try:
            out.append(events.get_nowait())
        except queue.Empty:
            return out


SPEECH = b"\x00\x10" * RATE  # 1 секундын хиймэл дуу


# --- Энгийн танилт: текст орж, түүх, статистик бүртгэгдэнэ ---
worker, injector = build([(["сайн байна уу"], 0.9)])
worker._handle(SPEECH, "mn-MN")
events = drain(worker.events)
check("хүлээлт буурсан", events[0], ("pending", -1))
check("таньсан эвент", events[1][0], "recognized")
check("харуулах текст", events[1][1][0], "Сайн байна уу")
check("түүхэнд нэмэгдсэн", worker.transcripts.added[0]["text"], "Сайн байна уу")
check("статистикт бүртгэгдсэн", len(worker.stats.records), 1)
check("зорилтот цонх идэвхжсэн", worker.target.ensured, 1)
check("оруулсан текст", injector.calls[0][0], "Сайн байна уу ")
check("буцаахад санагдсан", worker.insertions.items, ["Сайн байна уу "])

# --- Итгэлцэл бага бол текст орохгүй ---
worker, injector = build([(["магадгүй"], 0.1)])
worker._handle(SPEECH, "mn-MN")
events = drain(worker.events)
check("итгэлцэл багад хоосон", events[1], ("empty", "low_confidence"))
check("итгэлцэл багад текст ороогүй", injector.calls, [])

# --- Итгэлцэл багатай чимээ цэвэрлэгээгээр хоосорвол шалтгаан нь «чигчлүүр» биш ---
worker, injector = build([(["за"], 0.1)])
worker._handle(SPEECH, "mn-MN")
check(
    "итгэлцэл нь чигчлүүрээс түрүүнд шүүнэ",
    drain(worker.events)[1],
    ("empty", "low_confidence"),
)

# --- Юу ч танигдаагүй ---
worker, injector = build([([], 0.0)])
worker._handle(SPEECH, "mn-MN")
check("танигдаагүй эвент", drain(worker.events)[1], ("empty", "unrecognized"))

# --- Дуут "буцаа" команд нь текст болж орохгүй ---
worker, injector = build([(["буцаа"], 0.9)])
worker._handle(SPEECH, "mn-MN")
events = drain(worker.events)
check("буцаах эвент", events[1], ("undo", None))
check("буцаах үед текст ороогүй", injector.calls, [])

# --- Сүлжээний алдаа: хүлээлт эхлээд буурч, дараа нь алдаа мэдэгдэнэ ---
worker, injector = build([RecognitionError("Сүлжээний алдаа")])
worker._handle(SPEECH, "mn-MN")
events = drain(worker.events)
check("алдааны үед хүлээлт эхлээд буурсан", events[0], ("pending", -1))
check("алдааны эвент", events[1], ("error", "Сүлжээний алдаа"))

# --- Хэл нь сегмент бүрээр дамждаг ---
worker, injector = build([(["hello"], 0.9)])
worker._handle(SPEECH, "en-US")
check("хэл дамжсан", worker.recognizer.langs, ["en-US"])

# --- Чигчлүүр цэвэрлэгээ дамжлагад ажиллана ---
worker, injector = build([(["за ааа маргааш уулзъя"], 0.9)])
worker._handle(SPEECH, "mn-MN")
check("цэвэрлэсэн текст орсон", injector.calls[0][0], "Маргааш уулзъя ")

# --- Зөвхөн чигчлүүр сонсогдвол текст орохгүй ---
worker, injector = build([(["ааа ммм"], 0.9)])
worker._handle(SPEECH, "mn-MN")
check("чигчлүүр эвент", drain(worker.events)[1], ("empty", "filler"))
check("чигчлүүрт текст ороогүй", injector.calls, [])

# --- Цэвэрлэгээ унтраалттай бол хэлсэн чигээрээ ---
worker, injector = build(
    [(["за ааа маргааш уулзъя"], 0.9)],
    cfg={"min_confidence": 0.45, "restore_clipboard": True, "clean_speech": False},
)
worker._handle(SPEECH, "mn-MN")
check("унтраалттай бол хэвээр", injector.calls[0][0], "За ааа маргааш уулзъя ")

# --- Цэвэрлэгээ дуут командыг хөндөхгүй ---
worker, injector = build([(["ааа буцаа"], 0.9)])
worker._handle(SPEECH, "mn-MN")
check("чимээтэй ч буцаах команд ажиллана", drain(worker.events)[1], ("undo", None))

# --- Толь нь хоёр дахь хувилбарыг сонгож чадна ---
worker, injector = build(
    [(["клоуд код бичье", "клауд код бичье"], 0.9)],
    formatter=Formatter(replacements={"клауд": "Claude"}),
)
worker._handle(SPEECH, "mn-MN")
check("толиор сонгосон хувилбар", injector.calls[0][0], "Claude код бичье ")

# --- Толь юу ч заахгүй бол үйлчилгээний эрэмбэ хэвээр ---
worker, injector = build([(["нэг хоёр", "гурав дөрөв"], 0.9)])
worker._handle(SPEECH, "mn-MN")
check("нотолгоогүй бол эхнийх нь", injector.calls[0][0], "Нэг хоёр ")

# --- Оруулах үед гарсан алдаа аппыг унагахгүй ---
worker, injector = build([(["тест"], 0.9)])


def boom(*_args):
    raise RuntimeError("clipboard түгжээтэй")


injector.insert_text = boom
worker._handle(SPEECH, "mn-MN")
check("оруулалт унасан ч үргэлжилсэн", drain(worker.events)[1][0], "recognized")

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
