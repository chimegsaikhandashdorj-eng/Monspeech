"""Дизайны токенуудын хүртээмжийн тест.

Өнгө нь нүдээр «болж байна» гэж шийдэх зүйл биш — харьцааг тоогоор хэмжинэ.
WCAG AA: энгийн текст 4.5:1, удирдлагын хүрээ/фокус 3:1.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_theme.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech import theme

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


def _channel(value: int) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def luminance(colour: str) -> float:
    h = colour.lstrip("#")
    r, g, b = (int(h[i : i + 2], 16) for i in (0, 2, 4))
    return 0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)


def contrast(a: str, b: str) -> float:
    la, lb = luminance(a), luminance(b)
    high, low = max(la, lb), min(la, lb)
    return (high + 0.05) / (low + 0.05)


def at_least(label, fg, bg, need):
    ratio = contrast(fg, bg)
    ok = ratio >= need
    if not ok:
        fails.append(f"{label}: {ratio:.2f}:1, {need}:1 хэрэгтэй")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {ratio:.2f}:1")


# Текст өнгө бүр өөрийн гарч болох БҮХ гадаргуу дээр босго давах ёстой.
# Хамгийн бүдэг нь PANEL2 — тэнд давбал бусад дээр давна.
SURFACES = {
    "BG": theme.BG,
    "PANEL": theme.PANEL,
    "PANEL2": theme.PANEL2,
    "SIDEBAR": theme.SIDEBAR,
    "MOCK": theme.MOCK,
}

for name, surface in SURFACES.items():
    at_least(f"TEXT / {name}", theme.TEXT, surface, 4.5)
    at_least(f"MUTED / {name}", theme.MUTED, surface, 4.5)
    at_least(f"DIM / {name}", theme.DIM, surface, 4.5)

# Товшиж болох текст. `ACCENT` нь дүүргэлтийн өнгө тул текст болгож
# ашиглахгүй — `LINK` нь түүний гэрэлтүүлсэн хувилбар.
for name in ("BG", "PANEL", "PANEL2"):
    at_least(f"LINK / {name}", theme.LINK, SURFACES[name], 4.5)

# Төлөвийн өнгөнүүд
for name in ("PANEL", "BG"):
    at_least(f"OK / {name}", theme.OK, SURFACES[name], 4.5)
    at_least(f"WARN / {name}", theme.WARN, SURFACES[name], 4.5)
    at_least(f"DANGER / {name}", theme.DANGER, SURFACES[name], 4.5)

# Идэвхтэй цэс
at_least("TEXT / NAV_ACTIVE", theme.TEXT, theme.NAV_ACTIVE, 4.5)
at_least("MUTED / SIDEBAR", theme.MUTED, theme.SIDEBAR, 4.5)

# Фокусын хүрээ нь текст биш — удирдлагын тэмдэг тул 3:1
for name, surface in SURFACES.items():
    at_least(f"FOCUS / {name}", theme.FOCUS, surface, 3.0)
at_least("FOCUS / NAV_ACTIVE", theme.FOCUS, theme.NAV_ACTIVE, 3.0)

# `DIM` нь `MUTED`-ээс ялгарч байх ёстой — эс бөгөөс шатлал утгаа алдана
ok = contrast(theme.DIM, theme.MUTED) >= 1.2
if not ok:
    fails.append("DIM ба MUTED хоёр хэт ойрхон — шатлал ялгарахгүй")
print(f"{'ok  ' if ok else 'FAIL'} DIM ялгарна -> {contrast(theme.DIM, theme.MUTED):.2f}:1")

check("фокусын хүрээ тэг биш", theme.FOCUS_WIDTH > 0, True)

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
