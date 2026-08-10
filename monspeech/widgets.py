"""Захиалгат виджетүүд.

ttk-ийн стандарт чагт, товч нь хуучинсаг харагддаг ба өнгө нь бүрэн
хянагддаггүй. Tk-ийн Canvas дээр шууд зурвал ирмэг нь барзгар гардаг тул
унтраалга зэрэг дугуй хэлбэртэй зүйлсийг Pillow-оор 4 дахин том зураад
буулгаж, зөөлөн ирмэгтэй болгоно.
"""

from __future__ import annotations

import tkinter as tk

from PIL import Image, ImageDraw, ImageTk

from . import theme

SUPERSAMPLE = 4
_image_cache: dict[tuple, ImageTk.PhotoImage] = {}


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def toggle_image(on: bool, hover: bool = False, bg: str = theme.BG) -> ImageTk.PhotoImage:
    """Унтраалгын зураг (34×18). Кэшлэнэ — Tk зургийн лавлагааг барих ёстой."""
    key = ("toggle", on, hover, bg)
    cached = _image_cache.get(key)
    if cached is not None:
        return cached

    width, height = 34, 18
    scale = SUPERSAMPLE
    img = Image.new("RGB", (width * scale, height * scale), bg)
    draw = ImageDraw.Draw(img)

    track = theme.TOGGLE_ON if on else theme.TOGGLE_OFF
    if hover:
        track = _lighten(track, 0.12)
    knob = theme.KNOB_ON if on else theme.KNOB_OFF

    _rounded(draw, (0, 0, width * scale - 1, height * scale - 1), height * scale / 2, track)
    knob_size = 14 * scale
    inset = 2 * scale
    left = (width * scale - knob_size - inset) if on else inset
    draw.ellipse((left, inset, left + knob_size, inset + knob_size), fill=knob)

    photo = ImageTk.PhotoImage(img.resize((width, height), Image.LANCZOS))
    _image_cache[key] = photo
    return photo


def _lighten(colour: str, amount: float) -> str:
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (min(255, int(c + (255 - c) * amount)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


class Toggle(tk.Label):
    """Асаах/унтраах унтраалга. `command` нь шинэ утгыг хүлээж авна."""

    def __init__(self, parent, value: bool, command=None, bg: str = theme.BG) -> None:
        super().__init__(parent, bd=0, highlightthickness=0, bg=bg, cursor="hand2")
        self._value = bool(value)
        self._hover = False
        self._bg = bg
        self.command = command
        self._redraw()
        self.bind("<Button-1>", self._clicked)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)

    @property
    def value(self) -> bool:
        return self._value

    def set(self, value: bool) -> None:
        self._value = bool(value)
        self._redraw()

    def _redraw(self) -> None:
        self.configure(image=toggle_image(self._value, self._hover, self._bg))

    def _clicked(self, _event=None) -> None:
        self._value = not self._value
        self._redraw()
        if self.command:
            self.command(self._value)

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._redraw()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._redraw()


class ScrollFrame(tk.Frame):
    """Гүйлгэдэг талбар. Агуулгыг `.body` дотор байрлуулна."""

    def __init__(self, parent, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = tk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            bg=theme.BORDER,
            troughcolor=theme.BG,
            activebackground=theme.MUTED,
            bd=0,
            highlightthickness=0,
            width=8,
            relief="flat",
        )
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")

        self.body.bind("<Configure>", self._resize_body)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _on_scroll(self, first, last) -> None:
        """Бүх агуулга багтаж байвал гүйлгэгчийг нуухгүй харуулахгүй."""
        if float(first) <= 0.0 and float(last) >= 1.0:
            self.scrollbar.pack_forget()
        else:
            self.scrollbar.pack(side="right", fill="y")
        self.scrollbar.set(first, last)

    def _resize_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event) -> None:
        self.canvas.itemconfigure(self._window, width=event.width)

    def _wheel(self, event) -> None:
        try:
            # `bind_all` нь бүх цонхонд хүчинтэй тул түүхийн цонхон дээр
            # гүйлгэхэд ард байгаа энэ талбар хөдөлдөг байсан.
            if event.widget.winfo_toplevel() is not self.winfo_toplevel():
                return
            if not self.canvas.winfo_ismapped():
                return
            first, last = self.canvas.yview()
            if first <= 0.0 and last >= 1.0:
                return
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


