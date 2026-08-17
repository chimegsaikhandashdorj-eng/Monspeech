"""Танигчийн залгуурын тест — тохиргооноос зөв танигч үүсэж байна уу.

Сүлжээнд огт хандахгүй.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_recognizer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import recognizer
from monspeech.config import DEFAULTS
from monspeech.stt_google import GoogleWebSpeech
from monspeech.stt_openai import OpenAICompatible

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


def cfg(**overrides):
    values = {k: v for k, v in DEFAULTS.items() if k.startswith("stt_")}
    values["lang"] = "mn-MN"
    values.update(overrides)
    return values


# --- Анхны утга: түлхүүр, тохиргоо шаардахгүй ажиллана ---
made = recognizer.create(cfg())
check("анхны утга Google", type(made).__name__, "GoogleWebSpeech")
check("хэл дамжсан", made.lang, "mn-MN")
check("Google түлхүүргүй ажиллана", bool(made.key), True)

# --- Өөрийн үйлчилгээ ---
made = recognizer.create(
    cfg(
        stt_provider="openai",
        stt_url="https://example.test/v1/audio/transcriptions",
        stt_model="whisper-1",
        stt_key="sk-test",
        lang="en-US",
    )
)
check("openai сонгогдсон", type(made).__name__, "OpenAICompatible")
check("хаяг дамжсан", made.url, "https://example.test/v1/audio/transcriptions")
check("загвар дамжсан", made.model, "whisper-1")
check("түлхүүр дамжсан", made.key, "sk-test")
check("хэл дамжсан", made.lang, "en-US")

# --- Танихгүй нэр бол чимээгүй Google руу буцна (гараар засагдсан config) ---
check(
    "танихгүй нэр Google руу",
    type(recognizer.create(cfg(stt_provider="хачин"))).__name__,
    "GoogleWebSpeech",
)
check(
    "хоосон нэр Google руу",
    type(recognizer.create(cfg(stt_provider=""))).__name__,
    "GoogleWebSpeech",
)
check("дутуу тохиргоонд ч унахгүй", type(recognizer.create({})).__name__, "GoogleWebSpeech")

# --- Танигч бүр нэг ижил гэрээтэй ---
for cls in (GoogleWebSpeech, OpenAICompatible):
    for method in ("recognize", "prewarm", "prewarm_async", "close"):
        check(f"{cls.__name__}.{method} бий", callable(getattr(cls, method, None)), True)

# --- Цонхонд харуулах жагсаалт нь тохиргооны нэртэй таарна ---
names = [name for name, _ in recognizer.titles()]
check("жагсаалтын нэрс", names, ["google", "openai"])
check("анхны утга жагсаалтад бий", DEFAULTS["stt_provider"] in names, True)

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
