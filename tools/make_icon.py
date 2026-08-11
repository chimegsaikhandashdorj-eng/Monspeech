"""Эх логоны зургаас `assets/monspeech.png` ба `assets/monspeech.ico` үүсгэнэ.

Эх файл: `assets/logo-source.png` — түүнийг солиод энэ скриптийг дахин
ажиллуулбал аппын бүх дүрс шинэчлэгдэнэ.

Ажиллуулах:  .venv\\Scripts\\python.exe tools\\make_icon.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
SOURCE = ASSETS / "logo-source.png"

SIZE = 1024
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Дүрс жижгэрэхэд нарийн зураас бүдгэрдэг тул бага зэрэг хурцлана
SHARPEN_BELOW = 64


def load_master() -> Image.Image:
    """Эх зургийг уншиж, ил тод захыг нь тайрч, квадрат болгоно."""
    image = Image.open(SOURCE).convert("RGBA")

    # Зурагчид ихэвчлэн эргэн тойрон ил тод зай үлдээдэг — түүнийг авч хаяна
    box = image.split()[3].getbbox()
    if box:
        image = image.crop(box)

    # Өндөр/өргөн зөрвөл дутуу талд нь ил тод зай нэмж квадрат болгоно
    side = max(image.size)
    if image.size != (side, side):
        square = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        square.paste(image, ((side - image.width) // 2, (side - image.height) // 2))
        image = square

    return image.resize((SIZE, SIZE), Image.LANCZOS)


def scaled(master: Image.Image, size: int) -> Image.Image:
    icon = master.resize((size, size), Image.LANCZOS)
    if size < SHARPEN_BELOW:
        icon = icon.filter(ImageFilter.UnsharpMask(radius=1.0, percent=90, threshold=2))
    return icon


def main() -> None:
    # Windows консол cp1252 байвал кирилл үсэг хэвлэхэд унадаг
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    if not SOURCE.exists():
        raise SystemExit(f"эх зураг олдсонгүй: {SOURCE}")

    master = load_master()
    master.save(ASSETS / "monspeech.png")

    icons = [scaled(master, size) for size in ICO_SIZES]
    icons[-1].save(
        ASSETS / "monspeech.ico",
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[:-1],
    )
    print("хадгаллаа:", ASSETS / "monspeech.png", "|", ASSETS / "monspeech.ico")


if __name__ == "__main__":
    main()
