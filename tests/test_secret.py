"""DPAPI түлхүүр шифрлэлтийн тест.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_secret.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech import secret

fails = []


def check(name: str, condition: bool) -> None:
    if condition:
        print(f"  OK   {name}")
    else:
        fails.append(name)
        print(f"  FAIL {name}")


# ---------------------------------------------------------------- secret.encrypt/decrypt
print("secret:")
enc = secret.encrypt("sk-test-abc-123")
check("шифрлэсэн мөр dpapi: урдтайтай", enc.startswith("dpapi:"))
check("шифрлэсэн мөр ил текстийг агуулаагүй", "sk-test" not in enc)
check("тайлсан нь анхныхаа адил", secret.decrypt(enc) == "sk-test-abc-123")
check("хоосон утга шифрлэгдэхгүй", secret.encrypt("") == "")
check("хоосон утга тайлагдахгүй", secret.decrypt("") is None)
check("dpapi:-гүй мөр тайлагдахгүй", secret.decrypt("sk-plain-key") is None)
check("эвдэрсэн base64 тайлагдахгүй", secret.decrypt("dpapi:!!!буруу") is None)
check("is_encrypted зөв таньна", secret.is_encrypted(enc))
check("is_encrypted ил текстыг таньахгүй", not secret.is_encrypted("abc"))

# ---------------------------------------------------------------- Config round-trip
print("config:")
with tempfile.TemporaryDirectory() as tmp:
    import monspeech.config as config_module

    original_path = config_module.CONFIG_PATH
    config_module.CONFIG_PATH = Path(tmp) / "config.json"

    cfg = config_module.Config()
    cfg["stt_key"] = "sk-roundtrip-999"
    error = cfg.save()
    check("save алдаагүй", error is None)

    written = config_module.CONFIG_PATH.read_text(encoding="utf-8")
    check("файл дотор ил текст байхгүй", "sk-roundtrip-999" not in written)
    check("файл дотор dpapi: тэмдэглэгээтэй", "dpapi:" in written)

    loaded = config_module.Config.load()
    check("дахин уншсан түлхүүр анхныхаа адил", loaded["stt_key"] == "sk-roundtrip-999")

    # Хуучин ил тексттэй файл автоматаар шилждөг нь
    config_module.CONFIG_PATH.write_text(
        '{"stt_key": "sk-legacy-plain"}', encoding="utf-8"
    )
    legacy = config_module.Config.load()
    check("хуучин ил текст уншигдана", legacy["stt_key"] == "sk-legacy-plain")
    legacy.save()
    migrated = config_module.Config.load()
    check("хадгалсаны дараа шифрлэгдсэн", migrated["stt_key"] == "sk-legacy-plain")
    check(
        "миграцийн дараа файл цэвэр",
        "sk-legacy-plain" not in config_module.CONFIG_PATH.read_text(encoding="utf-8"),
    )

    config_module.CONFIG_PATH = original_path

print()
if fails:
    print(f"{len(fails)} тест уналаа: {', '.join(fails)}")
    sys.exit(1)
print("Бүх тест амжилттай")
