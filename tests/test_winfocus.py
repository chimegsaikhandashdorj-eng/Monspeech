"""Цонхны гарчиг тааруулах логикийн тест (Win32 API хөндөхгүй).

`match_marker` нь цэвэр функц тул цонх, апп барихгүйгээр шууд шалгана.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_winfocus.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech.winfocus import match_marker

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


APPS = {"Visual Studio Code": "en-US", "Messenger": "mn-MN"}

check(
    "гарчгийн хэсгээр таарна",
    match_marker("app.py - Monspeech - Visual Studio Code", APPS),
    "Visual Studio Code",
)
check("өөр апп", match_marker("Болд — Messenger", APPS), "Messenger")
check("таарахгүй бол None", match_marker("Notepad", APPS), None)
check("хоосон гарчиг", match_marker("", APPS), None)
check("None гарчиг", match_marker(None, APPS), None)
check("тэмдэггүй бол None", match_marker("Visual Studio Code", {}), None)

# Том/жижиг үсэг ялгахгүй — гарчиг нь системээс ямар ч хэлбэрээр ирж болно
check(
    "жижиг үсгээр ч таарна",
    match_marker("хичээл - visual studio code", APPS),
    "Visual Studio Code",
)

# Хоосон тэмдэг бүх гарчигт таарч болзошгүй тул алгасах ёстой
check("хоосон тэмдгийг алгасна", match_marker("Notepad", ["", "Notepad"]), "Notepad")

# Жагсаалт (type_mode_apps) ба толь (lang_apps) хоёулаа ажиллана
check("жагсаалтаар ч ажиллана", match_marker("Terminal — bash", ["Terminal"]), "Terminal")

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
