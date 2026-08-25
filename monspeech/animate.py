"""Хөдөлгөөний цөм.

Tk-д CSS-ийн `transition` гэж байхгүй: өнгө, байрлал бүрийг өөрсдөө кадр
кадраар нь тооцож, `after()`-оор дараалуулна. Тэр ажлыг виджет бүрд давтахын
оронд энд төвлөрүүлэв.

**Гурван дүрэм.**

1. Хөдөлгөөн нь ТӨЛӨВ өөрчлөгдсөнийг хэлнэ — чимэглэл биш. Юу ч
   өөрчлөгдөөгүй бол хөдлөх зүйл алга.
2. Тасалдвал БАЙГАА утгаасаа үргэлжилнэ. Хулгана хурдан нааш цааш
   хөдлөхөд эхнээс нь дахин эхэлбэл товч чичирнэ.
3. Хугацаа нь богино. 200 мс-ээс урт бүхэн ширээний аппад саад болно —
   хэрэглэгч товчоо дарчихсан, интерфейс нь хараахан амжаагүй байх нь
   удаан гэсэн мэдрэмж төрүүлдэг.

Хуудас сэлгэхийг ЗОРИУДААР хөдөлгөөнгүй үлдээв: `Page` бүр `ScrollFrame`
дотор сууж, `<Configure>` бүрд өндрөө дахин тооцдог. Хуудсыг гулсуулбал
тэр тооцоо кадр бүрд давтагдаж, хөдөлгөөн нь өөрөө таталдана. Цэс
солигдсоныг ЦЭС өөрөө хэлнэ — идэвхтэйн зураас ургаж, дэвсгэр нь уусна.
"""

from __future__ import annotations

import time
import tkinter as tk

#: Нэг кадрын хугацаа (мс). ~60 кадр/сек.
FRAME_MS = 16

#: Богино — өнгө, тунгалаг байдал. Хулганы хариу үүнээс удаан байвал
#: «наалдсан» мэт мэдрэгдэнэ.
FAST = 140
#: Дунд — хэмжээ, байрлал (унтраалгын бөмбөлөг, идэвхтэйн зураас).
BASE = 180
#: Цонх гарч ирэх/алга болох.
PANEL = 160

#: Бүх хөдөлгөөнийг нэг дор унтраах. `config["animations"]`-аас тохируулна.
#: Унтраасан үед `Motion` нь зорилгодоо ТЭР ДОР НЬ үсэрнэ — өөрөөр хэлбэл
#: интерфейс ажиллахаа болихгүй, зөвхөн шилжилт нь агшин болно.
enabled = True


def ease_out(t: float) -> float:
    """Хурдан эхэлж, зөөлөн зогсоно (cubic). Хэрэглэгчийн үйлдлийн хариу
    нь ЭХЛЭЭД хурдан байх ёстой — тэгвэл шуурхай мэдрэгдэнэ."""
    inverse = 1.0 - t
    return 1.0 - inverse * inverse * inverse


def mix(first: str, second: str, amount: float) -> str:
    """Хоёр `#rrggbb` өнгийн хооронд `amount` (0..1) хувиар холино.

    Захын утганд ЭХ мөрийг нь буцаана — тооцоолж гаргавал том/жижиг үсэг
    нь өөрчлөгдөж (`#7CD3A8` → `#7cd3a8`), сэдвийн тогтмолтой шууд
    харьцуулах боломжгүй болно.
    """
    if amount <= 0:
        return first
    if amount >= 1:
        return second
    a = tuple(int(first[i : i + 2], 16) for i in (1, 3, 5))
    b = tuple(int(second[i : i + 2], 16) for i in (1, 3, 5))
    return "#" + "".join(
        f"{round(x + (y - x) * amount):02x}" for x, y in zip(a, b, strict=True)
    )


def quantise(value: float, steps: int = 12) -> float:
    """Утгыг шатлуулна — зураг кэшлэдэг зүйлст (унтраалга, товч) хэрэгтэй.

    Тасралтгүй float бүрд шинэ PIL зураг үүсгэвэл кэш хязгааргүй хавдана.
    12 шат нь нүдэнд жигд, кэш нь хязгаартай.
    """
    return round(value * steps) / steps


