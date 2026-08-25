"""Хэцүү тохиолдлын дууг хадгалагч (benchmark-ийн сан ургуулагч)."""

import json
import sys
import tempfile
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401

from monspeech import samples as samples_module
from monspeech.samples import HardSampleStore

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


def store(enabled=True, **kwargs):
    return HardSampleStore(
        directory=Path(tempfile.mkdtemp()), enabled=enabled, **kwargs
    )


PCM = b"\x11\x22" * 16000  # 2 секунд @ 16 кГц

# --- Унтраалттай үед юу ч болохгүй --------------------------------------
off = store(enabled=False)
entry = {"text": "буруу"}
off.remember(PCM, entry)
check("унтраалттай бол бичихгүй", off.capture(PCM, "unrecognized"), False)
check("унтраалттай бол засвар ч бичихгүй", off.promote(entry, "зөв"), False)
check("файл үүсээгүй", off.count, 0)
check("хураангуй нь тодорхой", off.summary(), "Унтраалттай")

# --- Бичих: WAV нь benchmark-ийн шаардлагад тохирно ---------------------
one = store()
check("хоосон үеийн хураангуй", one.summary(), "Хараахан хадгалаагүй")
check("бичигдэв", one.capture(PCM, "unrecognized", language="mn-MN"), True)
check("нэг бүртгэл", one.count, 1)

written = one.directory / one.entries[0]["file"]
with wave.open(str(written), "rb") as handle:
    check("моно", handle.getnchannels(), 1)
    check("16 бит", handle.getsampwidth(), 2)
    check("16 кГц", handle.getframerate(), 16000)
    check("дуу бүтнээрээ", handle.readframes(handle.getnframes()), PCM)

check("урт нь бичигдэв", one.entries[0]["sec"], 1.0)
check("шалтгаан", one.entries[0]["reason"], "unrecognized")
check("зөв хариу мэдэгдэхгүй", one.entries[0]["text"], "")
check("файлын нэрэнд шалтгаан", written.name.endswith("-unrecognized.wav"), True)

# Бүртгэл нь JSONL — `make_manifest.py` үүнийг уншина
lines = one.index_path.read_text(encoding="utf-8").strip().splitlines()
check("бүртгэлд нэг мөр", len(lines), 1)
check("мөр нь JSON", json.loads(lines[0])["reason"], "unrecognized")

# --- Засвар: «дуу + зөв текст» гэсэн бүрэн хос -------------------------
paired = store()
entry = {"text": "клоуд код", "lang": "mn-MN", "provider": "google", "confidence": 0.62}
paired.remember(PCM, entry)
check("санахад дискэнд бичихгүй", paired.count, 0)
check("засвар хадгалагдав", paired.promote(entry, "клауд код"), True)
check("зөв хариу", paired.entries[0]["text"], "клауд код")
check("сонссон нь", paired.entries[0]["heard"], "клоуд код")
check("шалтгаан", paired.entries[0]["reason"], "corrected")
check("итгэлцэл", paired.entries[0]["confidence"], 0.62)
check("хоёр дахь удаа давхарлахгүй", paired.promote(entry, "клауд код"), False)

# Санаагүй таналтыг засахад юу ч болохгүй (хэт хуучин засвар)
check("санаагүйг дэвшүүлэхгүй", paired.promote({"text": "өөр"}, "зөв"), False)
check("хоосон зөв хариуг авахгүй", paired.promote(entry, "   "), False)

# ЯГ тэр объект байх ёстой — ижил агуулгатай өөр dict таарах ёсгүй
identity = store()
original = {"text": "нэг"}
identity.remember(PCM, original)
check("хуулбар dict таарахгүй", identity.promote({"text": "нэг"}, "хоёр"), False)
check("эх объект таарна", identity.promote(original, "хоёр"), True)

# --- Санах ойн хязгаар ---------------------------------------------------
limited = store()
kept = {"text": "сүүлийнх"}
dropped = {"text": "хамгийн эхний"}
limited.remember(PCM, dropped)
big = b"\x00" * (samples_module.MEMORY_BYTES + 1)
limited.remember(big, kept)
check("хязгаар хэтрэхэд хуучин нь гарна", limited.promote(dropped, "зөв"), False)

# --- Дискний хязгаар: хуучин файлууд өөрөө устана ----------------------
capped = store(max_files=2)
for index in range(4):
    capped.capture(PCM, "unrecognized", text=f"жишээ {index}")
check("хязгаараас хэтрэхгүй", capped.count, 2)
check("сүүлийнх нь үлдэв", capped.entries[-1]["text"], "жишээ 3")
check("хамгийн хуучин нь устав", capped.entries[0]["text"], "жишээ 2")
check("дискэн дээр ч 2", len(list(capped.directory.glob("*.wav"))), 2)
check("нэр давхардаагүй", len({e["file"] for e in capped.entries}), 2)
check("бүртгэл ч тайрагдав", len(capped.index_path.read_text(encoding="utf-8").strip().splitlines()), 2)

# --- Дахин уншихад бүртгэл сэргэнэ --------------------------------------
again = HardSampleStore(directory=capped.directory, enabled=True)
check("дискнээс сэргэв", again.count, 2)
check("хураангуй тоолно", again.summary().startswith("2 жишээ · 2 нь зөв хариутай"), True)

# --- Цэвэрлэх ------------------------------------------------------------
again.clear()
check("бүртгэл хоосорлоо", again.count, 0)
check("файлууд устав", list(again.directory.glob("*.wav")), [])
check("дахин уншихад ч хоосон", HardSampleStore(directory=again.directory).count, 0)

print()
if fails:
    print("FAILED:")
    for line in fails:
        print(" ", line)
    raise SystemExit(1)
print("ALL PASS")
