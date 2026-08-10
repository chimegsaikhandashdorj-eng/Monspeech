"""Текст цэгцлэх логикийн тест.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_textproc.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech.textproc import (
    Formatter,
    format_replacements,
    learn_corrections,
    match_action,
    parse_replacements,
)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


f = Formatter()
check("энгийн", f.format("сайн байна уу"), ("Сайн байна уу ", 0))
# Тусдаа ирсэн "цэг" нь өмнөх хэсгийн үлдээсэн зайг устгана (backspace=1)
check("цэг тусдаа хэсэг", f.format("цэг"), (". ", 1))
check("шинэ өгүүлбэр том үсэг", f.format("өнөөдөр сайхан байна"), ("Өнөөдөр сайхан байна ", 0))
# Өмнөх хэсэг цэгээр төгсөөгүй тул үргэлжлэл гэж үзнэ
check(
    "нэг хэсэг дотор цэг",
    f.format("би ирлээ цэг чи хаана байна асуултын тэмдэг"),
    ("би ирлээ. Чи хаана байна? ", 0),
)
check("шинэ мөр", f.format("шинэ мөр дараагийн мөр"), ("\nДараагийн мөр ", 1))
f.reset()
check("таслал дунд", f.format("нэг таслал хоёр таслал гурав"), ("Нэг, хоёр, гурав ", 0))
f.reset()
check("хаалт", f.format("тэмдэглэл хаалт нээх чухал хаалт хаах"), ("Тэмдэглэл (чухал) ", 0))
f.reset()
check("англи команд", f.format("hello comma world period"), ("Hello, world. ", 0))
check("хоосон", f.format("   "), ("", 0))

f2 = Formatter(auto_space=False, auto_capitalize=False)
check("тохиргоо унтраасан", f2.format("сайн уу цэг"), ("сайн уу.", 0))

f3 = Formatter(voice_punctuation=False)
check("дуут цэг унтраалттай", f3.format("сайн уу цэг"), ("Сайн уу цэг ", 0))

f4 = Formatter(replacements={"клауд": "Claude", "хоёр": "2"})
check("үг солих", f4.format("клауд бол сайн хоёр"), ("Claude бол сайн 2 ", 0))
f4.reset()
check("үг солих тэмдэгттэй", f4.format("клауд, тийм"), ("Claude, тийм ", 0))

mapping = parse_replacements("клауд=Claude\n# сэтгэгдэл\n\nбуруу = зөв\nмуу\n")
check("толь задлах", mapping, {"клауд": "Claude", "буруу": "зөв"})
check("толь бичих", format_replacements(mapping), "буруу=зөв\nклауд=Claude")

# --- олон үгтэй хэллэг солих ---
f6 = Formatter(replacements={"сайн байна уу": "Сайн байцгаана уу", "клауд": "Claude"})
check(
    "хэллэг солих",
    f6.format("сайн байна уу клауд"),
    ("Сайн байцгаана уу Claude ", 0),
)
f6.reset()
check("хэллэг таарахгүй бол хэвээр", f6.format("сайн уу"), ("Сайн уу ", 0))

# --- дуут үйлдэл (зөвхөн дангаар нь хэлсэн үед) ---
# --- дуут товчлол ---
f7 = Formatter(snippets={"миний хаяг": "Улаанбаатар хот, 1-р хороо"})
check(
    "товчлол тэлнэ",
    f7.format("надад миний хаяг руу илгээ"),
    ("Надад Улаанбаатар хот, 1-р хороо руу илгээ ", 0),
)
f7.reset()
check("товчлолгүй үг хэвээр", f7.format("миний ном"), ("Миний ном ", 0))

# --- засвараас сурах ---
check("нэг үг сурна", learn_corrections("клауд код бичлээ", "Claude код бичлээ"),
      {"клауд": "Claude"})
check("урт зөрвөл сурахгүй", learn_corrections("нэг хоёр", "нэг хоёр гурав"), {})
check("хэт олон зөрвөл сурахгүй",
      learn_corrections("өөр өөр өөр өөр", "нэг хоёр гурав дөрөв"), {})
check("зөвхөн том үсэг бол сурахгүй",
      learn_corrections("сайн байна уу", "Сайн байна уу"), {})
check("хоёр үг сурна",
      learn_corrections("клауд болон монспич", "Claude болон Monspeech"),
      {"клауд": "Claude", "монспич": "Monspeech"})

check("буцаах команд", match_action("буцаа"), "undo")
check("цэгтэй ч таних", match_action("Устга."), "undo")
check("өгүүлбэр дунд байвал үйлдэл биш", match_action("энэ файлыг устга"), None)
check("энгийн үг", match_action("сайн байна уу"), None)

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
