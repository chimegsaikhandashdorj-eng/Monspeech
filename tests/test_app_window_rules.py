"""Аппаар ялгах дүрмүүдийн тест: хэл, шууд бичих, цэвэрлэгээ.

Гурвуулаа нэг л тааруулагч (`winfocus.match_marker`) дээр суудаг ч тус бүрдээ
өөр нөхцөлтэй: хэл нь утга буцаадаг хүснэгт, нөгөө хоёр нь жагсаалт. Бодит Tk
цонх, Win32 API хөндөхгүй — `MonspeechApp`-ийн аргуудыг хуурмаг объект дээр
шууд дуудна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_app_window_rules.py
"""

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


class FakeTarget:
    def __init__(self, title):
        self._title = title

    def title(self):
        return self._title


class FakeApp:
    """`MonspeechApp`-аас зөвхөн шалгах аргуудыг зээлж авна."""

    _match_window = MonspeechApp._match_window
    _window_lang = MonspeechApp._window_lang
    _window_clean = MonspeechApp._window_clean
    _window_verbatim = MonspeechApp._window_verbatim
    _insert_mode = MonspeechApp._insert_mode
    _remember_window_in = MonspeechApp._remember_window_in
    remember_no_clean_app = MonspeechApp.remember_no_clean_app
    remember_type_mode_app = MonspeechApp.remember_type_mode_app

    def __init__(self, title, **overrides):
        self.target = FakeTarget(title)
        self.cfg = SavingCfg(
            {
                "lang": "mn-MN",
                "lang_apps": {},
                "clean_speech": True,
                "verbatim_mode": False,
                "no_clean_apps": [],
                "type_mode": False,
                "type_mode_apps": [],
                **overrides,
            }
        )


class SavingCfg(dict):
    """`Config`-ийн оронд: хадгалалт хэдэн удаа дуудагдсаныг тоолно."""

    def __init__(self, values):
        super().__init__(values)
        self.saves = 0

    def save(self):
        self.saves += 1


def app(title, **overrides):
    return FakeApp(title, **overrides)


# --- Цэвэрлэгээ: ерөнхий тохиргоо + цонхны үл хамаарах зүйл ---
check("анхдагчаар цэвэрлэнэ", app("Notepad")._window_clean(), True)
check(
    "жагсаалтад байвал цэвэрлэхгүй",
    app("Ярианы тэмдэглэл - Obsidian", no_clean_apps=["Obsidian"])._window_clean(),
    False,
)
check(
    "өөр цонхонд хэвээр",
    app("Messenger", no_clean_apps=["Obsidian"])._window_clean(),
    True,
)
# Ерөнхий тохиргоо унтраалттай бол цонхны жагсаалт үүнийг АСААХГҮЙ — жагсаалт
# нь зөвхөн хасалт, нэмэлт биш
check(
    "унтраалттай бол цонх ч асаахгүй",
    app("Obsidian", clean_speech=False, no_clean_apps=["Obsidian"])._window_clean(),
    False,
)
check("унтраалттай бол бүх цонхонд", app("Notepad", clean_speech=False)._window_clean(), False)
check("глобал үгчлэн", app("Notepad", verbatim_mode=True)._window_verbatim(), True)
check(
    "цонхны үгчлэн",
    app("Тэмдэглэл - Obsidian", no_clean_apps=["Obsidian"])._window_verbatim(),
    True,
)

# --- Хэл: хүснэгтээс утга ---
check("тохирох цонхны хэл", app("app.py - Code", lang_apps={"Code": "en-US"})._window_lang(), "en-US")
check("тохирохгүй бол үндсэн", app("Messenger", lang_apps={"Code": "en-US"})._window_lang(), "mn-MN")

# --- Шууд бичих ---
check("анхдагчаар буулгана", app("Notepad")._insert_mode(), "paste")
check("жагсаалтад байвал шууд", app("Notepad", type_mode_apps=["Notepad"])._insert_mode(), "type")
check("ерөнхий тохиргоо дийлнэ", app("Notepad", type_mode=True)._insert_mode(), "type")

# --- Цонх санах: хоёр жагсаалт нэг механизмаар ---
one = app("Тэмдэглэл - Obsidian")
check(
    "цэвэрлэхгүй цонх нэмэгдэв",
    one.remember_no_clean_app(),
    "«Obsidian» цонхонд одооноос үгчлэн бичнэ.",
)
check("жагсаалтад орсон", one.cfg["no_clean_apps"], ["Obsidian"])
check("хадгалагдсан", one.cfg.saves, 1)
check("одоо цэвэрлэхгүй", one._window_clean(), False)
check("давхар нэмэхгүй", one.remember_no_clean_app(), "«Obsidian» аль хэдийн жагсаалтад байна.")
check("дахин хадгалаагүй", one.cfg.saves, 1)

two = app("Untitled - Notepad")
check(
    "шууд бичих цонх нэмэгдэв",
    two.remember_type_mode_app(),
    "«Notepad» цонхонд одооноос шууд бичнэ.",
)
check("хоёр жагсаалт хоорондоо хөндөлдөхгүй", two.cfg["no_clean_apps"], [])

check("гарчиггүй цонх", app("").remember_no_clean_app(), "Цонх тодорхойгүй байна.")

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
