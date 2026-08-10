"""Дизайны токенууд — "Monspeech Window Directions" баримтын 2c чиглэл.

Өнгө, хэмжээ, фонтыг нэг дор төвлөрүүлснээр цонхны хэсгүүд ижил хэмнэлтэй
байж, дараа нь өнгө солиход нэг л газар засварлана.
"""

from __future__ import annotations

# --- Гадаргуу ---
BG = "#14161A"  # цонхны дэвсгэр
PANEL = "#1A1D22"  # оролт, жагсаалт, keycap
BORDER = "#333842"  # оролтын хүрээ
DIVIDER = "#262A31"  # хэсэг хоорондын шугам
ROW_LINE = "#1B1E23"  # мөр хоорондын нарийн шугам
HOVER = "#20242B"  # хулгана дээгүүр очиход

# --- Текст ---
TEXT = "#E9EBEE"
MUTED = "#99A0AA"
DIM = "#7C838D"

# --- Өргөлт ---
ACCENT = "#567AEB"  # холбоос, идэвхтэй заалт, түвшний зураас
TOGGLE_ON = "#4A63D8"
TOGGLE_OFF = "#2A2F37"
KNOB_ON = "#FFFFFF"
KNOB_OFF = "#8A9099"
OK = "#3DDC84"
WARN = "#FFB454"
DANGER = "#FF5F56"

# Логоны градиент — төлөвийн баганад ашиглана
GRADIENT = [
    "#29BEF0", "#3EA9F0", "#567AEB", "#6265E9", "#7C4DE8",
    "#9146E7", "#A742E9", "#B63DEB", "#C43AEC",
]

# --- Фонт ---
UI = ("Segoe UI", 10)  # ~13 px
UI_SMALL = ("Segoe UI", 9)  # ~11.5 px
UI_TITLE = ("Segoe UI Semibold", 11)
MONO = ("Consolas", 8)  # хэсгийн гарчиг, техник мэдээлэл
MONO_KEY = ("Consolas", 9)  # keycap

# --- Хэмжээс ---
WINDOW = (470, 660)
WINDOW_MIN = (430, 520)
PAD_X = 18  # хэсгийн хажуугийн зай
SECTION_GAP = 14
LABEL_WIDTH = 12  # зүүн талын шошгын багана (тэмдэгтээр)
HEADER_HEIGHT = 44
FOOTER_HEIGHT = 28

# Төлөвийн баганууд
BAR_COUNT = 9
BAR_WIDTH = 3
BAR_GAP = 3
BAR_MAX = 26
BAR_MIN = 4
