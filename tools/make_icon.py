"""Monspeech-ийн лого (дууны долгион) үүсгэж, .ico болон .png болгон хадгална.

Ажиллуулах:  .venv\\Scripts\\python.exe tools\\make_icon.py
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

SIZE = 1024
SUPER = 2  # дотоод нарийвчлал (нүх сүвгүй ирмэг)

# Долгионы хэлбэр: (байрлал 0..1, өндөр -1..1)
SHAPE = [
    (0.000, 0.00),
    (0.120, 0.02),
    (0.215, 0.52),
    (0.290, -0.50),
    (0.380, 1.00),
    (0.500, -0.92),
    (0.620, 1.00),
    (0.700, -0.52),
    (0.785, 0.50),
    (0.880, -0.02),
    (1.000, 0.00),
]

# Өнгөний шилжилт (зүүнээс баруун тийш)
GRADIENT = [
    (0.00, (41, 190, 244)),
    (0.35, (86, 122, 235)),
    (0.65, (124, 77, 232)),
    (1.00, (196, 58, 236)),
]


def catmull_rom(points: list[tuple[float, float]], samples: int) -> list[tuple[float, float]]:
    """Хяналтын цэгүүдийг гөлгөр муруй болгоно."""
    padded = [points[0]] + points + [points[-1]]
    curve: list[tuple[float, float]] = []
    segments = len(points) - 1
    for index in range(segments):
        p0, p1, p2, p3 = padded[index], padded[index + 1], padded[index + 2], padded[index + 3]
        steps = max(2, samples // segments)
        for step in range(steps):
            t = step / steps
            t2, t3 = t * t, t * t * t
            x = 0.5 * (
                (2 * p1[0])
                + (-p0[0] + p2[0]) * t
                + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
            )
            y = 0.5 * (
                (2 * p1[1])
                + (-p0[1] + p2[1]) * t
                + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
            )
            curve.append((x, y))
    curve.append(points[-1])
    return curve


def gradient_colour(t: float) -> tuple[int, int, int]:
    t = min(1.0, max(0.0, t))
    for index in range(len(GRADIENT) - 1):
        left_t, left_c = GRADIENT[index]
        right_t, right_c = GRADIENT[index + 1]
        if left_t <= t <= right_t:
            span = (t - left_t) / (right_t - left_t or 1)
            return tuple(int(left_c[i] + (right_c[i] - left_c[i]) * span) for i in range(3))
    return GRADIENT[-1][1]


def build_mask(size: int, boldness: float = 1.0) -> Image.Image:
    """Долгионы дүрсийг цагаан/хар маск болгон зурна."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)

    left, right = size * 0.05, size * 0.95
    centre_y = size * 0.5
    amplitude = size * 0.200
    thick_max = size * 0.074 * boldness
    thick_min = size * 0.004 * boldness

    points = [(left + (right - left) * t, centre_y - amplitude * v) for t, v in SHAPE]
    curve = catmull_rom(points, 900)

    # Зузаан нь голдоо их, хоёр захдаа нимгэн
    def thickness(t: float) -> float:
        envelope = math.sin(math.pi * min(1.0, max(0.0, t)) ** 0.75)
        return thick_min + (thick_max - thick_min) * envelope**1.25

    upper: list[tuple[float, float]] = []
    lower: list[tuple[float, float]] = []
    total = len(curve) - 1
    for index, (x, y) in enumerate(curve):
        t = index / total
        prev_point = curve[max(0, index - 1)]
        next_point = curve[min(total, index + 1)]
        dx = next_point[0] - prev_point[0]
        dy = next_point[1] - prev_point[1]
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length  # хэвийн вектор
        half = thickness(t) / 2
        upper.append((x + nx * half, y + ny * half))
        lower.append((x - nx * half, y - ny * half))

    draw.polygon(upper + lower[::-1], fill=255)
    return mask


def build_logo(size: int, boldness: float = 1.0) -> Image.Image:
    work = size * SUPER
    mask = build_mask(work, boldness)
    # Ирмэгийг зөөлрүүлнэ
    mask = mask.filter(ImageFilter.GaussianBlur(work / 900))

    gradient = Image.new("RGB", (work, 1))
    for x in range(work):
        gradient.putpixel((x, 0), gradient_colour(x / (work - 1)))
    gradient = gradient.resize((work, work))

    logo = Image.new("RGBA", (work, work), (0, 0, 0, 0))
    logo.paste(gradient, (0, 0), mask)
    return logo.resize((size, size), Image.LANCZOS)


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    master = build_logo(SIZE)
    master.save(ASSETS / "monspeech.png")

    # Жижиг хэмжээнд долгион танигдахуйц байхын тулд бүдүүвчийг нь тоддуулна
    icons = []
    for size in (16, 24, 32, 48, 64, 128, 256):
        boldness = 1.55 if size <= 24 else 1.35 if size <= 32 else 1.15 if size <= 48 else 1.0
        icons.append(build_logo(size * 2, boldness).resize((size, size), Image.LANCZOS))
    icons[-1].save(
        ASSETS / "monspeech.ico",
        format="ICO",
        sizes=[(i.width, i.height) for i in icons],
        append_images=icons[:-1],
    )
    print("хадгаллаа:", ASSETS / "monspeech.png", "|", ASSETS / "monspeech.ico")


if __name__ == "__main__":
    main()