class Section(tk.Frame):
    """Гарчигтай хэсэг. `collapsible=True` бол товшиход нээгдэж хаагдана."""

    def __init__(
        self,
        parent,
        title: str,
        collapsible: bool = False,
        count: int | None = None,
        expanded: bool = True,
        bg: str = theme.BG,
    ) -> None:
        super().__init__(parent, bg=bg)
        self.title = title
        self.collapsible = collapsible
        self._expanded = expanded if not collapsible else False
        self._bg = bg

        self.header = tk.Frame(self, bg=bg, cursor="hand2" if collapsible else "arrow")
        self.header.pack(fill="x", padx=theme.PAD_X, pady=(theme.SECTION_GAP, 6))

        if collapsible:
            self.arrow = tk.Label(
                self.header, text="▸", bg=bg, fg=theme.DIM, font=theme.UI_SMALL
            )
            self.arrow.pack(side="left", padx=(0, 8))
            self.label = tk.Label(
                self.header, text=title, bg=bg, fg=theme.MUTED, font=theme.UI
            )
            self.label.pack(side="left")
            self.count = tk.Label(
                self.header,
                text=f"({count})" if count is not None else "",
                bg=bg,
                fg=theme.DIM,
                font=theme.MONO,
            )
            self.count.pack(side="left", padx=6)
            for widget in (self.header, self.arrow, self.label, self.count):
                widget.bind("<Button-1>", self.toggle)
        else:
            self.label = tk.Label(
                self.header, text=title.upper(), bg=bg, fg=theme.DIM, font=theme.MONO
            )
            self.label.pack(side="left")

        self.body = tk.Frame(self, bg=bg)
        if self._expanded:
            self.body.pack(fill="x", padx=theme.PAD_X)

    @property
    def expanded(self) -> bool:
        return self._expanded

    def toggle(self, _event=None) -> None:
        self._expanded = not self._expanded
        if self._expanded:
            self.body.pack(fill="x", padx=theme.PAD_X)
            self.arrow.configure(text="▾")
        else:
            self.body.pack_forget()
            self.arrow.configure(text="▸")

    def set_count(self, count: int) -> None:
        if self.collapsible:
            self.count.configure(text=f"({count})")

    def divider(self) -> tk.Frame:
        line = tk.Frame(self, bg=theme.DIVIDER, height=1)
        line.pack(fill="x", padx=theme.PAD_X, pady=(theme.SECTION_GAP, 0))
        return line


