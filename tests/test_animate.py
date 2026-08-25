"""Хөдөлгөөний цөмийн тест — өнгө холих, эвэрлэлт, `Motion`-ий зан төлөв.

Жинхэнэ Tk цонх хэрэгтэй (`after` төлөвлөхийн тулд) ч дэлгэц дээр гаргахгүй.
Дэлгэцгүй орчинд чимээгүй алгасна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_animate.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно

import tkinter as tk

from monspeech import animate

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def near(label, got, want, tolerance=0.06):
    ok = abs(got - want) <= tolerance
    if not ok:
        fails.append(f"{label}: got {got!r} want ~{want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got:.3f}")


# --- Өнгө холих: захууд яг таг, дунд нь жигд ---
check("0 бол эхнийх", animate.mix("#000000", "#ffffff", 0.0), "#000000")
check("1 бол сүүлийнх", animate.mix("#000000", "#ffffff", 1.0), "#ffffff")
check("хагас нь дунд", animate.mix("#000000", "#ffffff", 0.5), "#808080")
# Хязгаараас гарсан утга нь захдаа хавчигдана — тооцоо нь хэзээ ч
# буруу өнгө (сөрөг сувагтай) гаргах ёсгүй.
check("сөрөг нь хавчигдана", animate.mix("#000000", "#ffffff", -3.0), "#000000")
check("нэгээс их нь хавчигдана", animate.mix("#000000", "#ffffff", 9.0), "#ffffff")
check("сувгууд тусдаа холигдоно", animate.mix("#ff0000", "#0000ff", 0.5), "#800080")

# --- Эвэрлэлт: хурдан эхэлж, зөөлөн зогсоно ---
check("эхлэл нь тэг", animate.ease_out(0.0), 0.0)
check("төгсгөл нь нэг", animate.ease_out(1.0), 1.0)
# Хагас хугацаанд ХАГАСААС ИЛҮҮ явсан байх ёстой — эс бөгөөс «хурдан
# эхэлдэг» гэсэн шинж алдагдана.
check("хагаст нь хагасаас илүү", animate.ease_out(0.5) > 0.5, True)

# --- Шатлуулалт: кэш хязгаартай байлгах ---
check("шатанд нааж бөөгнөрүүлнэ", animate.quantise(0.51, 4), 0.5)
check("захын утга хэвээр", animate.quantise(1.0, 12), 1.0)
check("шатны тоо баримталагдана", len({animate.quantise(i / 97, 8) for i in range(98)}), 9)

# --- Motion ---
try:
    root = tk.Tk()
    root.withdraw()
except tk.TclError:  # дэлгэцгүй орчин (CI)
    print("\nДэлгэц алга — Motion-ий тестийг алгаслаа.")
    print("ALL PASS" if not fails else "FAILED")
    for line in fails:
        print(" ", line)
    sys.exit(1 if fails else 0)

frame = tk.Frame(root)
seen = []

animate.enabled = True
motion = animate.Motion(frame, seen.append, ms=120)
motion.to(1.0)
check("эхний кадр нь эхлэлээсээ", seen[0] < 0.2, True)

deadline = time.monotonic() + 2.0
while motion.value < 0.999 and time.monotonic() < deadline:
    root.update()
    time.sleep(0.008)
near("зорилгодоо хүрлээ", motion.value, 1.0, 0.001)
check("олон кадраар явсан", len(seen) > 3, True)
check("утга нь өсөж явсан", seen == sorted(seen), True)

# Дунд нь чиглэл солиход БАЙГАА утгаасаа үргэлжилнэ — эс бөгөөс үсэрнэ
motion.to(0.0)
root.update()
mid = motion.value
check("буцахдаа нэгээс эхэлсэн", 0.8 < mid <= 1.0, True)

# Хөдөлгөөн унтраасан үед зорилгодоо ТЭР ДОР НЬ очно
animate.enabled = False
instant = animate.Motion(frame, lambda _v: None)
instant.to(1.0)
check("унтраасан үед шууд", instant.value, 1.0)

# `jump` нь хөдөлгөөнөөс үл хамааран шууд тавина
animate.enabled = True
jumped = []
quick = animate.Motion(frame, jumped.append)
quick.jump(0.42)
check("jump шууд хэрэгжинэ", quick.value, 0.42)
check("jump нэг л удаа зурна", jumped, [0.42])

# Устсан виджет дээр хөдөлгөөн эхлүүлэхэд апп унах ёсгүй
dead = tk.Frame(root)
gone = animate.Motion(dead, lambda _v: None)
dead.destroy()
gone.to(1.0)  # алдаа шидэх ёсгүй
check("устсан виджет аюулгүй", gone.value, 1.0)

root.destroy()

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
