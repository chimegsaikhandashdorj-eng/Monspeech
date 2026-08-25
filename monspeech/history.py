"""Сүүлийн оруулгыг санаж, буцаах (undo).

Текст буруу цонхонд орох нь бодитоор тохиолддог тул хамгийн сүүлд шивсэн
тэмдэгтийн тоог мэдэж, яг тэр хэмжээгээр устгах боломжтой байх ёстой.
"""

from __future__ import annotations

import threading
import time

# Үүнээс хуучин оруулгыг буцаахыг зөвшөөрөхгүй (хэрэглэгч аль хэдийн өөр зүйл
# бичсэн байх магадлалтай тул санамсаргүйгээр буруу текст устгахгүй)
MAX_AGE = 120.0


class InsertionHistory:
    """Оруулсан текстүүдийг дараалалд нь санана."""

    def __init__(self, limit: int = 20, max_age: float = MAX_AGE) -> None:
        self.limit = limit
        self.max_age = max_age
        self._items: list[tuple[str, float]] = []
        self._lock = threading.Lock()

    def record(self, text: str, when: float | None = None) -> None:
        if not text:
            return
        with self._lock:
            self._items.append((text, when if when is not None else time.monotonic()))
            while len(self._items) > self.limit:
                self._items.pop(0)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    @property
    def depth(self) -> int:
        with self._lock:
            return len(self._items)

    def last(self, now: float | None = None) -> str | None:
        """Сүүлийн оруулгыг УСТГАЛГҮЙ харна («давт», «хуулж ав» хоёрт).

        Хэт хуучирсан бол `None` — буцаахтай ижил хугацааны хязгаар үйлчилнэ.
        """
        moment = now if now is not None else time.monotonic()
        with self._lock:
            if not self._items:
                return None
            text, when = self._items[-1]
            if moment - when > self.max_age:
                return None
        return text

    def take_last(self, now: float | None = None) -> tuple[str, int] | None:
        """Сүүлийн оруулгыг гаргаж, `(текст, устгах тэмдэгтийн тоо)` буцаана.

        Хэт хуучирсан эсвэл байхгүй бол `None`.
        """
        moment = now if now is not None else time.monotonic()
        with self._lock:
            if not self._items:
                return None
            text, when = self._items[-1]
            if moment - when > self.max_age:
                self._items.clear()
                return None
            self._items.pop()
        return text, len(text)