def label_row(parent, text: str, bg: str = theme.BG) -> tuple[tk.Frame, tk.Frame]:
    """Зүүн талд шошго, баруун талд удирдлага байрлах мөр үүсгэнэ."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x", pady=4)
    tk.Label(
        row, text=text, bg=bg, fg=theme.MUTED, font=theme.UI,
        width=theme.LABEL_WIDTH, anchor="w",
    ).pack(side="left")
    holder = tk.Frame(row, bg=bg)
    holder.pack(side="left", fill="x", expand=True)
    return row, holder


def toggle_row(
    parent, text: str, value: bool, command, bg: str = theme.BG
) -> tuple[tk.Frame, Toggle]:
    """Шошго + унтраалга + доогуураа нарийн зураастай мөр."""
    row = tk.Frame(parent, bg=bg)
    row.pack(fill="x")
    inner = tk.Frame(row, bg=bg)
    inner.pack(fill="x", pady=6)
    tk.Label(inner, text=text, bg=bg, fg=theme.TEXT, font=theme.UI, anchor="w").pack(
        side="left"
    )
    toggle = Toggle(inner, value, command, bg=bg)
    toggle.pack(side="right")
    tk.Frame(row, bg=theme.ROW_LINE, height=1).pack(fill="x")
    return row, toggle


class Keycaps(tk.Frame):
    """Товчлуурын хослолыг keycap хэлбэрээр харуулна: [Win] + [Alt]."""

    def __init__(self, parent, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._items: list[tk.Widget] = []

    def show(self, parts: list[str]) -> None:
        for item in self._items:
            item.destroy()
        self._items = []
        colour = theme.TEXT
        for index, part in enumerate(parts):
            if index:
                plus = tk.Label(
                    self, text="+", bg=self._bg, fg=theme.DIM, font=theme.UI_SMALL
                )
                plus.pack(side="left", padx=3)
                self._items.append(plus)
            cap = tk.Label(
                self,
                text=part,
                bg=theme.PANEL,
                fg=colour,
                font=theme.MONO_KEY,
                padx=7,
                pady=3,
                highlightthickness=1,
                highlightbackground=theme.BORDER,
            )
            cap.pack(side="left")
            self._items.append(cap)

    def show_text(self, text: str, colour: str = theme.WARN) -> None:
        for item in self._items:
            item.destroy()
        self._items = []
        label = tk.Label(self, text=text, bg=self._bg, fg=colour, font=theme.UI_SMALL)
        label.pack(side="left")
        self._items.append(label)


class Link(tk.Label):
    """Товшиж болох текст."""

    def __init__(self, parent, text: str, command, bg: str = theme.BG, font=None) -> None:
        super().__init__(
            parent, text=text, bg=bg, fg=theme.ACCENT, font=font or theme.UI_SMALL,
            cursor="hand2",
        )
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Enter>", lambda _e: self.configure(fg=_lighten(theme.ACCENT, 0.25)))
        self.bind("<Leave>", lambda _e: self.configure(fg=theme.ACCENT))


class StatusBlock(tk.Frame):
    """Цонхны хамгийн дээд талын төлөв: амьд багана + гарчиг + тайлбар."""

    def __init__(self, parent, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        width = theme.BAR_COUNT * theme.BAR_WIDTH + (theme.BAR_COUNT - 1) * theme.BAR_GAP
        self.canvas = tk.Canvas(
            self, width=width, height=theme.BAR_MAX + 2, bg=bg, highlightthickness=0, bd=0
        )
        self.canvas.pack(side="left", padx=(0, 14))
        centre = (theme.BAR_MAX + 2) / 2
        self._bars = []
        for index in range(theme.BAR_COUNT):
            x = index * (theme.BAR_WIDTH + theme.BAR_GAP) + theme.BAR_WIDTH / 2
            self._bars.append(
                self.canvas.create_line(
                    x, centre - 2, x, centre + 2,
                    width=theme.BAR_WIDTH,
                    fill=theme.GRADIENT[index],
                    capstyle="round",
                )
            )

        text = tk.Frame(self, bg=bg)
        text.pack(side="left", fill="x", expand=True)
        self.title_var = tk.StringVar(value="Бэлэн")
        self.detail_var = tk.StringVar(value="Win + Alt дарж бариад ярь")
        tk.Label(
            text, textvariable=self.title_var, bg=bg, fg=theme.TEXT,
            font=theme.UI_TITLE, anchor="w",
        ).pack(fill="x")
        tk.Label(
            text, textvariable=self.detail_var, bg=bg, fg=theme.DIM,
            font=theme.MONO, anchor="w", justify="left", wraplength=300,
        ).pack(fill="x", pady=(2, 0))

    def set_text(self, title: str, detail: str) -> None:
        self.title_var.set(title)
        self.detail_var.set(detail)

    def set_bars(self, heights: list[float]) -> None:
        centre = (theme.BAR_MAX + 2) / 2
        for index, bar in enumerate(self._bars):
            height = max(theme.BAR_MIN, min(theme.BAR_MAX, heights[index]))
            x1, _, x2, _ = self.canvas.coords(bar)[:4]
            self.canvas.coords(bar, x1, centre - height / 2, x2, centre + height / 2)