class Motion:
    """Нэг виджетийн нэг шинжийг зорилго руу нь гулсуулна.

    Утга нь үргэлж 0..1 — өнгө, байрлал, өндөр рүү хөрвүүлэхийг дуудагч
    өөрөө `apply` дотроо хийнэ. Ингэснээр энэ анги ямар ч шинжид тохирно.

    Виджет устсан бол чимээгүй зогсоно: Tk дээр устсан виджет рүү `after`
    төлөвлөвөл `TclError` шидэгддэг ба цонх хаах үед энэ нь элбэг тохиолдол.
    """

    def __init__(self, widget: tk.Misc, apply, value: float = 0.0, ms: int = FAST) -> None:
        self.widget = widget
        self.apply = apply
        self.value = float(value)
        self.ms = ms
        self._job: str | None = None
        self._from = float(value)
        self._target = float(value)
        self._started = 0.0

    # ------------------------------------------------------------------
    def to(self, target: float, ms: int | None = None) -> None:
        """Зорилго руу гулсаж эхэлнэ (яг одоо байгаа утгаасаа)."""
        target = float(target)
        if not enabled or not self._alive():
            self.jump(target)
            return
        if abs(target - self._target) < 0.001 and self._job is not None:
            return  # аль хэдийн тийш явж байна
        if abs(target - self.value) < 0.001:
            self.jump(target)
            return
        self._from = self.value
        self._target = target
        self.ms = ms or self.ms
        self._started = time.monotonic()
        if self._job is None:
            self._step()

    def jump(self, value: float) -> None:
        """Хөдөлгөөнгүй, шууд тавина."""
        self.stop()
        self.value = self._from = self._target = float(value)
        self.apply(self.value)

    def stop(self) -> None:
        if self._job is not None:
            try:
                self.widget.after_cancel(self._job)
            except tk.TclError:  # виджет аль хэдийн устсан
                pass
            self._job = None

    # ------------------------------------------------------------------
    def _alive(self) -> bool:
        try:
            return bool(self.widget.winfo_exists())
        except tk.TclError:
            return False

    def _step(self) -> None:
        self._job = None
        if not self._alive():
            return
        elapsed = (time.monotonic() - self._started) * 1000.0
        share = 1.0 if self.ms <= 0 else min(1.0, elapsed / self.ms)
        self.value = self._from + (self._target - self._from) * ease_out(share)
        self.apply(self.value)
        if share >= 1.0:
            return
        try:
            self._job = self.widget.after(FRAME_MS, self._step)
        except tk.TclError:
            self._job = None


def fade_window(window: tk.Misc, target: float, ms: int = PANEL, on_done=None) -> None:
    """Toplevel-ийн тунгалаг байдлыг гулсуулна (`-alpha`).

    Виджетийн өнгөнөөс ялгаатай нь энэ нь ЖИНХЭНЭ тунгалаг байдал — Windows
    цонхны менежер зурдаг тул дотор нь юу байгаагаас үл хамаарна. Tk дээр
    жинхэнэ уусалт хийж болох цорын ганц газар.
    """
    try:
        current = float(window.attributes("-alpha"))
    except (tk.TclError, ValueError):
        current = 1.0

    def paint(value: float) -> None:
        try:
            window.attributes("-alpha", value)
        except tk.TclError:
            pass
        if on_done is not None and abs(value - target) < 0.001:
            on_done()

    motion = Motion(window, paint, value=current, ms=ms)
    # Лавлагааг цонхон дээр барина — эс бөгөөс хогийн цэвэрлэгч уусалт
    # дуусахаас өмнө `Motion`-ыг устгаж, кадрын гинж тасарна.
    window._fade_motion = motion  # noqa: SLF001 - зориудаар цонхон дээр хадгална
    if not enabled:
        motion.jump(target)
        return
    motion.to(target)
