"""Удирдлагын цонх — "Monspeech Window Directions" баримтын 2c чиглэл.

Таб ч, хажуугийн цэс ч байхгүй: дээрээ хайлт, доор нь төлөв → хэл/микрофон →
шивэлт → заалт → товчлуур → нуугдсан нарийн тохируулга гэсэн нэг урсгал.
Ховор нээдэг цонхны хамгийн хүнд зардал болох "аль таб дор байсан бол" гэсэн
эргэлзээг хайлт бүрэн арилгана.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from . import __version__, theme
from .hotkeys import pretty
from .widgets import (
    Keycaps,
    Link,
    ScrollFrame,
    Section,
    StatusBlock,
    Toggle,
    label_row,
    toggle_row,
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

# Чагтуудын бүлэглэл — баримтын "есөн чагтын эрэмбэ"
TYPING_TOGGLES = [
    ("type_mode", "Шууд бичих", "clipboard clipboard-гүй шивэх"),
    ("auto_space", "Зай нэмэх", "space зай"),
    ("auto_capitalize", "Том үсгээр эхлүүлэх", "capital том үсэг өгүүлбэр"),
    ("voice_punctuation", "Дуут цэг таслал", "цэг таслал punctuation дуут"),
]
APP_TOGGLES = [
    ("wave_overlay", "Долгион харуулах", "долгион заалт курсор overlay"),
    ("tray_enabled", "Хаахад tray руу нуух", "tray хаах"),
    (
        "start_with_windows",
        "Windows-тай хамт эхлүүлэх",
        "автомат эхлэх startup асахад компьютер нэвтрэх",
    ),
]
ADVANCED_TOGGLES = [
    ("ptt_enabled", "Push-to-talk горим", "push to talk дарж барих горим"),
    ("restore_clipboard", "Clipboard-ыг сэргээх", "clipboard сэргээх"),
    ("learn_corrections", "Засварыг сурах", "сурах толь засвар автомат"),
]

HOTKEY_ROWS = [
    ("ptt_key", "Дарж барих", "товчлуур дарж барих push to talk"),
    ("ptt_key_alt", "Хоёр дахь хэл", "товчлуур хоёр дахь хэл english"),
    ("hotkey", "Асаах/унтраах", "товчлуур асаах унтраах toggle"),
    ("undo_key", "Буцаах", "товчлуур буцаах undo"),
]

TUNING_ROWS = [
    (
        "silence_hold",
        "Завсарлага",
        "завсарлага чимээгүй өгүүлбэр таслах",
        [("0.4 сек — хурдан", 0.4), ("0.55 сек", 0.55), ("0.7 сек", 0.7),
         ("0.9 сек", 0.9), ("1.2 сек — тайван", 1.2)],
    ),
    (
        "min_confidence",
        "Итгэлцлийн босго",
        "итгэлцэл босго нарийвчлал",
        [("Шүүхгүй", 0.0), ("0.30 — зөөлөн", 0.3), ("0.45", 0.45),
         ("0.60 — хатуу", 0.6), ("0.75 — маш хатуу", 0.75)],
    ),
    (
        "mic_keep_open_seconds",
        "Микрофон бэлэн барих",
        "микрофон бэлэн хурдан эхлэх",
        [("Болих", 0), ("15 сек", 15), ("45 сек", 45), ("2 минут", 120)],
    ),
    (
        "max_recording_seconds",
        "Бичлэгийн дээд хугацаа",
        "бичлэг дээд хугацаа хязгаар аюулгүй гацах",
        [("1 минут", 60), ("3 минут", 180), ("5 минут", 300), ("10 минут", 600)],
    ),
]


class ControlWindow:
    """Цонхны бүх виджетийг эзэмшинэ. Логик нь `app`-д үлдэнэ."""

    def __init__(self, root: tk.Tk, app) -> None:
        self.root = root
        self.app = app
        self.rows: list[dict] = []  # хайлтад бүртгэгдсэн мөрүүд
        self.sections: list[Section] = []
        self.toggles: dict[str, Toggle] = {}
        self.keycaps: dict[str, Keycaps] = {}
        self.capture_links: dict[str, Link] = {}
        self.tuning_boxes: dict[str, ttk.Combobox] = {}
        self.history_window: tk.Toplevel | None = None
        self.history_box: tk.Listbox | None = None
        self._history_rows: list[dict] = []
        self._capturing_key: str | None = None

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
        self._build_header()
        self._build_status()
        self._build_body()
        self._build_footer()
        self.refresh_hotkeys()

    def _dark_titlebar(self) -> None:
        """Windows-ийн гарчгийн мөрийг бараан болгоно.

        Эс бөгөөс бараан цонхны дээр цагаан хүрээ тод харагдана.
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
            fieldbackground=theme.PANEL,
            background=theme.PANEL,
            foreground=theme.TEXT,
            bordercolor=theme.BORDER,
            lightcolor=theme.BORDER,
            darkcolor=theme.BORDER,
            arrowcolor=theme.DIM,
            selectbackground=theme.PANEL,
            selectforeground=theme.TEXT,
            padding=4,
        )
        # Сумны товчийг ч бараан болгоно — эс бөгөөс баруун тал нь саарал үлдэнэ
        style.map(
            "Mon.TCombobox",
            fieldbackground=[("readonly", theme.PANEL), ("!disabled", theme.PANEL)],
            background=[
                ("readonly", theme.PANEL), ("active", theme.HOVER), ("!disabled", theme.PANEL)
            ],
            bordercolor=[("focus", theme.ACCENT)],
            lightcolor=[("focus", theme.ACCENT), ("!focus", theme.BORDER)],
            darkcolor=[("!focus", theme.BORDER)],
            arrowcolor=[("active", theme.TEXT), ("!disabled", theme.DIM)],
            foreground=[("readonly", theme.TEXT)],
        )
        self.root.option_add("*TCombobox*Listbox.background", theme.PANEL)
        self.root.option_add("*TCombobox*Listbox.foreground", theme.TEXT)
        self.root.option_add("*TCombobox*Listbox.selectBackground", theme.ACCENT)
        self.root.option_add("*TCombobox*Listbox.font", theme.UI)

    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg=theme.BG, height=theme.HEADER_HEIGHT)
        header.pack(fill="x")
        header.pack_propagate(False)

        box = tk.Frame(
            header, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER
        )
        box.pack(fill="x", expand=True, padx=theme.PAD_X, pady=8)
        tk.Label(box, text="⌕", bg=theme.PANEL, fg=theme.DIM, font=("Segoe UI", 11)).pack(
            side="left", padx=(8, 4)
        )
        self.search_var = tk.StringVar()
        entry = tk.Entry(
            box,
            textvariable=self.search_var,
            bg=theme.PANEL,
            fg=theme.TEXT,
            insertbackground=theme.TEXT,
            relief="flat",
            font=theme.UI,
            highlightthickness=0,
        )
        entry.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=5)
        self._placeholder(entry, "Тохиргоо хайх")
        self.search_var.trace_add("write", lambda *_: self._apply_search())

        tk.Frame(self.root, bg=theme.DIVIDER, height=1).pack(fill="x")

    def _placeholder(self, entry: tk.Entry, text: str) -> None:
        """Хоосон үед сануулга харуулна (Tk-д placeholder байхгүй)."""
        ghost = tk.Label(entry, text=text, bg=theme.PANEL, fg=theme.DIM, font=theme.UI)

        def sync(*_):
            if self.search_var.get():
                ghost.place_forget()
            else:
                ghost.place(x=0, rely=0.5, anchor="w")

        self.search_var.trace_add("write", sync)
        sync()

    def _build_status(self) -> None:
        wrap = tk.Frame(self.root, bg=theme.BG)
        wrap.pack(fill="x", padx=theme.PAD_X, pady=14)
        self.status = StatusBlock(wrap)
        self.status.pack(side="left", fill="x", expand=True)
        self.action_link = Link(wrap, "Эхлүүлэх", self.app.toggle, font=theme.UI)
        self.action_link.pack(side="right", padx=(10, 0))
        tk.Frame(self.root, bg=theme.DIVIDER, height=1).pack(fill="x")

    def _build_body(self) -> None:
        self.scroll = ScrollFrame(self.root)
        self.scroll.pack(fill="both", expand=True)
        body = self.scroll.body

        self._section_audio(body)
        self._section_typing(body)
        self._section_toggles(body, "Заалт ба tray", APP_TOGGLES)
        self._section_hotkeys(body)
        self._section_advanced(body)
        self._section_words(body)
        self._section_snippets(body)
        tk.Frame(body, bg=theme.BG, height=10).pack(fill="x")

    def _register(
        self, section: Section, widget: tk.Widget, keywords: str, **pack
    ) -> None:
        """Мөрийг хайлтад бүртгэнэ.

        Багцлах тохиргоог нь хамт хадгална: хайлт мөрүүдийг нуугаад буцааж
        харуулахдаа яг анхныхаараа сэргээнэ (эс бөгөөс зай нь алдагдаж,
        зарим хэсэг огт эргэж гарахгүй байсан).
        """
        self.rows.append(
            {
                "section": section,
                "widget": widget,
                "keywords": keywords.lower(),
                "pack": pack or {"fill": "x"},
            }
        )

    def _add_section(self, parent, title, **kwargs) -> Section:
        section = Section(parent, title, **kwargs)
        section.pack(fill="x")
        self.sections.append(section)
        return section

    # --- хэсгүүд ---
    def _section_audio(self, parent) -> None:
        section = self._add_section(parent, "Хэл ба микрофон")

        row, holder = label_row(section.body, "Хэл")
        self.lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang"], LANGUAGES[0][0])
        )
        box = ttk.Combobox(
            holder, textvariable=self.lang_var, values=[n for n, _ in LANGUAGES],
            state="readonly", style="Mon.TCombobox",
        )
        box.pack(fill="x")
        box.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.app.on_lang_changed(NAME_TO_CODE[self.lang_var.get()]),
        )
        self._register(section, row, "хэл language монгол english", fill="x", pady=4)

        # Хоёрдогч товчлуураар (анхны утга Win+Shift) ярих хэл
        row, holder = label_row(section.body, "Хоёр дахь хэл")
        self.alt_lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang_alt"], LANGUAGES[1][0])
        )
        alt_box = ttk.Combobox(
            holder, textvariable=self.alt_lang_var, values=[n for n, _ in LANGUAGES],
            state="readonly", style="Mon.TCombobox",
        )
        alt_box.pack(fill="x")
        alt_box.bind(
            "<<ComboboxSelected>>",
            lambda _e: self.app.on_alt_lang_changed(NAME_TO_CODE[self.alt_lang_var.get()]),
        )
        self._register(
            section, row,
            f"хоёр дахь хэл second language {pretty(self.app.cfg['ptt_key_alt'])}",
            fill="x", pady=4,
        )

        row, holder = label_row(section.body, "Микрофон")
        self.mic_names, self.mic_indexes = self.app.list_microphones()
        self.mic_var = tk.StringVar(value=self._current_mic_name())
        mic_box = ttk.Combobox(
            holder, textvariable=self.mic_var, values=self.mic_names,
            state="readonly", style="Mon.TCombobox",
        )
        mic_box.pack(fill="x")
        mic_box.bind("<<ComboboxSelected>>", self._mic_changed)
        self._register(section, row, "микрофон mic төхөөрөмж", fill="x", pady=4)

        row, holder = label_row(section.body, "Түвшин")
        self.meter = tk.Canvas(holder, height=6, bg=theme.PANEL, highlightthickness=0, bd=0)
        self.meter.pack(fill="x", pady=6)
        self._meter_bar = self.meter.create_rectangle(0, 0, 0, 6, fill=theme.ACCENT, outline="")
        self._register(section, row, "түвшин level дуу", fill="x", pady=4)
        section.divider()

    def _add_toggles(self, section: Section, items: list) -> None:
        """Чагтын мөрүүдийг нэмж, хайлтад бүртгэнэ."""
        for key, label, keywords in items:
            row, toggle = toggle_row(
                section.body,
                label,
                bool(self.app.cfg[key]),
                lambda value, k=key: self.app.on_option_changed(k, value),
            )
            self.toggles[key] = toggle
            self._register(section, row, f"{label} {keywords}")

    def _section_toggles(self, parent, title: str, items: list) -> None:
        section = self._add_section(parent, title)
        self._add_toggles(section, items)
        section.divider()

    def _section_typing(self, parent) -> None:
        """Шивэлтийн чагтууд + Ctrl+V хүлээж авдаггүй аппыг санах мөр."""
        section = self._add_section(parent, "Шивэлт")
        self._add_toggles(section, TYPING_TOGGLES)

        row = tk.Frame(section.body, bg=theme.BG)
        row.pack(fill="x", pady=6)
        tk.Label(
            row, text="Clipboard ажиллахгүй цонх", bg=theme.BG, fg=theme.MUTED,
            font=theme.UI, anchor="w",
        ).pack(side="left")
        Link(row, "Сүүлийн цонхыг нэмэх", self._remember_type_mode_app).pack(side="right")
        self._register(
            section, row,
            "шууд бичих цонх нэмэх clipboard ажиллахгүй апп жагсаалт",
            fill="x", pady=6,
        )
        section.divider()

    def _remember_type_mode_app(self) -> None:
        self.set_detail(self.app.remember_type_mode_app())

    def _section_hotkeys(self, parent) -> None:
        section = self._add_section(parent, "Товчлуур")
        for key, label, keywords in HOTKEY_ROWS:
            row = tk.Frame(section.body, bg=theme.BG)
            row.pack(fill="x", pady=5)
            tk.Label(
                row, text=label, bg=theme.BG, fg=theme.MUTED, font=theme.UI,
                width=theme.LABEL_WIDTH, anchor="w",
            ).pack(side="left")
            caps = Keycaps(row)
            caps.pack(side="left")
            self.keycaps[key] = caps
            link = Link(row, "Солих", lambda k=key: self.begin_capture(k))
            link.pack(side="right")
            self.capture_links[key] = link
            self._register(section, row, f"{label} {keywords}", fill="x", pady=5)

        self.hotkey_note = tk.Label(
            section.body, text="", bg=theme.BG, fg=theme.DANGER,
            font=theme.UI_SMALL, anchor="w", wraplength=380, justify="left",
        )
        section.divider()

    def _section_advanced(self, parent) -> None:
        count = len(ADVANCED_TOGGLES) + len(TUNING_ROWS)
        section = self._add_section(
            parent, "Нарийн тохируулга", collapsible=True, count=count
        )
        self._add_toggles(section, ADVANCED_TOGGLES)

        for key, label, keywords, options in TUNING_ROWS:
            row, holder = label_row(section.body, label)
            current = next(
                (n for n, v in options if abs(float(v) - float(self.app.cfg[key])) < 1e-6),
                options[0][0],
            )
            var = tk.StringVar(value=current)
            box = ttk.Combobox(
                holder, textvariable=var, values=[n for n, _ in options],
                state="readonly", style="Mon.TCombobox",
            )
            box.pack(fill="x")
            box.bind(
                "<<ComboboxSelected>>",
                lambda _e, k=key, v=var, o=options: self.app.on_tuning_changed(
                    k, dict(o)[v.get()]
                ),
            )
            self.tuning_boxes[key] = box
            self._register(section, row, f"{label} {keywords}", fill="x", pady=4)
        section.divider()

    def _section_words(self, parent) -> None:
        section = self._add_section(
            parent, "Үг солих", collapsible=True, count=len(self.app.cfg["replacements"])
        )
        self.words_section = section
        tk.Label(
            section.body,
            text="Байнга буруу танигддаг үг, хэллэгээ засна. Мөр бүрт: буруу=зөв",
            bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL, anchor="w", justify="left",
        ).pack(fill="x", pady=(0, 6))
        self.words_text = tk.Text(
            section.body, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
            relief="flat", highlightthickness=1, highlightbackground=theme.BORDER,
            font=("Consolas", 10), height=7,
        )
        self.words_text.pack(fill="x")
        from . import textproc

        self.words_text.insert(
            "1.0", textproc.format_replacements(self.app.cfg["replacements"])
        )
        Link(section.body, "Хадгалах", self._save_words, font=theme.UI).pack(
            anchor="e", pady=6
        )
        self._register(section, section.body, "үг солих хэллэг орлуулга")

    def _section_snippets(self, parent) -> None:
        section = self._add_section(
            parent, "Дуут товчлол", collapsible=True, count=len(self.app.cfg["snippets"])
        )
        self.snippets_section = section
        tk.Label(
            section.body,
            text='Хэлэхэд урт текст болж тэлнэ. Мөр бүрт: хэллэг=бүтэн текст\n'
                 'Жишээ: миний хаяг=Улаанбаатар хот, Сүхбаатар дүүрэг',
            bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL, anchor="w", justify="left",
        ).pack(fill="x", pady=(0, 6))
        self.snippets_text = tk.Text(
            section.body, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
            relief="flat", highlightthickness=1, highlightbackground=theme.BORDER,
            font=("Consolas", 10), height=5,
        )
        self.snippets_text.pack(fill="x")
        from . import textproc

        self.snippets_text.insert(
            "1.0", textproc.format_replacements(self.app.cfg["snippets"])
        )
        Link(section.body, "Хадгалах", self._save_snippets, font=theme.UI).pack(
            anchor="e", pady=6
        )
        self._register(section, section.body, "товчлол snippet хаяг бэлэн текст")

    def _build_footer(self) -> None:
        tk.Frame(self.root, bg=theme.DIVIDER, height=1).pack(fill="x")
        footer = tk.Frame(self.root, bg=theme.BG, height=theme.FOOTER_HEIGHT)
        footer.pack(fill="x")
        footer.pack_propagate(False)

        left = tk.Frame(footer, bg=theme.BG)
        left.pack(side="left", padx=theme.PAD_X)
        self.dot = tk.Canvas(left, width=6, height=6, bg=theme.BG, highlightthickness=0)
        self.dot.pack(side="left", pady=2)
        self._dot_id = self.dot.create_oval(0, 0, 5, 5, fill=theme.OK, outline="")
        self.footer_var = tk.StringVar(value="Бэлэн")
        tk.Label(
            left, textvariable=self.footer_var, bg=theme.BG, fg=theme.DIM, font=theme.MONO
        ).pack(side="left", padx=8)
        self.stats_var = tk.StringVar(value="")
        tk.Label(
            left, textvariable=self.stats_var, bg=theme.BG, fg=theme.DIM, font=theme.MONO
        ).pack(side="left")
        self.refresh_stats()

        right = tk.Frame(footer, bg=theme.BG)
        right.pack(side="right", padx=theme.PAD_X)
        # Хувилбар — хэрэглэгч аль хувилбартайгаа мэдэхгүй байх нь тусламж
        # хүсэхэд хамгийн түрүүнд гардаг асуулт
        tk.Label(
            right, text=f"v{__version__}", bg=theme.BG, fg=theme.DIM, font=theme.MONO
        ).pack(side="right", padx=(10, 0))
        Link(right, "Лог", self.app.open_log, font=theme.MONO).pack(side="right")
        tk.Label(right, text="·", bg=theme.BG, fg=theme.DIM, font=theme.MONO).pack(
            side="right", padx=6
        )
        Link(right, "Түүх", self.show_history, font=theme.MONO).pack(side="right")

    # ------------------------------------------------------------------
    # Хайлт
    # ------------------------------------------------------------------
    def _apply_search(self) -> None:
        query = self.search_var.get().strip().lower()
        for section in self.sections:
            section.pack_forget()
        for row in self.rows:
            if row["widget"] is not row["section"].body:
                row["widget"].pack_forget()

        for section in self.sections:
            matches = [r for r in self.rows if r["section"] is section]
            if query:
                matches = [r for r in matches if query in r["keywords"]]
            if not matches:
                continue
            section.pack(fill="x")
            for row in matches:
                if row["widget"] is section.body:
                    continue  # хэсгийн биеийг Section өөрөө удирдана
                row["widget"].pack(**row["pack"])
            if query and section.collapsible and not section.expanded:
                section.toggle()
        if not query:
            self.scroll.to_top()

    # ------------------------------------------------------------------
    # Гаднаас дуудагдах
    # ------------------------------------------------------------------
    def set_state(self, kind: str, title: str, detail: str) -> None:
        colours = {
            "listening": theme.OK,
            "working": theme.ACCENT,
            "ready": theme.OK,
            "error": theme.DANGER,
        }
        self.status.set_text(title, detail)
        self.dot.itemconfigure(self._dot_id, fill=colours.get(kind, theme.DIM))
        self.footer_var.set(title)
        self.action_link.configure(text="Зогсоох" if kind == "listening" else "Эхлүүлэх")

    def set_detail(self, text: str) -> None:
        self.status.detail_var.set(text)

    def set_level(self, level: float, listening: bool) -> None:
        """Түвшний зураас ба төлөвийн баганыг шинэчилнэ.

        Цонх tray-д нуугдсан үед зурах нь утгагүй тул алгасна — 50 мс тутам
        давтагддаг ажил учир хоосон CPU хэрэглээ мэдэгдэхүйц.
        """
        if not self.root.winfo_viewable():
            return
        filled = min(1.0, level / 4000.0) if listening else 0.0
        width = self.meter.winfo_width() or 1
        self.meter.coords(self._meter_bar, 0, 0, width * filled, 6)

        if listening:
            base = min(1.0, level / 3200.0)
            heights = [
                theme.BAR_MIN + base * theme.BAR_MAX * (0.5 + 0.5 * (1 - abs(i - 4) / 4))
                for i in range(theme.BAR_COUNT)
            ]
        else:
            heights = [theme.BAR_MIN] * theme.BAR_COUNT
        self.status.set_bars(heights)

    def refresh_hotkeys(self) -> None:
        for key, caps in self.keycaps.items():
            caps.show(pretty(self.app.cfg[key]).split(" + "))

    # --- товчлуур барьж авах ---
    def begin_capture(self, key: str) -> None:
        if self._capturing_key:
            return
        self._capturing_key = key
        self.hotkey_note.pack_forget()
        self.keycaps[key].show_text("Одоо товчоо дар…  (Esc — цуцлах)")
        self.capture_links[key].configure(text="Цуцлах")
        self.capture_links[key].bind("<Button-1>", lambda _e: self.cancel_capture())
        self.app.begin_hotkey_capture(key)

    def cancel_capture(self) -> None:
        # Цуцлах нь listener-ээр дамжиж эргэж ирнэ — тэнд `finish_capture` дуудагдана
        self.app.cancel_hotkey_capture()

    def finish_capture(self, key: str | None, combo: str | None) -> None:
        if not key:
            return
        self._capturing_key = None
        link = self.capture_links[key]
        link.configure(text="Солих")
        link.unbind("<Button-1>")
        link.bind("<Button-1>", lambda _e, k=key: self.begin_capture(k))

        if combo:
            error = self.app.on_hotkey_changed(key, combo)
            if error:
                self.hotkey_note.configure(text=error)
                self.hotkey_note.pack(fill="x", pady=(4, 0))
        self.refresh_hotkeys()

    def _save_words(self) -> None:
        count = self.app.on_replacements_changed(self.words_text.get("1.0", "end"))
        self.words_section.set_count(count)

    def _save_snippets(self) -> None:
        count = self.app.on_snippets_changed(self.snippets_text.get("1.0", "end"))
        self.snippets_section.set_count(count)

    def refresh_words(self) -> None:
        """Толь өөрчлөгдсөн үед (жишээ нь засвараас сурсан) талбарыг шинэчилнэ."""
        from . import textproc

        mapping = self.app.cfg["replacements"]
        self.words_text.delete("1.0", "end")
        self.words_text.insert("1.0", textproc.format_replacements(mapping))
        self.words_section.set_count(len(mapping))

    def refresh_stats(self) -> None:
        summary = self.app.stats.summary()
        self.stats_var.set(f"  ·  {summary}" if summary else "")

    def _current_mic_name(self) -> str:
        try:
            return self.mic_names[self.mic_indexes.index(int(self.app.cfg["mic_index"]))]
        except (ValueError, IndexError):
            return self.mic_names[0]

    def _mic_changed(self, _event=None) -> None:
        try:
            index = self.mic_indexes[self.mic_names.index(self.mic_var.get())]
        except ValueError:
            return
        self.app.on_mic_changed(index)

    # ------------------------------------------------------------------
    # Түүхийн цонх
    # ------------------------------------------------------------------
    def refresh_history(self) -> None:
        """Түүхийн цонх нээлттэй байвал шинэ мөрийг тэр дор нь харуулна."""
        if self.history_box is not None and self.history_box.winfo_exists():
            self._fill_history()

    def clear_history(self) -> None:
        self.app.transcripts.clear()
        self._fill_history()

    def show_history(self) -> None:
        if self.history_window is not None and self.history_window.winfo_exists():
            self.history_window.lift()
            return
        window = tk.Toplevel(self.root)
        self.history_window = window
        window.title("Monspeech — түүх")
        window.configure(bg=theme.BG)
        window.geometry("520x460")

        head = tk.Frame(window, bg=theme.BG)
        head.pack(fill="x", padx=theme.PAD_X, pady=(14, 8))
        box = tk.Frame(
            head, bg=theme.PANEL, highlightthickness=1, highlightbackground=theme.BORDER
        )
        box.pack(side="left", fill="x", expand=True)
        tk.Label(box, text="⌕", bg=theme.PANEL, fg=theme.DIM, font=("Segoe UI", 11)).pack(
            side="left", padx=(8, 4)
        )
        self.history_query = tk.StringVar()
        tk.Entry(
            box, textvariable=self.history_query, bg=theme.PANEL, fg=theme.TEXT,
            insertbackground=theme.TEXT, relief="flat", font=theme.UI, highlightthickness=0,
        ).pack(side="left", fill="x", expand=True, padx=(0, 8), pady=5)
        self.history_query.trace_add("write", lambda *_: self._fill_history())
        Link(head, "Цэвэрлэх", self.clear_history, font=theme.MONO).pack(side="right", padx=8)

        self.history_box = tk.Listbox(
            window, bg=theme.PANEL, fg=theme.TEXT, selectbackground=theme.BORDER,
            selectforeground=theme.TEXT, highlightthickness=1,
            highlightbackground=theme.BORDER, relief="flat", font=theme.UI,
            activestyle="none",
        )
        self.history_box.pack(fill="both", expand=True, padx=theme.PAD_X, pady=(0, 8))
        self.history_box.bind("<Double-Button-1>", self._repaste)

        actions = tk.Frame(window, bg=theme.BG)
        actions.pack(fill="x", padx=theme.PAD_X, pady=(0, 6))
        Link(actions, "Засах (буруу таньсныг сурна)", self._edit_selected, font=theme.UI).pack(
            side="left"
        )
        self.history_note = tk.Label(
            window, text="Давхар товшвол 2 секундын дараа дахин буулгана",
            bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL, wraplength=460, justify="left",
        )
        self.history_note.pack(fill="x", padx=theme.PAD_X, pady=(0, 12))
        self._fill_history()

    def _fill_history(self) -> None:
        """Хайлтын үр дүнгээр жагсаалтыг дүүргэнэ."""
        if not self.history_box or not self.history_box.winfo_exists():
            return
        query = self.history_query.get() if hasattr(self, "history_query") else ""
        self._history_rows = self.app.transcripts.search(query)
        self.history_box.delete(0, "end")
        for entry in self._history_rows:
            stamp = entry.get("at", "")[5:16].replace("T", " ")
            self.history_box.insert("end", f"{stamp}   {entry['text']}")

    def _selected_entry(self) -> dict | None:
        if not self.history_box:
            return None
        selection = self.history_box.curselection()
        if not selection:
            return None
        try:
            return self._history_rows[selection[0]]
        except (AttributeError, IndexError):
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
        editor = tk.Toplevel(self.history_window or self.root)
        editor.title("Засах")
        editor.configure(bg=theme.BG)
        editor.geometry("460x180")
        tk.Label(
            editor, text="Зөв бичвэрийг оруулна уу:", bg=theme.BG, fg=theme.MUTED,
            font=theme.UI, anchor="w",
        ).pack(fill="x", padx=theme.PAD_X, pady=(14, 6))
        field = tk.Text(
            editor, bg=theme.PANEL, fg=theme.TEXT, insertbackground=theme.TEXT,
            relief="flat", highlightthickness=1, highlightbackground=theme.BORDER,
            font=theme.UI, height=3, wrap="word",
        )
        field.pack(fill="x", padx=theme.PAD_X)
        field.insert("1.0", entry["text"])
        field.focus_set()

        def save() -> None:
            corrected = field.get("1.0", "end").strip()
            editor.destroy()
            if corrected and corrected != entry["text"]:
                message = self.app.on_transcript_corrected(entry, corrected)
                self.history_note.configure(text=message)
                self._fill_history()

        Link(editor, "Хадгалах", save, font=theme.UI).pack(anchor="e", padx=theme.PAD_X, pady=10)
