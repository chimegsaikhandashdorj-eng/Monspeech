"""Дуут үйлдлүүдийн (буцаа, давт, хуулж ав) аппын талын тест.

Бодит Tk цонх, микрофон, clipboard хөндөхгүй: `MonspeechApp`-ийн методуудыг
хуурмаг объект дээр шууд дуудна. Шалгах гол зүйл нь курсор дээр ЯГ юу очих вэ
гэдэг — буруу тооны backspace явбал хэрэглэгчийн бичсэн текст устана.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_app_actions.py
"""

import queue
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import app as app_module
from monspeech.app import MonspeechApp, _times
from monspeech.history import InsertionHistory
from monspeech.samples import HardSampleStore

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


class FakeUi:
    def __init__(self):
        self.details = []

    def set_detail(self, text):
        self.details.append(text)


class FakeOverlay:
    def __init__(self):
        self.flashes = []

    def flash(self, text, kind="info"):
        self.flashes.append((text, kind))


class FakeApp:
    """Үйлдлийн методуудад хэрэгтэй хамгийн бага гадаргуу."""

    def __init__(self, texts=()):
        self.insertions = InsertionHistory()
        for text in texts:
            self.insertions.record(text)
        self.ui = FakeUi()
        self.overlay = FakeOverlay()
        self.cfg = {"wave_overlay": True}
        self.events = queue.Queue()
        self.delivered = []
        # Түр хавтас — жинхэнэ `%AppData%`-г хөндөхгүй
        self.samples = HardSampleStore(
            directory=Path(tempfile.mkdtemp()), enabled=True
        )

    def _deliver(self, text, backspaces, remember=True):
        self.delivered.append((text, backspaces, remember))

    # Ажлын thread-ээс дуудагддаг тул жинхэнэ хувилбарыг нь ашиглана
    _copied = MonspeechApp._copied
    copy_text = MonspeechApp.copy_text
    # Засварын шошгууд нь ангийн талбар — хуурмаг объектод ч хэрэгтэй
    EDIT_LABELS = MonspeechApp.EDIT_LABELS


def undo(app, times=1):
    MonspeechApp.undo_last(app, times)
    return app


def repeat(app, times=1):
    MonspeechApp.repeat_last(app, times)
    return app


# ----------------------------------------------------------------------
# Буцаах
# ----------------------------------------------------------------------
app = undo(FakeApp(["сайн байна "]))
check("нэг оруулга буцаав", app.delivered, [("", 11, False)])

# Хоёр оруулга курсор дээр зэрэгцээ байгаа тул НЭГ устгалаар явна
app = undo(FakeApp(["нэг ", "хоёр "]), times=2)
check("хоёр оруулгын нийлбэр", app.delivered, [("", 9, False)])
check("тоог мэдэгдэв", app.ui.details, ["Буцаалаа ×2 (9 тэмдэгт)."])

# Хүссэнээс цөөн оруулга байсан ч байгаа хэрээр нь буцаана
app = undo(FakeApp(["ганц "]), times=5)
check("байгаа хэрээр", app.delivered, [("", 5, False)])

app = undo(FakeApp())
check("буцаах зүйлгүй бол оруулалт хийхгүй", app.delivered, [])
check("буцаах зүйлгүйг хэлнэ", app.ui.details, ["Буцаах зүйл алга."])
check("анхааруулга улаанаар", app.overlay.flashes, [("Буцаах зүйл алга", "warning")])


# ----------------------------------------------------------------------
# Давтах
# ----------------------------------------------------------------------
app = repeat(FakeApp(["сайн байна "]))
check("сүүлийнхийг дахин бичив", app.delivered, [("сайн байна ", 0, True)])
check("давтсаныг санана (remember=True)", app.delivered[0][2], True)
check("давтахад түүх хоосорсонгүй", app.insertions.depth, 1)

app = repeat(FakeApp(["за "]), times=3)
check("гурав давтав", app.delivered, [("за за за ", 0, True)])

