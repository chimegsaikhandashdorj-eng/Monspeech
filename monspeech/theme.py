"""Дизайны токенууд — "Monspeech Redesign" (sidebar + 7 хуудас) хувилбар.

Өнгө, хэмжээ, фонтыг нэг дор төвлөрүүлснээр цонхны хэсгүүд ижил хэмнэлтэй
байж, дараа нь өнгө солиход нэг л газар засварлана.

**Хоёр сэдэв.** `PALETTES` дотор харанхуй, гэрэлтэй хоёр багц байна.
`apply(нэр)` нь модулийн глобал утгуудыг тэр багцаар сольдог — дуудагч код нь
`theme.BG` гэж уншсан хэвээр, юу ч засах шаардлагагүй.

⚠️ Tk-д өнгө нь виджет ҮҮСЭХ агшинд тогтдог тул `apply()` дуудахад аль хэдийн
байгаа виджетүүд өөрчлөгдөхгүй — цонхыг дахин барих ёстой (`app.rebuild_ui`).

Сэдэв нэмэхэд `PALETTES`-д мөр нэмнэ. Өнгө бүр `tests/test_theme.py`-гийн
харьцааны шалгуурыг давах ёстой — тэр тест сэдэв бүрийг тусад нь шалгана.
"""

from __future__ import annotations

# Токенуудын утгыг доор `apply()` тогтооно. Энд зөвхөн нэрийг нь зарлаж,
# анхны утгыг өгнө — модуль импортлогдонгуут харанхуй сэдэв идэвхжинэ.
DARK = {
    # --- Гадаргуу ---
    "BG": "#14161A",  # хуудасны дэвсгэр
    "PANEL": "#1A1D22",  # карт, жагсаалт
    "PANEL2": "#20242B",  # оролт, чип, keycap
    "MOCK": "#0D0F12",  # "ийм үр дүн гарна" гэсэн жишээний хайрцаг
    "SIDEBAR": "#101216",  # зүүн талын цэс
    "BORDER": "#333842",  # картны хүрээ
    "DIVIDER": "#262A31",  # хэсэг хоорондын шугам
    "ROW_LINE": "#262A31",  # картан дахь мөр хоорондын шугам
    "HOVER": "#20242B",  # хулгана дээгүүр очиход
    "NAV_ACTIVE": "#1E2536",  # идэвхтэй цэсний дэвсгэр
    # --- Текст ---
    "TEXT": "#E9EBEE",
    "MUTED": "#99A0AA",
    "DIM": "#848B94",  # өмнө #7C838D байсан нь 4.07:1 буюу босгоос доогуур
    # --- Өргөлт ---
    "ACCENT": "#567AEB",  # дүүргэлт, градиент — ТЕКСТ болгож ашиглахгүй
    "LINK": "#6485ED",  # товшиж болох текст
    "TOGGLE_ON": "#4A63D8",
    "TOGGLE_OFF": "#2A2F37",
    "KNOB_ON": "#E9EBEE",
    "KNOB_OFF": "#8A9099",
    "OK": "#3DDC84",
    "WARN": "#FFB454",
    "DANGER": "#FF5F56",
    # --- Гарын фокус ---
    "FOCUS": "#8FA8FF",
}

# Гэрэлтэй сэдэв. Харанхуйгаас зүгээр л «эргүүлсэн» биш: цайвар дэвсгэр дээр
# өргөлтийн өнгө хурц харагддаг тул акцент, төлөвийн өнгө бүгд гүнзгийрсэн —
# эс бөгөөс 4.5:1 давахгүй.
LIGHT = {
    "BG": "#F4F5F7",
    "PANEL": "#FFFFFF",
    "PANEL2": "#EDEFF3",
    "MOCK": "#E7E9EE",
    "SIDEBAR": "#EAECF0",
    "BORDER": "#D2D6DE",
    "DIVIDER": "#E1E4EA",
    "ROW_LINE": "#E1E4EA",
    "HOVER": "#E4E7EC",
    "NAV_ACTIVE": "#DCE3F7",
    "TEXT": "#15181D",
    "MUTED": "#4E5561",
    "DIM": "#5E6673",
    "ACCENT": "#2F53C4",
    "LINK": "#2A4CB8",
    "TOGGLE_ON": "#2F53C4",
    "TOGGLE_OFF": "#C6CBD4",
    "KNOB_ON": "#FFFFFF",
    "KNOB_OFF": "#FFFFFF",
    "OK": "#0F793D",
    "WARN": "#8A5200",
    "DANGER": "#B3261E",
    "FOCUS": "#1D3FB0",
}

PALETTES = {"dark": DARK, "light": LIGHT}
DEFAULT_THEME = "dark"

