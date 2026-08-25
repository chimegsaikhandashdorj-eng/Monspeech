"""Түүх хадгалах ба статистикийн тест (файлыг түр хавтсанд бичнэ).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_store.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech.store import TranscriptStore, UsageStats

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


with tempfile.TemporaryDirectory() as folder:
    root = Path(folder)

    # --- түүх ---
    store = TranscriptStore(path=root / "history.jsonl")
    check("эхэндээ хоосон", store.entries, [])
    first = store.add(
        "Сайн байна уу",
        "mn-MN",
        1.5,
        raw_text="сайн байна уу",
        provider="google",
        confidence=0.93456,
        requested_lang="mn-MN",
        mode="polished",
    )
    check("raw transcript", first["raw_text"], "сайн байна уу")
    check("provider metadata", first["provider"], "google")
    check("confidence metadata", first["confidence"], 0.9346)
    store.add("Энэ бол тест", "mn-MN", 2.0)
    store.add("Hello world", "en-US", 1.0)
    check("гурав нэмэгдсэн", len(store.entries), 3)

    # Дахин ачаалахад алга болохгүй
    again = TranscriptStore(path=root / "history.jsonl")
    check("дискнээс сэргэсэн", [e["text"] for e in again.entries],
          ["Сайн байна уу", "Энэ бол тест", "Hello world"])

    # Хайлт — шинэ нь эхэндээ
    check("хайлт", [e["text"] for e in again.search("тест")], ["Энэ бол тест"])
    check("том жижиг үсэг хамаарахгүй", len(again.search("HELLO")), 1)
    check("хоосон хайлт бүгдийг", len(again.search("")), 3)
    check("шинэ нь эхэндээ", again.search("")[0]["text"], "Hello world")

    # Засах — диск дээр ч өөрчлөгдөнө
    entry = again.search("тест")[0]
    again.replace(entry, "Энэ бол засвар")
    again.set_language(entry, "en-US")
    reloaded = TranscriptStore(path=root / "history.jsonl")
    check("засвар хадгалагдсан", [e["text"] for e in reloaded.entries],
          ["Сайн байна уу", "Энэ бол засвар", "Hello world"])
    fixed = reloaded.search("засвар")[0]
    check("хэлний засвар хадгалагдсан", fixed["lang"], "en-US")
    check("хэл баталсан тэмдэг", fixed["language_corrected"], True)

    # Хязгаар
    small = TranscriptStore(path=root / "small.jsonl", limit=3)
    for index in range(6):
        small.add(f"мөр {index}")
    check("хязгаар барина", [e["text"] for e in small.entries],
          ["мөр 3", "мөр 4", "мөр 5"])

    small.clear()
    check("цэвэрлэсэн", small.entries, [])
    check("файл ч цэвэрлэгдсэн", TranscriptStore(path=root / "small.jsonl").entries, [])

    # --- статистик ---
    stats = UsageStats(path=root / "stats.json")
    check("эхэндээ мэдээлэлгүй", stats.summary(), "Хараахан шивээгүй байна")
    stats.record("нэг хоёр гурав", seconds=2.0, recognise_ms=300.0)
    stats.record("дөрөв тав", seconds=1.0, recognise_ms=200.0)
    check("үг тоолсон", stats.data["words"], 5)
    check("өгүүлбэр тоолсон", stats.data["utterances"], 2)
    check("өнөөдрийн үг", stats.today_words, 5)
    check("дундаж хугацаа", round(stats.average_ms), 250)
    check("хоосон текст тоологдохгүй", (stats.record("   ", 1.0, 100.0), stats.data["words"])[1], 5)

    stats.save(force=True)
    restored = UsageStats(path=root / "stats.json")
    check("статистик сэргэсэн", restored.data["words"], 5)
    check("тойм", "нийт 5 үг" in restored.summary(), True)

# --- Танигчийн хэрэглээ ба зардал ---
usage = UsageStats(path=Path(tempfile.mkdtemp()) / "stats.json")
usage.record_usage("openai", 30.0)
usage.record_usage("openai", 45.0)
usage.record_usage("google", 10.0)
check("секунд нэмэгдэв", usage.usage("openai")["seconds"], 75.0)
check("хүсэлт тоологдов", usage.usage("openai")["requests"], 2)
check("өнөөдрийнх", usage.usage("openai")["today"], 75.0)
check("энэ сарынх", usage.usage("openai")["month"], 75.0)
check("танигчаар салсан", usage.usage("google")["seconds"], 10.0)
check("танихгүй танигч хоосон", usage.usage("deepgram")["requests"], 0)
usage.record_usage("", 10.0)
usage.record_usage("openai", 0.0)
check("хоосон нэр ба 0 секунд бүртгэгдэхгүй", usage.usage("openai")["requests"], 2)

# Дискнээс уншихад хэрэглээ хэвээр
usage.save(force=True)
again = UsageStats(path=usage.path)
check("дискнээс сэргэв", again.usage("openai")["seconds"], 75.0)


print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