app = repeat(FakeApp())
check("давтах зүйлгүй бол оруулалт хийхгүй", app.delivered, [])
check("давтах зүйлгүйг хэлнэ", app.ui.details, ["Давтах зүйл алга."])


# ----------------------------------------------------------------------
# Clipboard руу хуулах — курсор дээр ЮУ Ч оруулахгүй байх нь чухал
# ----------------------------------------------------------------------
class FakeInjector:
    def __init__(self, ok=True):
        self.ok = ok
        self.copied = []

    def copy_to_clipboard(self, text):
        self.copied.append(text)
        return self.ok


real_injector = app_module.injector
try:
    fake = FakeInjector()
    app_module.injector = fake
    app = FakeApp(["сайн байна "])
    MonspeechApp.copy_last(app)
    kind, payload = app.events.get(timeout=5)  # ажлын thread дуустал хүлээнэ
    # Хуулахдаа захын зайг таслана — 11 биш 10 тэмдэгт
    check("хуулах эвент", (kind, payload), ("copied", 10))
    check("зөвхөн текстийг хуулав", fake.copied, ["сайн байна"])
    check("курсорт юу ч ороогүй", app.delivered, [])

    # Дурын текстийг ч хуулж болно — Төлөв хуудасны түүхийн мөр үүнийг дуудна
    fake.copied.clear()
    app = FakeApp()
    MonspeechApp.copy_text(app, "  хурлын тэмдэглэл  ")
    kind, payload = app.events.get(timeout=5)
    check("дурын текст хуулагдав", (kind, payload), ("copied", 16))
    check("захын зай тасарсан", fake.copied, ["хурлын тэмдэглэл"])
    check("оруулалт хийгээгүй", app.delivered, [])

    # Хоосон мөрөөс thread ч эхлэхгүй — clipboard-ыг дэмий хөндөхгүй
    fake.copied.clear()
    app = FakeApp()
    MonspeechApp.copy_text(app, "   ")
    check("хоосон текстийг үл хуулна", fake.copied, [])
    check("хоосон үед эвент гарахгүй", app.events.empty(), True)

    app_module.injector = FakeInjector(ok=False)
    app = FakeApp(["сайн байна "])
    MonspeechApp.copy_last(app)
    kind, _ = app.events.get(timeout=5)
    check("clipboard завгүй бол алдаа", kind, "error")

    app = FakeApp()
    MonspeechApp.copy_last(app)
    check("хуулах зүйлгүйг хэлнэ", app.ui.details, ["Хуулах зүйл алга."])
    check("хуулах зүйлгүй бол эвент явахгүй", app.events.empty(), True)
finally:
    app_module.injector = real_injector


# ----------------------------------------------------------------------
# Хувилбар сэлгэх
# ----------------------------------------------------------------------
class FakeStore:
    def __init__(self):
        self.replaced = []

    def replace(self, entry, text):
        self.replaced.append((entry, text))
        entry["text"] = text


class FakeFormatter:
    def __init__(self):
        self.remembered = []

    def remember(self, text):
        self.remembered.append(text)


def variant_app(items, inserted=None, learn=False):
    app = FakeApp([inserted if inserted is not None else items[0]])
    app.cfg["learn_corrections"] = learn
    app.transcripts = FakeStore()
    app.formatter = FakeFormatter()
    app.entry = {"text": items[0].strip()}
    app._variants = {"items": list(items), "index": 0, "entry": app.entry}
    app.learned = []
    app._learn_pair = lambda heard, corrected: app.learned.append((heard, corrected))
    app.ui.refresh_history = lambda: None
    return app


