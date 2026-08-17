"""Ганц хуулбар барих ба "цонхоо нээ" дохионы тест.

Бодит Windows-ийн объект ашиглана (нэрлэсэн event), гэхдээ бүгд нэг процесс
дотор — апп ажиллуулах шаардлагагүй, ажиллаж байсан ч саад болохгүй.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_instance.py
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech.instance import ShowListener, request_show

fails = []

# Ажиллаж байгаа апп жинхэнэ дохиог өөртөө авдаг тул тест өөрийн нэртэй
# объект ашиглана — апп асаалттай эсэхээс үл хамааран ижил үр дүн гарна.
EVENT = f"Local\MonspeechTestShow_{os.getpid()}"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def wait_for(condition, timeout=2.0):
    """Дохио thread-ээр ирдэг тул тогтмол хугацаа хүлээхийн оронд шалгаж хүлээнэ."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


# --- Хүлээгч байхгүй үед дохио хүрэх газаргүй ---
check("хүлээгчгүй үед дохио явахгүй", request_show(EVENT), False)

# --- Хүлээгч дохиог хүлээж авна ---
hits = []
listener = ShowListener(lambda: hits.append(1), EVENT)
listener.start()
check("хүлээгч эхэлсэн", listener._thread is not None and listener._thread.is_alive(), True)

check("дохио илгээгдсэн", request_show(EVENT), True)
check("дохио хүрсэн", wait_for(lambda: len(hits) == 1), True)

# --- Дараалсан дохионууд тус бүр хүрнэ (event нь автоматаар цэвэрлэгддэг) ---
request_show(EVENT)
check("хоёр дахь дохио хүрсэн", wait_for(lambda: len(hits) == 2), True)
request_show(EVENT)
check("гурав дахь дохио хүрсэн", wait_for(lambda: len(hits) == 3), True)

# --- Зогсоосны дараа thread унтарч, дохио хүлээж авахаа болино ---
listener.stop()
check("thread унтарсан", listener._thread, None)
check("дескриптор хаагдсан", listener._handle, None)

before = len(hits)
check("зогссоны дараа дохио хүрэхгүй", request_show(EVENT), False)
time.sleep(0.3)
check("тоолуур хөдлөөгүй", len(hits), before)

# --- Дахин эхлүүлж болно (tray-тэй адил дахин ажиллах чадвар) ---
listener = ShowListener(lambda: hits.append(1), EVENT)
listener.start()
check("дахин эхэлсэн", request_show(EVENT), True)
check("дахин дохио хүрсэн", wait_for(lambda: len(hits) == before + 1), True)
listener.stop()

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
