"""«Төлөв» хуудасны робот — аппын царай.

Дизайнд энэ нь Canvas 2D дээр математикаар зурагдсан сүүдэрлэсэн дүрс.
Tkinter-ийн Canvas градиент ч, зөөлөн ирмэг ч зурж чаддаггүй тул хэсгүүдийг
Pillow-оор 3 дахин том зураад буулгаж, `tk.Canvas` дээр **зургийн элемент**
болгон байрлуулна.

Ингэснээр анимац бараг үнэгүй болно: кадр бүрт зөвхөн аль зургийг харуулахыг
сольж, элементийг хэдэн пиксель зөөнө — дахин зурах ажил огт байхгүй. Энэ бол
дэвсгэрт байнга ажилладаг апп учир чухал.

Гурван төлөв:
    idle         — удаан амьсгалж, инээмсэглэнэ
    listening    — микрофоны түвшний дагуу ам нь томорч, гэрэл нь чангарна
    recognizing  — нүд нь хажуу тийш харж, ам нь долгиолно
"""

from __future__ import annotations

import math
import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import theme

# Дизайны координатын орон зай (Canvas 2D эх хувилбартай ижил).
LOGICAL = 480
CROP_H = 400  # доод хэсэг хоосон — тайраад цонхны өндөр хэмнэнэ
SS = 3  # supersample: ирмэгийг зөөлрүүлэх

CX = LOGICAL / 2
BODY_DY = 62  # эх кодын ctx.translate(0, bob + 62)
EYE_Y = 148 + BODY_DY
EYE_X = 49

BLUE = (30, 58, 240)
CYAN = (53, 232, 245)
OUTLINE = (150, 163, 196, 191)  # rgba(150,163,196,.75)

MODES = ("idle", "listening", "recognizing")
IDLE_POLL_MS = 400  # цонх нуугдсан үеийн сэрэх давтамж

# Кэшийг нарийсгах алхмууд. Хүн 6 шатыг үргэлжилсэн хөдөлгөөн гэж хардаг ба
# кэшийн хэмжээ энэ тооны квадратаар өсдөг.
GLOW_STEPS = 6
AURA_STEPS = 6
RING_PHASES = 12
EYE_STEPS = 6
MOUTH_STEPS = 8


def _lerp(a, b, k):
    return tuple(round(x + (y - x) * k) for x, y in zip(a, b))


def _vertical_gradient(width: int, height: int, stops) -> Image.Image:
    """Босоо шугаман градиент. `stops` = [(0..1, (r,g,b)), ...] эрэмбэлэгдсэн."""
    strip = Image.new("RGB", (1, height))
    pixels = strip.load()
    for y in range(height):
        pos = y / max(1, height - 1)
        lower = stops[0]
        upper = stops[-1]
        for index in range(len(stops) - 1):
            if stops[index][0] <= pos <= stops[index + 1][0]:
                lower, upper = stops[index], stops[index + 1]
                break
        span = upper[0] - lower[0]
        k = 0.0 if span <= 0 else (pos - lower[0]) / span
        pixels[0, y] = _lerp(lower[1], upper[1], k)
    return strip.resize((width, height), Image.BILINEAR)


def _horizontal_gradient(width: int, height: int, colours) -> Image.Image:
    strip = Image.new("RGB", (len(colours), 1))
    strip.putdata(colours)
    return strip.resize((width, height), Image.BILINEAR)


def _rounded_mask(size, box, radius) -> Image.Image:
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(box, radius=radius, fill=255)
    return mask