app = variant_app(["Клауд код ", "Клоуд код "])
# Дамжлага таналтын дууг санаж үлдээсэн гэж дүрсэлнэ — сэлгэх нь түүнийг
# «зөв хариу нь энэ» гэсэн benchmark мөр болгох ёстой.
app.samples.remember(b"ab" * 8000, app.entry)
MonspeechApp.cycle_variant(app)
check("хуучныг устгаад шинийг оруулав", app.delivered, [("Клоуд код ", 10, True)])
check("түүх шинэчлэгдэв", app.entry["text"], "Клоуд код")
check("толинд жин болов", app.formatter.remembered, ["Клоуд код"])
check("хувилбарын дугаар", app.ui.details, ["Хувилбар 2/2: Клоуд код"])
check("дуу нь зөв текстийн хамт хадгалагдав", app.samples.count, 1)
check("зөв хариу нь бичигдэв", app.samples.entries[0]["text"], "Клоуд код")
check("буруу нь ч үлдэв", app.samples.entries[0]["heard"], "Клауд код")
check("шалтгаан нь засвар", app.samples.entries[0]["reason"], "corrected")

# Тойрог: сүүлийнхээс эхнийх рүү буцна
app.insertions.record("Клоуд код ")
MonspeechApp.cycle_variant(app)
check("тойрог хаагдав", app.delivered[-1], ("Клауд код ", 10, True))

# Хэрэглэгч энэ хооронд өөр зүйл бичсэн бол хөндөхгүй
app = variant_app(["Нэг ", "Хоёр "], inserted="Гараар бичсэн ")
MonspeechApp.cycle_variant(app)
check("өөрчлөгдсөн бол оруулахгүй", app.delivered, [])
check("төлөв цэвэрлэгдэв", app._variants, None)
check("шалтгааныг хэлнэ", app.ui.details, ["Текст өөрчлөгдсөн — хувилбар сэлгэсэнгүй."])

# Хувилбаргүй үед
app = FakeApp(["Сайн "])
app._variants = None
MonspeechApp.cycle_variant(app)
check("хувилбар алга", app.ui.details, ["Сэлгэх хувилбар алга."])

# Сурах асаалттай бол ҮРГЭЛЖ эхний хувилбартай харьцуулж сурна
app = variant_app(["Нэг ", "Хоёр ", "Гурав "], learn=True)
MonspeechApp.cycle_variant(app)
app.insertions.record("Хоёр ")
MonspeechApp.cycle_variant(app)
check("эхнийхээс нь сурсан", app.learned, [("Нэг", "Хоёр"), ("Нэг", "Гурав")])


# ----------------------------------------------------------------------
# Дуут засвар
# ----------------------------------------------------------------------
def edit_app(inserted, learn=False):
    app = FakeApp([inserted])
    app._variants = {"items": ["хуучин "], "index": 0, "entry": {}}
    return app


app = edit_app("нэг хоёр гурав ")
MonspeechApp.edit_last(app, "drop_words", "2")
check("хуучныг бүтнээр сольсон", app.delivered, [("нэг ", 15, True)])
check("хувилбарын төлөв цэвэрлэгдэв", app._variants, None)
check("хэрэглэгчид хэллээ", app.ui.details, ["Устгалаа: нэг"])

app = edit_app("сайн байна ")
MonspeechApp.edit_last(app, "capitalize")
check("том үсэг болов", app.delivered, [("сайн Байна ", 11, True)])

app = edit_app("клауд ")
MonspeechApp.edit_last(app, "replace_word", "Claude")
check("сүүлийн үг солигдов", app.delivered, [("Claude ", 6, True)])

# Засах зүйл байхгүй үед курсорыг хөндөхгүй
app = edit_app("сайн байна")
MonspeechApp.edit_last(app, "no_space")
check("зайгүй бол оруулалт хийхгүй", app.delivered, [])
check("шалтгааныг хэлнэ", app.ui.details, ["Засах зүйл олдсонгүй."])

app = FakeApp()
app._variants = None
MonspeechApp.edit_last(app, "capitalize")
check("текстгүй бол хэлнэ", app.ui.details, ["Засах текст алга."])


# ----------------------------------------------------------------------
# Эвентийн аргументыг тоо болгох
# ----------------------------------------------------------------------
check("товчлуураас ирсэн None", _times(None), 1)
check("дуут командгүй хоосон мөр", _times(""), 1)
check("тоон мөр", _times("3"), 3)
check("тэг ба сөрөг нь 1 болно", (_times("0"), _times("-2")), (1, 1))
check("утгагүй мөр", _times("хоёр"), 1)


print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
