r"""Хадгалсан хэцүү жишээнүүдээс benchmark-ийн manifest үүсгэнэ.

Апп «Яриа → Хэцүү жишээ хадгалах» асаалттай үед буруу таньсан дуунуудыг
`%AppData%\Monspeech\samples`-д цуглуулдаг. Энэ хэрэгсэл тэдгээрийг
`benchmarks/` доор хуулж, `benchmark_language.py`-ийн уншдаг manifest болгоно.

Жишээ:
  .venv\Scripts\python.exe tools\make_manifest.py
  .venv\Scripts\python.exe tools\make_manifest.py --all --append

Хоёр төрлийн мөр гарна:

- **Бэлэн** — хэрэглэгч зассан (`corrected`) тул зөв хариу нь мэдэгдэнэ.
  Шууд ажиллана.
- **Дутуу** — огт танигдаагүй, эсвэл итгэлцэл багатай гэж хаягдсан. Зөв хариу
  нь хэнд ч мэдэгдэхгүй тул `#`-ээр эхэлсэн тайлбар мөр болж бичигдэнэ:
  сонсоод, `text`-ийг нь бөглөж, `#`-ийг нь авбал ажиллана. `--all` өгөхөд л
  эдгээр орно.

Дууг ХУУЛНА, шилжүүлэхгүй: `samples` хавтас нь хязгаартай тул хуучин файлууд
өөрөө устдаг. Benchmark-ийн сан тогтвортой байх ёстой.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from monspeech.samples import SAMPLES_DIR, INDEX_NAME  # noqa: E402

BENCHMARKS = ROOT / "benchmarks"

#: Хэлний код нь manifest-д заавал байх ёстой. Түүхэнд «mixed» гэж
#: тэмдэглэгдсэн, эсвэл огт хоосон байвал энэ рүү буцна.
DEFAULT_LANGUAGE = "mn-MN"


def _language(item: dict) -> str:
    language = str(item.get("lang") or "").strip()
    return language or DEFAULT_LANGUAGE


def _row(item: dict, audio: str) -> dict:
    return {
        "audio": audio,
        "text": str(item.get("text") or ""),
        "language": _language(item),
        # Аль хэдийн мэдэгдэж байгаа зүйлсийг үлдээнэ: аль жишээ юунаас
        # үүссэнийг хожим тайлбарлахад хэрэгтэй (бүгд адилхан хэцүү биш).
        "reason": str(item.get("reason") or ""),
        "heard": str(item.get("heard") or ""),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="samples → benchmark manifest")
    parser.add_argument(
        "--samples", type=Path, default=SAMPLES_DIR, help="жишээний хавтас"
    )
    parser.add_argument(
        "--out", type=Path, default=BENCHMARKS / "manifest.jsonl", help="manifest файл"
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Зөв хариу нь мэдэгдэхгүй жишээг ч тайлбар мөр болгож оруулна",
    )
    parser.add_argument(
        "--append",
        action="store_true",
        help="Байгаа manifest дээр нэмнэ (анхдагчаар дарж бичнэ)",
    )
    args = parser.parse_args()

    index = args.samples / INDEX_NAME
    if not index.exists():
        print(f"Жишээ олдсонгүй: {index}")
        print("«Яриа → Хэцүү жишээ хадгалах»-ыг асаагаад хэсэг ашиглана уу.")
        return 2

    items = []
    for line in index.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("file"):
            items.append(item)

    audio_dir = args.out.parent / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)

    ready: list[str] = []
    todo: list[str] = []
    missing = 0
    for item in items:
        source = args.samples / item["file"]
        if not source.exists():
            missing += 1  # хязгаараас хэтэрч устсан — бүртгэлээс хоцорсон мөр
            continue
        shutil.copy2(source, audio_dir / item["file"])
        row = json.dumps(
            _row(item, f"audio/{item['file']}"), ensure_ascii=False
        )
        if item.get("text"):
            ready.append(row)
        else:
            todo.append("# ГАРААР БӨГЛӨНӨ: " + row)

    lines = list(ready)
    if args.all:
        lines += todo

    if not lines:
        print("Бичих мөр алга (--all өгч үзнэ үү).")
        return 2

    args.out.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if args.append else "w"
    with open(args.out, mode, encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")

    print(f"Manifest: {args.out}")
    print(f"  бэлэн (зөв хариутай): {len(ready)}")
    print(f"  гараар бөглөх:        {len(todo)}{'' if args.all else ' (--all-гүй тул орсонгүй)'}")
    if missing:
        print(f"  файл нь устсан:       {missing}")
    print()
    print("Ажиллуулах:")
    print(rf"  .venv\Scripts\python.exe tools\benchmark_language.py {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
