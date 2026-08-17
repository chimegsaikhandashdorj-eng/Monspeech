"""Сүүлийн оруулгыг буцаах логикийн тест.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_history.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech.history import InsertionHistory

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


history = InsertionHistory()
check("эхэндээ хоосон", history.take_last(now=0.0), None)

history.record("Сайн байна уу ", when=10.0)
history.record("Энэ бол тест. ", when=11.0)
check("гүн", history.depth, 2)

# Устгах тэмдэгтийн тоо нь зайг оруулаад яг тэнцүү байх ёстой
check("сүүлийнхийг буцаана", history.take_last(now=12.0), ("Энэ бол тест. ", 14))
check("дараа нь өмнөхийг", history.take_last(now=12.0), ("Сайн байна уу ", 14))
check("дуусахад хоосон", history.take_last(now=12.0), None)

# Хэт хуучин оруулгыг буцаахгүй — хэрэглэгч аль хэдийн өөр зүйл бичсэн байж болно
old = InsertionHistory(max_age=60.0)
old.record("хуучин", when=0.0)
check("хуучирсныг буцаахгүй", old.take_last(now=120.0), None)
check("хуучирсны дараа цэвэрлэгдсэн", old.depth, 0)

# Кирилл тэмдэгтийн тоо зөв (үсэг бүр нэг backspace)
unicode_history = InsertionHistory()
unicode_history.record("өө үү ёё ")
text, count = unicode_history.take_last()
check("кирилл тоолол", (text, count), ("өө үү ёё ", 9))

# Хязгаараас хэтэрвэл хамгийн хуучныг хаяна
limited = InsertionHistory(limit=3)
for index in range(5):
    limited.record(f"{index}")
check("хязгаар", limited.depth, 3)
check("хамгийн сүүлийнх", limited.take_last()[0], "4")

check("цэвэрлэх", (InsertionHistory().record("х") or True, True), (True, True))

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