#: Одоо идэвхтэй сэдвийн нэр. `apply()` шинэчилнэ.
name = DEFAULT_THEME


def apply(theme_name: str) -> str:
    """Сэдвийг идэвхжүүлж, идэвхжсэн нэрийг буцаана.

    Танихгүй нэр ирвэл чимээгүй анхны сэдэв рүү буцна — гараар `config.json`
    засаад алдаа бичсэн хүнд апп ажиллахаа болихоос дээр.
    """
    global name
    palette = PALETTES.get(theme_name)
    if palette is None:
        theme_name, palette = DEFAULT_THEME, PALETTES[DEFAULT_THEME]
    globals().update(palette)
    name = theme_name
    return theme_name


apply(DEFAULT_THEME)

# Фокусын хүрээний зузаан — сэдвээс хамаарахгүй.
FOCUS_WIDTH = 2

# Логоны градиент — заалт, төлөвийн баганад ашиглана
GRADIENT = [
    "#29BEF0", "#3EA9F0", "#567AEB", "#6265E9", "#7C4DE8",
    "#9146E7", "#A742E9", "#B63DEB", "#C43AEC",
]

# Роботын өнгө (Төлөв хуудасны бөмбөрцөг)
ROBOT_BLUE = "#1E3AF0"
ROBOT_CYAN = "#35E8F5"
ROBOT_OUTLINE = "#96A3C4"

# --- Фонт ---
UI = ("Segoe UI", 10)  # ~13 px
UI_SMALL = ("Segoe UI", 9)  # ~11.5 px
UI_TINY = ("Segoe UI", 8)  # хэсгийн жижиг гарчиг
UI_TITLE = ("Segoe UI Semibold", 11)
UI_HEAD = ("Segoe UI Semibold", 14)  # хуудасны гарчиг ~19 px
UI_NAV = ("Segoe UI Semibold", 10)
MONO = ("Consolas", 8)
MONO_KEY = ("Consolas", 9)
MONO_BIG = ("Consolas", 15, "bold")  # статистикийн тоо

# --- Хэмжээс ---
WINDOW = (880, 620)
WINDOW_MIN = (640, 560)
SIDEBAR_WIDTH = 208
SIDEBAR_COLLAPSED = 58
# Цонх нарийсахад цэс өөрөө дүрс болж хумигдана. Хоёр босго нь ойролцоо
# хэмжээнд байнга нааш цааш үсрэхээс сэргийлнэ.
SIDEBAR_COLLAPSE_AT = 780
SIDEBAR_EXPAND_AT = 820
# Зайн шатлал — 4 пикселийн алхамтай. Шинэ зай нэмэхдээ эндээс сонгоно;
# гараар шинэ тоо бичвэл хэмнэл аажмаар задарна.
#
# Фонт, радиусыг санаатай энэ шатлалд оруулаагүй: Windows-ийн UI фонт нь
# цэгээр (8–14 pt) хэмжигддэг бөгөөд модуль харьцаагаар өсгөвөл 12.5 pt гэх
# мэт бүдэг хэмжээ гарна. Радиус нь мөн өөрийн гэсэн ладдертай (10/7/5).
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16
SPACE_XL = 20
SPACE_2XL = 24

SCALE = (SPACE_XS, SPACE_SM, SPACE_MD, SPACE_LG, SPACE_XL, SPACE_2XL)

PAGE_PAD_X = SPACE_2XL  # 24 (өмнө 22 — шатлалд оруулав)
PAGE_PAD_Y = SPACE_XL  # 20
GAP = SPACE_MD  # 12

# --- Дугуйрал ---
# `RoundedBox` нь агуулгаа хэвтээ чиглэлд радиусын зайгаар доторшуулдаг тул
# картын мөрүүдийн дотоод зай нь радиусаар багасна (16 = RADIUS + CARD_PAD_X).
RADIUS = 10  # карт, жагсаалт
RADIUS_SMALL = 7  # товч, оролт, мөр
RADIUS_TINY = 5  # keycap, жижиг тэмдэг
# Картын мөрийн дотоод зай. `RADIUS`-тай нийлж жинхэнэ зай болно
# (10 + 6 = 16) тул энэ нь өөрөө шатлалын гишүүн байх шаардлагагүй —
# НИЙЛБЭР нь шатлалд байх ёстой.
CARD_PAD_X = SPACE_LG - RADIUS  # 6 → нийлбэр 16 = SPACE_LG
CARD_PAD_Y = SPACE_MD  # 12

# Төлөвийн баганууд (overlay капсул)
BAR_COUNT = 9
BAR_WIDTH = 3
BAR_GAP = 3
BAR_MAX = 26
BAR_MIN = 4

# Оролтын түвшний заалт (Яриа хуудас)
METER_SEGMENTS = 30
METER_HEIGHT = 18
