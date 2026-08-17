"""Бүх тестийг нэг тушаалаар ажиллуулна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\run_all.py

Тест бүр бие даасан скрипт (гуравдагч сан шаардахгүй) тул тус бүрийг нь
тусдаа процессоор ажиллуулж, гарах кодыг нь тоолно. Ингэснээр нэг тест унасан
ч бусад нь ажиллана, мөн Tk ашигладаг тест бусдыг нь бохирдуулахгүй.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Windows-ийн консол анхнаасаа cp1252 байдаг тул кирилл шошго хэвлэхэд
# `UnicodeEncodeError` шидээд тест бүхэлдээ уначихдаг байв — бодит алдааг
# нуусан хуурамч уналт. Өөрийн гаралт ба хүүхэд процессуудынхыг хоёуланг нь
# UTF-8 болгоно.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
CHILD_ENV = {**os.environ, "PYTHONIOENCODING": "utf-8"}


def main() -> int:
    files = sorted(p for p in HERE.glob("test_*.py"))
    failed: list[str] = []
    for path in files:
        result = subprocess.run(
            [sys.executable, str(path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=CHILD_ENV,
        )
        status = "PASS" if result.returncode == 0 else "FAIL"
        print(f"{status}  {path.name}")
        if result.returncode != 0:
            failed.append(path.name)
            tail = (result.stdout + result.stderr).strip().splitlines()
            for line in tail[-15:]:
                print(f"      {line}")

    print()
    if failed:
        print(f"{len(failed)}/{len(files)} тест уналаа: {', '.join(failed)}")
        return 1
    print(f"{len(files)}/{len(files)} тест бүгд амжилттай")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
