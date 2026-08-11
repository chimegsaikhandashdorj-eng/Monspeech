"""Цэсний шугаман дүрснүүд.

Дизайн нь emoji биш, цэвэр line icon шаарддаг. Tk нь SVG уншдаггүй тул
дүрс бүрийг Pillow-оор 4 дахин том зураад буулгана — ирмэг нь зөөлөн гарна.

Зам нь SVG-ийн `M`/`L`/`C` командуудтай дүйцэх энгийн бичиглэлтэй: цэгүүдийн
жагсаалт, `("c", x1, y1, x2, y2, x, y)` бол кубик Безье.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

VIEWBOX = 18.0
SS = 4
STROKE = 1.4

_cache: dict[tuple, ImageTk.PhotoImage] = {}


def _bezier(start, control1, control2, end, steps: int = 14):
    points = []
    for index in range(1, steps + 1):
        t = index / steps
        u = 1 - t
        points.append(
            (
                u ** 3 * start[0] + 3 * u * u * t * control1[0]
                + 3 * u * t * t * control2[0] + t ** 3 * end[0],
                u ** 3 * start[1] + 3 * u * u * t * control1[1]
                + 3 * u * t * t * control2[1] + t ** 3 * end[1],
            )
        )
    return points


def _path(commands) -> list[tuple[float, float]]:
    """`[(x, y), ..., ("c", cx1, cy1, cx2, cy2, x, y), ...]` → цэгийн жагсаалт."""
    points: list[tuple[float, float]] = []
    for item in commands:
        if item and item[0] == "c":
            _, x1, y1, x2, y2, x, y = item
            points.extend(_bezier(points[-1], (x1, y1), (x2, y2), (x, y)))
        else:
            points.append(item)
    return points


# Дүрс бүр: strokes (замууд), fills (дүүргэсэн эллипсүүд), rects (дугуй өнцөгт)
_SHAPES: dict[str, dict] = {
    # Төлөв — бай/фокус
    "status": {
        "circles": [(9, 9, 6.6, False), (9, 9, 2.4, True)],
    },
    # Яриа — микрофон
    "mic": {
        "rects": [(6.4, 2.4, 11.6, 10.8, 2.6)],
        "arcs": [(4, 4.4, 14, 14.4, 0, 180)],
        "strokes": [[(9, 14.4), (9, 16)]],
    },
    # Бичилт — текстийн курсор
    "write": {
        "strokes": [
            [(9, 3), (9, 15)],
            [(6.2, 3), (11.8, 3)],
            [(6.2, 15), (11.8, 15)],
        ],
    },
    # Товчлуур — гар
    "keyboard": {
        "rects": [(1.8, 4.4, 16.2, 13.6, 2)],
        "strokes": [
            [(5, 8), (5.4, 8)], [(8, 8), (8.4, 8)], [(11, 8), (11.4, 8)],
            [(5.6, 11), (12.4, 11)],
        ],
    },
    # Толь — ном
    "book": {
        "strokes": [
            [(9, 4.2), (9, 14.6)],
            _path([
                (9, 4.2),
                ("c", 7.4, 2.9, 5, 3, 2.8, 3.4),
                (2.8, 13.0),
                ("c", 5, 12.7, 7.4, 12.9, 9, 14.2),
                ("c", 10.6, 12.9, 13, 12.7, 15.2, 13.0),
                (15.2, 3.4),
                ("c", 13, 3, 10.6, 2.9, 9, 4.2),
            ]),
        ],
    },
    # Түүх — цаг
    "clock": {
        "circles": [(9, 9, 6.6, False)],
        "strokes": [[(9, 5.4), (9, 9), (11.8, 10.8)]],
    },
    # Нэмэлт — гулсуур
    "sliders": {
        "strokes": [
            [(2.6, 5.4), (15.4, 5.4)],
            [(2.6, 9), (15.4, 9)],
            [(2.6, 12.6), (15.4, 12.6)],
        ],
        "knobs": [(6.4, 5.4, 1.7), (11.4, 9, 1.7), (7.4, 12.6, 1.7)],
    },
    # Туслах дүрснүүд
    "search": {
        "circles": [(7.7, 7.7, 5.4, False)],
        "strokes": [[(11.8, 11.8), (15.9, 15.9)]],
    },
    "plus": {
        "strokes": [[(9, 3.4), (9, 14.6)], [(3.4, 9), (14.6, 9)]],
    },
    "close": {
        "strokes": [[(4.6, 4.6), (13.4, 13.4)], [(13.4, 4.6), (4.6, 13.4)]],
    },
    "chevron": {
        "strokes": [[(11.1, 3), (5.1, 9), (11.1, 15)]],
    },
    "chevron_right": {
        "strokes": [[(6.9, 3), (12.9, 9), (6.9, 15)]],
    },
}


def get(name: str, colour: str, size: int = 17, background: str = "") -> ImageTk.PhotoImage:
    """Дүрсийг өгсөн өнгөөр буцаана. Кэшлэнэ — Tk зургийн лавлагааг барих ёстой."""
    key = (name, colour, size, background)
    cached = _cache.get(key)
    if cached is not None:
        return cached

    shape = _SHAPES[name]
    side = size * SS
    scale = side / VIEWBOX
    image = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width = max(1, round(STROKE * scale))
    fill = _rgb(colour)
    knob_fill = _rgb(background) if background else None

    def box(x1, y1, x2, y2):
        return (x1 * scale, y1 * scale, x2 * scale, y2 * scale)

    for x, y, radius, solid in shape.get("circles", []):
        area = box(x - radius, y - radius, x + radius, y + radius)
        if solid:
            draw.ellipse(area, fill=fill)
        else:
            draw.ellipse(area, outline=fill, width=width)
    for area in shape.get("rects", []):
        x1, y1, x2, y2, radius = area
        draw.rounded_rectangle(
            box(x1, y1, x2, y2), radius=radius * scale, outline=fill, width=width
        )
    for x1, y1, x2, y2, start, end in shape.get("arcs", []):
        draw.arc(box(x1, y1, x2, y2), start=start, end=end, fill=fill, width=width)
    for points in shape.get("strokes", []):
        scaled = [(x * scale, y * scale) for x, y in points]
        if len(scaled) == 1:
            scaled = scaled * 2
        draw.line(scaled, fill=fill, width=width, joint="curve")
        # Дугуй үзүүр: `joint` нь зөвхөн уулзварыг гөлийлгөнө
        for x, y in (scaled[0], scaled[-1]):
            draw.ellipse((x - width / 2, y - width / 2, x + width / 2, y + width / 2), fill=fill)
    for x, y, radius in shape.get("knobs", []):
        area = box(x - radius, y - radius, x + radius, y + radius)
        if knob_fill:
            draw.ellipse(area, fill=knob_fill)
        draw.ellipse(area, outline=fill, width=width)

    photo = ImageTk.PhotoImage(image.resize((size, size), Image.LANCZOS))
    _cache[key] = photo
    return photo


def label(parent, name: str, colour: str, background: str, size: int = 17) -> tk.Label:
    """Дүрсийг агуулсан бэлэн шошго."""
    widget = tk.Label(parent, bd=0, highlightthickness=0, bg=background)
    widget.configure(image=get(name, colour, size, background))
    return widget


def _rgb(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[i : i + 2], 16) for i in (1, 3, 5))
