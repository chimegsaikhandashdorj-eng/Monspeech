"""Benchmark-ийн WER/CER хэмжүүр ба samples → manifest дамжлага."""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import _console  # noqa: E402, F401

from benchmark_language import error_rate  # noqa: E402

from monspeech.samples import HardSampleStore  # noqa: E402

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


check("ижил WER", error_rate("сайн байна", "сайн байна", characters=False), 0.0)
check("нэг үг зөрсөн WER", error_rate("hello world", "hello word", characters=False), 0.5)
check("нэг тэмдэг зөрсөн CER", error_rate("abc", "adc", characters=True), 1 / 3)
check("хоосон expected аюулгүй", error_rate("", "hello", characters=False), 1.0)

# ----------------------------------------------------------------------
# samples → manifest → benchmark: гурвуулаа нэг форматыг ойлгож байна уу
# ----------------------------------------------------------------------
work = Path(tempfile.mkdtemp())
store = HardSampleStore(directory=work / "samples", enabled=True)
pcm = b"ab" * 16000  # 1 секунд @ 16 кГц (escape-гүй, дурын агуулга)
store.capture(pcm, "corrected", text="клауд код", heard="клоуд код", language="mn-MN")
store.capture(pcm, "unrecognized", language="mn-MN")

out = work / "bench" / "manifest.jsonl"
result = subprocess.run(
    [sys.executable, str(ROOT / "tools" / "make_manifest.py"),
     "--samples", str(store.directory), "--out", str(out), "--all"],
    capture_output=True, text=True, encoding="utf-8", errors="replace",
)
check("make_manifest амжилттай", result.returncode, 0)
check("manifest үүсэв", out.exists(), True)
check("дуу нь хуулагдав", len(list((out.parent / "audio").glob("*.wav"))), 2)

# `benchmark_language.main()`-ийн уншдаг ЯГ тэр дүрмээр задална: `#`-ээр
# эхэлсэн мөр алгасагдаж, үлдсэнд нь гурван талбар заавал байх ёстой.
rows = []
for line in out.read_text(encoding="utf-8").splitlines():
    if not line.strip() or line.lstrip().startswith("#"):
        continue
    item = json.loads(line)
    check("audio/text/language бүрэн", all(item.get(k) for k in ("audio", "text", "language")), True)
    rows.append(item)
check("зөвхөн зөв хариутай нь ажиллана", len(rows), 1)
check("зөв хариу дамжив", rows[0]["text"], "клауд код")
check("буруу нь ч үлдэв", rows[0]["heard"], "клоуд код")
check("зам нь харьцангуй", rows[0]["audio"].startswith("audio/"), True)
check("зам нь бодитоор олдоно", (out.parent / rows[0]["audio"]).exists(), True)

# Жишээ manifest ч мөн адил задлагдана (баримтжуулалт хуучраагүй эсэх)
example = ROOT / "benchmarks" / "manifest.example.jsonl"
for line in example.read_text(encoding="utf-8").splitlines():
    if not line.strip():
        continue
    item = json.loads(line)
    check(
        f"жишээ мөр бүрэн: {item.get('audio')}",
        all(item.get(k) for k in ("audio", "text", "language")),
        True,
    )

print()
if fails:
    print("FAILED:")
    for line in fails:
        print(" ", line)
    raise SystemExit(1)
print("ALL PASS")
