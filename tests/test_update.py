"""Шинэчлэл шалгах логикийн тест (сүлжээ хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_update.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import __version__, update

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


# --- Хувилбар задлах ---
check("энгийн", update.parse_version("1.2.3"), (1, 2, 3))
check("v угтвартай", update.parse_version("v0.1.0"), (0, 1, 0))
check("шошготой", update.parse_version("v1.2.3-beta.4"), (1, 2, 3, 4))
check("тоогүй", update.parse_version("хувилбар"), ())
check("хоосон", update.parse_version(""), ())
check("None", update.parse_version(None), ())

# --- Харьцуулах ---
check("шинэ нь их", update.is_newer("0.2.0", "0.1.0"), True)
check("хуучин нь бага", update.is_newer("0.1.0", "0.2.0"), False)
check("тэнцүү бол шинэ биш", update.is_newer("0.1.0", "0.1.0"), False)
check("v угтвар саад биш", update.is_newer("v0.1.1", "0.1.0"), True)
check("богиныг тэгээр гүйцээнэ", update.is_newer("1.2", "1.2.0"), False)
check("богино нь бага", update.is_newer("1.2", "1.2.1"), False)
check("богино нь их", update.is_newer("1.3", "1.2.9"), True)
check("10 нь 9-өөс их", update.is_newer("0.10.0", "0.9.0"), True)
# Утга нь ойлгомжгүй бол ХЭЗЭЭ Ч шинэчлэл гэж мэдэгдэхгүй
check("тоогүй шошго", update.is_newer("latest", "0.1.0"), False)
check("одоогийнх нь тоогүй", update.is_newer("0.2.0", "хачин"), False)

# --- Releases API-ийн хариу ---
parse = update._parse
check("шошго авна", parse('{"tag_name": "v0.2.0"}'), "v0.2.0")
check("зайг тайрна", parse('{"tag_name": "  v0.2.0  "}'), "v0.2.0")
check("шошго байхгүй бол нэр", parse('{"name": "0.3.0"}'), "0.3.0")
check("ноорог тоохгүй", parse('{"tag_name": "v9.0.0", "draft": true}'), None)
check("урьдчилсан тоохгүй", parse('{"tag_name": "v9.0.0", "prerelease": true}'), None)
check("хоосон объект", parse("{}"), None)
check("эвдэрсэн JSON", parse("{"), None)
check("жагсаалт ирвэл", parse("[]"), None)

# --- Одоогийн хувилбар нь өөрөө зөв хэлбэртэй байх ёстой ---
check("аппын хувилбар задлагдана", bool(update.parse_version(__version__)), True)
check("өөрөөсөө шинэ биш", update.is_newer(__version__, __version__), False)

# --- Хаягууд ---
check("API зам", update.API_PATH.startswith("/repos/"), True)
check("Releases холбоос", update.RELEASES_URL.startswith("https://github.com/"), True)

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
