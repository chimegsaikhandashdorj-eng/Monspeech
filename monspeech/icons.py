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
    # Төлөв — түвшний баганууд. Аппын өөрийн долгионтой ижил дүрс тул
    # «энэ бол сонсох дэлгэц» гэдгийг бай/фокусын дүрснээс хамаагүй шууд
    # хэлнэ.
    "waveform": {
        "strokes": [
            [(3.4, 7.4), (3.4, 10.6)],
            [(6.2, 5.0), (6.2, 13.0)],
            [(9.0, 2.6), (9.0, 15.4)],
            [(11.8, 5.0), (11.8, 13.0)],
            [(14.6, 7.4), (14.6, 10.6)],
        ],
    },
    # Хөрвүүлэх — дуут файл: файлын дотор долгион. Энгийн файлын дүрс нь
    # «баримт» гэсэн утга өгдөг ч энд ДУУНААС текст болгодог.
    "file_audio": {
        "strokes": [
            _path([
                (10.6, 2.6), (13.4, 5.4), (13.4, 15.4),
                (4.6, 15.4), (4.6, 2.6), (10.6, 2.6),
            ]),
            [(10.6, 2.6), (10.6, 5.4), (13.4, 5.4)],
            [(6.9, 10.3), (6.9, 12.5)],
            [(9.0, 8.7), (9.0, 14.1)],
            [(11.1, 10.3), (11.1, 12.5)],
        ],
    },
    # Аппууд — гарчгийн мөртэй цонх. Дүрэм нь ЦОНХ бүрт үйлчилдэг тул
    # ерөнхий «апп сүлжээ» дүрснээс утга нь илүү нарийн.
    "window": {
        "rects": [(2.4, 3.8, 15.6, 14.2, 2.4)],
        "strokes": [[(2.4, 7.2), (15.6, 7.2)]],
        "circles": [(4.9, 5.5, 0.6, True), (7.1, 5.5, 0.6, True)],
    },
    # Хөрвүүлэх — булангуулсан файл
    "file": {
        "strokes": [
            _path([
                (10.6, 2.6), (13.4, 5.4), (13.4, 15.4),
                (4.6, 15.4), (4.6, 2.6), (10.6, 2.6),
            ]),
            [(10.6, 2.6), (10.6, 5.4), (13.4, 5.4)],
        ],
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
    # Аппууд — цонхнууд
    "apps": {
        "rects": [
            (2.6, 2.6, 8.2, 8.2, 1.4),
            (9.8, 2.6, 15.4, 8.2, 1.4),
            (2.6, 9.8, 8.2, 15.4, 1.4),
            (9.8, 9.8, 15.4, 15.4, 1.4),
        ],
    },
    # Хэрэглээ — багана график
    "chart": {
        "strokes": [
            [(3.6, 14.4), (3.6, 9.6)],
            [(9, 14.4), (9, 3.6)],
            [(14.4, 14.4), (14.4, 7.2)],
        ],
    },
    # Тохиргоо — шүд. Цагираг нь ТОМ, шүд нь БОГИНО байх ёстой: урьд нь
    # жижиг тойрог + урт хэлхээ байсан тул нар мэт харагдаж, «Алдаа
    # мэдээлэх»-ийн дүрстэй ялгагдахгүй байв.
    "gear": {
        "circles": [(9, 9, 4.8, False), (9, 9, 1.9, False)],
        "strokes": [
            [(13.5, 9), (15.7, 9)],
            [(9, 13.5), (9, 15.7)],
            [(4.5, 9), (2.3, 9)],
            [(9, 4.5), (9, 2.3)],
            [(12.18, 12.18), (13.74, 13.74)],
            [(5.82, 12.18), (4.26, 13.74)],
            [(5.82, 5.82), (4.26, 4.26)],
            [(12.18, 5.82), (13.74, 4.26)],
        ],
    },
    # Алдаа мэдээлэх — анхааруулгатай мессеж. Цох зурахыг оролдвол 18 px-д
    # хөлнүүд нь оддон болж хувирдаг; бөмбөлөг нь «хэлж мэдэгдэх» гэсэн
    # утгыг ч илүү нарийн өгнө.
    "report": {
        "rects": [(2.6, 3.4, 15.4, 12.6, 3.0)],
        "strokes": [
            [(6.3, 12.6), (6.3, 15.7), (9.5, 12.6)],
            [(9, 6.0), (9, 8.8)],
        ],
        "circles": [(9, 10.5, 0.62, True)],
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
    # Түүхийн мөрийн үйлдлүүд
    "play": {
        "strokes": [[(6.6, 3.8), (14.2, 9), (6.6, 14.2), (6.6, 3.8)]],
    },
    "copy": {
        "rects": [(2.8, 2.8, 11.0, 11.0, 1.6), (7.0, 7.0, 15.2, 15.2, 1.6)],
    },
    "pencil": {
        "strokes": [
            [(3.2, 14.8), (3.2, 11.7), (11.6, 3.3), (14.7, 6.4), (6.3, 14.8), (3.2, 14.8)],
            [(10.4, 4.5), (13.5, 7.6)],
        ],
    },
    "chevron": {
        "strokes": [[(11.1, 3), (5.1, 9), (11.1, 15)]],
    },
    "chevron_right": {
        "strokes": [[(6.9, 3), (12.9, 9), (6.9, 15)]],
    },
    # Тусламж — асуултын тэмдэг
    "help": {
        "circles": [(9, 9, 6.6, False), (9.6, 12.9, 1.05, True)],
        "strokes": [
            _path([
                (6.7, 7.1),
                ("c", 6.7, 5.6, 7.7, 4.8, 9.0, 4.8),
                ("c", 10.3, 4.8, 11.3, 5.6, 11.3, 6.9),
                ("c", 11.3, 8.0, 10.5, 8.5, 9.6, 9.1),
                (9.6, 10.4),
            ]),
        ],
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
