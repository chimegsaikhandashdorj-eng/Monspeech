"""Курсорын доор гарч ирдэг дууны долгион ба богино мэдэгдэл.

Хүрээгүй, фокус авдаггүй, дамжин товшигддог жижиг цонх. Сонсож эхэлмэгц
гарч ирээд микрофоны түвшний дагуу хөдөлнө, таних явцад давалгаа болно,
дуусахад үр дүнг богино хугацаанд харуулаад алга болно.
"""

from __future__ import annotations

import math
import tkinter as tk

from .winfocus import anchor_position, monitor_work_area, place_window

HEIGHT = 38
WAVE_WIDTH = 116
MAX_WIDTH = 340  # мэдэгдэл харуулах үеийн дээд өргөн
BARS = 9
BAR_WIDTH = 3
BAR_GAP = 2
RADIUS = HEIGHT / 2  # бүтэн капсул
FRAME_MS = 33
OFFSET_Y = 22  # курсорын доогуур
MESSAGE_MS = 1500

KEY_COLOR = "#010203"  # ил тод болгох түлхүүр өнгө
PANEL = "#191c21"
BORDER = "#2f333b"
BORDER_WARN = "#3a2a2e"
TEXT_COLOR = "#e6e8eb"
TEXT_MUTED = "#9aa1ab"
OK = "#3ddc84"
DANGER = "#ff5f56"

# Логоны градиент — заалт ба лого нэг гэр бүл болно
GRADIENT = [
    "#29BEF0", "#3EA9F0", "#567AEB", "#6265E9", "#7C4DE8",
    "#9146E7", "#A742E9", "#B63DEB", "#C43AEC",
]

MAX_BAR = 26.0  # дизайны 4..26 px
MIN_BAR = 4.0
HALF = BARS // 2

# Цонхны хэв маяг
GWL_EXSTYLE = -20
WS_EX_NOACTIVATE = 0x08000000
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_TRANSPARENT = 0x00000020


