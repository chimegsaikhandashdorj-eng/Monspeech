"""Удирдлагын цонх — "Monspeech Redesign" бүтэц.

Өмнөх хувилбар нь нэг урт скролл дээр 7 хэсгийг дараалуулж, хайлтыг үндсэн
навигаци болгосон байв. Хүн цонхыг нээмэгц юу тохируулж болохоо мэдэхийн тулд
скролл хийх эсвэл нэрийг нь таамаглаж бичих шаардлагатай болдог байсан — энэ
нь ховор нээгддэг цонхонд буруу шийдэл.

Одоо: **зүүн талын 7 цэс, баруун талд солигддог хуудас**. Хайлт үлдсэн ч
sidebar-ын дээд талд туслах хэрэгсэл болж жижигрэв — илэрц бүр "аль цэст
байгаа"-г хэлж, дарахад тэр цэс рүү аваачна.

Товчлол:  Ctrl+1…5 — цэс сонгох,  Ctrl+F — хайлт.

Тохиргоо («Яриа», «Бичилт», «Товчлуур», «Нэмэлт») нь тусдаа цонхоор
нээгддэг — өдөр бүр хэрэглэгдэх цэснээс салгасан.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import tkinter as tk
from tkinter import ttk

from . import __version__, animate, filetext, icons, textproc, theme
from .hotkeys import pretty
from .orb import RobotOrb
from .stt_settings import SttCard
from .widgets import (
    Button,
    Card,
    Keycaps,
    LevelMeter,
    Link,
    NavButton,
    Page,
    PairEditor,
    RoundedBox,
    RoundedLabel,
    SearchBox,
    SegmentedTabs,
    Slider,
    Toggle,
    combo,
    focusable,
    hover_group,
    refit,
    scrollbar,
)

#: Төлөв хуудсанд харагдах сүүлийн бичвэрийн тоо. Түүхийн бүтэн жагсаалт
#: «Түүх» хуудсанд байгаа тул энэ нь зөвхөн «сая юу бичив?» гэдгийг хэлнэ.
RECENT_ROWS = 5

#: Зүүн цэсний бүлгүүдийн хажуугийн зай. Лого нь цэснүүдтэй нэг оптик
#: шугамд эгнэхийн тулд үүнээс тооцогддог тул тогтмол болгов.
SIDEBAR_PAD = 8

#: Мөрийн текстийг нэг мөрөнд багтаах хязгаар. Tk-ийн `Label` агуулгаа
#: тайрдаггүй — урт бичвэр эцгийгээ тэлж, картыг цонхноос гаргана. Тиймээс
#: тайралтыг өөрсдөө хийнэ.
RECENT_CHARS = 58

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


def unknown_language_codes(mapping: dict[str, str]) -> list[str]:
    """Аппын хэлний хүснэгтээс аппын мэдэхгүй кодуудыг эрэмбэлж буцаана.

    Хэрэглэгч «en» гэж бичвэл (зөв нь «en-US») чимээгүй ажиллахгүй байхаас
    илүү шалтгааныг нь хэлэх нь дээр.
    """
    return sorted({code for code in mapping.values() if code not in CODE_TO_NAME})
NAME_TO_CODE = dict(LANGUAGES)

# «Төлөв» хуудасны хурдан сэлгэх чипүүд — бүтэн жагсаалт нь «Яриа» цэст
QUICK_LANGS = [("Монгол", "mn-MN"), ("English", "en-US")]

NAV = [
    ("waveform", "Төлөв"),
    ("book", "Толь"),
    ("clock", "Түүх"),
    ("file_audio", "Хөрвүүлэх"),
    ("chart", "Хэрэглээ"),
    ("window", "Аппууд"),
]

#: Тохиргооны цонхны зүүн цэс — өдөр бүр биш, тохируулах үедээ л нээгддэг
#: зүйлс бүгд энд төвлөрнө.
SETTINGS_NAV = [
    ("mic", "Яриа"),
    ("write", "Бичилт"),
    ("keyboard", "Товчлуур"),
    ("sliders", "Нэмэлт"),
]

WRITING_TOGGLES = [
    ("type_mode", "Шууд бичих",
     "Clipboard-г үл хөндөнө. Хуучин аппуудад арай хойрго байж болно."),
    ("verbatim_mode", "Үгчлэн бичих",
     "Цэвэрлэгээ, толь, тоо, цэг таслал, дуут үйлдлийг бүгдийг алгасана"),
    ("auto_space", "Зай нэмэх",
     "Өмнөх текстийн дараа шаардлагатай бол зай тавина"),
    ("auto_capitalize", "Том үсгээр эхлүүлэх",
     "Шинэ өгүүлбэрийн эхний үсгийг том болгоно"),
    ("voice_punctuation", "Дуут цэг таслал",
     "«цэг», «таслал», «шинэ мөр» гэж хэлэхэд тэмдэг болгоно"),
    ("auto_period", "Өгүүлбэр бүрд цэг",
     "Завсарлага болгоны төгсгөлд цэг тавина — «цэг» гэж хэлэх шаардлагагүй"),
    ("voice_numbers", "Тоог цифрээр",
     "«хорин гурван цагт» гэж хэлэхэд «23 цагт» гэж бичнэ"),
    ("clean_speech", "Чигчлүүр цэвэрлэх",
     "«ааа», эхний «за», давхардсан үг, «үгүй ээ» гэж зассаныг хасна"),
]
MODE_TOGGLES = [
    ("ptt_enabled", "Push-to-talk горим",
     "Дарж барих. Унтраавал зөвхөн асаах/унтраах товчлуураар ажиллана."),
    ("restore_clipboard", "Clipboard сэргээх",
     "Буулгасны дараа хуучин агуулгыг эгүүлж тавина"),
    ("double_tap_enabled", "Хоёр дарж асаах",
     "Ctrl-ыг хоёр хурдан дарахад бичлэг асна/унтарна (гар байрлалаа алдахгүй)"),
    ("learn_corrections", "Засварыг сурах",
     "Түүх дээр гараар засвал Толь руу автоматаар нэмнэ"),
    ("animations", "Хөдөлгөөнтэй шилжилт",
     "Цэс, унтраалга, товч, Тохиргооны цонх зөөлөн шилжинэ"),
]
HOTKEY_ROWS = [
    ("ptt_key", "Дарж барих", "Дарж байх зуур сонсоно"),
    ("ptt_key_alt", "Хоёр дахь хэл", "Хоёр дахь хэлээр таних"),
    ("hotkey", "Асаах / унтраах", "Нэг дарж эхлүүлж, дахин дарж дуусгана"),
    ("undo_key", "Буцаах", "Хамгийн сүүлийн буулгалтыг цуцлах"),
    ("command_key", "Команд горим",
     "Дарж барин ярихад текст орохгүй — зөвхөн дуут үйлдэл гүйцэтгэнэ"),
    ("variant_key", "Хувилбар сэлгэх",
     "Буруу таньсан бол дахин ярилгүйгээр дараагийн хувилбар руу"),
]
TUNING_ROWS = [
    ("silence_hold", "Завсарлага",
     "Хэдэн секунд дуугүй байвал өгүүлбэр дууссан гэж үзэх",
     0.4, 1.2, 0.1, lambda v: f"{v:.1f} сек"),
    ("min_confidence", "Итгэлцлийн босго",
     "Босгоос доогуур таналтыг буулгахгүй",
     0.0, 0.9, 0.05, lambda v: "Шүүхгүй" if v <= 0 else f"{v * 100:.0f}%"),
    ("language_margin", "Хэл солихын зай",
     "Хоёр хэл ойр оноотой үед үндсэн/сүүлийн хэлээ хадгалах хэмжээ",
     0.0, 0.3, 0.02, lambda v: f"{v:.2f}"),
    ("preroll_seconds", "Товчны өмнөх дуу",
     "Товч дармагц эхэлсэн үг тасрахгүй байх — өмнөх энэ хугацааны дууг залгана",
     0.0, 1.6, 0.2, lambda v: "Болих" if v <= 0 else f"{v:.1f} сек"),
    ("mic_keep_open_seconds", "Микрофон бэлэн барих",
     "Бичлэгийн дараа микрофоныг хэдэн секунд нээлттэй барих",
     0, 300, 15, lambda v: "Болих" if v <= 0 else f"{v:.0f} сек"),
    ("max_recording_seconds", "Бичлэгийн дээд хугацаа",
     "Товч гацсан ч энэ хугацааны дараа бичлэг өөрөө зогсоно",
     30, 600, 30, lambda v: f"{v / 60:.0f} мин" if v >= 60 else f"{v:.0f} сек"),
]

#: «Аппууд» хуудсан дээр «дүрэмгүй» гэдгийг илэрхийлэх сонголт.
DEFAULT_RULE = "Үндсэн"


def _rule_summary(rule: dict) -> str:
    """Нэг аппын дүрмүүдийг богино мөр болгоно."""
    parts = []
    if rule.get("lang"):
        parts.append(CODE_TO_NAME.get(rule["lang"], rule["lang"]))
    if rule.get("type_mode"):
        parts.append("шууд бичих")
    if rule.get("no_clean"):
        parts.append("цэвэрлэхгүй")
    return " · ".join(parts) or "дүрэмгүй"


#: Сэдвийн тохиргооны нэр → цонхонд харагдах нэр.
THEME_NAMES = {"dark": "Харанхуй", "light": "Гэрэлтэй"}
THEME_CODES = {title: code for code, title in THEME_NAMES.items()}

ORB_MODES = {"listening": "listening", "working": "recognizing"}
LEVEL_FULL = 3200.0  # энэ RMS-ийг 100% гэж үзнэ
DICTIONARY_SAVE_MS = 500  # толь засварлахад хүлээх хугацаа


def day_label(stamp: str) -> str:
    """ISO огноог «Өнөөдөр» / «Өчигдөр» / «08-11» болгоно."""
    date = (stamp or "")[:10]
    try:
        day = datetime.date.fromisoformat(date)
    except ValueError:
        return ""
    delta = (datetime.date.today() - day).days
    if delta == 0:
        return "Өнөөдөр"
    if delta == 1:
        return "Өчигдөр"
    return day.strftime("%m-%d")


def _parse_day(key: str) -> datetime.date | None:
    """Статистикийн түлхүүрийг («2026-08-24») огноо болгоно, буруу бол `None`."""
    try:
        return datetime.date.fromisoformat(str(key)[:10])
    except ValueError:
        return None


def _mix_hex(a: str, b: str, k: float) -> str:
    """Хоёр өнгийн хоорондох k (0..1) хувийг холино."""
    first = tuple(int(a[i : i + 2], 16) for i in (1, 3, 5))
    second = tuple(int(b[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(
        f"{round(x + (y - x) * k):02x}" for x, y in zip(first, second, strict=True)
    )


def _streaks(days: dict) -> tuple[int, int]:
    """`(одоогийн тасралт, хамгийн урт тасралт)` — үг бичсэн өдрүүдээр.

    Өнөөдөр хараахан бичээгүй бол тасралт өчигдрөөс үргэлжилж байгаа гэж
    тооцно: өдөржин бичээгүй хүн өөрийн тасралтыг алга болсон гэж бодоход
    хэрэггүй сэтгэл хөдөлгөөн.
    """
    active = {
        day
        for key, value in days.items()
        if int(value or 0) > 0 and (day := _parse_day(key)) is not None
    }
    if not active:
        return 0, 0
    today = datetime.date.today()
    current = 0
    cursor = today if today in active else today - datetime.timedelta(days=1)
    while cursor in active:
        current += 1
        cursor -= datetime.timedelta(days=1)
    longest = best = 0
    previous: datetime.date | None = None
    for day in sorted(active):
        longest = longest + 1 if previous and (day - previous).days == 1 else 1
        best = max(best, longest)
        previous = day
    return current, best


def clip(text: str, limit: int = RECENT_CHARS) -> str:
    """Урт бичвэрийг нэг мөрөнд багтаана."""
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _dark_titlebar(window) -> None:
    """Windows-ийн гарчгийн мөрийг бараан болгоно.

    Дизайны зурсан хиймэл гарчгийн мөрийг давтахгүй — чирэх, наах,
    хэмжээ солих зэрэг зан үйлийг гараар бичих нь Windows апп биш
    болгодог. Оронд нь системийн мөрийг бараан болгоно.
    """
    try:
        import ctypes

        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id()) or window.winfo_id()
        value = ctypes.c_int(1)
        for attribute in (20, 19):  # шинэ ба хуучин Windows 10 бүтээлтүүд
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
    except Exception:  # noqa: BLE001 - гоо сайхны зүйл, апп зогсоохгүй
        pass


class SettingsWindow:
    """Тусдаа нээгддэг Тохиргооны цонх.

    Үндсэн цонхны sidebar-д өдөр бүр хэрэглэгдэх зүйлс л үлдэнэ. Тохиргоо
    нь ховор нээгддэг тул тэдгээрийг үндсэн цэснээс салгаад, товшвол
    дэлгэцэн дээр давхаргарч ирэх тусдаа цонхоор харуулна — Flow-ийн
    settings цонхтой ижил бүтэц: зүүн талд хэсгүүд, баруун талд агуулга.

    Хуудсуудыг ҮНДСЭН цонх нээгдмэгц бүтээд, цонхыг нь нууж байрлуулна:
    `app`-ийн код (`ui.toggles`, `ui.set_level` гэх мэт) ямар ч цагт
    эдгээр виджетүүд рүү хандах боломжтой байх ёстой.
    """

    WIDTH, HEIGHT = 940, 660
    #: Өнцгийн бөөрөнхийн радиус (пиксел).
    CORNER_RADIUS = 14

    def __init__(self, root: tk.Tk, ui) -> None:
        self.root = root
        self.ui = ui
        self.pages: list[Page] = []
        self.nav: list[NavButton] = []
        self.page_index = 0
        # Цонхыг НЭЭЖ буй товшилтыг алгасах далбаа: bind_all-ын хаагч нь
        # виджетийн холбоосын АРААР ажилладаг тул нээгч өөрөө тэмдэглээд,
        # хаагч тэр товшилтыг «гадна товшилт» гэж бүү тоо.
        self._suppress_dismiss = False
        # Аль хэмжээнд бөөрөнхий бүс тавьснаа санана — давхар ажиллахаас
        # сэргийлнэ (<Configure> нь зөөхөд ч дуудагддаг).
        self._region_size: tuple[int, int] = (0, 0)

        self.win = tk.Toplevel(root)
        self.win.title("Тохиргоо — Monspeech")
        # Хүрээгүй popover: системийн гарчиг байхгүй. Хаалт нь 1 px шугам —
        # дэвсгэрийн ялгаа бага үед ч цонхны хил харагдана.
        self.win.overrideredirect(True)
        # Хүрээ нь ЭНГИЙН биш тод өнгөтэй: систем гарчиг зурдаггүй тул цонхны
        # хил бол цорын ганц зааг. Бүдэг дэвсгэртэй хамт самбарыг ард талаасаа
        # бүрэн салгана.
        self.win.configure(
            bg=theme.BG,
            highlightthickness=1,
            highlightbackground=theme.BORDER_STRONG,
            highlightcolor=theme.BORDER_STRONG,
        )
        self.win.geometry(f"{self.WIDTH}x{self.HEIGHT}")
        self.win.minsize(720, 520)
        # transient: үндсэн цонхны «эзэмшигчтэй» цонх — үндсэнхийн дээр
        # үлдэнэ, taskbar-д тусдаа мөр гарахгүй.
        self.win.transient(root)
        self.win.withdraw()
        self.win.protocol("WM_DELETE_WINDOW", self.hide)
        self.win.bind("<Escape>", lambda _e: self.hide())
        self.win.bind("<Configure>", self._apply_round_corners, add="+")
        # Гадна нэг товшиход шууд хаагдана — popover-ийн гол зан үйл.
        self.win.bind_all("<Button-1>", self._global_press, add="+")

        # Бүдэг дэвсгэр. Tk-д нэг цонхны зарим хэсгийг бүдгэрүүлэх арга
        # байхгүй тул үндсэн цонхыг яг таглах тунгалаг Toplevel үүсгэнэ:
        # самбар нь ард талаасаа тодорхой салж, анхаарал түүн дээр төвлөрнө.
        # Дээр нь товшвол хаагдана — popover-ийн хүлээгдсэн зан үйл.
        self.scrim = tk.Toplevel(root)
        self.scrim.overrideredirect(True)
        self.scrim.configure(bg=theme.SCRIM)
        self.scrim.attributes("-alpha", theme.SCRIM_ALPHA)
        self.scrim.withdraw()
        self.scrim.bind("<Button-1>", lambda _e: self.hide())

        shell = tk.Frame(self.win, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        self._build_sidebar(shell)
        self.stack = tk.Frame(shell, bg=theme.BG)
        self.stack.pack(side="left", fill="both", expand=True)

    def _apply_round_corners(self, _event=None) -> None:
        """Цонхны 4 өнцгийг бөөрөнхийлнө (Win32 цонхны бүс).

        Tk-ийн цонх үргэлж дөрвөлжин байдаг тул Windows-ийн
        `SetWindowRgn`-ээр бөөрөнхий бүс тавина — бүст хамтрагдаагүй
        өнцгийн хэсэгт цонхны ард буй зүйл шууд харагдана. Хэмжээ
        солигдох бүрд бүсийг дахин тавина (нарийсч томсоход чөлөөтэй).
        """
        try:
            import ctypes

            width, height = self.win.winfo_width(), self.win.winfo_height()
            if width < 10 or height < 10 or (width, height) == self._region_size:
                return
            self._region_size = (width, height)
            user32 = ctypes.windll.user32
            hwnd = user32.GetParent(self.win.winfo_id()) or self.win.winfo_id()
            radius = self.CORNER_RADIUS
            region = ctypes.windll.gdi32.CreateRoundRectRgn(
                0, 0, width + 1, height + 1, radius, radius
            )
            if region:
                # Бүсийг системд өглөө — цаашид систем өөрөө эзэмшинэ.
                user32.SetWindowRgn(hwnd, region, True)
        except Exception:  # noqa: BLE001 - гоо сайхны зүйл, апп зогсоохгүй
            pass

    @property
    def visible(self) -> bool:
        try:
            return bool(self.win.winfo_viewable())
        except tk.TclError:
            return False

    def _global_press(self, event) -> None:
        """Цонхны ГАДНА хийсэн товшилт — шууд нууна.

        Доторх товшилт (хүүхэд виджет, combobox-ын унадаг жагсаалт гэх
        мэт) цонхны хүүхэд замд багтдаг тул тэдгээрийг ялгаж хөндөхгүй.
        """
        if self._suppress_dismiss:
            self._suppress_dismiss = False
            return
        if not self.visible:
            return
        try:
            top = event.widget.winfo_toplevel()
        except tk.TclError:
            return
        if top is self.win or str(top).startswith(str(self.win) + "."):
            return
        # Тохиргоо товч дээрх товшилт — тэр нь нээх/хаах хоёуланг
        # өөрөө удирддаг тул энд хөндөхгүй.
        widget = event.widget
        while widget is not None:
            if widget is self.ui.settings_button:
                return
            widget = getattr(widget, "master", None)
        self.hide()

    def _build_sidebar(self, parent) -> None:
        bar = tk.Frame(parent, bg=theme.SIDEBAR, width=200)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self.sidebar = bar
        tk.Frame(parent, bg=theme.BORDER, width=1).pack(side="left", fill="y")

        tk.Label(
            bar, text="ТОХИРГОО", bg=theme.SIDEBAR, fg=theme.DIM,
            font=theme.UI_LABEL, anchor="w",
        ).pack(fill="x", padx=18, pady=(16, 8))

        self.menu = tk.Frame(bar, bg=theme.SIDEBAR)
        self.menu.pack(fill="both", expand=True, padx=SIDEBAR_PAD)
        for index, (icon, label) in enumerate(SETTINGS_NAV):
            button = NavButton(self.menu, icon, label, lambda i=index: self.select(i))
            button.pack(fill="x", pady=theme.NAV_GAP)
            self.nav.append(button)

    def select(self, index: int) -> None:
        """Тохиргооны хэсэг сэлгэнэ. Хуудас бүр гүйлгэлтээ эхнээсээ нээнэ."""
        if not self.pages:
            return
        index = max(0, min(len(self.pages) - 1, index))
        self.page_index = index
        for position, page in enumerate(self.pages):
            if position == index:
                page.pack(fill="both", expand=True)
                page.to_top()
            else:
                page.pack_forget()
            self.nav[position].set_active(position == index)

    def show(self, section: int | None = None) -> None:
        """Цонхыг үндсэнхийн голд нь давхарган гаргана. Хэсэг заавал биш."""
        if section is not None:
            self.select(section)
        try:
            # Үндсэн цонхны байрлалыг УНШИХААС өмнө хүлээгдэж буй
            # байрлуулалтыг гүйцээнэ — эс бөгөөс анх нээхэд координат нь
            # хараахан тогтоогүй байж, самбар дэлгэцийн буланд гарч ирнэ.
            self.root.update_idletasks()
            self._cover()
            # Байрлалыг ГАРГАХААС ӨМНӨ тогтооно: эхлээд буланд гараад дараа
            # нь голдоо үсрэх нь тод харагддаг.
            self._centre()
            if self.win.state() == "iconic":
                self.win.state("normal")
            # Тунгалагаас эхэлнэ — `deiconify` нь цонхыг бүтнээр нь тэр дор
            # нь гаргадаг тул уусалт эхлэхээс ӨМНӨ 0 болгож тавина.
            self.win.attributes("-alpha", 0.0)
            self.win.deiconify()
            self.win.lift()
            self.win.focus_force()
            animate.fade_window(self.win, 1.0)
        except tk.TclError:  # цонх хаагдаж байх агшин таарч болно
            pass

    def _cover(self) -> None:
        """Бүдэг дэвсгэрийг үндсэн цонхны яг дээр тавина."""
        try:
            if not self.root.winfo_viewable():
                return
            self.scrim.geometry(
                f"{self.root.winfo_width()}x{self.root.winfo_height()}"
                f"+{self.root.winfo_rootx()}+{self.root.winfo_rooty()}"
            )
            self.scrim.attributes("-alpha", 0.0)
            self.scrim.deiconify()
            self.scrim.lift()
            animate.fade_window(self.scrim, theme.SCRIM_ALPHA)
        except tk.TclError:
            pass

    def _centre(self) -> None:
        """Үндсэн цонхны төвд байрлуулна — dialog гэдгээ байрлалаараа хэлнэ.

        `winfo_rootx/rooty` нь ДЭЛГЭЦИЙН координат; `winfo_x/y` нь эцэг
        цонхтойгоо харьцангуй бөгөөд Windows дээр цонхны хүрээнээс тоологддог
        тул самбар дээш, зүүн тийш шилжиж байв. Хэмжээ, байрлал хоёрыг НЭГ
        `geometry` дуудлагад өгнө — тусад нь өгвөл Tk хооронд нь дахин зурна.
        """
        try:
            x = self.root.winfo_rootx() + max(0, (self.root.winfo_width() - self.WIDTH) // 2)
            y = self.root.winfo_rooty() + max(0, (self.root.winfo_height() - self.HEIGHT) // 3)
            self.win.geometry(f"{self.WIDTH}x{self.HEIGHT}+{x}+{y}")
        except tk.TclError:
            pass

    def hide(self) -> None:
        """Цонхыг нууна. Виджетүүдээ хадгална — дахин нээхэд шууд гарна."""
        # Програмын кодоор хаагдав — нээж буй товшилтыг хүлээж буй далбаа
        # хоцрох ёсгүй, эс тэгвэл дараагийн жинхэнэ товшилтыг алгасана.
        self._suppress_dismiss = False
        try:
            if not animate.enabled:
                self.win.withdraw()
                self.scrim.withdraw()
                return
            # Уусаж дуусмагц нуух — `withdraw` шууд дуудвал уусалт харагдахгүй.
            animate.fade_window(self.win, 0.0, on_done=self._hidden)
            animate.fade_window(self.scrim, 0.0, on_done=self.scrim.withdraw)
        except tk.TclError:
            pass

    def _hidden(self) -> None:
        try:
            self.win.withdraw()
        except tk.TclError:
            pass


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
        self._dictionary_pending: dict | None = None

        self._build()

    # ------------------------------------------------------------------
    # Бүтэц
    # ------------------------------------------------------------------
    def _build(self) -> None:
        root = self.root
        root.configure(bg=theme.BG)
        root.geometry("{}x{}".format(*theme.WINDOW))
        root.minsize(*theme.WINDOW_MIN)

        _dark_titlebar(root)
        self._style()

        shell = tk.Frame(root, bg=theme.BG)
        shell.pack(fill="both", expand=True)
        self._build_sidebar(shell)
        self._build_main(shell)

        # Тохиргооны цонх: нуугдсан байдлаар УРТААС нь бүтээнэ — app-ийн код
        # (toggles, sliders, keycaps) ямар ч цагт виджетүүд рүү хандах ёстой.
        self.settings = SettingsWindow(root, self)
        self._page_speech()
        self._page_writing()
        self._page_hotkeys()
        self._page_advanced()
        self.settings.select(0)
        # Яриа хуудасны хэрэглээний мөр хоосон «—»-ээр бүү үлдээ
        self.refresh_stats()

        self.root.bind("<Configure>", self._window_resized)
        self._bind_keys()
        self.select(0)
        self.refresh_hotkeys()

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
    #: Аппын лого — sidebar-ын толгой. Хуучирсан хэмжээгээр хоёр удаа
    #: уншихгүйн тулд кэшлэнэ.
    LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "monspeech.png"

    def _logo_image(self, width: int):
        """Логог өгсөн өргөнд (дугуй хэлбэртэй тул өндөр = өргөн) буцаана."""
        try:
            from PIL import Image, ImageTk

            image = Image.open(self.LOGO_PATH).convert("RGBA")
            return ImageTk.PhotoImage(
                image.resize((width, width), Image.LANCZOS), master=self.root
            )
        except (OSError, ImportError):  # лого байхгүй ч апп ажиллана
            return None

    def _place_logo(self) -> None:
        """Логог одоогийн (дэлгэсэн/хумисан) байдалд тохируулж байрлуулна.

        Дэлгэсэн үед цэсний ДҮРСНИЙ баганад эгнэнэ: `menu`-гийн хажуугийн зай
        + `NavButton`-ий доторх зай. Тоог гараар бичихгүй — `INDENT` өөрчлөгдвөл
        лого өөрөө дагаж шилжинэ.
        """
        if self.collapsed:
            # Хумигдсан цэсэнд нэр багтахгүй — тэмдэг ганцаараа голлоно.
            self.wordmark.pack_forget()
            inset = max(0, (theme.SIDEBAR_COLLAPSED - theme.LOGO_COLLAPSED) // 2)
        else:
            self.wordmark.pack(side="left", padx=(theme.SPACE_MD, 0))
            inset = SIDEBAR_PAD + NavButton.INDENT
        self.brand.pack_forget()
        self.brand.pack(anchor="w", padx=(inset, 0), pady=(theme.SPACE_LG, theme.SPACE_MD))

    def _build_sidebar(self, parent) -> None:
        bar = tk.Frame(parent, bg=theme.SIDEBAR, width=theme.SIDEBAR_WIDTH)
        bar.pack(side="left", fill="y")
        bar.pack_propagate(False)
        self.sidebar = bar
        tk.Frame(parent, bg=theme.BORDER, width=1).pack(side="left", fill="y")

        # Аппын толгой: тэмдэг + нэр. Дүрсний баганад эгнэнэ (доорх
        # цэснүүдтэй нэг оптик шугам) тул толгой нь өөрөө «энэ бол цэсний
        # эхлэл» гэдгийг хэлнэ. Хумигдсан үед нэр нь хураагдаж, тэмдэг
        # жижгэрч голлоно.
        self._logo_large = self._logo_image(theme.LOGO_SIZE)
        self._logo_small = self._logo_image(theme.LOGO_COLLAPSED)
        self.brand = tk.Frame(bar, bg=theme.SIDEBAR)
        # Лого уншигдаагүй байсан ч нэр нь үлдэнэ — толгой хоосрохгүй.
        self.logo = tk.Label(self.brand, bg=theme.SIDEBAR, image=self._logo_large)
        if self._logo_large is not None:
            self.logo.pack(side="left")
        self.wordmark = tk.Label(
            self.brand, text="Monspeech", bg=theme.SIDEBAR, fg=theme.TEXT,
            font=theme.LOGO_TEXT, anchor="w",
        )
        self._place_logo()

        # Байрлалын дараалал: лого → үндсэн цэс (үлдсэн бүх зай) →
        # Тохиргоо/Тусламжийн бүлэг → төлөв/хумих мөр. Доод хоёр нь
        # menu-гийн АРААР багцлагдсанаар доод захад наалдана.
        self.menu = tk.Frame(bar, bg=theme.SIDEBAR)
        self.menu.pack(fill="both", expand=True, padx=SIDEBAR_PAD)

        self.utility = tk.Frame(bar, bg=theme.SIDEBAR)
        self.utility.pack(fill="x", padx=SIDEBAR_PAD, pady=(3, 2))
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

        # Цэсүүд: үндсэн хуудсууд голд, Тохиргоо ба Тусламж доод бүлэгт.
        # `self.nav`-ийн дараалал ХУУДАСНЫ дараалалтай яг таарч байх ёстой —
        # `select()` болон Ctrl+1…6 түүнээс хамаарна.
        for index, (icon, label) in enumerate(NAV):
            button = NavButton(self.menu, icon, label, lambda i=index: self.select(i))
            button.pack(fill="x", pady=theme.NAV_GAP)
            self.nav.append(button)

        # Тохиргоо — хуудас сонгох биш, ТУСДАА ЦОНХ нээх үйлдэл тул
        # `self.nav`-д орохгүй. Шинэчлэлийн тэмдэг энд гардаг.
        self.settings_button = NavButton(self.utility, "gear", "Тохиргоо", self.open_settings)
        self.settings_button.pack(fill="x", pady=theme.NAV_GAP)

        # Тусламж — мөн шууд үйлдэл.
        self.help_button = NavButton(
            self.utility, "report", "Алдаа мэдээлэх", self._copy_diagnostics
        )
        self.help_button.pack(fill="x", pady=(theme.NAV_GAP, 2))

    def _window_resized(self, event) -> None:
        """Дизайны дагуу хамгийн бага хэмжээнд цэс өөрөө дүрс болж хумигдана."""
        if event.widget is not self.root:
            return
        if (
            event.width < theme.SIDEBAR_COLLAPSE_AT and not self.collapsed
        ) or (
            event.width >= theme.SIDEBAR_EXPAND_AT and self.collapsed
        ):
            self.toggle_sidebar()

    def toggle_sidebar(self) -> None:
        """Нарийсгах — дэлгэц бага үед эсвэл цэсний нэр хэрэггүй болсон үед.

        Хумихдаа шошгыг нуухаас гадна цэсийг өөрийг нь давчуу болгоно: 58 px
        нь дүрс + идэвхтэйн зураас багтах хамгийн бага өргөн. Хэрэглээний
        карт нь текстээ ганцаараа тайлбарладаг тул хумигдсан үед огт саад
        болохгүйн тулд бүтнээрөө нуугдана.
        """
        self.collapsed = not self.collapsed
        self.sidebar.configure(
            width=theme.SIDEBAR_COLLAPSED if self.collapsed else theme.SIDEBAR_WIDTH
        )
        for button in self.nav:
            button.set_compact(self.collapsed)
        self.settings_button.set_compact(self.collapsed)
        self.help_button.set_compact(self.collapsed)
        if self._logo_large is not None:
            self.logo.configure(
                image=self._logo_small if self.collapsed else self._logo_large
            )
        self._place_logo()
        if self.collapsed:
            self.state_label.pack_forget()
        else:
            self.state_label.pack(side="left", padx=7)
        self.collapse_button.configure(
            image=icons.get(
                "chevron" if not self.collapsed else "chevron_right", theme.MUTED, 11, theme.SIDEBAR
            )
        )

    # ------------------------------------------------------------------
    # Хуудсууд
    # ------------------------------------------------------------------
    def _build_main(self, parent) -> None:
        main = tk.Frame(parent, bg=theme.BG)
        main.pack(side="left", fill="both", expand=True)

        self.stack = tk.Frame(main, bg=theme.BG)
        self.stack.pack(fill="both", expand=True)

        tk.Frame(main, bg=theme.BORDER, height=1).pack(fill="x")
        status = tk.Frame(main, bg=theme.SIDEBAR, height=30)
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
        self._page_dictionary()
        self._page_history()
        self._page_file()
        self._page_usage()
        self._page_apps()

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

    def open_settings(self, section: int | None = None) -> None:
        """Тохиргооны цонхыг нээнэ. Нээлттэй үед товчоор нь хаана (toggle).

        Хэсэг заасан үед (хайлт, танилцуулгаас) хаахгүй — заасан хэсэг
        рүүг нь аваачина. Шинэчлэлийн тэмдгийг нээх бүрд арилгана.
        """
        self.settings_button.set_badge(False)
        if section is None and self.settings.visible:
            self.settings.hide()
            return
        # Энэ товшилтоор цонх нээгдэж байна — гадна товшилт гэж бүү тоо
        self.settings._suppress_dismiss = True
        self.settings.show(section)

    def hide_settings(self) -> None:
        """Тохиргооны цонхыг нууна (үндсэн цонх tray руу оход)."""
        self.settings.hide()

    def _bind_keys(self) -> None:
        # Цонхны түвшинд холбоно. Tk-ийн `Entry` класс нь Ctrl+товчлуурт
        # ерөнхий холбоостой ч тэр нь эдгээрийг залгидаггүй — курсор хайлт,
        # түлхүүрийн талбарт байхад ч навигац ажиллана (тестээр баталсан).
        for number in range(1, len(NAV) + 1):
            self.root.bind(f"<Control-Key-{number}>", lambda _e, n=number: self.select(n - 1))

    def _add_page(self, page: Page) -> Page:
        self.pages.append(page)
        return page

    def _add_settings_page(self, page: Page) -> Page:
        """Хуудсыг Тохиргооны цонхны жагсаалтад бүртгэнэ."""
        self.settings.pages.append(page)
        return page

    # --- Төлөв ---------------------------------------------------
    def _page_status(self) -> None:
        page = self._add_page(
            Page(self.stack, "Төлөв", aside=f"{pretty(self.app.cfg['ptt_key'])} дарж барин ярь")
        )

        self._welcome_card(page)
        hero = Card(page.body)
        inner = tk.Frame(hero.body, bg=theme.PANEL)
        inner.pack(pady=(theme.SPACE_SM, theme.SPACE_MD))
        self.orb = RobotOrb(inner, width=240)
        self.orb.pack()

        # Төлөвийн капсул. Радиус нь өндрийн хагас тул `pad` хэвтээ чиглэлд том.
        # Өнгө нь төлөв бүрд солигдоно — `_paint_pill` үзнэ үү.
        self.pill = RoundedBox(
            inner, fill=theme.OK_SOFT, outside=theme.PANEL, radius=16,
            border=None, pad=(16, 2),
        )
        self.pill.pack(pady=(theme.SPACE_SM, 0))
        self.pill_dot = tk.Canvas(
            self.pill.inner, width=9, height=9, bg=theme.OK_SOFT, highlightthickness=0
        )
        self.pill_dot.pack(side="left", pady=6)
        self._pill_dot_id = self.pill_dot.create_oval(0, 0, 8, 8, fill=theme.OK, outline="")
        # Одоо ямар өнгөтэй байгааг санана — дараагийн төлөв рүү ЭНДЭЭС уусна.
        self._pill_colours = (theme.OK_SOFT, theme.OK)
        self._pill_fade = animate.Motion(self.pill, lambda _v: None)
        self.title_var = tk.StringVar(value="Бэлэн")
        self.pill_label = tk.Label(
            self.pill.inner, textvariable=self.title_var, bg=theme.OK_SOFT, fg=theme.OK,
            font=theme.UI_TITLE,
        )
        self.pill_label.pack(side="left", padx=(9, 2))

        self.default_hint = (
            f"Дурын цонхон дээр {pretty(self.app.cfg['ptt_key'])} дарж барин ярь — "
            "курсор байгаа газарт шууд шивэгдэнэ."
        )
        self.hint_var = tk.StringVar(value=self.default_hint)
        tk.Label(
            inner, textvariable=self.hint_var, bg=theme.PANEL, fg=theme.MUTED,
            font=theme.UI_SMALL, justify="center", wraplength=340,
        ).pack(pady=(theme.SPACE_MD, 0))

        actions = tk.Frame(inner, bg=theme.PANEL)
        actions.pack(pady=(theme.SPACE_LG, 0))
        # Хуудасны цорын ганц дүүргэсэн товч — нүд эндээс эхэлнэ.
        self.action_button = Button(actions, "Эхлүүлэх", self.app.toggle, primary=True)
        self.action_button.pack(side="left")

        # Чипүүд өөрсдөө юу болохоо хэлэхгүй тул шошготой нэг эгнээнд.
        # Тусад нь мөр болгоход хуудас уртсаж, доорх түүх нүднээс гардаг.
        chips = tk.Frame(inner, bg=theme.PANEL)
        chips.pack(pady=(theme.SPACE_MD, 0))
        tk.Label(
            chips, text="Ярих хэл", bg=theme.PANEL, fg=theme.DIM, font=theme.UI_SMALL,
        ).pack(side="left", padx=(0, theme.SPACE_SM))
        for name, code in QUICK_LANGS:
            chip = RoundedLabel(
                chips, 14, theme.PANEL, theme.PANEL, theme.BORDER,
                text=name, fg=theme.MUTED, font=theme.UI_NAV,
                padx=14, pady=5, cursor="hand2",
            )
            chip.pack(side="left", padx=3)
            chip.bind("<Button-1>", lambda _e, c=code: self._quick_lang(c))
            self.lang_chips[code] = chip
        self._paint_lang_chips()

        # Сүүлийн бичвэрүүд роботын ЯГ ДООР — хэрэглэгч ярьсныхаа дараа
        # хамгийн түрүүнд «юу орсон бэ?» гэдгийг хардаг. Тоон хураангуй нь
        # «Хэрэглээ» хуудсанд бүтэн хуудас болов.
        self._recent_card(page)
        page.spacer()
        self.refresh_stats()

    def _recent_card(self, page) -> None:
        """Сүүлийн бичвэрүүдийн жагсаалт — өдрөөр бүлэглэсэн мөрүүд."""
        holder = RoundedBox(
            page.body, fill=theme.PANEL, outside=theme.BG, pad=(theme.RADIUS, 0)
        )
        holder.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        self.recent_rows: list[tk.Frame] = []
        self.recent_body = tk.Frame(holder.inner, bg=theme.PANEL)
        self.recent_body.pack(fill="x")
        self._fill_recent()

    def _fill_recent(self) -> None:
        body = getattr(self, "recent_body", None)
        if body is None or not body.winfo_exists():
            return
        for child in body.winfo_children():
            child.destroy()

        self.recent_rows = []
        refit(body)  # мөрийн тоо солигдоход хуудасны өндөр дагана
        entries = self.app.transcripts.search("")[:RECENT_ROWS]
        if not entries:
            self._recent_empty(body)
            return

        day = None
        for index, entry in enumerate(entries):
            label = day_label(entry.get("at", ""))
            if index:
                tk.Frame(body, bg=theme.ROW_LINE, height=1).pack(fill="x")
            if label != day:
                day = label
                self._recent_header(body, label, first=index == 0)
            self._recent_row(body, entry)
        tk.Frame(body, bg=theme.PANEL, height=theme.SPACE_SM).pack(fill="x")

    def _recent_empty(self, body) -> None:
        tk.Label(
            body,
            text="Одоо хүртэл юу ч бичээгүй байна. Дээрх товчийг дараад ярьж үз.",
            bg=theme.PANEL, fg=theme.DIM, font=theme.UI_SMALL, anchor="w",
        ).pack(fill="x", padx=theme.CARD_PAD_X, pady=theme.SPACE_LG)

    def _recent_header(self, body, text: str, first: bool) -> None:
        head = tk.Frame(body, bg=theme.PANEL)
        head.pack(fill="x", pady=(theme.SPACE_MD if first else theme.SPACE_LG, 0))
        tk.Label(
            head, text=text.upper(), bg=theme.PANEL, fg=theme.DIM, font=theme.UI_LABEL,
        ).pack(side="left", padx=(theme.CARD_PAD_X, 0))
        if first:
            Link(
                head, "Бүгдийг үзэх", lambda: self.select(2), bg=theme.PANEL
            ).pack(side="right", padx=(0, theme.CARD_PAD_X))

    def _recent_row(self, body, entry: dict) -> None:
        """Нэг мөр: цаг · бичвэр · (хулгана хүрэхэд) үйлдлүүд."""
        row = tk.Frame(body, bg=theme.PANEL, takefocus=True)
        row.pack(fill="x")
        self.recent_rows.append(row)

        stamp = tk.Label(
            row, text=(entry.get("at", "") or "")[11:16], bg=theme.PANEL,
            fg=theme.DIM, font=theme.UI_SMALL, width=6, anchor="w",
        )
        stamp.pack(side="left", padx=(theme.CARD_PAD_X, theme.SPACE_SM), pady=theme.SPACE_SM)

        # Үйлдлүүдийг эхлээд баруун талд байрлуулна — үлдсэн зайг бичвэр авна
        actions = tk.Frame(row, bg=theme.PANEL)
        actions.pack(side="right", padx=(theme.SPACE_SM, theme.CARD_PAD_X))
        icons_shown = [
            self._recent_action(actions, name, tip, command)
            for name, tip, command in (
                ("play", "Дахин буулгах", lambda: self._repaste_entry(entry)),
                ("copy", "Хуулах", lambda: self._copy_entry(entry)),
                ("pencil", "Засах — апп ялгааг нь сурна", lambda: self._edit_entry(entry)),
            )
        ]

        text = tk.Label(
            row, text=clip(entry.get("text", "")), bg=theme.PANEL, fg=theme.TEXT,
            font=theme.UI, anchor="w", justify="left",
        )
        text.pack(side="left", fill="x", expand=True)

        state = {"hover": False, "focus": False}

        def paint(hover: bool | None = None, focus: bool | None = None) -> None:
            if hover is not None:
                state["hover"] = hover
            if focus is not None:
                state["focus"] = focus
            active = state["hover"] or state["focus"]
            bg = theme.HOVER if active else theme.PANEL
            for widget in (row, stamp, text, actions):
                widget.configure(bg=bg)
            for show in icons_shown:
                show(active, bg)

        hover_group(row, lambda active: paint(hover=active))
        # Хулганагүйгээр ч хүрэхийн тулд: мөр өөрөө фокус авч, Enter дарахад
        # дахин буулгана — «Түүх» хуудасны давхар товшилттой ижил үйлдэл.
        focusable(
            row, lambda _e: self._repaste_entry(entry),
            paint=lambda focused: paint(focus=focused),
        )
        for widget in (row, stamp, text):
            widget.bind("<Double-Button-1>", lambda _e: self._repaste_entry(entry))

    def _recent_action(self, parent, name: str, tooltip: str, command):
        """Дүрст товч. Хулгана мөр дээр ирэх хүртэл үл үзэгдэнэ.

        Нуухдаа `pack_forget` ХИЙХГҮЙ: тэгвэл бичвэрийн өргөн мөр бүрд
        үсэрч, жагсаалт «чичирнэ». Оронд нь дүрсийг дэвсгэртэйгээ ижил
        өнгөөр зурна — байрлал нь хэвээр.
        """
        widget = tk.Label(parent, bd=0, highlightthickness=0, bg=theme.PANEL, cursor="hand2")
        widget.pack(side="left", padx=3)
        state = {"shown": False, "hot": False, "bg": theme.PANEL}

        def draw() -> None:
            if state["hot"]:
                colour = theme.TEXT
            elif state["shown"]:
                colour = theme.MUTED
            else:
                colour = state["bg"]
            widget.configure(image=icons.get(name, colour, 16, state["bg"]), bg=state["bg"])

        def show(shown: bool, bg: str) -> None:
            state["shown"], state["bg"] = shown, bg
            if not shown:
                state["hot"] = False
            draw()

        def hot(value: bool) -> None:
            state["hot"] = value
            draw()

        widget.bind("<Enter>", lambda _e: hot(True), add="+")
        widget.bind("<Leave>", lambda _e: hot(False), add="+")
        widget.bind("<Button-1>", lambda _e: command())
        # Дүрс дээр бичиг байхгүй тул зорилгыг нь доод мөрөнд хэлж өгнө
        widget.bind("<Enter>", lambda _e: self.set_detail(tooltip), add="+")
        draw()
        return show

    def _repaste_entry(self, entry: dict) -> None:
        self.app.repaste(entry.get("text", ""))

    def _copy_entry(self, entry: dict) -> None:
        self.app.copy_text(entry.get("text", ""))

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

        # Эхнийх нь үргэлж «Системийн үндсэн» тул жинхэнэ төхөөрөмж
        # илэрсэн эсэхийг үлдсэнээр нь мэднэ.
        found = len(self.app.microphones()) - 1
        _, holder = card.row(
            "1. Микрофон",
            f"{found} төхөөрөмж илэрлээ" if found else "Төхөөрөмж илрээгүй — залгаад шалгана уу",
        )
        Button(holder, "Сонгох", lambda: self.open_settings(0)).pack()

        _, holder = card.row(
            "2. Ярих хэл",
            f"Одоо: {CODE_TO_NAME.get(self.app.cfg['lang'], self.app.cfg['lang'])}",
        )
        Button(holder, "Солих", lambda: self.open_settings(0)).pack()

        combo = pretty(self.app.cfg["ptt_key"])
        card.row(
            f"3. {combo} дарж бариад ярь",
            "Курсороо текст бичих цонхон дээр тавиад тушаа — товчоо тавимагц шивэгдэнэ",
        )

        # Дугаарлаагүй: гурван алхмын дараах нэмэлт мэдээлэл. Хэрэглэгч анхны
        # танигчийн хязгаарыг ЭНД мэдэж байвал тасалдах өдөр гайхахгүй.
        _, holder = card.row("Танигч", "Анхныхаа нийтлэг түлхүүр — хааяа тасалдана")
        Button(holder, "Үзэх", lambda: self.open_settings(0)).pack()

        _, holder = card.row("Аппын цонх хэрэггүй", "Хаавал цагны хажууд үлдэнэ")
        Button(holder, "Ойлголоо", self._finish_welcome).pack()

    def _finish_welcome(self) -> None:
        self.app.finish_onboarding()
        if self.welcome is not None:
            parent = self.welcome.master
            self.welcome.destroy()
            self.welcome = None
            refit(parent)
        self.set_detail("Амжилттай! Дахиад хэрэгтэй бол README-г үзнэ үү.")

    def _quick_lang(self, code: str) -> None:
        self.app.on_lang_changed(code)
        self.lang_var.set(CODE_TO_NAME.get(code, code))
        self._paint_lang_chips()

    def _paint_lang_chips(self) -> None:
        """Сонгосныг акцентаар ДҮҮРГЭХГҮЙ — `SegmentedTabs`-тай нэг зарчим.

        Дүүргэсэн акцент нь «үндсэн үйлдэл» гэсэн утга агуулдаг ба хуудсанд
        аль хэдийн «Эхлүүлэх» гэсэн нэг тийм товч байна. Мөн энэ сэдвийн акцент
        цайвар тул түүн дээрх цайвар бичиг 2.7:1 болж уншигдахгүй. Хүрээ,
        дэвсгэрийн шат, бичгийн тодрол гурав ялгахад хангалттай.
        """
        current = self.app.cfg["lang"]
        for code, chip in self.lang_chips.items():
            active = code == current
            chip.restyle(
                fill=theme.PANEL2 if active else theme.PANEL,
                border=theme.ACCENT if active else theme.BORDER,
                fg=theme.TEXT if active else theme.MUTED,
            )

    # --- Тохиргоо · Яриа --------------------------------------------
    def _page_speech(self) -> None:
        page = self._add_settings_page(
            Page(
                self.settings.stack, "Яриа",
                "Ямар хэлээр танихыг, аль микрофоноор сонсохыг тохируулна.",
            )
        )
        card = Card(page.body)

        _, holder = card.row("Үндсэн хэл", "Товчлуур дарахад энэ хэлээр танина")
        self.lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang"], LANGUAGES[0][0])
        )
        combo(holder, self.lang_var, [n for n, _ in LANGUAGES], self._lang_changed)

        _, holder = card.row(
            "Хоёр дахь хэл",
            f"{pretty(self.app.cfg['ptt_key_alt'])} дарахад энэ хэл рүү сэлгэнэ",
        )
        self.alt_lang_var = tk.StringVar(
            value=CODE_TO_NAME.get(self.app.cfg["lang_alt"], LANGUAGES[1][0])
        )
        combo(
            holder, self.alt_lang_var, [n for n, _ in LANGUAGES],
            lambda: self.app.on_alt_lang_changed(NAME_TO_CODE[self.alt_lang_var.get()]),
        )

        _, holder = card.row(
            "Микрофон",
            "Системийн үндсэн төхөөрөмжийг дагана. «Чанга яригч …» сонговол "
            "микрофон биш, компьютерийн тоглуулж буй дууг бичнэ (хурал, видео).",
        )
        self.mics = self.app.microphones()
        self.mic_var = tk.StringVar(value=self._current_mic_label())
        combo(holder, self.mic_var, [mic.label for mic in self.mics], self._mic_changed)

        _, holder = card.row("Оролтын түвшин", "Ярихад баганууд хөдөлж байвал зөв")
        self.meter = LevelMeter(holder)
        self.meter.pack(side="left")
        self.level_var = tk.StringVar(value="0%")
        tk.Label(
            holder, textvariable=self.level_var, bg=theme.PANEL, fg=theme.MUTED,
            font=theme.MONO_KEY, width=5, anchor="e",
        ).pack(side="left", padx=(9, 0))

        _, holder = card.row(
            "Хэл автоматаар таних", "Үндсэн товчоор Монгол + English-ийг өөрөө сонгоно"
        )
        self._toggle(holder, "detect_language")

        _, holder = card.row(
            "Хамгийн зөв таних",
            "Хоёр хэлийг зэрэг танина — хүсэлт хоёр дахин нэмэгдэнэ",
        )
        self._toggle(holder, "language_accuracy_mode")

        _, holder = card.row(
            "Долгион харуулах", "Курсорын доорх капсул дээр 9 багана"
        )
        self._toggle(holder, "wave_overlay")

        _, holder = card.row(
            "Чимээ дарах",
            "Илгээхийн өмнө сэнс, кондиционер, гудамжны шуугианыг сулруулна",
        )
        self._toggle(holder, "noise_suppression")

        _, holder = card.row(
            "Ярианы илрүүлэгч",
            "Өгүүлбэрийн хилийг дууны түвшингээр биш, ярианы шинжээр тогтооно "
            "— аяархан хэлсэн сүүлийн үе тайрагдахгүй",
        )
        self._toggle(holder, "vad")

        _, holder = card.row(
            "Хэцүү жишээ хадгалах",
            "Танигдаагүй, итгэлцэл багатай, эсвэл өөрөө зассан таналтын ДУУГ "
            "диск дээр үлдээнэ — сайжруулалтыг хэмжих benchmark сан болно",
        )
        self._toggle(holder, "save_hard_audio")

        self.samples_var = tk.StringVar(value="—")
        _, holder = card.row("Хадгалсан жишээ", self.samples_var)
        Button(holder, "Цэвэрлэх", self._clear_samples).pack()

        _, holder = card.row(
            "Толиор дохио өгөх",
            "Нэрс ба толио танигчид урьдчилан хэлнэ — эхнээсээ зөв гарна "
            "(зөвхөн OpenAI-нийцтэй танигч дэмжинэ)",
        )
        self._toggle(holder, "vocabulary_boost")

        self.usage_var = tk.StringVar(value="—")
        _, holder = card.row("Хэрэглээ", self.usage_var)
        Button(holder, "Шинэчлэх", self.refresh_stats).pack()

        self.stt = SttCard(page, self.app.cfg, self.app.on_stt_changed)

    def _theme_changed(self) -> None:
        self.app.on_theme_changed(THEME_CODES.get(self.theme_var.get(), "dark"))

    def _lang_changed(self) -> None:
        self.app.on_lang_changed(NAME_TO_CODE[self.lang_var.get()])
        self._paint_lang_chips()

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
        if key in (
            "auto_capitalize", "auto_space", "voice_punctuation",
            "voice_numbers", "clean_speech", "auto_period", "verbatim_mode",
        ):
            self._refresh_preview()

    # --- Тохиргоо · Бичилт ------------------------------------------
    def _page_writing(self) -> None:
        page = self._add_settings_page(
            Page(self.settings.stack, "Бичилт", "Таньсан текстийг курсор дээр хэрхэн буулгах.")
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

        row, holder = card.row(
            "Үгчлэн бичих цонх",
            "Эш татах, ярианы тэмдэглэлд бүх цэвэрлэгээ, толь, команд, "
            "тоо ба цэг таслалыг хүчингүй болгоно.",
        )
        Button(holder, "Сүүлийн цонхыг нэмэх", self._remember_no_clean_app).pack()
        page.spacer()
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        """Жишээ: «за ааа өнөөдрийн хурал гурван цагт болно цэг» гэж хэлсэн гэж үзнэ."""
        cfg = self.app.cfg
        if cfg["verbatim_mode"]:
            text = "за ааа өнөөдрийн хурал гурван цагт болно цэг"
            self.preview_var.set(("␣" if cfg["auto_space"] else "") + text)
            return
        text = "өнөөдрийн хурал гурван цагт болно"
        if not cfg["clean_speech"]:
            text = "за ааа " + text  # цэвэрлэхгүй бол хэлсэн чигээрээ
        if cfg["voice_numbers"]:
            text = textproc.spell_numbers(text)
        if cfg["voice_punctuation"] or cfg["auto_period"]:
            text += "."
        if cfg["auto_capitalize"]:
            text = text[0].upper() + text[1:]
        self.preview_var.set(("␣" if cfg["auto_space"] else "") + text)

    def _remember_type_mode_app(self) -> None:
        self.set_detail(self.app.remember_type_mode_app())

    def _remember_no_clean_app(self) -> None:
        self.set_detail(self.app.remember_no_clean_app())

    # --- Тохиргоо · Товчлуур ----------------------------------------
    def _page_hotkeys(self) -> None:
        page = self._add_settings_page(
            Page(
                self.settings.stack, "Товчлуур",
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

    # --- Толь ----------------------------------------------------
    def _page_dictionary(self) -> None:
        page = self._add_page(
            Page(self.stack, "Толь", "Аппыг өөрийн нэр томьёо, хэллэгт сургана.")
        )
        tabs = SegmentedTabs(
            page.body,
            ["Үг солих", "Нэрс", "Дуут товчлол", "Аппын хэл", "Дуут үйлдэл"],
            self._dictionary_tab,
        )
        tabs.pack(anchor="w", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))

        self.dictionary_tab = 0
        self.pairs = PairEditor(page.body, self._dictionary_changed)
        self.pairs.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        self.pairs.load(self.app.cfg["replacements"])
        self.dictionary_note = tk.Label(
            page.body, text="", bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL,
            anchor="w", justify="left", wraplength=560,
        )
        self.dictionary_note.pack(fill="x", padx=theme.PAGE_PAD_X)
        page.spacer()

    #: Толины таб бүр: (зүүн шошго, баруун шошго, тохиргооны түлхүүр, тайлбар).
    DICTIONARY_TABS = (
        ("Буруу таньсан", "Зөв бичих", "replacements", ""),
        (
            "Нэр",
            "Сонсогддог хувилбар (заавал биш)",
            "names",
            "Нэрийг ОЙРОЛЦООГООР таньдаг тул хувилбар бүрийг бичих "
            "шаардлагагүй: «Чимэгсайхан» гэж нэг нэмэхэд «чимэг сайхан», "
            "«чимэгсайхны» хоёулаа баригдана. Хол зөрдөг хувилбарыг баруун "
            "талд таслалаар тусгаарлан нэмнэ. 6-аас богино нэр зөвхөн яг таг "
            "таарвал солигдоно.",
        ),
        ("Хэллэг", "Бүтэн текст", "snippets", ""),
        (
            "Цонхны нэрний хэсэг",
            "Хэлний код",
            "lang_apps",
            "Тухайн цонхонд ярихад энэ хэлээр танина. Жишээ: «Visual Studio Code» → "
            "en-US. Хоёрдогч товчлуураар заасан хэл үүнээс дээгүүр.",
        ),
        (
            "Хэлэх үг",
            "Юу хийх",
            "actions",
            "Энэ хэллэгийг ЯГ ТАГ, ганцаараа хэлэхэд текст оруулахын оронд "
            "үйлдэл гүйцэтгэнэ. Баруун талд: буцаах, давтах, хуулах, зогсоох. "
            "Дотор нь суусан «буцаа», «давт», «хуулж ав», «зогс» нь эндээс "
            "үл хамаарч ажиллана; «хоёр удаа буцаа» гэж тоо нэмж болно. "
            "Байнга хэлдэг энгийн үгээ бүү сонго — тэр үг цаашид бичигдэхээ болино.",
        ),
    )

    def _dictionary_tab(self, index: int) -> None:
        # Хүлээгдэж буй хадгалалт нь ХУУЧИН табынх — таб солихоос ӨМНӨ
        # дуусгана. Эс бөгөөс 500 мс дотор таб сольсон хүний засвар өөр
        # тохиргооны түлхүүр рүү бичигдэнэ (жишээ нь дуут үйлдэл → орлуулга).
        self._flush_dictionary()
        self.dictionary_tab = index
        left, right, key, note = self.DICTIONARY_TABS[index]
        self.pairs.set_labels((left, right))
        mapping = self.app.cfg[key]
        if key == "actions":
            # Дискэн дээр "undo" гэж хадгалагддаг — хүнд монголоор нь харуулна.
            mapping = textproc.label_actions(mapping)
        self.pairs.load(mapping)
        self.dictionary_note.configure(text=note)

    def _dictionary_changed(self, mapping: dict) -> None:
        """Товч дарах бүрт диск рүү бичихгүй — бичиж дуустал хүлээнэ."""
        self._dictionary_pending = mapping
        if self._dictionary_save is not None:
            try:
                self.root.after_cancel(self._dictionary_save)
            except tk.TclError:
                pass
        self._dictionary_save = self.root.after(
            DICTIONARY_SAVE_MS, self._flush_dictionary
        )

    def _flush_dictionary(self) -> None:
        """Хүлээгдэж буй хадгалалтыг ОДОО гүйцэтгэнэ (байхгүй бол юу ч хийхгүй)."""
        if self._dictionary_save is not None:
            try:
                self.root.after_cancel(self._dictionary_save)
            except tk.TclError:
                pass
            self._dictionary_save = None
        mapping, self._dictionary_pending = self._dictionary_pending, None
        if mapping is not None:
            self._save_dictionary(mapping)

    def _save_dictionary(self, mapping: dict) -> None:
        self._dictionary_save = None
        raw = textproc.format_replacements(mapping)
        handlers = (
            self.app.on_replacements_changed,
            self.app.on_names_changed,
            self.app.on_snippets_changed,
            self.app.on_lang_apps_changed,
            self.app.on_actions_changed,
        )
        handlers[self.dictionary_tab](raw)

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
        list_area = tk.Frame(holder.inner, bg=theme.PANEL)
        list_area.pack(fill="both", expand=True)
        self.history_box = tk.Listbox(
            list_area, bg=theme.PANEL, fg=theme.TEXT, selectbackground=theme.NAV_ACTIVE,
            selectforeground=theme.TEXT, relief="flat",
            font=theme.UI, activestyle="none", height=12, bd=0,
            highlightthickness=theme.FOCUS_WIDTH,
            highlightbackground=theme.PANEL, highlightcolor=theme.FOCUS,
        )
        bar = scrollbar(list_area, self.history_box.yview, trough=theme.PANEL)
        bar.pack(side="right", fill="y")
        self.history_box.configure(yscrollcommand=bar.set)
        self.history_box.pack(fill="both", expand=True)
        self.history_box.bind("<Double-Button-1>", self._repaste)

        # Хоосон төлөв: жагсаалт хоосон үед л дунд нь харагдана — юу ч
        # байхгүй үед хэрэглэгч дараагийн алхамаа мэдэх ёстой.
        self.history_empty = tk.Label(
            holder.inner,
            text="Одоогоор түүх хоосон байна.\nДурын цонхон дээр товчоо дараад ярьж үзээрэй.",
            bg=theme.PANEL, fg=theme.DIM, font=theme.UI_SMALL, justify="center",
        )

        foot = RoundedBox(
            page.body, fill=theme.PANEL2, outside=theme.BG, pad=(theme.RADIUS, 6)
        )
        foot.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(theme.GAP, 0))
        self.history_count = tk.StringVar(value="")
        tk.Label(
            foot.inner, textvariable=self.history_count, bg=theme.PANEL2, fg=theme.MUTED,
            font=theme.UI_SMALL, anchor="w",
        ).pack(side="left", padx=4)
        # Хэлийг батлах товчууд хамтдаа — «сонгосон мөрийг аль хэл рүү
        # бүртгэх вэ» гэсэн нэг үйлдлийн хоёр сонголт.
        Button(
            foot.inner,
            "Монгол",
            lambda: self._mark_language("mn-MN"),
            bg=theme.PANEL2,
        ).pack(side="right")
        Button(
            foot.inner,
            "English",
            lambda: self._mark_language("en-US"),
            bg=theme.PANEL2,
        ).pack(side="right", padx=(0, 6))
        Button(
            foot.inner, "Засах (сурна)", self._edit_selected, bg=theme.PANEL2
        ).pack(side="right", padx=(0, 10))
        Button(
            foot.inner, "Цэвэрлэх", self.clear_history, bg=theme.PANEL2, danger=True
        ).pack(side="right", padx=(10, 0))

        self.history_note = tk.Label(
            page.body, text="", bg=theme.BG, fg=theme.DIM, font=theme.UI_SMALL,
            anchor="w", justify="left", wraplength=560,
        )
        self.history_note.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(8, 0))
        page.spacer()
        self._fill_history()

    # --- Хөрвүүлэх ---------------------------------------------------
    def _page_file(self) -> None:
        """Аудио/видео файлыг текст болгох хуудас.

        Түүхэн дээр хавчуулсан байснаас тусдаа цэс болгосон: энэ нь
        бичлэг хөрвүүлөх ТУСДАА ажил — түүх хайхтай холбоогүй.
        """
        page = self._add_page(
            Page(
                self.stack, "Хөрвүүлэх",
                "Хурлын бичлэг, лекц, дуут тэмдэглэлийг текст болгоно. Үр дүн нь "
                "эх файлын хажууд .txt болж хадгалагдана.",
            )
        )
        card = Card(page.body)
        _, holder = card.row(
            "Файлаас хөрвүүлэх",
            "Яриаг чимээгүй завсраар нь хэсэглээд дараалан илгээнэ — урт "
            "бичлэг ч ажиллана, явц нь доор харагдана.",
        )
        Button(holder, "Файл сонгох", self._choose_audio_file).pack()
        card.note(
            "WAV файл нэмэлт хэрэгсэлгүй ажиллана. MP3, M4A, MP4 зэрэгт "
            "ffmpeg шаардлагатай — байхгүй бол цонх тэр тухай мэдэгдэнэ."
        )
        # Гарчиг нь ЗААВАЛ байх ёстой: `Card.row` нь гарчиггүй үед зүүн талын
        # блокоо бүтээдэггүй тул тайлбар (энэ явцын мөр) огт зурагдахгүй.
        self.file_progress = tk.StringVar(value="Файл сонгоогүй байна.")
        card.row("Явц", self.file_progress)
        page.spacer()

    # --- Хэрэглээ -------------------------------------------------
    #: Халивийн нүд ба хоорондын зай (пиксел). Долоо хоногийн тоо нь
    #: картын өргөнөөс автоматаар тооцогдоно.
    HEAT_CELL = 15
    HEAT_GAP = 4
    #: Багана график хэдэн өдрийг харуулах вэ.
    DAY_BARS = 7
    #: Нэг өдрийн мөрийн өндөр. Графикийг картын үлдсэн зайд СУНГАХГҮЙ:
    #: сунгавал 7 нимгэн зураас хагас метр талбайд хөвж, карт нь агуулгаасаа
    #: хоёр дахин өндөр болно. Тогтмол хэмнэл нь картыг агуулгынхаа хэрээр
    #: богиносгоно.
    BAR_ROW = 32
    #: Халивын өндөр: 7 гараг × алхам + сарын шошгын мөр.
    HEAT_ROWS = 7
    #: Халивийн мөр шошго — Нямгаас эхэлнэ (дизайны дагуу).
    WEEKDAY_LABELS = ("Ня", "Да", "Мя", "Лх", "Пү", "Ба", "Бя")

    def _page_usage(self) -> None:
        """Хэрэглээний хуудас: тоон карт → өдрийн багана → тасралтын халив.

        Бүх тоо `stats.json`-д аль хэдийн бичигддэг өгөгдөл дээр суурилна —
        хуурамч харьцуулалт («top 66%» гэх мэт) байхгүй: юу ч хэмжигдээгүй
        бол карт хоосон утгаараа хэвээр үлдэнэ.
        """
        page = self._add_page(
            Page(
                self.stack, "Хэрэглээ",
                "Шивсэн үг, ярьсан хурд, өдрүүдийн тасралт — бүгд энэ "
                "төхөөрөмж дээр хуримтласан тоо.",
            )
        )

        # Дээд мөр — гурван тоон карт. sticky="nsew": нэг карт урт байвал
        # бусад хоёр ч мөртлөө сунаж, өндөр нь тэгш хэвээр үлдэнэ.
        top = tk.Frame(page.body, bg=theme.BG)
        top.pack(fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP))
        for column in range(3):
            top.columnconfigure(column, weight=1, uniform="insight")
        self.speed_var = tk.StringVar(value="—")
        self.speed_note_var = tk.StringVar(value="")
        self._insight_card(top, 0, self.speed_var, "Үг / минут", self.speed_note_var)
        self.rules_var = tk.StringVar(value="0")
        self.rules_note_var = tk.StringVar(value="буруу → зөв хосууд")
        self._insight_card(top, 1, self.rules_var, "Толийн дүрэм", self.rules_note_var)
        # Гурван карт ИЖИЛ бүтэцтэй: том тоо → шошго → нэг мөр тайлбар.
        # Урьд нь энэ карт дотроо тусгаарлагч ба хоёр нэмэлт мөртэй байсан
        # тул бусад хоёр нь түүнтэй өндрөө тэнцүүлээд доод хагасаа хоосон
        # орхидог байв.
        self.total_var = tk.StringVar(value="0")
        self.total_note_var = tk.StringVar(value="")
        self._insight_card(top, 2, self.total_var, "Нийт шивсэн үг", self.total_note_var)

        # Доод мөр — хоёр график карт. expand=True + Page-ийн өндрийн
        # сунгалт хоёулаа нийлээд цонх дүүрэн харагдуулна.
        bottom = tk.Frame(page.body, bg=theme.BG)
        bottom.pack(fill="x", padx=theme.PAGE_PAD_X)
        bottom.columnconfigure(0, weight=1, uniform="usage")
        bottom.columnconfigure(1, weight=1, uniform="usage")

        bars_card = RoundedBox(bottom, fill=theme.PANEL, outside=theme.BG, radius=theme.RADIUS)
        bars_card.grid(row=0, column=0, sticky="nsew", padx=(0, theme.GAP // 2))
        bars_body = tk.Frame(bars_card.inner, bg=theme.PANEL)
        bars_body.pack(fill="both", expand=True, padx=theme.CARD_PAD_X, pady=theme.CARD_PAD_Y)
        head = tk.Frame(bars_body, bg=theme.PANEL)
        head.pack(fill="x")
        tk.Label(
            head, text="Өдрийн хэрэглээ", bg=theme.PANEL, fg=theme.TEXT,
            font=theme.UI_TITLE, anchor="w",
        ).pack(side="left")
        self.bars_note_var = tk.StringVar(value="")
        tk.Label(
            head, textvariable=self.bars_note_var, bg=theme.PANEL, fg=theme.DIM,
            font=theme.UI_LABEL, anchor="e",
        ).pack(side="right")
        # Хэмжээгээ КАРТААСАА авна: цонх томорч багасахад график дагаж,
        # талбайгаа үргэлж дүүргэнэ.
        self.bars_canvas = tk.Canvas(
            bars_body, bg=theme.PANEL, highlightthickness=0, bd=0,
            height=self.DAY_BARS * self.BAR_ROW,
        )
        self.bars_canvas.pack(fill="both", expand=True, pady=(theme.SPACE_MD, 0))
        self.bars_canvas.bind(
            "<Configure>", lambda _e: self._draw_day_bars(), add="+"
        )

        heat_card = RoundedBox(bottom, fill=theme.PANEL, outside=theme.BG, radius=theme.RADIUS)
        heat_card.grid(row=0, column=1, sticky="nsew", padx=(theme.GAP // 2, 0))
        heat_body = tk.Frame(heat_card.inner, bg=theme.PANEL)
        heat_body.pack(fill="both", expand=True, padx=theme.CARD_PAD_X, pady=theme.CARD_PAD_Y)
        head = tk.Frame(heat_body, bg=theme.PANEL)
        head.pack(fill="x")
        self.streak_var = tk.StringVar(value="0 хоног тасралтгүй")
        tk.Label(
            head, textvariable=self.streak_var, bg=theme.PANEL, fg=theme.TEXT,
            font=theme.UI_TITLE, anchor="w",
        ).pack(side="left")
        self.best_streak_var = tk.StringVar(value="")
        tk.Label(
            head, textvariable=self.best_streak_var, bg=theme.PANEL, fg=theme.DIM,
            font=theme.UI_LABEL, anchor="e",
        ).pack(side="right")
        # Домайн доод талд бэхлэнэ — халив үлдсэн өндрийг бүтнээрээ авна.
        legend = tk.Frame(heat_body, bg=theme.PANEL)
        # `side="bottom"` — код дотор халивын ӨМНӨ бичигдсэн ч домог нь доор
        # байрлана (pack эхлээд доод захыг нь эзэмшүүлнэ).
        legend.pack(side="bottom", fill="x", pady=(theme.SPACE_MD, 0))
        tk.Label(
            legend, text="Бага", bg=theme.PANEL, fg=theme.DIM, font=theme.UI_TINY
        ).pack(side="left")
        for colour in self._heat_levels()[1:]:
            swatch = tk.Canvas(
                legend, width=11, height=11, bg=theme.PANEL, highlightthickness=0
            )
            swatch.pack(side="left", padx=2, pady=1)
            swatch.create_rectangle(0, 0, 11, 11, fill=colour, outline="")
        tk.Label(
            legend, text="Их", bg=theme.PANEL, fg=theme.DIM, font=theme.UI_TINY
        ).pack(side="left")
        self.heat_canvas = tk.Canvas(
            heat_body, bg=theme.PANEL, highlightthickness=0, bd=0,
            height=self.DAY_BARS * self.BAR_ROW,
        )
        self.heat_canvas.pack(fill="both", expand=True, pady=(theme.SPACE_MD, 0))
        self.heat_canvas.bind(
            "<Configure>", lambda _e: self._draw_heatmap(), add="+"
        )

        self._usage_days: dict = {}
        self._refresh_usage_page()

    def _insight_card(self, parent, column: int, value_var, caption: str, note_var=None):
        """Том тоо + шошго (заавал биш нэмэлт тайлбар) бүхий карт."""
        card = RoundedBox(parent, fill=theme.PANEL, outside=theme.BG, radius=theme.RADIUS)
        # Хоёр хажуугийн зайг тэнцүү — эхний карт зүүн захад, сүүлийнх
        # баруун захад нягт наалдана.
        left = 0 if column == 0 else theme.GAP // 2
        right = 0 if column == 2 else theme.GAP // 2
        card.grid(row=0, column=column, sticky="nsew", padx=(left, right))
        body = tk.Frame(card.inner, bg=theme.PANEL)
        body.pack(fill="both", expand=True, padx=theme.CARD_PAD_X, pady=theme.CARD_PAD_Y)
        tk.Label(
            body, textvariable=value_var, bg=theme.PANEL, fg=theme.GRADIENT[2],
            font=theme.MONO_BIG, anchor="w",
        ).pack(fill="x")
        tk.Label(
            body, text=caption.upper(), bg=theme.PANEL, fg=theme.MUTED,
            font=theme.UI_LABEL, anchor="w",
        ).pack(fill="x", pady=(2, 0))
        if note_var is not None:
            tk.Label(
                body, textvariable=note_var, bg=theme.PANEL, fg=theme.DIM,
                font=theme.UI_LABEL, anchor="w",
            ).pack(fill="x", pady=(6, 0))
        return card, body

    def _heat_levels(self) -> list[str]:
        """Халивийн 5 өнгө: хоосон → зөөлөн → акцент. Сэдэв бүрд тооцогдоно."""
        soft, accent = theme.ACCENT_SOFT, theme.ACCENT
        return [
            theme.PANEL2,
            soft,
            _mix_hex(soft, accent, 0.45),
            _mix_hex(soft, accent, 0.75),
            accent,
        ]

    @staticmethod
    def _heat_level(value: int) -> int:
        """Үгийн тоог халивийн шат руу хөрвүүлнэ (логариф маягийн босго)."""
        if value >= 100:
            return 4
        if value >= 30:
            return 3
        if value >= 10:
            return 2
        if value >= 1:
            return 1
        return 0

    def _refresh_usage_page(self) -> None:
        """Хэрэглээний хуудасны бүх тоо, графикыг статистиктэй тааруулна."""
        if not hasattr(self, "speed_var"):
            return
        stats = self.app.stats
        data = getattr(stats, "data", {})
        total = int(data.get("words", 0) or 0)
        seconds = float(data.get("seconds_spoken", 0.0) or 0.0)
        # Ярьсан хурд: нийт үг / нийт ярьсан минут. Таних хугацаа биш —
        # хэрэглэгч хэр хурдан ярьдгийг хэмждэг.
        self.speed_var.set(f"{total / (seconds / 60):.0f}" if seconds > 0 and total else "—")
        self.rules_var.set(str(len(self.app.cfg.get("replacements") or {})))
        self.total_var.set(f"{total:,}".replace(",", " "))

        days = data.get("days") or {}
        today = datetime.date.today()
        week = sum(
            int(value or 0)
            for key, value in days.items()
            if (day := _parse_day(key)) and 0 <= (today - day).days < 7
        )
        today_words = int(getattr(stats, "today_words", 0) or 0)
        self.total_note_var.set(
            f"өнөөдөр {today_words:,} · энэ 7 хоногт {week:,}".replace(",", " ")
        )

        current, best = _streaks(days)
        self.streak_var.set(f"{current} хоног тасралтгүй")
        self.best_streak_var.set(f"ХАМГИЙН УРТ | {best} ХОНОГ" if best else "")
        self.bars_note_var.set(f"СҮҮЛИЙН {self.DAY_BARS} ӨДӨР")
        if seconds > 0 and total:
            self.speed_note_var.set(f"ярьсан ~{seconds / 60:.0f} минут")
        else:
            self.speed_note_var.set("")
        # Графикууд өөрсдийн хэмжээгээ canvas-ийн <Configure>-оос авдаг тул
        # зөвхөн ӨГӨГДӨЛ нь шинэчлэгдлээ — дахин зурахыг тэдгээр өөрөө хийнэ.
        self._usage_days = days
        self._draw_day_bars()
        self._draw_heatmap()

    def _draw_day_bars(self) -> None:
        """Сүүлийн 7 өдрийн үгийн тоог баганаар харуулна.

        Өндөр, өргөнөө canvas-ийнхээ бодит хэмжээнээс тооцно — карт
        сунаж нарийссан баганадууд дагаж, талбайгаа үргэлж дүүргэнэ.
        """
        canvas = self.bars_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 100 or height < 50:
            return
        days = getattr(self, "_usage_days", {})
        today = datetime.date.today()
        values = [
            (today - datetime.timedelta(days=offset), int(days.get(
                (today - datetime.timedelta(days=offset)).isoformat(), 0
            ) or 0))
            for offset in range(self.DAY_BARS - 1, -1, -1)
        ]
        peak = max(value for _, value in values)
        count_zone = 44
        bar_x = 66
        bar_end = width - count_zone - 6
        # Мөрийн хэмнэл ТОГТМОЛ. Картын үлдсэн зайд сунгавал 7 нимгэн зураас
        # хоорондоо 100 px зайтай хөвж, график нь хүснэгт ч биш, зураг ч биш
        # болно. Илүү зай гарвал блокийг голлуулна.
        row_h = min(self.BAR_ROW, (height - 8) / self.DAY_BARS)
        top = max(4, (height - row_h * self.DAY_BARS) / 2)
        bar_h = max(8, min(18, row_h - 12))
        for index, (day, value) in enumerate(values):
            cy = top + row_h * index + row_h / 2
            canvas.create_text(
                0, cy, text=day_label(day.isoformat()), anchor="w",
                font=theme.UI_SMALL, fill=theme.MUTED,
            )
            ratio = value / peak if peak else 0.0
            bar_w = max(4, int((bar_end - bar_x) * ratio)) if value else 4
            canvas.create_rectangle(
                bar_x, cy - bar_h / 2, bar_x + bar_w, cy + bar_h / 2,
                fill=theme.ACCENT if value else theme.PANEL2, outline="",
            )
            canvas.create_text(
                width - 4, cy, text=str(value), anchor="e",
                font=theme.MONO_KEY, fill=theme.TEXT if value else theme.DIM,
            )

    def _draw_heatmap(self) -> None:
        """Өдөр бүрийн үгийн тоог GitHub хэлбэрийн халиваар зурна.

        Багана бүр нэг долоо хоног, мөр бүр гарагийн өдөр (Ням дээдэд).
        Сүүлийн багана ЯГ ӨНӨӨДӨРт хүртэл эцэслэнэ — ирээдгүй өдөр хоосон
        байх нь «юу ч хийгээгүй» гэсэн буруу ойлголт төрүүлнэ.

        Долоо хоногийн тоо ӨРГӨНӨЭСӨӨ гарна: өргөн цонхонд илүү урт
        хугацаа багтана (12–40 долоо хоногийн хооронд), өндрийн дунд
        төвлөрөнө.
        """
        canvas = self.heat_canvas
        canvas.delete("all")
        width, height = canvas.winfo_width(), canvas.winfo_height()
        if width < 140 or height < 80:
            return
        days = getattr(self, "_usage_days", {})
        cell, gap = self.HEAT_CELL, self.HEAT_GAP
        pitch = cell + gap
        left0 = 26
        weeks = max(12, min(40, (width - left0 - 6) // pitch))
        today = datetime.date.today()
        # Зүүн дээд нүд нь Ням байх ёстой: өнөөдрөөс гараг доторх
        # зөрүүг хасаад, нийт долоо хоногийн тоогоор ухрана.
        week_offset = (today.weekday() + 1) % 7
        start = today - datetime.timedelta(days=week_offset + (weeks - 1) * 7)
        top0 = max(16, (height - 7 * pitch) // 2)
        colours = self._heat_levels()
        last_month = 0
        # Сарын шошгыг хамгийн багадаа ийм зайтай зурна. Хоёр сарын зааг
        # ойрхон таарвал шошгууд бие бие рүүгээ орж «2 сарсар» болдог байв.
        label_gap = 46
        last_label_x = -label_gap
        for col in range(weeks):
            for row in range(7):
                day = start + datetime.timedelta(days=col * 7 + row)
                if day > today:
                    continue
                value = int(days.get(day.isoformat(), 0) or 0)
                x, y = left0 + col * pitch, top0 + row * pitch
                canvas.create_rectangle(
                    x, y, x + cell, y + cell,
                    fill=colours[self._heat_level(value)], outline="",
                )
            mid = start + datetime.timedelta(days=col * 7 + 3)
            label_x = left0 + col * pitch
            if mid.month != last_month:
                last_month = mid.month
                if label_x - last_label_x >= label_gap:
                    last_label_x = label_x
                    canvas.create_text(
                        label_x, top0 - 13, text=f"{mid.month} сар",
                        anchor="w", font=theme.UI_TINY, fill=theme.DIM,
                    )
        for row, name in enumerate(self.WEEKDAY_LABELS):
            canvas.create_text(
                0, top0 + row * pitch + cell / 2, text=name, anchor="w",
                font=theme.UI_TINY, fill=theme.DIM,
            )

    # --- Тохиргоо · Нэмэлт ------------------------------------------
    def _page_advanced(self) -> None:
        page = self._add_settings_page(Page(self.settings.stack, "Нэмэлт"))

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

        page.group("Харагдац")
        card = Card(page.body)
        _, holder = card.row("Өнгөний сэдэв", "Дахин эхлүүлэхэд идэвхжинэ")
        self.theme_var = tk.StringVar(value=THEME_NAMES.get(theme.name, THEME_NAMES["dark"]))
        combo(
            holder, self.theme_var, list(THEME_NAMES.values()), self._theme_changed
        )

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

    # --- Аппууд --------------------------------------------------
    def _page_apps(self) -> None:
        """Цонх бүрийн дүрмийг нэг дор: хэл, шууд бичих, цэвэрлэхгүй.

        Дүрмүүд нь гурван тусдаа тохиргоонд (`lang_apps`, `type_mode_apps`,
        `no_clean_apps`) хадгалагддаг ба өмнө нь хоёр өөр цэсэн дээр тарж
        байв. Энд «энэ цонхонд юу үйлчилж байна вэ» гэдгийг бүтнээр харна.
        """
        page = self._add_page(
            Page(
                self.stack, "Аппууд",
                "Цонх бүрт өөр дүрэм: ямар хэлээр таних, хэрхэн буулгах.",
            )
        )
        # Цонхны нэрийг ЗҮҮН талын амьд тайлбар болгож харуулна. Баруун талд
        # тавибал урт гарчиг картыг өргөсгөж, тайлбарын мөр таслалттай
        # тэмцэлдэн Tk-г төгсгөлгүй дахин байрлуулалтад оруулдаг.
        self.app_marker_var = tk.StringVar(value="—")
        card = Card(page.body)
        _, holder = card.row("Сүүлд бичсэн цонх", self.app_marker_var)
        Button(holder, "Шинэчлэх", self.refresh_apps).pack()

        _, holder = card.row("Хэл", "Энэ цонхонд ярихад энэ хэлээр танина")
        self.app_lang_var = tk.StringVar(value=DEFAULT_RULE)
        combo(
            holder, self.app_lang_var,
            [DEFAULT_RULE] + [name for name, _ in LANGUAGES], self._app_lang_changed,
        )

        _, holder = card.row(
            "Шууд бичих", "Синтетик Ctrl+V-г хүлээж авдаггүй цонхонд товчлуураар бичнэ"
        )
        self.app_type_toggle = Toggle(
            holder, False, lambda value: self._app_rule_changed("type_mode", value)
        )
        self.app_type_toggle.pack()

        _, holder = card.row(
            "Цэвэрлэхгүй",
            "Энэ цонхонд бүрэн үгчлэн бичнэ: цэвэрлэгээ, толь, нэр, тоо, "
            "цэг таслал, дуут үйлдэл бүгд хүчингүй болно",
        )
        self.app_clean_toggle = Toggle(
            holder, False, lambda value: self._app_rule_changed("no_clean", value)
        )
        self.app_clean_toggle.pack()

        page.group("Дүрэмтэй аппууд")
        # Карт нэг л удаа бүтээгдэнэ; шинэчлэхдээ зөвхөн МӨРҮҮДИЙГ нь солино.
        self.rules_card = Card(page.body)
        page.spacer()
        self.refresh_apps()

    def refresh_apps(self) -> None:
        """Сүүлийн цонх ба дүрмүүдийн жагсаалтыг дахин зурна."""
        if not hasattr(self, "app_marker_var"):
            return
        marker = self.app.current_window_marker()
        self.app_marker_var.set(marker or "— (эхлээд хаа нэгтээ бичээрэй)")
        rule = self.app.window_rule(marker)
        self.app_lang_var.set(CODE_TO_NAME.get(rule["lang"], DEFAULT_RULE))
        self.app_type_toggle.set(bool(rule["type_mode"]))
        self.app_clean_toggle.set(bool(rule["no_clean"]))
        self._fill_rules()

    def _fill_rules(self) -> None:
        card = self.rules_card
        for child in card.inner.winfo_children():
            child.destroy()
        card._rows = 0  # тусгаарлагч нь эхний мөрөнд зурагдахгүй байх ёстой
        refit(card)  # дүрмийн тоо солигдоход хуудасны өндөр дагана
        rules = self.app.window_rules()
        if not rules:
            card.note("Одоогоор дүрэм алга. Дээрх тохиргоог өөрчлөхөд энд гарч ирнэ.")
            return
        for rule in rules:
            _, holder = card.row(rule["marker"], _rule_summary(rule))
            Button(
                holder, "Устгах", lambda m=rule["marker"]: self._remove_rule(m),
                bg=theme.PANEL2, danger=True,
            ).pack()

    def _remove_rule(self, marker: str) -> None:
        self.set_detail(self.app.remove_window_rule(marker))
        self.refresh_apps()

    def _app_lang_changed(self) -> None:
        name = self.app_lang_var.get()
        code = "" if name == DEFAULT_RULE else NAME_TO_CODE.get(name, "")
        self.set_detail(
            self.app.set_window_rule(self.app.current_window_marker(), "lang", code)
        )
        self._fill_rules()

    def _app_rule_changed(self, kind: str, value: bool) -> None:
        self.set_detail(
            self.app.set_window_rule(self.app.current_window_marker(), kind, bool(value))
        )
        self._fill_rules()

    def _copy_diagnostics(self) -> None:
        self.set_detail(self.app.copy_diagnostics())

    def show_update(self, tag: str) -> None:
        """Шинэ хувилбар олдлоо — «Тохиргоо» цэсэн дээр тэмдэг, цонхонд товч.

        Тэмдгийг цонхыг нээхээс ӨМНӨ харагдуулна: шинэчлэл нь ховор
        мэдэгдэл тул хүн цонх нээхгүй л байхад анзаарах ёстой.
        """
        self.version_var.set(f"Monspeech {__version__} · шинэ хувилбар: {tag}")
        self.update_button.pack()
        refit(self.update_button)
        self.settings_button.set_badge(True)
        self.set_detail(f"Шинэ хувилбар гарсан байна: {tag}")

    # ------------------------------------------------------------------
    # Гаднаас дуудагдах
    # ------------------------------------------------------------------
    #: Төлөв бүрийн (дэвсгэр, бичиг) хос. Капсулыг бүтнээр нь өнгөлөх нь ганц
    #: цэгийг будахаас хамаагүй холоос танигдана. Утга нь зөвхөн өнгөөр
    #: илэрхийлэгдэхгүй — цэг, бичиг, роботын хөдөлгөөн гурав давхар хэлнэ.
    #:
    #: Ангийн биед байгаа тул өнгө нь ИМПОРТЫН үед тогтоно. Энэ нь виджетийн
    #: анхны утгуудтай (`bg: str = theme.PANEL`) ижил дүрэм: `__main__.py` нь
    #: сэдвийг эдгээр модулиас өмнө идэвхжүүлдэг тул зөв ажиллана.
    PILL_COLOURS = {
        "listening": (theme.ACCENT, theme.ON_ACCENT),
        "working": (theme.WARN_SOFT, theme.WARN),
        "ready": (theme.OK_SOFT, theme.OK),
        "error": (theme.DANGER_SOFT, theme.DANGER),
    }

    def _paint_pill(self, kind: str) -> None:
        """Төлөвийн капсулын өнгийг ХУУЧНААС шинэ рүү уусгана.

        Бэлэн → Сонсож байна → Таниж байна гэсэн гурван төлөв нь секундын
        дотор дараалж солигддог. Тэр дор нь үсэрвэл нүд гялсхийж, «ямар
        төлөвөөс ямар руу шилжив» гэдэг нь алдагдана.
        """
        target = self.PILL_COLOURS.get(kind, (theme.PANEL2, theme.MUTED))
        start = self._pill_colours

        def paint(amount: float) -> None:
            fill = animate.mix(start[0], target[0], amount)
            fg = animate.mix(start[1], target[1], amount)
            self.pill.restyle(fill=fill)
            self.pill_dot.configure(bg=fill)
            self.pill_dot.itemconfigure(self._pill_dot_id, fill=fg)
            self.pill_label.configure(bg=fill, fg=fg)

        self._pill_colours = target
        self._pill_fade.stop()
        self._pill_fade = animate.Motion(self.pill, paint, ms=animate.FAST)
        self._pill_fade.to(1.0)

    def set_state(self, kind: str, title: str, detail: str) -> None:
        colours = {
            "listening": theme.GRADIENT[0],
            "working": theme.WARN,
            "ready": theme.OK,
            "error": theme.DANGER,
        }
        self.title_var.set(title)
        self.state_var.set(title)
        self.dot.itemconfigure(self._dot_id, fill=colours.get(kind, theme.DIM))
        self._paint_pill(kind)
        listening = kind == "listening"
        # Сонсож байх үед капсул өөрөө акцентаар дүрэлзэнэ. Товчийг ч бас
        # дүүргэвэл хоёр тод юм зэрэгцэж, аль нь ч анхаарал татахаа болино —
        # тиймээс тэр үед товч хүрээт хэлбэртээ буцна.
        self.action_button.set_text("Зогсоох" if listening else "Эхлүүлэх")
        self.action_button.set_primary(not listening)
        self.orb.set_mode(ORB_MODES.get(kind, "idle"))
        self.hint_var.set(detail or self.default_hint)

    def set_detail(self, text: str) -> None:
        """Түр зуурын мэдэгдэл — доод талын мөрөнд гарна (аль ч хуудсанд харагдана)."""
        self.detail_var.set(text)

    def set_level(self, level: float, listening: bool) -> None:
        """Заалт, роботыг шинэчилнэ.

        Цонх tray-д нуугдсан үед зурах нь утгагүй тул алгасна — 50 мс тутам
        давтагддаг ажил учир хоосон CPU хэрэглээ мэдэгдэхүйц. Микрофоны
        түвшний заалт Тохиргооны цонхны Яриа хэсэгт шилжсэн тул хэсэг
        харагдаж байгаа эсэхийг ялгахгүй шинэчилнэ — өөрчлөлтгүй үед
        `LevelMeter` өөрөө зурахаа алгасдаг.
        """
        if not self.root.winfo_viewable():
            return
        filled = min(1.0, level / LEVEL_FULL) if listening else 0.0
        self.orb.set_level(filled)
        self.meter.set_level(filled)
        self.level_var.set(f"{filled * 100:.0f}%")

    def refresh_hotkeys(self) -> None:
        for key, caps in self.keycaps.items():
            caps.show(pretty(self.app.cfg[key]).split(" + "))

    def refresh_stats(self) -> None:
        """Статистик харагдах БҮХ газрыг шинэчилнэ.

        Хуудаснууд баригдах дарааллаас үл хамааран дуудагдаж болох тул
        хуудас бүрийн шинэчлэгч өөрийн виджээ бүрсэн эсэхийг өөрөө шалгана.
        """
        self._refresh_usage()
        self._refresh_usage_page()
        self.refresh_samples()

    def refresh_samples(self) -> None:
        """Хадгалсан хэцүү жишээний тоог шинэчилнэ.

        Хуудаснууд баригдах дарааллаас үл хамааран дуудагдана — «Яриа»
        хуудас хараахан баригдаагүй байхад ч аюулгүй байх ёстой.
        """
        if not hasattr(self, "samples_var"):
            return
        self.samples_var.set(self.app.samples.summary())

    def _clear_samples(self) -> None:
        self.app.clear_samples()
        self.refresh_samples()

    def _refresh_usage(self) -> None:
        """Одоогийн танигчийн минут ба ойролцоо зардал.

        Google нь үнэгүй тул зардал харуулахгүй — зөвхөн хэр их ашигласныг.
        Зардал нь ЗАВСРЫН тооцоо: минутын үнийг тохиргооноос авна.
        """
        if not hasattr(self, "usage_var"):
            return
        cfg = self.app.cfg
        provider = str(cfg.get("stt_provider") or "google")
        reader = getattr(self.app.stats, "usage", None)
        if reader is None:
            return  # хуучин статистикийн файл — хэрэглээ бүртгэгдээгүй
        usage = reader(provider)
        if not usage["requests"]:
            self.usage_var.set("Хараахан хүсэлт явуулаагүй")
            return
        parts = [
            f"өнөөдөр {usage['today'] / 60:.1f} мин",
            f"энэ сар {usage['month'] / 60:.1f} мин",
            f"нийт {usage['requests']} хүсэлт",
        ]
        rate = float(cfg.get("stt_cost_per_minute") or 0.0)
        if provider != "google" and rate > 0:
            parts.append(f"~${usage['month'] / 60 * rate:.2f}")
        self.usage_var.set(" · ".join(parts))

    def refresh_words(self) -> None:
        """Толь өөрчлөгдсөн үед (жишээ нь засвараас сурсан) жагсаалтыг шинэчилнэ."""
        if self.dictionary_tab == 0:
            self.pairs.load(self.app.cfg["replacements"])

    def show_history(self) -> None:
        self.select(2)

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
                refit(self.hotkey_note)
        self.refresh_hotkeys()

    # ------------------------------------------------------------------
    # Микрофон
    # ------------------------------------------------------------------
    def _current_mic_label(self) -> str:
        """Хадгалсан сонголтыг жагсаалтаас олно.

        Нэрээр нь эхэлж хайна: дугаар нь шилжсэн байж болох ч хэрэглэгчийн
        сонгосон төхөөрөмж жагсаалтад байсаар байна.
        """
        saved = self.app.cfg["mic_name"], int(self.app.cfg["mic_index"])
        for mic in self.mics:
            if saved[0] and mic.name == saved[0]:
                return mic.label
        for mic in self.mics:
            if mic.index == saved[1]:
                return mic.label
        return self.mics[0].label

    def _mic_changed(self) -> None:
        chosen = self.mic_var.get()
        for mic in self.mics:
            if mic.label == chosen:
                self.app.on_mic_changed(mic)
                return

    # ------------------------------------------------------------------
    # Түүх
    # ------------------------------------------------------------------
    def set_file_progress(self, text: str) -> None:
        if hasattr(self, "file_progress"):
            self.file_progress.set(text)

    def _choose_audio_file(self) -> None:
        """Файл сонгуулж, хөрвүүлэлтийг аппд даалгана."""
        from tkinter import filedialog

        native = " ".join(f"*{suffix}" for suffix in sorted(filetext.NATIVE_SUFFIXES))
        others = " ".join(f"*{suffix}" for suffix in sorted(filetext.FFMPEG_SUFFIXES))
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Хөрвүүлэх файл",
            filetypes=[
                ("Дуу, видео", f"{native} {others}"),
                ("WAV (хэрэгсэлгүй)", native),
                ("Бүх файл", "*.*"),
            ],
        )
        if not path:
            return
        if not filetext.ffmpeg_path() and Path(path).suffix.lower() not in filetext.NATIVE_SUFFIXES:
            self.set_file_progress("Энэ бичиглэлд ffmpeg хэрэгтэй — WAV бол шууд ажиллана.")
            return
        self.app.transcribe_file(path)

    def refresh_history(self) -> None:
        self._fill_recent()
        if self.history_box.winfo_exists():
            self._fill_history()

    def clear_history(self) -> None:
        self.app.transcripts.clear()
        self._fill_recent()
        self._fill_history()

    def _fill_history(self) -> None:
        """Хайлтын үр дүнгээр жагсаалтыг дүүргэнэ."""
        if not self.history_box.winfo_exists():
            return
        self._history_rows = self.app.transcripts.search(self.history_query.get())
        self.history_box.delete(0, "end")
        for entry in self._history_rows:
            stamp = entry.get("at", "")[5:16].replace("T", " ")
            language = {"mn-MN": "MN", "en-US": "EN", "mixed": "MN+EN"}.get(
                entry.get("lang", ""), entry.get("lang", "")
            )
            mode = " · RAW" if entry.get("mode") == "verbatim" else ""
            tag = f" [{language}{mode}]" if language else ""
            self.history_box.insert("end", f"  {stamp}{tag}   {entry['text']}")
        self.history_count.set(f"{len(self._history_rows)} мөр")
        # Хоосон үед л дунд нь туслах бичиг гарна — хайлт илэрцгүй үед ч
        # «юу ч олдсонгүй» гэдгээр ялгагдана.
        if hasattr(self, "history_empty") and self.history_empty.winfo_exists():
            if self._history_rows:
                self.history_empty.place_forget()
            else:
                self.history_empty.place(relx=0.5, rely=0.35, anchor="center")

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

    def _mark_language(self, language: str) -> None:
        entry = self._selected_entry()
        if not entry:
            self.history_note.configure(text="Эхлээд мөр сонгоно уу.")
            return
        message = self.app.on_transcript_language_changed(entry, language)
        self.history_note.configure(text=message)
        self._fill_history()

    def _edit_selected(self) -> None:
        """Сонгосон мөрийг засах — ялгааг нь толинд сурна."""
        entry = self._selected_entry()
        if not entry:
            self.history_note.configure(text="Эхлээд мөр сонгоно уу.")
            return
        self._edit_entry(entry)

    def _edit_entry(self, entry: dict) -> None:
        """Түүхийн нэг мөрийг засах цонх (жагсаалтаас ч, Төлөв хуудаснаас ч)."""
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
                self.set_detail(message)
                self.history_note.configure(text=message)
                self._fill_history()
                self._fill_recent()

        Button(editor, "Хадгалах", save, bg=theme.BG).pack(
            anchor="e", padx=theme.PAGE_PAD_X, pady=12
        )
