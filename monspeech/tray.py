"""Системийн tray дүрс — аппыг далд ажиллуулах."""

from __future__ import annotations

import threading
from pathlib import Path

try:
    import pystray
    from PIL import Image, ImageDraw

    AVAILABLE = True
except ImportError:  # pystray/Pillow суугаагүй ч апп ажиллана
    AVAILABLE = False

LOGO_PATH = Path(__file__).resolve().parent.parent / "assets" / "monspeech.png"


# Дизайны 1b: дугуй булантай дөрвөлжин дээр 4 багана.
# Бүтэн долгионы логог 16 px хүртэл багасгахад танигдахаа больдог тул
# tray-д хялбаршуулсан тэмдэг ашиглана — заалттай нэг гэр бүл.
BAR_COLOURS = ["#29BEF0", "#567AEB", "#7C4DE8", "#C43AEC"]
BAR_HEIGHTS = [16, 32, 24, 12]
IDLE_COLOUR = "#4A5058"
PANEL = "#191C21"
SUPERSAMPLE = 4


def _make_image(active: bool):
    """Tray тэмдэг: сонсож байхад градиент, амарч байхад саарал."""
    size = 64
    scale = SUPERSAMPLE
    img = Image.new("RGBA", (size * scale, size * scale), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1), radius=14 * scale, fill=PANEL
    )

    width, gap = 5 * scale, 4 * scale
    span = len(BAR_HEIGHTS) * width + (len(BAR_HEIGHTS) - 1) * gap
    left = (size * scale - span) / 2
    centre = size * scale / 2
    for index, height in enumerate(BAR_HEIGHTS):
        x = left + index * (width + gap)
        half = height * scale / 2
        colour = BAR_COLOURS[index] if active else IDLE_COLOUR
        draw.rounded_rectangle(
            (x, centre - half, x + width, centre + half), radius=width / 2, fill=colour
        )
    return img.resize((size, size), Image.LANCZOS)


class Tray:
    """pystray дүрсийг тусдаа thread дээр ажиллуулна.

    Хэрэглэгч tray-г тохиргооноос асааж унтраадаг тул `start()`/`stop()` нь
    аппын дундуур ч дуудагдана. pystray-ийн Icon нь зогссоны дараа дахин
    ажилладаггүй тул асаах бүрд шинээр үүсгэнэ.
    """

    def __init__(self, on_toggle, on_show, on_quit) -> None:
        self._on_toggle = on_toggle
        self._on_show = on_show
        self._on_quit = on_quit
        self._active = False
        self.icon = None
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        """Дүрс үнэхээр цагны хажууд харагдаж байна уу."""
        return bool(self.icon and self._thread and self._thread.is_alive())

    def _build_icon(self):
        menu = pystray.Menu(
            pystray.MenuItem("Эхлүүлэх / Зогсоох", lambda *_: self._on_toggle(), default=True),
            pystray.MenuItem("Цонх нээх", lambda *_: self._on_show()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Гарах", lambda *_: self._on_quit()),
        )
        return pystray.Icon("Monspeech", _make_image(self._active), "Monspeech", menu)

    def start(self) -> None:
        if not AVAILABLE or self.running:
            return
        self.icon = self._build_icon()
        self._thread = threading.Thread(target=self.icon.run, daemon=True)
        self._thread.start()

    def set_active(self, active: bool) -> None:
        self._active = active
        if not self.icon:
            return
        try:
            self.icon.icon = _make_image(active)
            self.icon.title = "Monspeech — сонсож байна" if active else "Monspeech"
        except Exception:  # noqa: BLE001 - tray нь хоёрдогч, апп зогсоохгүй
            pass

    def notify(self, message: str, title: str = "Monspeech") -> None:
        """Цонх далд байхад мэдэгдэл харуулна."""
        if not self.icon:
            return
        try:
            self.icon.notify(message, title)
        except Exception:  # noqa: BLE001 - бүх системд дэмжигдэхгүй байж болно
            pass

    def stop(self) -> None:
        if self.icon:
            try:
                self.icon.stop()
            except Exception:  # noqa: BLE001
                pass
        if self._thread:
            self._thread.join(timeout=1.0)
        self.icon = None
        self._thread = None
