"""Удирдлагын цонх — "Monspeech Redesign" бүтэц.

Өмнөх хувилбар нь нэг урт скролл дээр 7 хэсгийг дараалуулж, хайлтыг үндсэн
навигаци болгосон байв. Хүн цонхыг нээмэгц юу тохируулж болохоо мэдэхийн тулд
скролл хийх эсвэл нэрийг нь таамаглаж бичих шаардлагатай болдог байсан — энэ
нь ховор нээгддэг цонхонд буруу шийдэл.

Одоо: **зүүн талын 7 цэс, баруун талд солигддог хуудас**. Хайлт үлдсэн ч
sidebar-ын дээд талд туслах хэрэгсэл болж жижигрэв — илэрц бүр "аль цэст
байгаа"-г хэлж, дарахад тэр цэс рүү аваачна.

Товчлол:  Ctrl+1…7 — цэс сонгох,  Ctrl+F — хайлт.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import __version__, icons, recognizer, textproc, theme
from .hotkeys import pretty
from .orb import RobotOrb
from .widgets import (
    Button,
    Card,
    Keycaps,
    LevelMeter,
    NavButton,
    Page,
    PairEditor,
    RoundedBox,
    RoundedLabel,
    SearchBox,
    SegmentedTabs,
    Slider,
    StatTile,
    Toggle,
    rounded_entry,
    scrollbar,
)

LANGUAGES = [
    ("Монгол", "mn-MN"),
    ("English (US)", "en-US"),
    ("English (UK)", "en-GB"),
    ("Русский", "ru-RU"),
    ("日本語", "ja-JP"),
    ("한국어", "ko-KR"),
    ("中文", "zh-CN"),
]
CODE_TO_NAME = {code: name for name, code in LANGUAGES}
NAME_TO_CODE = dict(LANGUAGES)

# «Төлөв» хуудасны хурдан сэлгэх чипүүд — бүтэн жагсаалт нь «Яриа» цэст
QUICK_LANGS = [("Монгол", "mn-MN"), ("English", "en-US")]

NAV = [
    ("status", "Төлөв"),
    ("mic", "Яриа"),
    ("write", "Бичилт"),
    ("keyboard", "Товчлуур"),
    ("book", "Толь"),
    ("clock", "Түүх"),
    ("sliders", "Нэмэлт"),
]

WRITING_TOGGLES = [
    ("type_mode", "Шууд бичих",
     "Clipboard-г үл хөндөнө. Хуучин аппуудад арай хойрго байж болно."),
    ("auto_space", "Зай нэмэх",
     "Өмнөх текстийн дараа шаардлагатай бол зай тавина"),
    ("auto_capitalize", "Том үсгээр эхлүүлэх",
     "Шинэ өгүүлбэрийн эхний үсгийг том болгоно"),
    ("voice_punctuation", "Дуут цэг таслал",
     "«цэг», «таслал», «шинэ мөр» гэж хэлэхэд тэмдэг болгоно"),
    ("clean_speech", "Чигчлүүр цэвэрлэх",
     "«ааа», эхний «за», давхардсан үг, «үгүй ээ» гэж зассаныг хасна"),
]
STT_FIELDS = [
    ("stt_url", "Хаяг", "…/v1/audio/transcriptions"),
    ("stt_model", "Загвар", "Үйлчилгээний зааж өгсөн нэр"),
    ("stt_key", "API түлхүүр", "Шаардахгүй сервер бол хоосон"),
]
MODE_TOGGLES = [
    ("ptt_enabled", "Push-to-talk горим",
     "Дарж барих. Унтраавал зөвхөн асаах/унтраах товчлуураар ажиллана."),
    ("restore_clipboard", "Clipboard сэргээх",
     "Буулгасны дараа хуучин агуулгыг эгүүлж тавина"),
    ("learn_corrections", "Засварыг сурах",
     "Түүх дээр гараар засвал Толь руу автоматаар нэмнэ"),
]
HOTKEY_ROWS = [
    ("ptt_key", "Дарж барих", "Дарж байх зуур сонсоно"),
    ("ptt_key_alt", "Хоёр дахь хэл", "Хоёр дахь хэлээр таних"),
    ("hotkey", "Асаах / унтраах", "Нэг дарж эхлүүлж, дахин дарж дуусгана"),
    ("undo_key", "Буцаах", "Хамгийн сүүлийн буулгалтыг цуцлах"),
]
TUNING_ROWS = [
    ("silence_hold", "Завсарлага",
     "Хэдэн секунд дуугүй байвал өгүүлбэр дууссан гэж үзэх",
     0.4, 1.2, 0.1, lambda v: f"{v:.1f} сек"),
    ("min_confidence", "Итгэлцлийн босго",
     "Босгоос доогуур таналтыг буулгахгүй",
     0.0, 0.9, 0.05, lambda v: "Шүүхгүй" if v <= 0 else f"{v * 100:.0f}%"),
    ("mic_keep_open_seconds", "Микрофон бэлэн барих",
     "Бичлэгийн дараа микрофоныг хэдэн секунд нээлттэй барих",
     0, 300, 15, lambda v: "Болих" if v <= 0 else f"{v:.0f} сек"),
    ("max_recording_seconds", "Бичлэгийн дээд хугацаа",
     "Товч гацсан ч энэ хугацааны дараа бичлэг өөрөө зогсоно",
     30, 600, 30, lambda v: f"{v / 60:.0f} мин" if v >= 60 else f"{v:.0f} сек"),
]

# Хайлтын товч жагсаалт: нэр → (цэсний дугаар, нэмэлт түлхүүр үгс)
SEARCH_INDEX = [
    ("Төлөв ба статистик", 0, "төлөв статистик үг хэмнэсэн"),
    ("Хэл хурдан солих", 0, "хэл солих language"),
    ("Үндсэн хэл", 1, "хэл language монгол english"),
    ("Хоёр дахь хэл", 1, "хоёр дахь хэл second language"),
    ("Микрофон", 1, "микрофон mic төхөөрөмж"),
    ("Оролтын түвшин", 1, "түвшин level дуу"),
    ("Долгион харуулах", 1, "долгион заалт курсор overlay"),
    ("Шууд бичих", 2, "clipboard шууд бичих type"),
    ("Зай нэмэх", 2, "зай space"),
    ("Том үсгээр эхлүүлэх", 2, "том үсэг өгүүлбэр capital"),
    ("Дуут цэг таслал", 2, "цэг таслал punctuation дуут"),
    ("Clipboard ажиллахгүй цонх", 2, "clipboard ажиллахгүй апп жагсаалт нэмэх"),
    ("Дарж барих товчлуур", 3, "товчлуур push to talk дарж барих"),
    ("Асаах / унтраах", 3, "товчлуур асаах унтраах toggle"),
    ("Буцаах", 3, "товчлуур буцаах undo"),
    ("Үг солих", 4, "толь үг солих орлуулга"),
    ("Дуут товчлол", 4, "толь товчлол snippet хаяг"),
    ("Таньсан текстүүд", 5, "түүх history текст"),
    ("Push-to-talk горим", 6, "push to talk горим"),
    ("Clipboard сэргээх", 6, "clipboard сэргээх"),
    ("Засварыг сурах", 6, "сурах толь засвар автомат"),
    ("Завсарлага", 6, "завсарлага чимээгүй өгүүлбэр таслах"),
    ("Итгэлцлийн босго", 6, "итгэлцэл босго нарийвчлал"),
    ("Микрофон бэлэн барих", 6, "микрофон бэлэн хурдан эхлэх"),
    ("Бичлэгийн дээд хугацаа", 6, "бичлэг дээд хугацаа хязгаар"),
    ("Windows-тай хамт эхлүүлэх", 6, "автомат эхлэх startup нэвтрэх"),
    ("Хаахад tray руу нуух", 6, "tray хаах нуух"),
    ("Лог ба хувилбар", 6, "лог хувилбар version log"),
]

ORB_MODES = {"listening": "listening", "working": "recognizing"}
LEVEL_FULL = 3200.0  # энэ RMS-ийг 100% гэж үзнэ
DICTIONARY_SAVE_MS = 500  # толь засварлахад хүлээх хугацаа
TILE_ROW_MIN = 560  # үүнээс нарийн бол статистикийн 4 карт 2×2 болно


class ControlWindow:
    """Цонхны бүх виджетийг эзэмшинэ. Логик нь `app`-д үлдэнэ."""

    def __init__(self, root: tk.Tk, app) -> None:
        self.root = root
        self.app = app
        self.pages: list[Page] = []
        self.nav: list[NavButton] = []
        self.toggles: dict[str, Toggle] = {}
        self.keycaps: dict[str, Keycaps] = {}
        self.capture_buttons: dict[str, Button] = {}
        self.sliders: dict[str, Slider] = {}
        self.lang_chips: dict[str, RoundedLabel] = {}
        self.page_index = 0
        self.collapsed = False
        self._history_rows: list[dict] = []
        self._capturing_key: str | None = None
        self._dictionary_save: str | None = None

        self._build()

    # ------------------------------------------------------------------
    # Бүтэц
    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = self.root
        root.configure(bg=theme.BG)
        root.geometry("{}x{}".format(*theme.WINDOW))
        root.minsize(*theme.WINDOW_MIN)

        self._dark_titlebar()
        self._style()

        shell = tk.Frame(root, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        self._build_sidebar(shell)
        self._build_main(shell)
        self.root.bind("<Configure>", self._window_resized)
        self._bind_keys()
        self.select(0)
        self.refresh_hotkeys()

    def _dark_titlebar(self) -> None:
        """Windows-ийн гарчгийн мөрийг бараан болгоно.

        Дизайны зурсан хиймэл гарчгийн мөрийг давтахгүй — чирэх, наах,
        хэмжээ солих зэрэг зан үйлийг гараар бичих нь Windows апп биш
        болгодог. Оронд нь системийн мөрийг бараан болгоно.
        """
        try:
            import ctypes

            self.root.update_idletasks()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
            value = ctypes.c_int(1)
            for attribute in (20, 19):  # шинэ ба хуучин Windows 10 бүтээлтүүд
                ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
                )
        except Exception:  # noqa: BLE001 - гоо сайхны зүйл, апп зогсоохгүй
            pass

    def _style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Mon.TCombobox",
            fieldbackground=theme.PANEL2,
            background=theme.PANEL2,
            foreground=theme.TEXT,
            bordercolor=theme.BORDER,
            lightcolor=theme.BORDER,
            darkcolor=theme.BORDER,
            arrowcolor=theme.MUTED,
            selectbackground=theme.PANEL2,
            selectforeground=theme.TEXT,
            padding=5,
        )
        # Сумны товчийг ч бараан болгоно — эс бөгөөс баруун тал нь саарал үлдэнэ
        style.map(
            "Mon.TCombobox",
            fieldbackground=[("readonly", theme.PANEL2), ("!disabled", theme.PANEL2)],
            background=[
                ("readonly", theme.PANEL2), ("active", theme.HOVER), ("!disabled", theme.PANEL2)
            ],
            bordercolor=[("focus", theme.ACCENT)],
            lightcolor=[("focus", theme.ACCENT), ("!focus", theme.BORDER)],
            darkcolor=[("!focus", theme.BORDER)],
            arrowcolor=[("active", theme.TEXT), ("!disabled", theme.MUTED)],
            foreground=[("readonly", theme.TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", theme.PANEL2)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", theme.UI)

    # ------------------------------------------------------------------
    # Sidebar
    # ------------------------------------------------------------------
    def _build_sidebar(self, parent) -> None:
        bar = tk.Frame(parent, bg=theme.SIDEBAR, width=theme.SIDEBAR_WIDTH)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self.sidebar = bar
        tk.Frame(parent, bg=theme.BORDER, width=1).pack(side="left", fill="y")

        # Логон нэр, хувилбарыг энд давтахгүй: Windows-ийн гарчгийн мөр аль
        # хэдийн дүрс, нэрийг харуулж байгаа. Хувилбар нь «Нэмэлт» цэст байна.
        self.search_var = tk.StringVar()
        self.search = SearchBox(bar, self.search_var, "Хайх  (Ctrl+F)")
        self.search.pack(fill="x", padx=10, pady=(12, 8))
        self.search_var.trace_add("write", lambda *_: self._apply_search())

        self.results = RoundedBox(
            bar, fill=theme.PANEL, outside=theme.SIDEBAR, radius=theme.RADIUS_SMALL
        )

        self.menu = tk.Frame(bar, bg=theme.SIDEBAR)
        self.menu.pack(fill="both", expand=True, padx=8)
        for index, (icon, label) in enumerate(NAV):
            button = NavButton(self.menu, icon, label, lambda i=index: self.select(i))
            button.pack(fill="x", pady=1)
            self.nav.append(button)

        tk.Frame(bar, bg=theme.BORDER, height=1).pack(fill="x")
        foot = tk.Frame(bar, bg=theme.SIDEBAR)
        foot.pack(fill="x", padx=10, pady=9)
        self.dot = tk.Canvas(foot, width=8, height=8, bg=theme.SIDEBAR, highlightthickness=0)
        self.dot.pack(side="left", pady=3)
        self._dot_id = self.dot.create_oval(0, 0, 7, 7, fill=theme.OK, outline="")
        self.state_var = tk.StringVar(value="Бэлэн")
        self.state_label = tk.Label(
            foot, textvariable=self.state_var, bg=theme.SIDEBAR, fg=theme.MUTED,
            font=theme.UI_SMALL, anchor="w",
        )
        self.state_label.pack(side="left", padx=7)
        # Дүрстэй тул `RoundedLabel` тохирохгүй (зургийн слот дүрсэнд хэрэгтэй)
        # — дугуй хайрцгийн дотор байрлуулна.
        collapse = RoundedBox(
            foot, fill=theme.SIDEBAR, outside=theme.SIDEBAR, radius=theme.RADIUS_TINY,
            border=theme.BORDER, pad=(theme.RADIUS_TINY, 3),
        )
        collapse.pack(side="right")
        self.collapse_button = tk.Label(
            collapse.inner, bg=theme.SIDEBAR, cursor="hand2",
            image=icons.get("chevron", theme.MUTED, 11, theme.SIDEBAR),
        )
        self.collapse_button.pack()
        for widget in (collapse, collapse.inner, self.collapse_button):
            widget.bind("<Button-1>", lambda _e: self.toggle_sidebar())

    def _window_resized(self, event) -> None:
        """Дизайны дагуу хамгийн бага хэмжээнд цэс өөрөө дүрс болж хумигдана."""
        if event.widget is not self.root:
            return
        if event.width < theme.SIDEBAR_COLLAPSE_AT and not self.collapsed:
            self.toggle_sidebar()
        elif event.width >= theme.SIDEBAR_EXPAND_AT and self.collapsed:
            self.toggle_sidebar()

    def toggle_sidebar(self) -> None:
        """Нарийсгах — дэлгэц бага үед эсвэл цэсний нэр хэрэггүй болсон үед.

        Хумихдаа шошгыг нуухаас гадна цэсийг өөрийг нь давчуу болгоно: 58 px
        нь дүрс + идэвхтэйн зураас багтах хамгийн бага өргөн.
        """
        self.collapsed = not self.collapsed
        self.sidebar.configure(
            width=theme.SIDEBAR_COLLAPSED if self.collapsed else theme.SIDEBAR_WIDTH
        )
        for button in self.nav:
            button.set_compact(self.collapsed)
        if self.collapsed:
            self.state_label.pack_forget()
            self.search.pack_forget()
            self.results.pack_forget()
        else:
            self.state_label.pack(side="left", padx=7)
            self.search.pack(fill="x", padx=10, pady=(12, 8), before=self.menu)
            self._apply_search()
        self.collapse_button.configure(
            image=icons.get(
                "chevron" if not self.collapsed else "chevron_right", theme.MUTED, 11, theme.SIDEBAR
            )
        )

    # ------------------------------------------------------------------
    # Хайлт
    # ------------------------------------------------------------------
    def _apply_search(self) -> None:
        for child in self.results.inner.winfo_children():
            child.destroy()
        query = self.search_var.get().strip().lower()
        if not query:
            self.results.pack_forget()
            return

        matches = [
            item for item in SEARCH_INDEX
            if query in item[0].lower() or query in item[2]
        ][:5]
        self.results.pack(fill="x", padx=10, pady=(0, 8), after=self.search)
        if not matches:
            tk.Label(
                self.results.inner, text="Илэрц олдсонгүй", bg=theme.PANEL, fg=theme.DIM,
                font=theme.UI_SMALL, anchor="w",
            ).pack(fill="x", padx=4, pady=8)
            return
        for name, page, _ in matches:
            row = tk.Frame(self.results.inner, bg=theme.PANEL, cursor="hand2")
            row.pack(fill="x")
            title = tk.Label(
                row, text=name, bg=theme.PANEL, fg=theme.TEXT, font=theme.UI_NAV, anchor="w"
            )
            title.pack(fill="x", padx=4, pady=(7, 0))
            where = tk.Label(
                row, text=f"{NAV[page][1]} цэс", bg=theme.PANEL, fg=theme.DIM,
                font=theme.UI_SMALL, anchor="w",
            )
            where.pack(fill="x", padx=4, pady=(1, 7))
            for widget in (row, title, where):
                widget.bind("<Button-1>", lambda _e, p=page: self._go_from_search(p))

    def _go_from_search(self, page: int) -> None:
        self.search_var.set("")
        self.select(page)

    # ------------------------------------------------------------------
    # Хуудсууд
    # ------------------------------------------------------------------
    def _build_main(self, parent) -> None:
        main = tk.Frame(parent, bg=theme.BG)
        main.pack(side="left", fill="both", expand=True)

        self.stack = tk.Frame(main, bg=theme.BG)
        self.stack.pack(fill="both", expand=True)

        tk.Frame(main, bg=theme.BORDER, height=1).pack(fill="x")
        status = tk.Frame(main, bg=theme.SIDEBAR, height=26)
        status.pack(fill="x")
        status.pack_propagate(False)
        # Лог руу хүрэх зам «Нэмэлт → Логийн хавтас» дээр байгаа тул энд
        # давтахгүй — доод мөр зөвхөн сүүлийн мэдэгдлийг харуулна.
        self.detail_var = tk.StringVar(value="")
        tk.Label(
            status, textvariable=self.detail_var, bg=theme.SIDEBAR, fg=theme.MUTED,
            font=theme.UI_SMALL, anchor="w",
        ).pack(side="left", padx=theme.PAGE_PAD_X)

        self._page_status()
        self._page_speech()
        self._page_writing()
        self._page_hotkeys()
        self._page_dictionary()
        self._page_history()
        self._page_advanced()

    def select(self, index: int) -> None:
        index = max(0, min(len(self.pages) - 1, index))
        self.page_index = index
        for position, page in enumerate(self.pages):
            if position == index:
                page.pack(fill="both", expand=True)
                page.to_top()
            else:
                page.pack_forget()
            self.nav[position].set_active(position == index)
        # Робот зөвхөн харагдаж байхдаа зурагдана
        self.orb.start() if index == 0 else self.orb.stop()

    def _bind_keys(self) -> None:
        for number in range(1, 8):
            self.root.bind(f"<Control-Key-{number}>", lambda _e, n=number: self.select(n - 1))
        self.root.bind("<Control-f>", lambda _e: self._focus_search())
        self.root.bind("<Control-F>", lambda _e: self._focus_search())

    def _focus_search(self) -> str:
        if self.collapsed:
            self.toggle_sidebar()
        self.search.focus_entry()
        return "break"

    def _add_page(self, page: Page) -> Page:
        self.pages.append(page)
        return page

    # --- 1. Төлөв ---------------------------------------------------
    def _page_status(self) -> None:
        page = self._add_page(
            Page(self.stack, "Төлөв", aside=f"{pretty(self.app.cfg['ptt_key'])} дарж барин ярь")
        )

        self._welcome_card(page)
        hero = Card(page.body)
        inner = tk.Frame(hero.body, bg=theme.PANEL)
        inner.pack(pady=(10, 16))
        self.orb = RobotOrb(inner, width=240)
        self.orb.pack()

        # Капсул: радиус нь өндрийн хагас тул `pad` нь хэвтээ чиглэлд том
        pill = RoundedBox(
            inner, fill=theme.PANEL2, outside=theme.PANEL, radius=16,
            border=theme.BORDER, pad=(16, 2),
        )
        pill.pack(pady=(6, 0))
        self.pill_dot = tk.Canvas(
            pill.inner, width=9, height=9, bg=theme.PANEL2, highlightthickness=0
        )
        self.pill_dot.pack(side="left", pady=6)
        self._pill_dot_id = self.pill_dot.create_oval(0, 0, 8, 8, fill=theme.OK, outline="")
        self.title_var = tk.StringVar(value="Бэлэн")
        tk.Label(
            pill.inner, textvariable=self.title_var, bg=theme.PANEL2, fg=theme.TEXT,
            font=theme.UI_TITLE,
        ).pack(side="left", padx=(9, 2))

        self.default_hint = (
            f"Дурын цонхон дээр {pretty(self.app.cfg['ptt_key'])} дарж барин ярь. "
            "Курсор байгаа газарт текст шууд шивэгдэнэ."
        )
        self.hint_var = tk.StringVar(value=self.default_hint)
        tk.Label(
            inner, textvariable=self.hint_var, bg=theme.PANEL, fg=theme.MUTED,
            font=theme.UI_SMALL, justify="center", wraplength=340,
        ).pack(pady=(11, 0))

        actions = tk.Frame(inner, bg=theme.PANEL)
        actions.pack(pady=(12, 0))
        self.action_button = Button(actions, "Эхлүүлэх", self.app.toggle)
        self.action_button.pack(side="left")

        chips = tk.Frame(inner, bg=theme.PANEL)
        chips.pack(pady=(12, 0))
        for name, code in QUICK_LANGS:
            chip = RoundedLabel(
                chips, 14, theme.PANEL2, theme.PANEL, theme.BORDER,
                text=name, fg=theme.MUTED, font=theme.UI_NAV,
                padx=14, pady=5, cursor="hand2",
            )
            chip.pack(side="left", padx=3)
            chip.bind("<Button-1>", lambda _e, c=code: self._quick_lang(c))
            self.lang_chips[code] = chip
        self._paint_lang_chips()

        self.tile_grid = tk.Frame(page.body, bg=theme.BG)
        self.tile_grid.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        self.tiles = {}
        for key, caption in [
            ("today", "Өнөөдрийн үг"),
            ("total", "Нийт үг"),
            ("average", "Дундаж таних"),
            ("saved", "Шивэхэд хэмнэсэн"),
        ]:
            self.tiles[key] = StatTile(self.tile_grid, caption)
        self._tile_columns = 0
        self._layout_tiles(4)
        self.tile_grid.bind("<Configure>", self._tiles_resized)
        page.spacer()
        self.refresh_stats()

    def _welcome_card(self, page) -> None:
        """Анх ажиллуулахад л гарах гурван алхамт танилцуулга.

        Дараалал нь санаатай: микрофон ажиллахгүй бол хэл, товчлуур хоёр
        утгагүй; хэлээ сонгоогүй бол товч дарахад буруу хэлээр танина. Тиймээс
        микрофон → хэл → товчлуур. Эхний хоёр нь «Яриа» хуудас руу үсэрнэ,
        гурав дахийг нь хэрэглэгч байгаа газраа туршина.

        Аппын гол санаа нь цонх огт нээхгүйгээр ажиллах явдал тул төгсгөлд нь
        цонхыг хаах нь аппыг зогсоохгүй гэдгийг сануулна. Дараа нь дахин
        гарахгүй.
        """
        self.welcome = None
        if self.app.cfg["onboarded"]:
            return

        card = Card(page.body)
        self.welcome = card

        names, _ = self.app.list_microphones()
        # Эхний нэр нь үргэлж «Системийн үндсэн» тул жинхэнэ төхөөрөмж
        # илэрсэн эсэхийг үлдсэнээр нь мэднэ.
        found = len(names) - 1
        _, holder = card.row(
            "1. Микрофон",
            f"{found} төхөөрөмж илэрлээ" if found else "Төхөөрөмж илрээгүй — залгаад шалгана уу",
        )
        Button(holder, "Сонгох", lambda: self.select(1)).pack()

        _, holder = card.row(
            "2. Ярих хэл",
            f"Одоо: {CODE_TO_NAME.get(self.app.cfg['lang'], self.app.cfg['lang'])}",
        )
        Button(holder, "Солих", lambda: self.select(1)).pack()

        combo = pretty(self.app.cfg["ptt_key"])
        card.row(
            f"3. {combo} дарж бариад ярь",
            "Курсороо текст бичих цонхон дээр тавиад тушаа — товчоо тавимагц шивэгдэнэ",
        )

        _, holder = card.row("Аппын цонх хэрэггүй", "Хаавал цагны хажууд үлдэнэ")
        Button(holder, "Ойлголоо", self._finish_welcome).pack()

    def _finish_welcome(self) -> None:
        self.app.finish_onboarding()
        if self.welcome is not None:
            self.welcome.destroy()
            self.welcome = None
        self.set_detail("Амжилттай! Дахиад хэрэгтэй бол README-г үзнэ үү.")

    def _tiles_resized(self, event) -> None:
        """Нарийн цонхонд 4 картыг нэг эгнээнд багтаахад кирилл шошго таслагдана."""
        self._layout_tiles(4 if event.width >= TILE_ROW_MIN else 2)

    def _layout_tiles(self, columns: int) -> None:
        if columns == self._tile_columns:
            return
        self._tile_columns = columns
        for index, tile in enumerate(self.tiles.values()):
            tile.grid(
                row=index // columns, column=index % columns, sticky="ew",
                padx=(0 if index % columns == 0 else 5, 0),
                pady=(0 if index < columns else 5, 0),
            )
        for column in range(4):
            used = column < columns
            self.tile_grid.columnconfigure(
                column, weight=1 if used else 0, uniform="tiles" if used else ""
            )

    def _quick_lang(self, code: str) -> None:
        self.app.on_lang_changed(code)
        self.lang_var.set(CODE_TO_NAME.get(code, code))
        self._paint_lang_chips()

    def _paint_lang_chips(self) -> None:
        current = self.app.cfg["lang"]
        for code, chip in self.lang_chips.items():
            active = code == current
            chip.restyle(
                fill=theme.ACCENT if active else theme.PANEL2,
                border=theme.ACCENT if active else theme.BORDER,
                fg=theme.TEXT if active else theme.MUTED,
            )

    # --- 2. Яриа ----------------------------------------------------
    def _page_speech(self) -> None:
        page = self._add_page(
            Page(
                self.stack, "Яриа",
                "Ямар хэлээр танихыг, аль микрофоноор сонсохыг тохируулна.",
            )
        )
        card = Card(page.body)

        _, holder = card.row("Үндсэн хэл", "Товчлуур дарахад энэ хэлээр танина")
        self.lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang"], LANGUAGES[0][0])
        )
        self._combo(holder, self.lang_var, [n for n, _ in LANGUAGES], self._lang_changed)

        _, holder = card.row(
            "Хоёр дахь хэл",
            f"{pretty(self.app.cfg['ptt_key_alt'])} дарахад энэ хэл рүү сэлгэнэ",
        )
        self.alt_lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang_alt"], LANGUAGES[1][0])
        )
        self._combo(
            holder, self.alt_lang_var, [n for n, _ in LANGUAGES],
            lambda: self.app.on_alt_lang_changed(NAME_TO_CODE[self.alt_lang_var.get()]),
        )

        _, holder = card.row("Микрофон", "Системийн үндсэн төхөөрөмжийг дагана")
        self.mic_names, self.mic_indexes = self.app.list_microphones()
        self.mic_var = tk.StringVar(value=self._current_mic_name())
        self._combo(holder, self.mic_var, self.mic_names, self._mic_changed)

        _, holder = card.row("Оролтын түвшин", "Ярихад баганууд хөдөлж байвал зөв")
        self.meter = LevelMeter(holder)
        self.meter.pack(side="left")
        self.level_var = tk.StringVar(value="0%")
        tk.Label(
            holder, textvariable=self.level_var, bg=theme.PANEL, fg=theme.MUTED,
            font=theme.MONO_KEY, width=5, anchor="e",
        ).pack(side="left", padx=(9, 0))

        _, holder = card.row(
            "Долгион харуулах", "Курсорын доорх капсул дээр 9 багана"
        )
        self._toggle(holder, "wave_overlay")

        self._stt_card(page)
        self._stt_tail = page.spacer()
        self._sync_stt_fields()

    # --- Танигч сонгох ----------------------------------------------
    def _stt_card(self, page) -> None:
        """Аль үйлчилгээгээр таних вэ.

        Анхны утга нь юу ч тохируулахгүйгээр ажилладаг тул хаяг/загвар/түлхүүрийн
        талбарууд зөвхөн өөрийн үйлчилгээ сонгосон үед л гарна — ихэнх хүнд
        эдгээрийг харах шаардлагагүй.
        """
        names = recognizer.titles()
        self._stt_titles = dict(names)
        self._stt_names = {title: name for name, title in names}

        card = Card(page.body)
        _, holder = card.row("Танигч", "Google нь түлхүүр шаардахгүй")
        self.stt_var = tk.StringVar(
            value=self._stt_titles.get(self.app.cfg["stt_provider"], names[0][1])
        )
        self._combo(
            holder, self.stt_var, [title for _, title in names], self._stt_selected
        )

        # Тусдаа карт — сонголтоос хамааран харагдана/нуугдана
        self._stt_shown = False
        self.stt_extra = Card(page.body, pad=False)
        self.stt_vars: dict[str, tk.StringVar] = {}
        for key, title, desc in STT_FIELDS:
            _, holder = self.stt_extra.row(title, desc)
            variable = tk.StringVar(value=str(self.app.cfg[key]))
            self.stt_vars[key] = variable
            self._field(holder, variable, secret=key == "stt_key")
        self.stt_extra.note("Түлхүүр тохиргооны файлд ил хадгалагдана")
        self._stt_applied = self._stt_values()

    def _field(self, parent, variable, secret: bool = False) -> tk.Entry:
        """Тохиргооны текстийн талбар — гармагц хадгална."""
        box, entry = rounded_entry(
            parent, variable, width=24, font=theme.UI_SMALL, secret=secret
        )
        box.pack()
        # Бичих бүрт биш, талбараас гармагц (эсвэл Enter дарахад) хадгална
        entry.bind("<FocusOut>", lambda _e: self._stt_changed())
        entry.bind("<Return>", lambda _e: self._stt_changed())
        return entry

    def _stt_values(self) -> dict[str, str]:
        values = {"stt_provider": self._stt_names.get(self.stt_var.get(), "google")}
        for key, variable in self.stt_vars.items():
            values[key] = variable.get().strip()
        return values

    def _sync_stt_fields(self) -> None:
        """Талбаруудыг харуулах/нуух.

        Төлөв нь аль хэдийн зөв бол юу ч хийхгүй: багцлалт өөрчлөх нь фокусын
        эвент төрүүлдэг ба тэр нь эргээд энэ функцийг дуудвал цонх мөчлөгт
        орж гацна.
        """
        wanted = self._stt_names.get(self.stt_var.get(), "google") != "google"
        if wanted == self._stt_shown:
            return
        self._stt_shown = wanted
        if wanted:
            self.stt_extra.pack(
                fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP),
                before=self._stt_tail,
            )
        else:
            self.stt_extra.pack_forget()

    def _stt_selected(self) -> None:
        """Танигч солигдлоо — талбаруудыг тааруулаад хэрэглэнэ."""
        self._sync_stt_fields()
        self._stt_changed()

    def _stt_changed(self) -> None:
        """FocusOut нь хуудас солиход ч дуудагддаг тул үнэхээр өөрчлөгдсөн
        үед л танигчийг дахин босгоно."""
        values = self._stt_values()
        if values == self._stt_applied:
            return
        self._stt_applied = values
        self.app.on_stt_changed(values)

    def _lang_changed(self) -> None:
        self.app.on_lang_changed(NAME_TO_CODE[self.lang_var.get()])
        self._paint_lang_chips()

    def _combo(self, parent, variable, values, command) -> ttk.Combobox:
        box = ttk.Combobox(
            parent, textvariable=variable, values=values, state="readonly",
            style="Mon.TCombobox", width=22,
        )
        box.pack()
        box.bind("<<ComboboxSelected>>", lambda _e: command())
        return box

    def _toggle(self, parent, key: str) -> Toggle:
        toggle = Toggle(
            parent, bool(self.app.cfg[key]),
            lambda value, k=key: self._option_changed(k, value),
        )
        toggle.pack()
        self.toggles[key] = toggle
        return toggle

    def _option_changed(self, key: str, value: bool) -> None:
        self.app.on_option_changed(key, value)
        if key in ("auto_capitalize", "auto_space", "voice_punctuation", "clean_speech"):
            self._refresh_preview()

    # --- 3. Бичилт --------------------------------------------------
    def _page_writing(self) -> None:
        page = self._add_page(
            Page(self.stack, "Бичилт", "Таньсан текстийг курсор дээр хэрхэн буулгах.")
        )

        mock = Card(page.body, bg=theme.MOCK)
        tk.Label(
            mock.body, text="ОДООГИЙН ТОХИРГООГООР ГАРАХ ҮР ДҮН", bg=theme.MOCK, fg=theme.DIM,
            font=theme.UI_TINY, anchor="w",
        ).pack(fill="x", padx=14, pady=(11, 6))
        self.preview_var = tk.StringVar()
        tk.Label(
            mock.body, textvariable=self.preview_var, bg=theme.MOCK, fg=theme.TEXT,
            font=theme.MONO_KEY, anchor="w", justify="left",
        ).pack(fill="x", padx=14, pady=(0, 12))

        card = Card(page.body)
        for key, title, desc in WRITING_TOGGLES:
            _, holder = card.row(title, desc)
            self._toggle(holder, key)

        row, holder = card.row(
            "Clipboard ажиллахгүй цонх",
            "Зарим апп синтетик Ctrl+V-г хүлээж авдаггүй. Сүүлд бичсэн цонхыг "
            "жагсаалтад нэмвэл зөвхөн тэнд шууд бичнэ.",
        )
        Button(holder, "Сүүлийн цонхыг нэмэх", self._remember_type_mode_app).pack()
        page.spacer()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Жишээ өгүүлбэр: «за ааа өнөөдрийн хурал 3 цагт болно цэг» гэж хэлсэн гэж үзнэ."""
        cfg = self.app.cfg
        text = "өнөөдрийн хурал 3 цагт болно"
        if not cfg["clean_speech"]:
            text = "за ааа " + text  # цэвэрлэхгүй бол хэлсэн чигээрээ
        if cfg["voice_punctuation"]:
            text += "."
        if cfg["auto_capitalize"]:
            text = text[0].upper() + text[1:]
        self.preview_var.set(("␣" if cfg["auto_space"] else "") + text)

    def _remember_type_mode_app(self) -> None:
        self.set_detail(self.app.remember_type_mode_app())

    # --- 4. Товчлуур ------------------------------------------------
    def _page_hotkeys(self) -> None:
        page = self._add_page(
            Page(
                self.stack, "Товчлуур",
                "«Солих» дарж шинэ товчлуураа дарахад л сольж болно.",
            )
        )
        card = Card(page.body)
        for key, title, desc in HOTKEY_ROWS:
            _, holder = card.row(title, desc)
            caps = Keycaps(holder)
            caps.pack(side="left", padx=(0, 9))
            self.keycaps[key] = caps
            button = Button(holder, "Солих", lambda k=key: self.begin_capture(k))
            button.pack(side="left")
            self.capture_buttons[key] = button
        card.note(
            "Win, Ctrl, Alt, Shift-тэй хослол зөвшөөрнө. "
            "Системийн товчлууртай давхцвал анхааруулна."
        )
        # Алдааны мөрийг картын гадна байрлуулна — нуухад картын доор
        # эзэнгүй тусгаарлагч үлдэхгүй.
        self.hotkey_note = tk.Label(
            page.body, text="", bg=theme.BG, fg=theme.DANGER, font=theme.UI_SMALL,
            anchor="w", justify="left", wraplength=560,
        )
        self._hotkey_tail = page.spacer()

    # --- 5. Толь ----------------------------------------------------
    def _page_dictionary(self) -> None:
        page = self._add_page(
            Page(self.stack, "Толь", "Аппыг өөрийн нэр томьёо, хэллэгт сургана.")
        )
        tabs = SegmentedTabs(
            page.body, ["Үг солих", "Дуут товчлол"], self._dictionary_tab
        )
        tabs.pack(anchor="w", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))

        self.dictionary_tab = 0
        self.pairs = PairEditor(page.body, self._dictionary_changed)
        self.pairs.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        self.pairs.load(self.app.cfg["replacements"])
        page.spacer()

    def _dictionary_tab(self, index: int) -> None:
        self.dictionary_tab = index
        if index == 0:
            self.pairs.set_labels(("Буруу таньсан", "Зөв бичих"))
            self.pairs.load(self.app.cfg["replacements"])
        else:
            self.pairs.set_labels(("Хэллэг", "Бүтэн текст"))
            self.pairs.load(self.app.cfg["snippets"])

    def _dictionary_changed(self, mapping: dict) -> None:
        """Товч дарах бүрт диск рүү бичихгүй — бичиж дуустал хүлээнэ."""
        if self._dictionary_save is not None:
            try:
                self.root.after_cancel(self._dictionary_save)
            except tk.TclError:
                pass
        self._dictionary_save = self.root.after(
            DICTIONARY_SAVE_MS, lambda: self._save_dictionary(mapping)
        )

    def _save_dictionary(self, mapping: dict) -> None:
        self._dictionary_save = None
        raw = textproc.format_replacements(mapping)
        if self.dictionary_tab == 0:
            self.app.on_replacements_changed(raw)
        else:
            self.app.on_snippets_changed(raw)

    # --- 6. Түүх ----------------------------------------------------
    def _page_history(self) -> None:
        page = self._add_page(
            Page(
                self.stack, "Түүх",
                "Мөр дээр давхар товшвол дахин буулгана. Засвал апп тэр залруулгыг сурна.",
            )
        )
        self.history_query = tk.StringVar()
        search = SearchBox(
            page.body, self.history_query, "Түүхээс хайх", outside=theme.BG
        )
        search.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, 10))
        self.history_query.trace_add("write", lambda *_: self._fill_history())

        holder = RoundedBox(page.body, fill=theme.PANEL, outside=theme.BG, pad=(theme.RADIUS, 6))
        holder.pack(fill="both", expand=True, padx=theme.PAGE_PAD_X)
        self.history_box = tk.Listbox(
            holder.inner, bg=theme.PANEL, fg=theme.TEXT, selectbackground=theme.NAV_ACTIVE,
            selectforeground=theme.TEXT, highlightthickness=0, relief="flat",
            font=theme.UI, activestyle="none", height=12, bd=0,
        )
        bar = scrollbar(holder.inner, self.history_box.yview, trough=theme.PANEL)
        bar.pack(side="right", fill="y")
        self.history_box.configure(yscrollcommand=bar.set)
        self.history_box.pack(fill="both", expand=True)
        self.history_box.bind("<Double-Button-1>", self._repaste)

        foot = RoundedBox(
            page.body, fill=theme.PANEL2, outside=theme.BG, pad=(theme.RADIUS, 6)
        )
        foot.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(theme.GAP, theme.GAP))
        self.history_count = tk.StringVar(value="")
        tk.Label(
            foot.inner, textvariable=self.history_count, bg=theme.PANEL2, fg=theme.MUTED,
            font=theme.UI_SMALL, anchor="w",
        ).pack(side="left", padx=4)
        Button(
            foot.inner, "Цэвэрлэх", self.clear_history, bg=theme.PANEL2, danger=True
        ).pack(side="right", padx=(6, 0))
        Button(
            foot.inner, "Засах (сурна)", self._edit_selected, bg=theme.PANEL2
        ).pack(side="right")

        self.history_note = tk.Label(
            page.body, text="", bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL,
            anchor="w", justify="left", wraplength=560,
        )
        self.history_note.pack(fill="x", padx=theme.PAGE_PAD_X)
        page.spacer()
        self._fill_history()

    # --- 7. Нэмэлт --------------------------------------------------
    def _page_advanced(self) -> None:
        page = self._add_page(Page(self.stack, "Нэмэлт"))

        page.group("Горим")
        card = Card(page.body)
        for key, title, desc in MODE_TOGGLES:
            _, holder = card.row(title, desc)
            self._toggle(holder, key)

        page.group("Тохируулга")
        card = Card(page.body)
        for key, title, desc, low, high, step, fmt in TUNING_ROWS:
            _, holder = card.row(title, desc)
            value = max(low, min(high, float(self.app.cfg[key])))
            slider = Slider(
                holder, low, high, step, value,
                lambda v, k=key: self.app.on_tuning_changed(k, v), fmt,
            )
            slider.pack()
            self.sliders[key] = slider

        page.group("Систем")
        card = Card(page.body)
        _, holder = card.row("Windows-тай хамт эхлүүлэх", "Нэвтэрмэгц дэвсгэрт ажиллана")
        self._toggle(holder, "start_with_windows")
        _, holder = card.row("Хаахад tray руу нуух", "Хаах товч дарахад аппыг зогсоохгүй")
        self._toggle(holder, "tray_enabled")
        _, holder = card.row("Шинэчлэл шалгах", "Эхлэхдээ GitHub-аас нэг удаа")
        self._toggle(holder, "check_updates")

        # Тайлбар нь амьд: шинэчлэл олдоход текст нь солигдоно.
        self.version_var = tk.StringVar(value=f"Monspeech {__version__} · Windows")
        _, holder = card.row("Хувилбар", self.version_var)
        self.update_button = Button(holder, "Шинэчлэл авах", self.app.open_releases)

        _, holder = card.row("Алдаа мэдээлэх", "Орчны мэдээлэл ба лог")
        Button(holder, "Логийн хавтас", self.app.open_log).pack(side="left", padx=(0, 6))
        Button(holder, "Мэдээлэл хуулах", self._copy_diagnostics).pack(side="left")
        page.spacer()

    def _copy_diagnostics(self) -> None:
        self.set_detail(self.app.copy_diagnostics())

    def show_update(self, tag: str) -> None:
        """Шинэ хувилбар олдлоо — «Нэмэлт» хуудсанд товч гаргана."""
        self.version_var.set(f"Monspeech {__version__} · шинэ хувилбар: {tag}")
        self.update_button.pack()
        self.set_detail(f"Шинэ хувилбар гарсан байна: {tag}")

    # ------------------------------------------------------------------
    # Гаднаас дуудагдах
    # ------------------------------------------------------------------
    def set_state(self, kind: str, title: str, detail: str) -> None:
        colours = {
            "listening": theme.GRADIENT[0],
            "working": theme.WARN,
            "ready": theme.OK,
            "error": theme.DANGER,
        }
        colour = colours.get(kind, theme.DIM)
        self.title_var.set(title)
        self.state_var.set(title)
        self.dot.itemconfigure(self._dot_id, fill=colour)
        self.pill_dot.itemconfigure(self._pill_dot_id, fill=colour)
        self.action_button.set_text("Зогсоох" if kind == "listening" else "Эхлүүлэх")
        self.orb.set_mode(ORB_MODES.get(kind, "idle"))
        self.hint_var.set(detail or self.default_hint)

    def set_detail(self, text: str) -> None:
        """Түр зуурын мэдэгдэл — доод талын мөрөнд гарна (аль ч хуудсанд харагдана)."""
        self.detail_var.set(text)

    def set_level(self, level: float, listening: bool) -> None:
        """Заалт, роботыг шинэчилнэ.

        Цонх tray-д нуугдсан үед зурах нь утгагүй тул алгасна — 50 мс тутам
        давтагддаг ажил учир хоосон CPU хэрэглээ мэдэгдэхүйц.
        """
        if not self.root.winfo_viewable():
            return
        filled = min(1.0, level / LEVEL_FULL) if listening else 0.0
        self.orb.set_level(filled)
        if self.page_index == 1:
            self.meter.set_level(filled)
            self.level_var.set(f"{filled * 100:.0f}%")

    def refresh_hotkeys(self) -> None:
        for key, caps in self.keycaps.items():
            caps.show(pretty(self.app.cfg[key]).split(" + "))

    def refresh_stats(self) -> None:
        stats = self.app.stats
        data = getattr(stats, "data", {})
        total = data.get("words", 0)
        self.tiles["today"].set(f"{getattr(stats, 'today_words', 0):,}".replace(",", " "))
        self.tiles["total"].set(f"{total:,}".replace(",", " "))
        average = getattr(stats, "average_ms", 0.0)
        self.tiles["average"].set(f"{average / 1000:.1f} сек" if average else "—")
        # Гараар бичихээс хэдэн минут хожсоныг барагцаална (40 үг/мин)
        saved = total / 40 - data.get("seconds_spoken", 0.0) / 60
        self.tiles["saved"].set(f"{saved:,.0f} мин".replace(",", " ") if saved > 1 else "—")

    def refresh_words(self) -> None:
        """Толь өөрчлөгдсөн үед (жишээ нь засвараас сурсан) жагсаалтыг шинэчилнэ."""
        if self.dictionary_tab == 0:
            self.pairs.load(self.app.cfg["replacements"])

    def show_history(self) -> None:
        self.select(5)

    # --- товчлуур барьж авах ---
    def begin_capture(self, key: str) -> None:
        if self._capturing_key:
            return
        self._capturing_key = key
        self.hotkey_note.pack_forget()
        self.keycaps[key].show_text("Одоо товчоо дар…  (Esc — цуцлах)")
        self.capture_buttons[key].set_text("Цуцлах")
        self.capture_buttons[key].bind("<Button-1>", lambda _e: self.cancel_capture())
        self.app.begin_hotkey_capture(key)

    def cancel_capture(self) -> None:
        # Цуцлах нь listener-ээр дамжиж эргэж ирнэ — тэнд `finish_capture` дуудагдана
        self.app.cancel_hotkey_capture()

    def finish_capture(self, key: str | None, combo: str | None) -> None:
        if not key:
            return
        self._capturing_key = None
        button = self.capture_buttons[key]
        button.set_text("Солих")
        button.unbind("<Button-1>")
        button.bind("<Button-1>", lambda _e, k=key: self.begin_capture(k))

        if combo:
            error = self.app.on_hotkey_changed(key, combo)
            if error:
                self.hotkey_note.configure(text=error)
                self.hotkey_note.pack(
                    fill="x", padx=theme.PAGE_PAD_X, pady=(0, 8), before=self._hotkey_tail
                )
        self.refresh_hotkeys()

    # ------------------------------------------------------------------
    # Микрофон
    # ------------------------------------------------------------------
    def _current_mic_name(self) -> str:
        try:
            return self.mic_names[self.mic_indexes.index(int(self.app.cfg["mic_index"]))]
        except (ValueError, IndexError):
            return self.mic_names[0]

    def _mic_changed(self) -> None:
        try:
            index = self.mic_indexes[self.mic_names.index(self.mic_var.get())]
        except ValueError:
            return
        self.app.on_mic_changed(index)

    # ------------------------------------------------------------------
    # Түүх
    # ------------------------------------------------------------------
    def refresh_history(self) -> None:
        if self.history_box.winfo_exists():
            self._fill_history()

    def clear_history(self) -> None:
        self.app.transcripts.clear()
        self._fill_history()

    def _fill_history(self) -> None:
        """Хайлтын үр дүнгээр жагсаалтыг дүүргэнэ."""
        if not self.history_box.winfo_exists():
            return
        self._history_rows = self.app.transcripts.search(self.history_query.get())
        self.history_box.delete(0, "end")
        for entry in self._history_rows:
            stamp = entry.get("at", "")[5:16].replace("T", " ")
            self.history_box.insert("end", f"  {stamp}   {entry['text']}")
        self.history_count.set(f"{len(self._history_rows)} мөр")

    def _selected_entry(self) -> dict | None:
        selection = self.history_box.curselection()
        if not selection:
            return None
        try:
            return self._history_rows[selection[0]]
        except IndexError:
            return None

    def _repaste(self, _event=None) -> None:
        entry = self._selected_entry()
        if entry:
            self.app.repaste(entry["text"])

    def _edit_selected(self) -> None:
        """Сонгосон мөрийг засах — ялгааг нь толинд сурна."""
        entry = self._selected_entry()
        if not entry:
            self.history_note.configure(text="Эхлээд мөр сонгоно уу.")
            return
        editor = tk.Toplevel(self.root)
        editor.title("Засах")
        editor.configure(bg=theme.BG)
        editor.geometry("460x190")
        editor.transient(self.root)
        tk.Label(
            editor, text="Зөв бичвэрийг оруулна уу:", bg=theme.BG, fg=theme.MUTED,
            font=theme.UI, anchor="w",
        ).pack(fill="x", padx=theme.PAGE_PAD_X, pady=(16, 6))
        box = RoundedBox(
            editor, fill=theme.PANEL2, outside=theme.BG,
            radius=theme.RADIUS_SMALL, pad=(theme.RADIUS_SMALL, 6),
        )
        box.pack(fill="x", padx=theme.PAGE_PAD_X)
        field = tk.Text(
            box.inner, bg=theme.PANEL2, fg=theme.TEXT, insertbackground=theme.TEXT,
            relief="flat", highlightthickness=0, bd=0,
            font=theme.UI, height=3, wrap="word",
        )
        field.pack(fill="x")
        field.insert("1.0", entry["text"])
        field.focus_set()

        def save() -> None:
            corrected = field.get("1.0", "end").strip()
            editor.destroy()
            if corrected and corrected != entry["text"]:
                message = self.app.on_transcript_corrected(entry, corrected)
                self.history_note.configure(text=message)
                self._fill_history()

        Button(editor, "Хадгалах", save, bg=theme.BG).pack(
            anchor="e", padx=theme.PAGE_PAD_X, pady=12
        )