class _Sprites:
    """Нэг хэмжээст зориулсан зургийн үйлдвэр. Шаардлагатай үед нь л зурна."""

    def __init__(self, width: int) -> None:
        self.width = width
        self.height = round(width * CROP_H / LOGICAL)
        self.scale = width / LOGICAL
        self._cache: dict[tuple, ImageTk.PhotoImage] = {}
        self._ring_gradient: Image.Image | None = None

    # --- туслах ---
    def _blank(self, size=None) -> Image.Image:
        size = size or (self.width * SS, self.height * SS)
        return Image.new("RGBA", size, (0, 0, 0, 0))

    def _finish(self, image: Image.Image, key: tuple) -> ImageTk.PhotoImage:
        target = (image.width // SS, image.height // SS)
        photo = ImageTk.PhotoImage(image.resize(target, Image.LANCZOS))
        self._cache[key] = photo
        return photo

    def _k(self, value: float) -> float:
        """Дизайны координатыг supersample хийсэн пиксел рүү."""
        return value * self.scale * SS

    # ------------------------------------------------------------------
    # Аура — робот доорх зөөлөн гэрэл
    # ------------------------------------------------------------------
    def aura(self, step: int) -> ImageTk.PhotoImage:
        key = ("aura", step)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        strength = step / (AURA_STEPS - 1)
        inner = 0.11 + 0.21 * strength
        middle = 0.07 + 0.14 * strength

        # Радиал градиентийг жижигхэн зураад томсгоно — концентр эллипсээр
        # зурсан шатлал 4 дахин томсоход бүрэн жигдэрнэ.
        side = 128
        small = Image.new("RGBA", (side, side), (0, 0, 0, 0))
        draw = ImageDraw.Draw(small)
        steps = 56
        for index in range(steps, 0, -1):
            pos = index / steps
            if pos <= 0.55:
                k = pos / 0.55
                colour = _lerp(CYAN, BLUE, k)
                alpha = inner + (middle - inner) * k
            else:
                k = (pos - 0.55) / 0.45
                colour = BLUE
                alpha = middle * (1 - k)
            radius = pos * side / 2
            draw.ellipse(
                (side / 2 - radius, side / 2 - radius, side / 2 + radius, side / 2 + radius),
                fill=colour + (round(alpha * 255),),
            )

        diameter = round(self._k(232 * 2))
        glow = small.resize((diameter, diameter), Image.BICUBIC)
        layer = self._blank()
        layer.alpha_composite(
            glow,
            (round(self._k(CX) - diameter / 2), round(self._k(201) - diameter / 2)),
        )
        return self._finish(layer, key)

    # ------------------------------------------------------------------
    # Тэлж буй цагиргууд
    # ------------------------------------------------------------------
    def rings(self, active: bool, phase: int) -> ImageTk.PhotoImage:
        key = ("rings", active, phase)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        size = (self.width * SS, self.height * SS)
        mask = Image.new("L", size, 0)
        draw = ImageDraw.Draw(mask)
        count = 4 if active else 2
        spread = 104 if active else 78
        peak = 0.55 if active else 0.40
        base = phase / RING_PHASES
        for index in range(count):
            pos = (base + index / count) % 1.0
            radius = self._k(132 + pos * spread)
            fade = math.sin((1 - pos) * 2.2)
            if fade <= 0:
                continue
            cx, cy = self._k(CX), self._k(201)
            draw.ellipse(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                outline=round(fade * peak * 255),
                width=max(1, round(self._k(5 - 2.2 * pos))),
            )

        if self._ring_gradient is None or self._ring_gradient.size != size:
            self._ring_gradient = _horizontal_gradient(
                size[0], size[1], [(53, 232, 245), (91, 139, 255), (138, 91, 255)]
            )
        layer = self._ring_gradient.convert("RGBA")
        layer.putalpha(mask)
        return self._finish(layer, key)

    # ------------------------------------------------------------------
    # Бие — толгой, дэлгэц, чихний хайрцаг (хөдөлгөөнгүй)
    # ------------------------------------------------------------------
    def body(self) -> ImageTk.PhotoImage:
        key = ("body",)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        layer = self._blank()
        draw = ImageDraw.Draw(layer)
        k = self._k

        def shell(box, radius, y1, y2) -> None:
            """Цагаан хуванцар гадаргуу — дээрээсээ доошоо бага зэрэг харлана."""
            left, top, right, bottom = box
            width, height = round(right - left), round(bottom - top)
            gradient = _vertical_gradient(
                width, height,
                [(0.0, (255, 255, 255)), (0.55, (250, 251, 254)), (1.0, (228, 233, 243))],
            )
            mask = _rounded_mask((width, height), (0, 0, width - 1, height - 1), radius)
            layer.paste(gradient, (round(left), round(top)), mask)
            draw.rounded_rectangle(box, radius=radius, outline=OUTLINE, width=max(1, round(k(1.5))))

        # --- чихний хайрцаг ---
        for sign in (-1, 1):
            px = CX + sign * 128
            shell(
                (k(px - 20), k(108 + BODY_DY), k(px + 20), k(196 + BODY_DY)),
                k(20), k(108 + BODY_DY), k(196 + BODY_DY),
            )
            ex = px + sign * 7
            draw.ellipse(
                (k(ex - 9), k(152 + BODY_DY - 30), k(ex + 9), k(152 + BODY_DY + 30)),
                fill=BLUE + (255,),
            )

        # --- толгой ---
        shell(
            (k(CX - 122), k(40 + BODY_DY), k(CX + 122), k(238 + BODY_DY)),
            k(46), k(40 + BODY_DY), k(238 + BODY_DY),
        )
        draw.rounded_rectangle(
            (k(CX - 90), k(50 + BODY_DY), k(CX + 90), k(70 + BODY_DY)),
            radius=k(10), fill=(255, 255, 255, 230),
        )

        # --- дэлгэц ---
        left, top = k(CX - 100), k(62 + BODY_DY)
        right, bottom = k(CX + 100), k(216 + BODY_DY)
        width, height = round(right - left), round(bottom - top)
        screen = _vertical_gradient(width, height, [(0.0, (21, 34, 73)), (1.0, (10, 18, 48))])
        mask = _rounded_mask((width, height), (0, 0, width - 1, height - 1), k(30))
        layer.paste(screen, (round(left), round(top)), mask)
        draw.rounded_rectangle(
            (left, top, right, bottom),
            radius=k(30), outline=(255, 255, 255, 153), width=max(1, round(k(3))),
        )
        return self._finish(layer, key)

    # ------------------------------------------------------------------
    # Чихний гэрэл
    # ------------------------------------------------------------------
    EAR_BOX = (34, 68)  # дизайны координат дахь өргөн/өндөр

    def ear_glow(self, step: int) -> ImageTk.PhotoImage:
        key = ("ear", step)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        alpha = round((0.35 + 0.65 * step / (GLOW_STEPS - 1)) * 255)
        box = (round(self._k(self.EAR_BOX[0])), round(self._k(self.EAR_BOX[1])))
        layer = self._blank(box)
        rx, ry = self._k(5), self._k(24)
        cx, cy = box[0] / 2, box[1] / 2
        ImageDraw.Draw(layer).ellipse(
            (cx - rx, cy - ry, cx + rx, cy + ry), fill=CYAN + (alpha,)
        )
        return self._finish(layer, key)

    # ------------------------------------------------------------------
    # Нүд
    # ------------------------------------------------------------------
    EYE_BOX = (44, 64)

    def eye(self, mode: str, step: int) -> ImageTk.PhotoImage:
        key = ("eye", mode, step)
        cached = self._cache.get(key)
        if cached is not None:
            return cached
        full = {"listening": 28.0, "recognizing": 19.0}.get(mode, 25.0)
        rx = 18.0 if mode == "listening" else 17.0
        ry = max(2.0, full * step / (EYE_STEPS - 1))

        box = (round(self._k(self.EYE_BOX[0])), round(self._k(self.EYE_BOX[1])))
        layer = self._blank(box)
        cx, cy = box[0] / 2, box[1] / 2
        ImageDraw.Draw(layer).ellipse(
            (cx - self._k(rx), cy - self._k(ry), cx + self._k(rx), cy + self._k(ry)),
            fill=CYAN + (255,),
        )
        return self._finish(layer, key)

    # ------------------------------------------------------------------
    # Ам
    # ------------------------------------------------------------------
    MOUTH_BOX = (70, 86)
    MOUTH_CY = 200 + BODY_DY  # хайрцгийн төв (дизайны координат)

    def mouth(self, mode: str, step: int) -> ImageTk.PhotoImage:
        key = ("mouth", mode, step)
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        box = (round(self._k(self.MOUTH_BOX[0])), round(self._k(self.MOUTH_BOX[1])))
        layer = self._blank(box)
        draw = ImageDraw.Draw(layer)
        k = self._k
        # Хайрцгийн (0,0) нь дизайны координатын аль цэг болохыг тооцно
        ox = CX - self.MOUTH_BOX[0] / 2
        oy = self.MOUTH_CY - self.MOUTH_BOX[1] / 2

        def point(x, y):
            return k(x - ox), k(y - oy)

        if mode == "listening":
            level = step / (MOUTH_STEPS - 1)
            rx = 14 + 3 * level
            ry = (9 + 20 * level) / 2
            cx, cy = point(CX, EYE_Y + 40)
            draw.ellipse((cx - k(rx), cy - k(ry), cx + k(rx), cy + k(ry)), fill=CYAN + (255,))
        elif mode == "recognizing":
            phase = 2 * math.pi * step / MOUTH_STEPS
            points = []
            for index in range(21):
                x = CX - 20 + index * 2
                y = EYE_Y + 38 + math.sin(phase + index * 0.55) * 4
                points.append(point(x, y))
            draw.line(points, fill=CYAN + (255,), width=max(1, round(k(5.5))), joint="curve")
        else:
            cx, cy = point(CX, EYE_Y + 20)
            radius = k(19)
            draw.arc(
                (cx - radius, cy - radius, cx + radius, cy + radius),
                start=36, end=144, fill=CYAN + (255,), width=max(1, round(k(5.5))),
            )
        return self._finish(layer, key)


class RobotOrb(tk.Canvas):
    """Роботыг харуулж, төлөв/түвшний дагуу амьдруулна."""

    def __init__(self, parent, width: int = 240, bg: str = theme.PANEL) -> None:
        self.sprites = _Sprites(width)
        super().__init__(
            parent, width=width, height=self.sprites.height,
            bg=bg, highlightthickness=0, bd=0,
        )
        self.mode = "idle"
        self._level = 0.0
        self._target = 0.0
        self._time = 0.0
        self._job: str | None = None

        centre = (width / 2, self.sprites.height / 2)
        self._aura = self.create_image(centre, image=self.sprites.aura(0))
        self._rings = self.create_image(centre, image=self.sprites.rings(False, 0))
        self._ears = [
            self.create_image(self._at(CX + sign * 136, 152 + BODY_DY), image=None)
            for sign in (-1, 1)
        ]
        self._body = self.create_image(centre, image=self.sprites.body())
        self._eyes = [
            self.create_image(self._at(CX + sign * EYE_X, EYE_Y), image=None)
            for sign in (-1, 1)
        ]
        self._mouth = self.create_image(
            self._at(CX, _Sprites.MOUTH_CY), image=self.sprites.mouth("idle", 0)
        )
        for index, sign in enumerate((-1, 1)):
            self.itemconfigure(self._ears[index], image=self.sprites.ear_glow(3))
            self.itemconfigure(self._eyes[index], image=self.sprites.eye("idle", EYE_STEPS - 1))

        self.bind("<Destroy>", lambda _e: self.stop())

    # ------------------------------------------------------------------
    def _at(self, x: float, y: float) -> tuple[float, float]:
        return x * self.sprites.scale, y * self.sprites.scale

    def set_mode(self, mode: str) -> None:
        if mode not in MODES or mode == self.mode:
            return
        self.mode = mode
        self._draw()

    def set_level(self, level: float) -> None:
        """0..1 хооронд нормчилсон микрофоны түвшин."""
        self._target = max(0.0, min(1.0, level))

    def start(self) -> None:
        if self._job is None:
            self._job = self.after(16, self._tick)

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.after_cancel(self._job)
            except tk.TclError:
                pass
            self._job = None

    # ------------------------------------------------------------------
    def _tick(self) -> None:
        # Цонх tray-д нуугдсан үед зурах нь дэмий. Цагийг бүр мөсөн зогсоохгүй
        # — цонх дахин нээгдэхийг мэдэхийн тулд ховорхон сэрнэ.
        if not self.winfo_viewable():
            self._job = self.after(IDLE_POLL_MS, self._tick)
            return
        active = self.mode != "idle"
        step = 33 if active else 66
        self._job = self.after(step, self._tick)
        self._time += step / 1000.0
        moment = self._time

        if self.mode == "listening":
            target = self._target
        elif self.mode == "recognizing":
            target = 0.52 + 0.12 * math.sin(moment * 7.5)
        else:
            target = 0.1 + 0.03 * math.sin(moment * 0.9)
        self._level += (target - self._level) * (0.28 if active else 0.08)
        self._draw()

    def _draw(self) -> None:
        moment, level, mode = self._time, self._level, self.mode
        active = mode != "idle"
        scale = self.sprites.scale
        width, height = self.sprites.width, self.sprites.height

        bob = (
            math.sin(moment * 1.2) * 4
            if mode == "idle"
            else math.sin(moment * 4) * 2.6 * (0.4 + level)
        )
        glow = (
            0.55 + 0.2 * math.sin(moment * 1.3)
            if mode == "idle"
            else 0.7 + 0.3 * min(1.0, level * 1.4)
        )
        dy = bob * scale

        self.itemconfigure(self._aura, image=self.sprites.aura(_bucket(level, AURA_STEPS)))
        speed = 0.95 if mode == "recognizing" else 0.6
        phase = int(moment * speed * RING_PHASES) % RING_PHASES
        self.itemconfigure(self._rings, image=self.sprites.rings(active, phase))

        self.coords(self._body, width / 2, height / 2 + dy)

        ear = self.sprites.ear_glow(_bucket(glow, GLOW_STEPS))
        for index, sign in enumerate((-1, 1)):
            x, y = self._at(CX + sign * 136, 152 + BODY_DY)
            self.itemconfigure(self._ears[index], image=ear)
            self.coords(self._ears[index], x, y + dy)

        # Нүд анивчих: 4.4 секунд тутам богинохон
        cycle = moment % 4.4
        open_amount = abs(cycle - 0.08) / 0.08 if cycle < 0.16 else 1.0
        eye = self.sprites.eye(mode, _bucket(open_amount, EYE_STEPS))
        look = math.sin(moment * 2.2) * 5 if mode == "recognizing" else 0.0
        for index, sign in enumerate((-1, 1)):
            x, y = self._at(CX + sign * EYE_X + look, EYE_Y)
            self.itemconfigure(self._eyes[index], image=eye)
            self.coords(self._eyes[index], x, y + dy)

        if mode == "listening":
            step = _bucket(min(1.0, level * 1.3), MOUTH_STEPS)
        elif mode == "recognizing":
            step = int(moment * 8 / (2 * math.pi) * MOUTH_STEPS) % MOUTH_STEPS
        else:
            step = 0
        self.itemconfigure(self._mouth, image=self.sprites.mouth(mode, step))
        x, y = self._at(CX, _Sprites.MOUTH_CY)
        self.coords(self._mouth, x, y + dy)


def _bucket(value: float, steps: int) -> int:
    return max(0, min(steps - 1, int(round(value * (steps - 1)))))
