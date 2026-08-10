"""Тохиргоо унших, баталгаажуулах тест.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_config.py
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech import config as config_module
from monspeech.config import DEFAULTS, Config

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def load_with(raw) -> Config:
    """Өгсөн агуулгатай файлаас тохиргоо уншина (raw=None бол файлгүй)."""
    folder = Path(tempfile.mkdtemp())
    config_module.CONFIG_PATH = folder / "config.json"
    if raw is not None:
        config_module.CONFIG_PATH.write_text(
            json.dumps(raw, ensure_ascii=False), encoding="utf-8"
        )
    return Config.load()


# --- Анхны утгууд хуваалцагдахгүй байх ---
# Гүехэн хуулбар үед `snippets` нь DEFAULTS-тэй нэг объект болж, нэг дээр нь
# бичсэн зүйл нөгөөд нь бас гарч ирдэг байсан.
first = load_with(None)
second = load_with(None)
first["snippets"]["туршилт"] = "утга"
first["type_mode_apps"].append("Notepad")
first["replacements"]["а"] = "б"

check("DEFAULTS цэвэр хэвээр", DEFAULTS["snippets"], {})
check("type_mode_apps цэвэр хэвээр", DEFAULTS["type_mode_apps"], [])
check("өөр хуулбарт нөлөөлөөгүй", second["snippets"], {})
check("өөр хуулбарын жагсаалт", second["type_mode_apps"], [])
check("орлуулга ч тусдаа", second["replacements"], {})

# --- Файлаас уншсан утгууд ---
loaded = load_with({"lang": "en-US", "silence_hold": 0.9, "mic_index": 3})
check("хэл уншигдсан", loaded["lang"], "en-US")
check("завсарлага уншигдсан", loaded["silence_hold"], 0.9)
check("микрофон уншигдсан", loaded["mic_index"], 3)

# --- Буруу утгыг хаяж, анхны утгаа барина ---
bad = load_with(
    {
        "silence_hold": "удаан",  # огт тоо биш
        "min_confidence": 5.0,  # хүрээнээс гадуур
        "max_recording_seconds": -10,  # сөрөг
        "lang": 7,  # буруу төрөл
        "tray_enabled": 1,  # bool биш
        "танихгүй": True,  # байхгүй түлхүүр
    }
)
check("текст завсарлага хаягдсан", bad["silence_hold"], DEFAULTS["silence_hold"])
check("хэт өндөр итгэлцэл хаягдсан", bad["min_confidence"], DEFAULTS["min_confidence"])
check("сөрөг хугацаа хаягдсан", bad["max_recording_seconds"], DEFAULTS["max_recording_seconds"])
check("буруу төрлийн хэл хаягдсан", bad["lang"], DEFAULTS["lang"])
check("1 нь True болохгүй", bad["tray_enabled"], DEFAULTS["tray_enabled"])
check("танихгүй түлхүүр орж ирээгүй", "танихгүй" in bad, False)

# --- Бүхэл тоо ба бутархай солигдох нь зүгээр ---
mixed = load_with({"silence_hold": 1, "mic_keep_open_seconds": 30.0})
check("бүхэл тоог хүлээж авна", mixed["silence_hold"], 1)
check("бутархайг хүлээж авна", mixed["mic_keep_open_seconds"], 30.0)

# --- Эвдэрсэн файл ---
folder = Path(tempfile.mkdtemp())
config_module.CONFIG_PATH = folder / "config.json"
config_module.CONFIG_PATH.write_text("{ энэ бол JSON биш", encoding="utf-8")
check("эвдэрсэн файл анхны утга өгнө", Config.load()["lang"], DEFAULTS["lang"])

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
