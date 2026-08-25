"""Эвент дамжуулагчийн тест — нэг эвент унасан ч дараалал үхэх ёсгүй.

`_drain_events` нь өөрийгөө `root.after`-аар дахин товлодог. Хэрэв аль нэг
хариу үйлдэл алдаа шидвэл тэр товлолт хийгдэхгүй өнгөрч, апп амьд харагдсаар
байгаад эвент боловсруулахаа БҮРМӨСӨН болино: таньсан текст цонхонд гарахгүй,
төлөв шинэчлэгдэхгүй, статистик хадгалагдахгүй. Хэрэглэгч аппаа хаагаад дахин
нээхээс өөр арга үлдэхгүй тул энэ нь чимээгүй, ноцтой эвдрэл.

Бодит Tk цонх нээхгүй: `MonspeechApp._drain_events`-ыг хуурмаг объект дээр
шууд дуудна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_app_events.py
"""

import queue
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech.app import MonspeechApp

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


class FakeUi:
    def __init__(self):
        self.levels = []

    def set_level(self, level, listening):
        self.levels.append((level, listening))


class FakeStats:
    def __init__(self):
        self.saves = 0

    def save(self, force=False):
        self.saves += 1


class FakeRoot:
    """`after` дуудлагыг тэмдэглэнэ — дахин товлогдсон эсэхийг эндээс мэдэнэ."""

    def __init__(self):
        self.scheduled = []

    def after(self, delay, callback):
        self.scheduled.append((delay, callback))


class FakeApp:
    """`_drain_events`-т хэрэгтэй хамгийн бага гадаргуу."""

    def __init__(self, handlers):
        self.events = queue.Queue()
        self._event_handlers = handlers
        self.ui = FakeUi()
        self.stats = FakeStats()
        self.root = FakeRoot()
        self._level = 0.0
        self.listening = False
        self.keepalives = 0
        self.quits = 0

    def _keepalive(self):
        self.keepalives += 1

    def quit(self):
        self.quits += 1

    def drain(self):
        # `_drain_events` нь өөрийгөө дахин товлохдоо `self._drain_events`-ыг
        # авдаг тул хуурмаг объект дээр тэр нэр байх ёстой.
        self._drain_events = self.drain
        MonspeechApp._drain_events(self)


# ----------------------------------------------------------------------
# Хэвийн урсгал
# ----------------------------------------------------------------------
seen = []
app = FakeApp({"ping": seen.append})
app.events.put(("ping", "нэг"))
app.events.put(("ping", "хоёр"))
app.drain()

check("хоёр эвент боловсрогдлоо", seen, ["нэг", "хоёр"])
check("дараагийн ээлж товлогдлоо", len(app.root.scheduled), 1)
check("статистик хадгалагдлаа", app.stats.saves, 1)


# ----------------------------------------------------------------------
# Танихгүй эвент дарааллыг үхээхгүй (аль хэдийн `continue`-ээр хамгаалагдсан)
# ----------------------------------------------------------------------
app = FakeApp({})
app.events.put(("байхгүй", None))
app.drain()
check("танихгүй эвентийн дараа товлогдсон", len(app.root.scheduled), 1)


# ----------------------------------------------------------------------
# Хариу үйлдэл унасан ч дараалал үргэлжилнэ
# ----------------------------------------------------------------------
def boom(_payload):
    raise RuntimeError("цонхны виджет устсан")


after_boom = []
app = FakeApp({"boom": boom, "ping": after_boom.append})
app.events.put(("boom", None))
app.events.put(("ping", "дараах"))
app.drain()

check("унасан эвентийн дараа ч товлогдсон", len(app.root.scheduled), 1)
check("араас нь ирсэн эвент боловсрогдсон", after_boom, ["дараах"])


# ----------------------------------------------------------------------
# Дараалал цэвэрлэсний дараах ажил унасан ч товлолт хийгдэнэ
# ----------------------------------------------------------------------
class ExplodingUi(FakeUi):
    def set_level(self, level, listening):
        raise RuntimeError("цонх хаагдсан")


app = FakeApp({})
app.ui = ExplodingUi()
app.drain()
check("цонх унасан ч товлогдсон", len(app.root.scheduled), 1)


# ----------------------------------------------------------------------
# "quit" нь дуусгах ёстой — дахин товлохгүй
# ----------------------------------------------------------------------
app = FakeApp({})
app.events.put(("quit", None))
app.drain()
check("гарахад дахин товлогдоогүй", len(app.root.scheduled), 0)
check("гарах дуудагдсан", app.quits, 1)


print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
