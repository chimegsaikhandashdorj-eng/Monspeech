"""Автомат эхлүүлэлтийн тест.

Жинхэнэ `Run` түлхүүрийг хөндөхгүй — HKCU дор тусдаа туршилтын түлхүүр
ашиглаад төгсгөлд нь устгана.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_autostart.py
"""

import sys
import winreg
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import autostart

fails = []

TEST_KEY = r"Software\MonspeechTest\Run"
TEST_VALUE = "MonspeechTestEntry"


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def cleanup():
    for path in (TEST_KEY, r"Software\MonspeechTest"):
        try:
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)
        except OSError:
            pass


try:
    # --- Эх кодоос ажиллах үеийн тушаал ---
    command = autostart.command()
    check("тушаал хашилтанд орсон", command.startswith('"'), True)
    check("Monspeech.bat-ыг заасан", command.lower().endswith('monspeech.bat"'), True)

    # --- Багцалсан (.exe) горим ---
    sys.frozen = True  # PyInstaller ингэж тэмдэглэдэг
    try:
        frozen_command = autostart.command()
    finally:
        del sys.frozen
    check("багцалсан үед өөрийгөө заана", frozen_command, f'"{Path(sys.executable)}"')
    check("багцалсан үед .bat заахгүй", "monspeech.bat" in frozen_command.lower(), False)

    # --- Асаах / унтраах ---
    cleanup()
    check("эхэндээ унтраалттай", autostart.enabled(TEST_KEY, TEST_VALUE), False)

    error = autostart.apply(True, TEST_KEY, TEST_VALUE)
    check("асаахад алдаагүй", error, None)
    check("асаалттай болсон", autostart.enabled(TEST_KEY, TEST_VALUE), True)

    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, TEST_KEY) as key:
        stored, kind = winreg.QueryValueEx(key, TEST_VALUE)
    check("бүртгэлд текст хэлбэрээр", kind, winreg.REG_SZ)
    check("бүртгэсэн тушаал", stored, autostart.command())

    error = autostart.apply(False, TEST_KEY, TEST_VALUE)
    check("унтраахад алдаагүй", error, None)
    check("унтарсан", autostart.enabled(TEST_KEY, TEST_VALUE), False)

    # --- Байхгүй утгыг дахин унтраах нь алдаа биш ---
    check("давхар унтраахад алдаагүй", autostart.apply(False, TEST_KEY, TEST_VALUE), None)

    # --- Ижил нэртэй ч ӨӨР програмын бичлэгийг хүндэтгэнэ ---
    # (бодит машин дээр `Monspeech` нэртэй бичлэг өөр төсөл рүү заасан байсан)
    other = '"C:\\Program Files\\Other\\other.exe"'
    with winreg.CreateKeyEx(
        winreg.HKEY_CURRENT_USER, TEST_KEY, 0, winreg.KEY_SET_VALUE
    ) as key:
        winreg.SetValueEx(key, TEST_VALUE, 0, winreg.REG_SZ, other)
    check("өөрийн бичлэг биш тул унтраалттай", autostart.enabled(TEST_KEY, TEST_VALUE), False)
    autostart.apply(False, TEST_KEY, TEST_VALUE)
    check("унтраахад өөрийн бус бичлэг үлдсэн", autostart.current(TEST_KEY, TEST_VALUE), other)
    autostart.apply(True, TEST_KEY, TEST_VALUE)
    check("асаахад бидний тушаал болсон", autostart.current(TEST_KEY, TEST_VALUE), autostart.command())
    autostart.apply(False, TEST_KEY, TEST_VALUE)
    check("бидний бичлэг устсан", autostart.current(TEST_KEY, TEST_VALUE), None)

    # --- Тохируулж чадахгүй үед унахгүй, мессеж буцаана ---
    # (хүчингүй түлхүүрийн нэр — бодит амьдрал дээр эрхгүй байх, бодлогоор
    #  хаагдсан байх зэрэг шалтгаанаар ижил замаар унана)
    denied = autostart.apply(True, "Software\\Monspeech\x00Test", TEST_VALUE)
    check("тохируулж чадахгүй үед мессеж", isinstance(denied, str), True)
    check("тэр үед асаалттай гэж хэлэхгүй", autostart.enabled(TEST_KEY, TEST_VALUE), False)
finally:
    cleanup()

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
