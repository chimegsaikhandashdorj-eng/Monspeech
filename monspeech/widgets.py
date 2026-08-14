"""Захиалгат виджетүүд.

ttk-ийн стандарт чагт, товч нь хуучинсаг харагддаг ба өнгө нь бүрэн
хянагддаггүй. Tk-ийн Canvas дээр шууд зурвал ирмэг нь барзгар гардаг тул
унтраалга зэрэг дугуй хэлбэртэй зүйлсийг Pillow-оор 4 дахин том зураад
буулгаж, зөөлөн ирмэгтэй болгоно.

**Дугуй булан.** Tk-ийн Frame нь зөвхөн дөрвөлжин хүрээтэй. Дизайны дугуй
буланг гаргахын тулд хоёр арга хэрэглэв:

* `RoundedLabel` — текст агуулсан жижиг зүйлс (товч, чип, keycap). Шошгын
  байгалийн хэмжээг хэмжээд яг тэр хэмжээний дугуй дэвсгэр зураг үүсгэж,
  `compound="center"`-оор текстийг дээр нь бичнэ.
* `RoundedBox` — агуулагч (карт, жагсаалт, хайлтын талбар). Дэвсгэр зураг нь
  `place`-ээр бүтэн талбайг эзэлж, агуулга нь **хэвтээ чиглэлд радиусын
  зайгаар доторшуулж** багцлагдана. Ингэснээр 4 булангийн нуман хэсэгт
  агуулга огт хүрэхгүй тул дугуй ирмэг харагдана.

Дизайны бүтэц: `Page` (нэг цэсний агуулга) → `Card` (хүрээтэй бүлэг) →
`Card.row()` (гарчиг + тайлбар + баруун талын удирдлага).
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageDraw, ImageTk

from . import icons, theme

SUPERSAMPLE = 4
_image_cache: dict[tuple, ImageTk.PhotoImage] = {}
_corner_cache: dict[tuple, tuple] = {}


def _rounded(draw, box, radius, fill):
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def _lighten(colour: str, amount: float) -> str:
    r, g, b = (int(colour[i : i + 2], 16) for i in (1, 3, 5))
    r, g, b = (min(255, int(c + (255 - c) * amount)) for c in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"


def _corners(radius: int, fill: str, outside: str, border: str | None) -> tuple:
    """Дугуй булангийн 4 хавтанг үүсгэнэ (radius × radius).

    Бүтэн зургийг supersample хийж зурвал том карт дээр удаан — зөвхөн булан
    нь л зөөлрүүлэх шаардлагатай тул нумыг ганц удаа зураад кэшлэнэ.
    """
    key = (radius, fill, outside, border)
    cached = _corner_cache.get(key)
    if cached is not None:
        return cached
    scale = SUPERSAMPLE
    side = radius * 2 * scale
    image = Image.new("RGB", (side, side), outside)
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, side - 1, side - 1), radius=radius * scale, fill=fill,
        outline=border, width=scale if border else 0,
    )
    image = image.resize((radius * 2, radius * 2), Image.LANCZOS)
    tiles = (
        image.crop((0, 0, radius, radius)),
        image.crop((radius, 0, radius * 2, radius)),
        image.crop((0, radius, radius, radius * 2)),
        image.crop((radius, radius, radius * 2, radius * 2)),
    )
    _corner_cache[key] = tiles
    return tiles


def rounded_photo(
    width: int, height: int, radius: int, fill: str,
    outside: str, border: str | None = None,
) -> ImageTk.PhotoImage:
    """Дугуй буланлаг тэгш өнцөгт зураг. Булангийн хавтангаас угсарна."""
    width, height = max(1, width), max(1, height)
    radius = max(0, min(radius, width // 2, height // 2))
    image = Image.new("RGB", (width, height), fill)
    draw = ImageDraw.Draw(image)
    if border:
        draw.line([(radius, 0), (width - radius - 1, 0)], fill=border)
        draw.line([(radius, height - 1), (width - radius - 1, height - 1)], fill=border)
        draw.line([(0, radius), (0, height - radius - 1)], fill=border)
        draw.line([(width - 1, radius), (width - 1, height - radius - 1)], fill=border)
    if radius:
        top_left, top_right, bottom_left, bottom_right = _corners(radius, fill, outside, border)
        image.paste(top_left, (0, 0))
        image.paste(top_right, (width - radius, 0))
        image.paste(bottom_left, (0, height - radius))
        image.paste(bottom_right, (width - radius, height - radius))
    return ImageTk.PhotoImage(image)


def _rounded_cached(
    width: int, height: int, radius: int, fill: str,
    outside: str, border: str | None = None,
) -> ImageTk.PhotoImage:
    """Хэмжээ нь тогтмол зүйлсэд (товч, чип) — кэшлэнэ."""
    key = (width, height, radius, fill, outside, border)
    cached = _image_cache.get(key)
    if cached is not None:
        return cached
    photo = rounded_photo(width, height, radius, fill, outside, border)
    _image_cache[key] = photo
    return photo


class RoundedLabel(tk.Label):
    """Дугуй дэвсгэртэй текст — товч, чип, keycap.

    Эхлээд зурагггүйгээр хэмжээгээ хэмжиж, дараа нь яг тэр хэмжээний дэвсгэр
    зураг тавина. `compound="center"` тул текст нь зургийн дээр бичигдэнэ.
    """

    def __init__(
        self, parent, radius: int, fill: str, outside: str,
        border: str | None = None, **kwargs,
    ) -> None:
        super().__init__(parent, bd=0, highlightthickness=0, bg=outside, **kwargs)
        self._radius = radius
        self._fill = fill
        self._outside = outside
        self._border = border
        self._photo: ImageTk.PhotoImage | None = None
        self.refresh()

    def refresh(self) -> None:
        self.configure(image="")
        width, height = self.winfo_reqwidth(), self.winfo_reqheight()
        self._photo = _rounded_cached(
            width, height, self._radius, self._fill, self._outside, self._border
        )
        self.configure(image=self._photo, compound="center", bg=self._outside)

    def restyle(
        self, fill: str | None = None, border: str | None = ...,
        outside: str | None = None, **kwargs,
    ) -> None:
        """Өнгө эсвэл текст солиод дэвсгэрийг нь дахин зурна."""
        if fill is not None:
            self._fill = fill
        if border is not ...:
            self._border = border
        if outside is not None:
            self._outside = outside
        if kwargs:
            self.configure(**kwargs)
        self.refresh()


class RoundedBox(tk.Frame):
    """Дугуй буланлаг агуулагч. Агуулгыг `.inner` дотор байрлуулна.

    Дэвсгэр зураг нь бүтэн талбайг эзэлж, `inner` нь хэвтээ чиглэлд радиусын
    зайгаар доторшино — булангийн нуман хэсэг ил үлдэнэ.
    """

    def __init__(
        self, parent, fill: str = theme.PANEL, outside: str = theme.BG,
        radius: int = theme.RADIUS, border: str | None = theme.BORDER,
        pad: tuple[int, int] | None = None,
    ) -> None:
        super().__init__(parent, bg=outside)
        self.radius = radius
        self.fill = fill
        self.outside = outside
        self.border = border
        self._photo: ImageTk.PhotoImage | None = None
        self._size = (0, 0)

        self._back = tk.Label(self, bd=0, highlightthickness=0, bg=outside)
        self._back.place(x=0, y=0, relwidth=1, relheight=1)
        self.inner = tk.Frame(self, bg=fill)
        padx, pady = pad if pad is not None else (radius, 1)
        self.inner.pack(fill="both", expand=True, padx=padx, pady=pady)
        self.bind("<Configure>", self._resized)

    def _resized(self, event) -> None:
        size = (event.width, event.height)
        if size == self._size or event.width < 4 or event.height < 4:
            return
        self._size = size
        self._photo = rounded_photo(
            event.width, event.height, self.radius, self.fill, self.outside, self.border
        )
        self._back.configure(image=self._photo)

    def restyle(self, fill: str | None = None, border: str | None = ...) -> None:
        if fill is not None:
            self.fill = fill
            self.inner.configure(bg=fill)
        if border is not ...:
            self.border = border
        self._size = (0, 0)
        self.event_generate("<Configure>")


SCROLLBAR_STYLE = "Mon.Vertical.TScrollbar"
_scrollbar_ready = False


def scrollbar(parent, command, trough: str = theme.BG) -> ttk.Scrollbar:
    """Бараан гүйлгэгч.

    Windows дээр `tk.Scrollbar` нь системийн харагдацтай тул `bg`,
    `troughcolor`-ыг үл тоомсорлодог — цайвар зураас болж харагдана. `clam`
    сэдэвтэй `ttk.Scrollbar` нь өнгөө бүрэн дагадаг.
    """
    global _scrollbar_ready
    style = ttk.Style(parent)
    if not _scrollbar_ready:
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        _scrollbar_ready = True
    style.configure(
        SCROLLBAR_STYLE, troughcolor=trough, background=theme.BORDER,
        bordercolor=trough, darkcolor=theme.BORDER, lightcolor=theme.BORDER,
        arrowcolor=trough, arrowsize=0, gripcount=0, relief="flat", borderwidth=0,
    )
    style.map(
        SCROLLBAR_STYLE,
        background=[("active", theme.MUTED), ("!active", theme.BORDER)],
    )
    return ttk.Scrollbar(parent, orient="vertical", command=command, style=SCROLLBAR_STYLE)


def wrap_to(label: tk.Label, container: tk.Widget, inset: int = 6) -> tk.Label:
    """Шошгын мөр таслах өргөнийг эзэн виджетийнхээ өргөнд дагуулна.

    Tk-д `wraplength` нь тогтмол пиксел — цонхыг нарийсгахад урт монгол
    тайлбарууд таслагдаж эхэлдэг. Хэмжээ солигдох бүрт дахин тооцно.
    """

    def resized(event) -> None:
        width = max(80, event.width - inset)
        if int(label.cget("wraplength")) != width:
            label.configure(wraplength=width)

    container.bind("<Configure>", resized, add="+")
    return label


def rounded_entry(
    parent,
    variable,
    *,
    width: int,
    font=theme.UI,
    secret: bool = False,
    stretch: bool = False,
) -> tuple[RoundedBox, tk.Entry]:
    """Дугуй хайрцаг доторх текстийн талбар (`tk.Entry` өөрөө дөрвөлжин).

    Хайрцгийг багцлахгүй буцаана — дуудагч `pack` эсвэл `grid`-ээр өөрөө
    байрлуулна.

    ⚠️ `width` нь ТЭМДЭГТЭЭР тогтмол. `fill="x"`-ээр сунгавал мөрийн өргөн →
    тайлбарын мөр таслалт → мөрийн өргөн гэсэн хэлхээ үүсч, цонх хэмжээгээ
    хоёр утгын хооронд эргэлдүүлж гацдаг. `stretch` нь зөвхөн эзэн виджет нь
    өргөнөө өөрөө тогтоодог газарт (`grid` багана) хэрэглэнэ.
    """
    box = RoundedBox(
        parent, fill=theme.PANEL2, outside=theme.PANEL,
        radius=theme.RADIUS_SMALL, border=None, pad=(theme.RADIUS_SMALL, 4),
    )
    entry = tk.Entry(
        box.inner, textvariable=variable, bg=theme.PANEL2, fg=theme.TEXT,
        insertbackground=theme.TEXT, relief="flat", font=font,
        bd=0, width=width,
        show="•" if secret else "",
    )
    # Оролт нь Tab-аар аль хэдийн хүрдэг ч хүрээгүй бол хаана байгаа нь
    # мэдэгдэхгүй — курсор анивчих нь хангалттай тэмдэг биш.
    entry.configure(
        highlightthickness=theme.FOCUS_WIDTH,
        highlightbackground=theme.PANEL2,
        highlightcolor=theme.FOCUS,
    )
    entry.pack(fill="x" if stretch else "none")
    return box, entry


def focusable(widget, activate=None, *, surface: str | None = None, paint=None) -> None:
    """Виджетийг Tab-аар хүрч, товчлуураар ажиллуулж болдог болгоно.

    Хоёр төрлийн виджет байна:

    * **`Entry`, `Listbox`, `Canvas`** — Tk өөрөө фокусын хүрээг зурдаг тул
      `surface` өгөхөд л хангалттай (хүрээ нь үргэлж байрлаж, фокусгүй үед
      гадаргуутай ижил өнгөтэй тул үл үзэгдэнэ; зузаан нь өөрчлөгддөггүй тул
      фокус хөдлөхөд зохион байгуулалт үсрэхгүй).
    * **`Label`-д суурилсан захиалгат удирдлагууд** (унтраалга, товч, холбоос,
      цэс) — Tk эдгээр дээр хүрээг **огт зурдаггүй** (пикселээр баталсан).
      Тэдгээр нь `paint(focused)` дамжуулж, харагдацаа өөрсдөө зурна.

    `activate` өгвөл Enter, зай хоёрыг товшилттой адилтгана — хулганагүй хүнд
    хүрч болох мөртлөө ажиллуулж болдоггүй товч нь дэмий.
    """
    widget.configure(takefocus=True)
    if surface is not None:
        widget.configure(
            highlightthickness=theme.FOCUS_WIDTH,
            highlightbackground=surface,
            highlightcolor=theme.FOCUS,
        )
    if paint is not None:
        widget.bind("<FocusIn>", lambda _e: paint(True), add="+")
        widget.bind("<FocusOut>", lambda _e: paint(False), add="+")
    if activate is not None:
        widget.bind("<Return>", activate)
        widget.bind("<space>", activate)


def combo(parent, variable, values, command) -> ttk.Combobox:
    """Уншихаас өөр боломжгүй сонголтын цэс. Сонгомогц `command` дуудагдана."""
    box = ttk.Combobox(
        parent, textvariable=variable, values=values, state="readonly",
        style="Mon.TCombobox", width=22,
    )
    box.pack()
    box.bind("<<ComboboxSelected>>", lambda _e: command())
    return box


def gradient_colours(count: int) -> list[str]:
    """Логоны 9 зогсоолыг `count` ширхэг өнгө болгон сунгана."""
    stops = [tuple(int(c[i : i + 2], 16) for i in (1, 3, 5)) for c in theme.GRADIENT]
    out = []
    for index in range(count):
        pos = index / max(1, count - 1) * (len(stops) - 1)
        low = min(len(stops) - 1, int(pos))
        high = min(len(stops) - 1, low + 1)
        k = pos - low
        r, g, b = (round(a + (b_ - a) * k) for a, b_ in zip(stops[low], stops[high]))
        out.append(f"#{r:02x}{g:02x}{b:02x}")
    return out


def toggle_image(
    on: bool, hover: bool = False, bg: str = theme.PANEL, focused: bool = False
) -> ImageTk.PhotoImage:
    """Унтраалгын зураг (40×22). Кэшлэнэ — Tk зургийн лавлагааг барих ёстой.

    Фокусын хүрээг зурган дотор зурна: Tk-ийн `highlightthickness` нь `Entry`
    дээр ажилладаг ч `Label` дээр огт зурагддаггүй (пикселээр хэмжсэн), энэ
    унтраалга нь Label юм.
    """
    key = ("toggle", on, hover, bg, focused)
    cached = _image_cache.get(key)
    if cached is not None:
        return cached

    width, height = 40, 22
    scale = SUPERSAMPLE
    img = Image.new("RGB", (width * scale, height * scale), bg)
    draw = ImageDraw.Draw(img)

    track = theme.TOGGLE_ON if on else theme.TOGGLE_OFF
    if hover:
        track = _lighten(track, 0.12)
    knob = theme.KNOB_ON if on else theme.KNOB_OFF

    # Фокустай үед мөрийг гаднаас нь хүрээлнэ — зам нь өөрөө нарийсна.
    inset_track = theme.FOCUS_WIDTH * scale if focused else 0
    if focused:
        _rounded(
            draw, (0, 0, width * scale - 1, height * scale - 1),
            height * scale / 2, theme.FOCUS,
        )
    _rounded(
        draw,
        (inset_track, inset_track,
         width * scale - 1 - inset_track, height * scale - 1 - inset_track),
        (height * scale - 2 * inset_track) / 2,
        track,
    )
    knob_size = 16 * scale - 2 * inset_track
    inset = 3 * scale + inset_track
    left = (width * scale - knob_size - inset) if on else inset
    draw.ellipse((left, inset, left + knob_size, inset + knob_size), fill=knob)

    photo = ImageTk.PhotoImage(img.resize((width, height), Image.LANCZOS))
    _image_cache[key] = photo
    return photo


class Toggle(tk.Label):
    """Асаах/унтраах унтраалга. `command` нь шинэ утгыг хүлээж авна."""

    def __init__(self, parent, value: bool, command=None, bg: str = theme.PANEL) -> None:
        super().__init__(parent, bd=0, highlightthickness=0, bg=bg, cursor="hand2")
        self._value = bool(value)
        self._hover = False
        self._focused = False
        self._bg = bg
        self.command = command
        self._redraw()
        self.bind("<Button-1>", self._clicked)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        focusable(self, self._clicked, paint=self._set_focus)

    @property
    def value(self) -> bool:
        return self._value

    def set(self, value: bool) -> None:
        self._value = bool(value)
        self._redraw()

    def _redraw(self) -> None:
        self.configure(
            image=toggle_image(self._value, self._hover, self._bg, self._focused)
        )

    def _set_focus(self, focused: bool) -> None:
        self._focused = focused
        self._redraw()

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
    """Гүйлгэдэг талбар. Агуулгыг `.body` дотор байрлуулна.

    ⚠️ Гүйлгэгч нь `place`-ээр агуулгын ДЭЭР давхарлагдана, `pack`-аар хажууд нь
    биш. Учир нь: `pack` бол гүйлгэгч зай эзэлж, агуулгын өргөнийг нарийсгана.
    Нарийссан өргөн нь урт тайлбаруудыг нэмэлт мөрөнд шилжүүлж, агуулгыг уртасгаж,
    гүйлгэгчийг хэрэгтэй хэвээр үлдээнэ — цонх хоёр хэмжээний хооронд
    ТӨГСГӨЛГҮЙ эргэлдэж гацдаг. `place` нь урсгалаас гадуур тул энэ гогцоо
    үүсэхгүй.
    """

    #: Гүйлгэгчийн өргөн (пиксел). Агуулга үүгээр нарийсахгүй — зөвхөн баруун
    #: захын дотоод зай болж, текст доогуур нь орохоос сэргийлнэ.
    BAR_WIDTH = 12

    def __init__(self, parent, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar = scrollbar(self, self.canvas.yview, trough=bg)
        self.canvas.configure(yscrollcommand=self._on_scroll)
        self.body = tk.Frame(self.canvas, bg=bg)
        self._window = self.canvas.create_window((0, 0), window=self.body, anchor="nw")
        self._bar_shown = False

        self.body.bind("<Configure>", self._resize_body)
        self.canvas.bind("<Configure>", self._resize_canvas)
        self.bind_all("<MouseWheel>", self._wheel, add="+")

    def _on_scroll(self, first, last) -> None:
        """Бүх агуулга багтаж байвал гүйлгэгчийг харуулахгүй.

        Харагдах/нуугдах нь агуулгын өргөнд НӨЛӨӨЛӨХГҮЙ (`place` тул) — өөрөөр
        хэлбэл энэ дуудалт дахин `_on_scroll` төрүүлэхгүй.
        """
        needed = not (float(first) <= 0.0 and float(last) >= 1.0)
        if needed != self._bar_shown:
            self._bar_shown = needed
            if needed:
                self.scrollbar.place(
                    relx=1.0, rely=0.0, anchor="ne", relheight=1.0, width=self.BAR_WIDTH
                )
            else:
                self.scrollbar.place_forget()
        self.scrollbar.set(first, last)

    def _resize_body(self, _event=None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _resize_canvas(self, event) -> None:
        # Гүйлгэгчийн зайг ҮРГЭЛЖ үлдээнэ — харагдаж байгаа эсэхээс үл хамааран.
        # Тогтмол учраас өргөн хэлбэлзэхгүй; хэлбэлзэл нь дээр тайлбарласан
        # гогцоог төрүүлдэг.
        self.canvas.itemconfigure(
            self._window, width=max(1, event.width - self.BAR_WIDTH)
        )

    def _wheel(self, event) -> None:
        try:
            # `bind_all` нь бүх цонхонд хүчинтэй тул өөр цонхон дээр гүйлгэхэд
            # ард байгаа энэ талбар хөдөлдөг байсан.
            if event.widget.winfo_toplevel() is not self.winfo_toplevel():
                return
            if not self.canvas.winfo_ismapped():
                return
            # Дотроо гүйлгэдэг жагсаалт дээр байвал тэрийг нь л гүйлгэнэ —
            # эс бөгөөс хуудас, жагсаалт хоёр зэрэг хөдөлнө.
            widget = event.widget
            while widget is not None and widget is not self:
                if isinstance(widget, (tk.Listbox, tk.Text)):
                    return
                widget = getattr(widget, "master", None)
            first, last = self.canvas.yview()
            if first <= 0.0 and last >= 1.0:
                return
            self.canvas.yview_scroll(int(-event.delta / 120), "units")
        except tk.TclError:
            pass

    def to_top(self) -> None:
        self.canvas.yview_moveto(0)


class Page(ScrollFrame):
    """Нэг цэсний агуулга: гарчиг, тайлбар, доор нь картууд.

    Өмнөх `Section`-ийн үүрэг — гарчигтай бүлэг — үлдсэн ч одоо нэг урт
    скроллын хэсэг биш, sidebar-аас сонгогддог бүтэн хуудас болов.
    """

    def __init__(self, parent, title: str, subtitle: str = "", aside: str = "") -> None:
        super().__init__(parent, bg=theme.BG)
        self.title = title

        head = tk.Frame(self.body, bg=theme.BG)
        head.pack(
            fill="x", padx=theme.PAGE_PAD_X,
            pady=(theme.PAGE_PAD_Y, 4 if subtitle else theme.GAP),
        )
        tk.Label(
            head, text=title, bg=theme.BG, fg=theme.TEXT, font=theme.UI_HEAD, anchor="w"
        ).pack(side="left")
        if aside:
            tk.Label(
                head, text=aside, bg=theme.BG, fg=theme.DIM, font=theme.MONO, anchor="e"
            ).pack(side="right")
        if subtitle:
            label = tk.Label(
                self.body, text=subtitle, bg=theme.BG, fg=theme.MUTED, font=theme.UI_SMALL,
                anchor="w", justify="left", wraplength=520,
            )
            label.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
            wrap_to(label, self.body, inset=2 * theme.PAGE_PAD_X)

    def group(self, text: str) -> tk.Frame:
        """Картуудын дээрх жижиг ГАРЧИГ (градиент зураастай)."""
        row = tk.Frame(self.body, bg=theme.BG)
        row.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(6, 6))
        tk.Frame(row, bg=theme.GRADIENT[2], width=3, height=11).pack(side="left", padx=(2, 9))
        tk.Label(
            row, text=text.upper(), bg=theme.BG, fg=theme.DIM, font=theme.UI_TINY, anchor="w"
        ).pack(side="left")
        return row

    def spacer(self, height: int = theme.PAGE_PAD_Y) -> tk.Frame:
        frame = tk.Frame(self.body, bg=theme.BG, height=height)
        frame.pack(fill="x")
        return frame


class Card(RoundedBox):
    """Дугуй буланлаг бүлэг. Мөрүүдийг `row()`-оор нэмнэ."""

    def __init__(self, parent, bg: str = theme.PANEL, pad: bool = True) -> None:
        super().__init__(parent, fill=bg, outside=theme.BG, radius=theme.RADIUS)
        if pad:
            self.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        self.body = self.inner
        self._bg = bg
        self._rows = 0

    def separator(self) -> None:
        if self._rows:
            tk.Frame(self.inner, bg=theme.ROW_LINE, height=1).pack(fill="x")

    def row(
        self, title: str = "", desc: str | tk.StringVar = ""
    ) -> tuple[tk.Frame, tk.Frame]:
        """Гарчиг + тайлбар зүүн талд, удирдлага баруун талд байх мөр.

        `desc` нь `StringVar` байвал тайлбар амьд болно — ажиллаж байхад
        солигдох мөрүүд (шинэчлэл олдох гэх мэт) зүүн талаа өөрсдөө угсрах
        шаардлагагүй.
        """
        self.separator()
        self._rows += 1
        row = tk.Frame(self.inner, bg=self._bg)
        row.pack(fill="x", padx=theme.CARD_PAD_X, pady=theme.CARD_PAD_Y)

        holder = tk.Frame(row, bg=self._bg)
        holder.pack(side="right", padx=(theme.GAP, 0))

        if title:
            text = tk.Frame(row, bg=self._bg)
            text.pack(side="left", fill="x", expand=True)
            tk.Label(
                text, text=title, bg=self._bg, fg=theme.TEXT, font=theme.UI_TITLE, anchor="w"
            ).pack(fill="x")
            if desc:
                live = isinstance(desc, tk.Variable)
                label = tk.Label(
                    text, bg=self._bg, fg=theme.MUTED, font=theme.UI_SMALL,
                    anchor="w", justify="left", wraplength=380,
                    **({"textvariable": desc} if live else {"text": desc}),
                )
                label.pack(fill="x", pady=(3, 0))
                wrap_to(label, text)
        return row, holder

    def note(self, text: str, colour: str = theme.DIM) -> tk.Label:
        """Картын хамгийн доор байх тайлбар мөр."""
        self.separator()
        self._rows += 1
        label = tk.Label(
            self.inner, text=text, bg=self._bg, fg=colour, font=theme.UI_SMALL,
            anchor="w", justify="left", wraplength=560,
        )
        label.pack(fill="x", padx=theme.CARD_PAD_X, pady=10)
        return wrap_to(label, self.inner, inset=2 * theme.CARD_PAD_X)


class SegmentedTabs(tk.Frame):
    """Хоёр-гурван сонголтын капсул хэлбэрийн сэлгүүр."""

    def __init__(self, parent, options: list[str], command, bg: str = theme.BG) -> None:
        super().__init__(parent, bg=bg)
        self.command = command
        self._bg = bg
        self._buttons: list[RoundedLabel] = []
        for index, text in enumerate(options):
            button = RoundedLabel(
                self, theme.RADIUS_SMALL, theme.PANEL2, bg, theme.BORDER,
                text=text, fg=theme.MUTED, font=theme.UI_NAV, padx=14, pady=6,
                cursor="hand2",
            )
            button.pack(side="left", padx=(0, 5))
            button.bind("<Button-1>", lambda _e, i=index: self.select(i))
            self._buttons.append(button)
        self.select(0, notify=False)

    def select(self, index: int, notify: bool = True) -> None:
        # Сонгогдсоныг акцент өнгөөр дүүргэхгүй — тэр нь "үндсэн товч" гэсэн
        # утга өгнө. Хүрээ, тодрол хоёроор ялгана.
        for position, button in enumerate(self._buttons):
            active = position == index
            button.restyle(
                fill=theme.PANEL2 if active else self._bg,
                border=theme.ACCENT if active else theme.BORDER,
                fg=theme.TEXT if active else theme.MUTED,
            )
        if notify and self.command:
            self.command(index)


class NavButton(tk.Frame):
    """Sidebar-ын нэг цэс: зүүн талын идэвхтэйн зураас, дүрс, нэр.

    Дэвсгэр нь дугуй буланлаг зураг тул идэвхтэйн зураасыг тусдаа виджет
    болгож болохгүй (зүүн буланг халхлана) — зурган дотор нь зурна. Дүрс,
    шошго нь радиусаас цааш доторшсон тул булангуудыг халхлахгүй.
    """

    INDENT = 11  # дүрсний зүүн зай: радиусаас том байх ёстой

    def __init__(self, parent, icon: str, text: str, command, tooltip: str = "") -> None:
        super().__init__(parent, bg=theme.SIDEBAR, cursor="hand2")
        self.icon_name = icon
        self.command = command
        self._active = False
        self._hover = False
        self._focused = False
        self._photo: ImageTk.PhotoImage | None = None
        self._size = (0, 0)

        self._back = tk.Label(self, bd=0, highlightthickness=0, bg=theme.SIDEBAR)
        self._back.place(x=0, y=0, relwidth=1, relheight=1)
        self.icon = tk.Label(self, bd=0, highlightthickness=0, bg=theme.SIDEBAR)
        self.icon.pack(side="left", padx=(self.INDENT, 0), pady=8)
        self.label = tk.Label(
            self, text=text, bg=theme.SIDEBAR, fg=theme.MUTED, font=theme.UI_NAV, anchor="w"
        )
        self.label.pack(side="left", padx=(11, 10))

        for widget in (self, self.icon, self.label, self._back):
            widget.bind("<Button-1>", lambda _e: self.command())
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)
        self.bind("<Configure>", self._resized)
        # Фокус нь эцэг Frame дээр очно — дүрс, шошго хоёр тусдаа зогсоол
        # болбол нэг цэс дээр Tab гурав дарах хэрэгтэй болно.
        for widget in (self.icon, self.label, self._back):
            widget.configure(takefocus=False)
        focusable(self, lambda _e: self.command(), paint=self._set_focus)
        self._paint()

    def _set_focus(self, focused: bool) -> None:
        self._focused = focused
        self._paint()

    def set_active(self, active: bool) -> None:
        self._active = active
        self._paint()

    def set_compact(self, compact: bool) -> None:
        if compact:
            self.label.pack_forget()
        else:
            self.label.pack(side="left", padx=(11, 10))

    def _enter(self, _event=None) -> None:
        self._hover = True
        self._paint()

    def _leave(self, _event=None) -> None:
        self._hover = False
        self._paint()

    def _resized(self, event) -> None:
        if (event.width, event.height) == self._size:
            return
        self._size = (event.width, event.height)
        self._paint()

    def _paint(self) -> None:
        if self._active:
            bg = theme.NAV_ACTIVE
        elif self._hover:
            bg = theme.HOVER
        else:
            bg = theme.SIDEBAR
        fg = theme.TEXT if self._active else theme.MUTED
        self.icon.configure(bg=bg, image=icons.get(self.icon_name, fg, 17, bg))
        self.label.configure(bg=bg, fg=fg)

        width, height = self._size
        if width < 4 or height < 4:
            return
        image = Image.new("RGB", (width, height), theme.SIDEBAR)
        draw = ImageDraw.Draw(image)
        radius = theme.RADIUS_SMALL
        if bg != theme.SIDEBAR:
            corners = _corners(radius, bg, theme.SIDEBAR, None)
            draw.rectangle((radius, 0, width - radius - 1, height - 1), fill=bg)
            draw.rectangle((0, radius, width - 1, height - radius - 1), fill=bg)
            image.paste(corners[0], (0, 0))
            image.paste(corners[1], (width - radius, 0))
            image.paste(corners[2], (0, height - radius))
            image.paste(corners[3], (width - radius, height - radius))
        if self._active:
            draw = ImageDraw.Draw(image)
            draw.rounded_rectangle(
                (3, 8, 5, height - 9), radius=1, fill=theme.GRADIENT[2]
            )
        if self._focused:
            # Tk нь Frame/Label дээр фокусын хүрээ зурдаггүй тул дэвсгэр
            # зурган дотроо зурна. Идэвхтэйн зураасаас ялгаатай: энэ нь
            # «Tab энд байна», тэр нь «энэ хуудас нээлттэй» гэсэн үг.
            ImageDraw.Draw(image).rounded_rectangle(
                (0, 0, width - 1, height - 1),
                radius=radius, outline=theme.FOCUS, width=theme.FOCUS_WIDTH,
            )
        self._photo = ImageTk.PhotoImage(image)
        self._back.configure(image=self._photo)


class StatTile(RoundedBox):
    """Том тоо + доор нь тайлбар."""

    def __init__(self, parent, caption: str, value: str = "—") -> None:
        super().__init__(parent, fill=theme.PANEL, outside=theme.BG, radius=theme.RADIUS)
        self.value_var = tk.StringVar(value=value)
        tk.Label(
            self.inner, textvariable=self.value_var, bg=theme.PANEL, fg=theme.GRADIENT[2],
            font=theme.MONO_BIG, anchor="w",
        ).pack(fill="x", padx=3, pady=(10, 0))
        tk.Label(
            self.inner, text=caption, bg=theme.PANEL, fg=theme.MUTED,
            font=theme.UI_SMALL, anchor="w",
        ).pack(fill="x", padx=3, pady=(2, 10))

    def set(self, value: str) -> None:
        self.value_var.set(value)


def knob_image(bg: str) -> ImageTk.PhotoImage:
    """Гулсуурын цагаан бариул.

    Фокусыг бариулын өнгөөр биш, Canvas-ийн хүрээгээр харуулна: өмнө нь фокус
    ирэхэд бариул цагаанаас акцент цэнхэр болдог байсан нь урвуу дохио байв —
    фокустай үед харагдац нь СУЛРАХ ёсгүй. Хүрээ нь мөн аппын бусад бүх
    удирдлагатай ижил хэл болно.
    """
    key = ("knob", bg)
    cached = _image_cache.get(key)
    if cached is not None:
        return cached
    size, scale = 14, SUPERSAMPLE
    img = Image.new("RGB", (size * scale, size * scale), bg)
    draw = ImageDraw.Draw(img)
    edge = 1 * scale
    draw.ellipse((0, 0, size * scale - 1, size * scale - 1), fill=theme.KNOB_ON)
    draw.ellipse((edge, edge, size * scale - 1 - edge, size * scale - 1 - edge), fill="#FFFFFF")
    photo = ImageTk.PhotoImage(img.resize((size, size), Image.LANCZOS))
    _image_cache[key] = photo
    return photo


class Slider(tk.Frame):
    """Гулсуур + баруун талд одоогийн утга.

    Tk-ийн `Scale` нь бариулаа виджетийн дэвсгэр өнгөөр зурдаг тул бараан
    картан дээр огт харагдахгүй болдог. Иймд Canvas дээр өөрсдөө зурав:
    нимгэн зам, дүүрсэн хэсэг нь акцент өнгөтэй, бариул нь цагаан дугуй.

    Чирэх бүрт тохиргоо хадгалахгүй — суллах эсвэл товчлуур авах агшинд л
    дуудна (диск рүү олон бичихээс сэргийлнэ).
    """

    LENGTH = 150
    HEIGHT = 20
    PAD = 7  # бариулын радиус

    def __init__(
        self, parent, low: float, high: float, step: float, value: float,
        command, fmt, bg: str = theme.PANEL,
    ) -> None:
        super().__init__(parent, bg=bg)
        self.low, self.high, self.step = float(low), float(high), float(step)
        self.command = command
        self.fmt = fmt
        self._value = float(value)
        self._bg = bg

        self.readout = tk.Label(
            self, text=fmt(value), bg=bg, fg=theme.TEXT, font=theme.MONO_KEY,
            width=8, anchor="e",
        )
        self.readout.pack(side="right", padx=(10, 0))

        self.canvas = tk.Canvas(
            self, width=self.LENGTH, height=self.HEIGHT, bg=bg,
            bd=0, cursor="hand2", takefocus=True,
            highlightthickness=theme.FOCUS_WIDTH,
            highlightbackground=bg, highlightcolor=theme.FOCUS,
        )
        self.canvas.pack(side="right")
        middle = self.HEIGHT / 2
        self._track = self.canvas.create_rectangle(
            self.PAD, middle - 2, self.LENGTH - self.PAD, middle + 2,
            fill=theme.TOGGLE_OFF, outline="",
        )
        self._fill = self.canvas.create_rectangle(
            self.PAD, middle - 2, self.PAD, middle + 2, fill=theme.ACCENT, outline=""
        )
        self._knob = self.canvas.create_image(self.PAD, middle, image=knob_image(bg))

        for sequence in ("<Button-1>", "<B1-Motion>"):
            self.canvas.bind(sequence, self._dragged)
        self.canvas.bind("<ButtonRelease-1>", lambda _e: self._settled())
        self.canvas.bind("<Left>", lambda _e: self._nudge(-1))
        self.canvas.bind("<Right>", lambda _e: self._nudge(+1))
        self._paint()

    @property
    def value(self) -> float:
        return self._value

    def set(self, value: float) -> None:
        self._value = self._snap(value)
        self._paint()

    def _snap(self, value: float) -> float:
        value = max(self.low, min(self.high, value))
        steps = round((value - self.low) / self.step)
        return round(min(self.high, self.low + steps * self.step), 6)

    def _dragged(self, event) -> None:
        self.canvas.focus_set()
        span = self.LENGTH - 2 * self.PAD
        ratio = (event.x - self.PAD) / span
        self.set(self.low + ratio * (self.high - self.low))

    def _nudge(self, direction: int) -> None:
        self.set(self._value + direction * self.step)
        self._settled()

    def _paint(self) -> None:
        span = self.LENGTH - 2 * self.PAD
        ratio = (self._value - self.low) / (self.high - self.low)
        x = self.PAD + ratio * span
        middle = self.HEIGHT / 2
        self.canvas.coords(self._fill, self.PAD, middle - 2, x, middle + 2)
        self.canvas.coords(self._knob, x, middle)
        self.readout.configure(text=self.fmt(self._value))

    def _settled(self) -> None:
        if self.command:
            self.command(self._value)


class LevelMeter(tk.Canvas):
    """Оролтын түвшин — градиент өнгөтэй 30 сегмент."""

    def __init__(self, parent, bg: str = theme.PANEL, width: int = 150) -> None:
        height = theme.METER_HEIGHT
        super().__init__(parent, width=width, height=height, bg=bg, highlightthickness=0, bd=0)
        count = theme.METER_SEGMENTS
        self._colours = gradient_colours(count)
        self._segments = []
        bar = width / count - 2
        for index in range(count):
            x = index * (bar + 2)
            self._segments.append(
                self.create_rectangle(
                    x, height * 0.32, x + bar, height * 0.68,
                    fill=theme.TOGGLE_OFF, outline="",
                )
            )
        self._level = -1.0

    def set_level(self, level: float) -> None:
        """0..1. Өөрчлөлт мэдэгдэхүйц үед л дахин зурна."""
        level = max(0.0, min(1.0, level))
        if abs(level - self._level) < 0.02:
            return
        self._level = level
        height = theme.METER_HEIGHT
        count = theme.METER_SEGMENTS
        for index, item in enumerate(self._segments):
            on = index / count < level
            x1, _, x2, _ = self.coords(item)
            self.coords(
                item, x1, height * (0.12 if on else 0.32), x2, height * (0.88 if on else 0.68)
            )
            self.itemconfigure(item, fill=self._colours[index] if on else theme.TOGGLE_OFF)


class PairEditor(RoundedBox):
    """«буруу → зөв» хосуудыг мөр мөрөөр нь засварладаг жагсаалт.

    Өмнө нь энэ хоёр тохиргоо нь `a=b` гэсэн форматтай нэг том текст талбар
    байсан — хүн форматаа санах шаардлагатай байв. Одоо мөр бүр тусдаа хоёр
    оролт болов.
    """

    def __init__(self, parent, on_change, labels=("Буруу таньсан", "Зөв бичих")) -> None:
        super().__init__(parent, fill=theme.PANEL, outside=theme.BG, radius=theme.RADIUS)
        self.on_change = on_change
        self._labels = labels
        self._rows: list[tuple[tk.Frame, tk.StringVar, tk.StringVar]] = []

        # Толгой мөр нь доорх мөрүүдтэй яг ижил тор ашиглана — эс бөгөөс багана
        # нь оролтуудтайгаа эгнэхгүй (виджетүүдийн байгалийн өргөн өөр).
        self.header = tk.Frame(self.inner, bg=theme.PANEL)
        self.header.pack(fill="x")
        head = tk.Frame(self.header, bg=theme.PANEL)
        head.pack(fill="x", padx=6, pady=(9, 5))
        self.head_a = tk.Label(
            head, text=labels[0].upper(), bg=theme.PANEL, fg=theme.DIM,
            font=theme.UI_TINY, anchor="w",
        )
        self.head_b = tk.Label(
            head, text=labels[1].upper(), bg=theme.PANEL, fg=theme.DIM,
            font=theme.UI_TINY, anchor="w",
        )
        self.head_a.grid(row=0, column=0, sticky="ew", padx=(9, 0))
        # Мөрүүд дэх сумтай яг ижил өргөнтэй, гэхдээ үл харагдах зай
        tk.Label(
            head, text="→", bg=theme.PANEL, fg=theme.PANEL, font=theme.MONO_KEY
        ).grid(row=0, column=1, padx=8)
        self.head_b.grid(row=0, column=2, sticky="ew", padx=(9, 0))
        tk.Frame(head, bg=theme.PANEL, width=21, height=1).grid(row=0, column=3)
        self._columns(head)

        self.list = tk.Frame(self.inner, bg=theme.PANEL)
        self.list.pack(fill="x")

        footer = tk.Frame(self.inner, bg=theme.PANEL)
        footer.pack(fill="x", padx=6, pady=10)
        add = tk.Label(
            footer, text="  Мөр нэмэх", bg=theme.PANEL, fg=theme.TEXT, font=theme.UI_NAV,
            compound="left", cursor="hand2", image=icons.get("plus", theme.TEXT, 11, theme.PANEL),
        )
        add.pack(side="left")
        add.bind("<Button-1>", lambda _e: self.add_row("", "", focus=True))
        self.hint = tk.Label(
            footer, text="", bg=theme.PANEL, fg=theme.DIM, font=theme.UI_SMALL, anchor="e"
        )
        self.hint.pack(side="right")

    def set_labels(self, labels) -> None:
        self._labels = labels
        self.head_a.configure(text=labels[0].upper())
        self.head_b.configure(text=labels[1].upper())

    def load(self, mapping: dict) -> None:
        for row, _, _ in self._rows:
            row.destroy()
        self._rows = []
        for key, value in mapping.items():
            self.add_row(key, value, notify=False)
        self._update_hint()

    def add_row(self, key: str, value: str, focus: bool = False, notify: bool = True) -> None:
        row = tk.Frame(self.list, bg=theme.PANEL)
        row.pack(fill="x")
        tk.Frame(row, bg=theme.ROW_LINE, height=1).pack(fill="x")
        inner = tk.Frame(row, bg=theme.PANEL)
        inner.pack(fill="x", padx=6, pady=5)

        left = tk.StringVar(value=key)
        right = tk.StringVar(value=value)
        first_box, first = rounded_entry(inner, left, width=8, stretch=True)
        first_box.grid(row=0, column=0, sticky="ew")
        tk.Label(
            inner, text="→", bg=theme.PANEL, fg=theme.DIM, font=theme.MONO_KEY
        ).grid(row=0, column=1, padx=8)
        rounded_entry(inner, right, width=8, stretch=True)[0].grid(
            row=0, column=2, sticky="ew"
        )

        remove = tk.Label(
            inner, bg=theme.PANEL, cursor="hand2",
            image=icons.get("close", theme.MUTED, 11, theme.PANEL),
        )
        remove.grid(row=0, column=3, padx=(10, 0))
        remove.bind("<Button-1>", lambda _e: self._remove(row))
        self._columns(inner)

        self._rows.append((row, left, right))
        for var in (left, right):
            var.trace_add("write", lambda *_: self._changed())
        if focus:
            first.focus_set()
        if notify:
            self._changed()

    @staticmethod
    def _columns(frame: tk.Frame) -> None:
        """Хоёр талбарын багана яг тэнцүү — толгой мөр ч мөрүүд ч ижил."""
        frame.columnconfigure(0, weight=1, uniform="pair")
        frame.columnconfigure(2, weight=1, uniform="pair")

    def _remove(self, row: tk.Frame) -> None:
        self._rows = [item for item in self._rows if item[0] is not row]
        row.destroy()
        self._changed()

    def mapping(self) -> dict:
        out = {}
        for _, left, right in self._rows:
            key = left.get().strip()
            if key:
                out[key] = right.get().strip()
        return out

    def _changed(self) -> None:
        self._update_hint()
        if self.on_change:
            self.on_change(self.mapping())

    def _update_hint(self) -> None:
        self.hint.configure(text=f"{len(self._rows)} мөр")


class Keycaps(tk.Frame):
    """Товчлуурын хослолыг keycap хэлбэрээр харуулна: [Win] + [Alt]."""

    def __init__(self, parent, bg: str = theme.PANEL) -> None:
        super().__init__(parent, bg=bg)
        self._bg = bg
        self._items: list[tk.Widget] = []

    def show(self, parts: list[str]) -> None:
        for item in self._items:
            item.destroy()
        self._items = []
        for index, part in enumerate(parts):
            if index:
                plus = tk.Label(
                    self, text="+", bg=self._bg, fg=theme.DIM, font=theme.UI_SMALL
                )
                plus.pack(side="left", padx=3)
                self._items.append(plus)
            cap = RoundedLabel(
                self, theme.RADIUS_TINY, theme.PANEL2, self._bg, theme.BORDER,
                text=part, fg=theme.TEXT, font=theme.MONO_KEY, padx=8, pady=5,
            )
            cap.pack(side="left")
            self._items.append(cap)

    def show_text(self, text: str, colour: str = theme.WARN) -> None:
        for item in self._items:
            item.destroy()
        self._items = []
        label = RoundedLabel(
            self, theme.RADIUS_TINY, theme.PANEL2, self._bg, colour,
            text=text, fg=colour, font=theme.MONO_KEY, padx=10, pady=5,
        )
        label.pack(side="left")
        self._items.append(label)


class Link(tk.Label):
    """Товшиж болох текст."""

    def __init__(self, parent, text: str, command, bg: str = theme.BG, font=None) -> None:
        super().__init__(
            parent, text=text, bg=bg, fg=theme.LINK, font=font or theme.UI_SMALL,
            cursor="hand2",
        )
        self._font = font or theme.UI_SMALL
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Enter>", lambda _e: self.configure(fg=_lighten(theme.LINK, 0.25)))
        self.bind("<Leave>", lambda _e: self.configure(fg=theme.LINK))
        focusable(self, lambda _e: command(), paint=self._set_focus)

    def _set_focus(self, focused: bool) -> None:
        """Фокусыг доогуур зураасаар — холбоосны уламжлалт тэмдэг.

        `Label` дээр Tk фокусын хүрээ зурдаггүй тул өөрсдөө тэмдэглэнэ.
        """
        self.configure(
            fg=theme.FOCUS if focused else theme.LINK,
            font=(*self._font, "underline") if focused else self._font,
        )


class Button(RoundedLabel):
    """Дугуй буланлаг хоёрдогч товч ("Солих", "Цэвэрлэх" гэх мэт)."""

    def __init__(
        self, parent, text: str, command, bg: str = theme.PANEL,
        danger: bool = False, icon: str = "",
    ) -> None:
        # Дүрстэй товч дээр `image` слот дүрсэнд хэрэгтэй тул дугуй дэвсгэр
        # багтахгүй — дүрсийг зөвхөн текстгүй тохиолдолд ашиглана.
        super().__init__(
            parent, theme.RADIUS_SMALL, bg, bg, theme.BORDER,
            text=text, fg=theme.TEXT, font=theme.UI_NAV, padx=13, pady=6, cursor="hand2",
        )
        self._danger = danger
        self._base = bg
        self._focused = False
        self.bind("<Button-1>", lambda _e: command())
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        focusable(self, lambda _e: command(), paint=self._set_focus)

    def set_text(self, text: str) -> None:
        self.restyle(text=text)

    def _idle_border(self) -> str:
        return theme.FOCUS if self._focused else theme.BORDER

    def _idle_fg(self) -> str:
        return theme.FOCUS if self._focused else theme.TEXT

    def _set_focus(self, focused: bool) -> None:
        """Фокусыг хүрээ БА бичгийн өнгө хоёулангаар нь тэмдэглэнэ.

        Зөвхөн хүрээнд найдаж болохгүй: энэ товчны `padx/pady` нь дугуй
        дэвсгэр зургийн ирмэгийг тайрдаг тул хүрээ нь бодитоор харагдахгүй
        байх боломжтой (пикселээр хэмжсэн). Бичгийн өнгө үргэлж харагдана.
        """
        self._focused = focused
        self.restyle(border=self._idle_border(), fg=self._idle_fg())

    def _enter(self, _event=None) -> None:
        if self._danger:
            self.restyle(border=theme.DANGER, fg=theme.DANGER)
        else:
            self.restyle(fill=theme.HOVER)

    def _leave(self, _event=None) -> None:
        self.restyle(fill=self._base, border=self._idle_border(), fg=self._idle_fg())


class SearchBox(RoundedBox):
    """Дүрстэй хайлтын талбар (sidebar болон түүхийн хуудсанд)."""

    def __init__(
        self, parent, variable, placeholder: str,
        bg: str = theme.PANEL2, outside: str = theme.SIDEBAR,
    ) -> None:
        super().__init__(
            parent, fill=bg, outside=outside, radius=theme.RADIUS_SMALL,
            border=theme.BORDER, pad=(theme.RADIUS_SMALL, 2),
        )
        self.variable = variable
        self._icon = tk.Label(self.inner, image=icons.get("search", theme.DIM, 12, bg), bg=bg)
        self._icon.pack(side="left", padx=(2, 5))
        self.entry = tk.Entry(
            self.inner, textvariable=variable, bg=bg, fg=theme.TEXT,
            insertbackground=theme.TEXT, relief="flat", font=theme.UI_SMALL,
            bd=0,
            highlightthickness=theme.FOCUS_WIDTH,
            highlightbackground=bg, highlightcolor=theme.FOCUS,
        )
        self.entry.pack(side="left", fill="x", expand=True, padx=(0, 4), pady=5)

        ghost = tk.Label(self.entry, text=placeholder, bg=bg, fg=theme.DIM, font=theme.UI_SMALL)

        def sync(*_):
            if variable.get():
                ghost.place_forget()
            else:
                ghost.place(x=0, rely=0.5, anchor="w")

        variable.trace_add("write", sync)
        sync()

    def focus_entry(self) -> None:
        self.entry.focus_set()
        self.entry.select_range(0, "end")