class WaveOverlay:
    """Микрофоны түвшин ба богино мэдэгдлийг харуулах жижиг заалт."""

    def __init__(self, root: tk.Tk, get_level) -> None:
        self.root = root
        self.get_level = get_level
        self.visible = False
        self.processing = False
        self.mode = "wave"  # "wave" эсвэл "message"
        self._job = None
        self._message_job = None
        self._phase = 0.0
        self._levels = [0.0] * (BARS // 2 + 1)
        self._anchor = (0, 0)
        self._panel_width = WAVE_WIDTH
        self.hwnd = None

        self.win = tk.Toplevel(root)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.configure(bg=KEY_COLOR)
        try:
            self.win.attributes("-topmost", True)
            self.win.attributes("-transparentcolor", KEY_COLOR)
            self.win.attributes("-alpha", 0.96)
        except tk.TclError:
            pass

        # Зурагдах талбар нь үргэлж хамгийн өргөн хэмжээтэй; ашиглаагүй хэсэг нь
        # ил тод тул харагдахгүй. Ингэснээр мэдэгдэл харуулахад цонх сэлгэхгүй.
        self.canvas = tk.Canvas(
            self.win, width=MAX_WIDTH, height=HEIGHT, bg=KEY_COLOR, highlightthickness=0, bd=0
        )
        self.canvas.pack()

        self._panel_id = self.canvas.create_polygon(
            0, 0, 0, 0, fill=PANEL, outline=BORDER, width=1, smooth=True
        )
        self._bar_ids = [
            self.canvas.create_line(
                0, HEIGHT / 2 - 2, 0, HEIGHT / 2 + 2,
                width=BAR_WIDTH, fill=GRADIENT[index], capstyle="round",
            )
            for index in range(BARS)
        ]
        self._dot_id = self.canvas.create_oval(0, 0, 0, 0, fill=OK, outline="")
        self._text_id = self.canvas.create_text(
            0, HEIGHT / 2, text="", fill=TEXT_COLOR, font=("Segoe UI", 9), anchor="w"
        )
        self._layout(WAVE_WIDTH)

        self.win.update_idletasks()
        self._apply_window_style()

    # ------------------------------------------------------------------
    def _apply_window_style(self) -> None:
        """Фокус авахгүй, taskbar-т харагдахгүй, товшилтыг дамжуулна."""
        try:
            import ctypes

            user32 = ctypes.windll.user32
            self.hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            style = user32.GetWindowLongW(self.hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(
                self.hwnd,
                GWL_EXSTYLE,
                style | WS_EX_NOACTIVATE | WS_EX_TOOLWINDOW | WS_EX_TRANSPARENT,
            )
        except Exception:  # noqa: BLE001 - заалт бол хоёрдогч, апп зогсоохгүй
            self.hwnd = None

    def _rounded_points(self, x1, y1, x2, y2, radius):
        return [
            x1 + radius, y1, x2 - radius, y1, x2, y1, x2, y1 + radius,
            x2, y2 - radius, x2, y2, x2 - radius, y2, x1 + radius, y2,
            x1, y2, x1, y2 - radius, x1, y1 + radius, x1, y1,
        ]

    def _layout(self, panel_width: int, border: str = BORDER) -> None:
        """Самбарыг өгсөн өргөнөөр голлуулан байрлуулна."""
        self._panel_width = panel_width
        left = (MAX_WIDTH - panel_width) / 2
        right = left + panel_width
        self.canvas.coords(
            self._panel_id, *self._rounded_points(left + 1, 1, right - 1, HEIGHT - 1, RADIUS)
        )
        self.canvas.itemconfigure(self._panel_id, outline=border)
        centre = MAX_WIDTH / 2
        span = BARS * BAR_WIDTH + (BARS - 1) * BAR_GAP
        start = centre - span / 2 + BAR_WIDTH / 2
        for index, bar_id in enumerate(self._bar_ids):
            x = start + index * (BAR_WIDTH + BAR_GAP)
            self.canvas.coords(bar_id, x, HEIGHT / 2 - 2, x, HEIGHT / 2 + 2)
        # Мэдэгдлийн цэг ба текст зүүн талдаа
        self.canvas.coords(self._dot_id, left + 14, HEIGHT / 2 - 4, left + 22, HEIGHT / 2 + 4)
        self.canvas.coords(self._text_id, left + 30, HEIGHT / 2)

    def _show_wave(self) -> None:
        for bar_id in self._bar_ids:
            self.canvas.itemconfigure(bar_id, state="normal")
        self.canvas.itemconfigure(self._dot_id, state="hidden")
        self.canvas.itemconfigure(self._text_id, state="hidden")

    def _show_message(self) -> None:
        for bar_id in self._bar_ids:
            self.canvas.itemconfigure(bar_id, state="hidden")
        self.canvas.itemconfigure(self._dot_id, state="normal")
        self.canvas.itemconfigure(self._text_id, state="normal")

    # ------------------------------------------------------------------
    def show(self) -> None:
        """Сонсох горимд шилжиж, долгион харуулна."""
        self._cancel_message()
        self.processing = False
        self.mode = "wave"
        self._levels = [0.0] * (BARS // 2 + 1)
        self._layout(WAVE_WIDTH)
        self._show_wave()
        if not self.visible:
            self.visible = True
            self.win.deiconify()
            self.win.lift()
            # Tk нь харагдах болохдоо хуучин байрлалаа сэргээж мэднэ
            self._move_to_anchor(force=True)
            self._tick()
        else:
            self._move_to_anchor(force=True)

    def set_processing(self, value: bool) -> None:
        self.processing = value

    def flash(self, text: str, kind: str = "text") -> None:
        """Богино мэдэгдэл харуулаад өөрөө алга болно."""
        if not text:
            return
        self._cancel_message()
        shown = text if len(text) <= 40 else text[:39] + "…"
        warning = kind == "warning"
        self.canvas.itemconfigure(
            self._text_id, text=shown, fill=TEXT_MUTED if warning else TEXT_COLOR
        )
        self.canvas.itemconfigure(self._dot_id, fill=DANGER if warning else OK)

        self.mode = "message"
        width = min(MAX_WIDTH, max(150, 56 + int(len(shown) * 7.2)))
        self._layout(width, BORDER_WARN if warning else BORDER)
        self._show_message()

        if not self.visible:
            self.visible = True
            self.win.deiconify()
            self.win.lift()
            self._move_to_anchor(force=True)
            self._tick()
        self._message_job = self.root.after(MESSAGE_MS, self.hide)

    def _cancel_message(self) -> None:
        if self._message_job is not None:
            try:
                self.root.after_cancel(self._message_job)
            except Exception:  # noqa: BLE001
                pass
            self._message_job = None

    def hide(self) -> None:
        self._cancel_message()
        self.visible = False
        self.processing = False
        self.mode = "wave"
        if self._job is not None:
            try:
                self.root.after_cancel(self._job)
            except Exception:  # noqa: BLE001
                pass
            self._job = None
        self.win.withdraw()

    def destroy(self) -> None:
        self.hide()
        try:
            self.win.destroy()
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------------
    def _move_to_anchor(self, force: bool = False) -> None:
        x, y = anchor_position()
        left = x - MAX_WIDTH // 2
        top = y + OFFSET_Y

        # Курсор байгаа дэлгэцийн хүрээнд барина (олон дэлгэцтэй үед чухал).
        # Хэмжилтийг харагдах самбарын өргөнөөр хийнэ — цонхны ил тод хэсэг
        # дэлгэцээс халих нь асуудалгүй.
        margin = (MAX_WIDTH - self._panel_width) / 2
        work_left, work_top, work_right, work_bottom = monitor_work_area(x, y)
        left = max(work_left + 4 - margin, min(left, work_right - MAX_WIDTH - 4 + margin))
        if top + HEIGHT > work_bottom - 4:
            top = y - HEIGHT - OFFSET_Y // 2  # доогуур багтахгүй бол дээгүүр нь
        top = max(work_top + 4, min(top, work_bottom - HEIGHT - 4))
        left, top = int(left), int(top)

        if force or abs(left - self._anchor[0]) > 6 or abs(top - self._anchor[1]) > 6:
            self._anchor = (left, top)
            # Tk-ийн geometry нь сөрөг координатыг "баруун захаас" гэж ойлгодог тул
            # цонхыг Win32-оор шууд байрлуулна.
            if not place_window(self.hwnd, left, top):
                self.win.geometry(f"{MAX_WIDTH}x{HEIGHT}+{left}+{top}")

    def _tick(self) -> None:
        if not self.visible:
            return
        self._move_to_anchor()
        self._phase += 0.28

        if self.mode == "wave":
            if self.processing:
                self._render_processing()
            else:
                self._render_levels()

        self._job = self.root.after(FRAME_MS, self._tick)

    def _set_bar(self, bar_id, height: float, colour: str) -> None:
        height = max(MIN_BAR, min(MAX_BAR, height))
        x1, _, x2, _ = self.canvas.coords(bar_id)[:4]
        self.canvas.coords(bar_id, x1, HEIGHT / 2 - height / 2, x2, HEIGHT / 2 + height / 2)
        self.canvas.itemconfig(bar_id, fill=colour)

    def _render_levels(self) -> None:
        """Шинэ түвшин голдоо төрж, хоёр тийшээ тархана."""
        level = min(1.0, max(0.0, self.get_level() / 3200.0))
        # Чимээгүй үед ч бага зэрэг амьд харагдана
        level = max(level, 0.05)
        # Огцом үсрэхээс сэргийлж зөөлрүүлнэ
        previous = self._levels[0]
        smoothed = previous + (level - previous) * (0.55 if level > previous else 0.3)
        self._levels = [smoothed] + self._levels[:-1]

        for index, bar_id in enumerate(self._bar_ids):
            distance = abs(index - HALF)
            value = self._levels[distance] * (1.0 - 0.11 * distance)
            self._set_bar(bar_id, MIN_BAR + value * (MAX_BAR - MIN_BAR) * 1.6, GRADIENT[index])

    def _render_processing(self) -> None:
        """Таниж байх үе: ижил градиент, гэхдээ жигд гүйх давалгаа."""
        for index, bar_id in enumerate(self._bar_ids):
            wave = math.sin(self._phase - index * 0.55)
            height = MIN_BAR + (wave + 1.0) / 2.0 * (MAX_BAR - MIN_BAR) * 0.7
            self._set_bar(bar_id, height, GRADIENT[index])
