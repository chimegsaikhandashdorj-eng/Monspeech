"""«Яриа» хуудсан дахь танигчийн тохиргооны хэсэг.

Цонхны бусад хэсэг зөвхөн НЭГ зүйл мэднэ: энэ картыг байрлуулаад, тохиргоо
өөрчлөгдөхөд дуудагдах хаалт өгнө. Аль танигч сонгогдсон, нэмэлт талбарууд
хэзээ гарч ирэх, юу үнэхээр өөрчлөгдсөн зэрэг нь бүгд энд.

Өмнө нь эдгээр нь `ControlWindow` дээр найман талбар (`stt_var`, `stt_vars`,
`stt_extra`, `_stt_titles`, `_stt_names`, `_stt_shown`, `_stt_applied`,
`_stt_tail`) эзэлж байсан — цонхны төлөв нь тэр хэмжээгээр бага болов.
"""

from __future__ import annotations

import tkinter as tk

from . import recognizer, theme
from .widgets import Card, combo, rounded_entry

#: Зөвхөн өөрийн үйлчилгээ сонгосон үед гарах талбарууд.
FIELDS = [
    ("stt_url", "Хаяг", "…/v1/audio/transcriptions"),
    ("stt_model", "Загвар", "Үйлчилгээний зааж өгсөн нэр"),
    ("stt_key", "API түлхүүр", "Шаардахгүй сервер бол хоосон"),
]


class SttCard:
    """Танигч сонгох цэс ба түүний нэмэлт талбарууд.

    `on_change(values)` нь тохиргоо ҮНЭХЭЭР өөрчлөгдсөн үед л дуудагдана —
    талбараас гармагц бүрд биш.
    """

    def __init__(self, page, cfg, on_change) -> None:
        self.cfg = cfg
        self._on_change = on_change

        names = recognizer.titles()
        self._titles = dict(names)
        self._names = {title: name for name, title in names}

        card = Card(page.body)
        _, holder = card.row("Танигч", "Google нь түлхүүргүй, хааяа тасалдаж болно")
        self.provider_var = tk.StringVar(
            value=self._titles.get(cfg["stt_provider"], names[0][1])
        )
        combo(
            holder, self.provider_var, [title for _, title in names], self._selected
        )
        # Шулуун байх нь: анхны танигч бол бүх хэрэглэгчид нийтлэг задгай
        # түлхүүр дээр сууна. Хязгаарт хүрэх өдөр хүн бүрт зэрэг цохино тул
        # яагаад тасарснаа урьдчилан мэдэж байвал өөрийн түлхүүр рүү шилжинэ.
        card.note(
            "Анхны танигч нь бүх хэрэглэгчид нийтлэг түлхүүр ашигладаг тул "
            "ачаалал ихсэх үед түр тасалдаж болно. Тогтвортой ажиллуулахыг "
            "хүсвэл өөрийн үйлчилгээ сонгоод үнэгүй түлхүүрээ оруулна уу."
        )

        # Тусдаа карт — сонголтоос хамааран харагдана/нуугдана
        self._shown = False
        self.extra = Card(page.body, pad=False)
        self.vars: dict[str, tk.StringVar] = {}
        for key, title, desc in FIELDS:
            _, holder = self.extra.row(title, desc)
            variable = tk.StringVar(value=str(cfg[key]))
            self.vars[key] = variable
            self._field(holder, variable, secret=key == "stt_key")
        self.extra.note("Түлхүүр Windows DPAPI-гаар шифрлэгдэж хадгалагдана")

        # Нэмэлт карт хаана орохыг тэмдэглэх зай — `before=` үүнийг заана
        self._tail = page.spacer()
        self._applied = self.values()
        self.sync()

    # ------------------------------------------------------------------
    def values(self) -> dict[str, str]:
        """Одоогийн сонголтыг тохиргооны түлхүүрүүд болгож буцаана."""
        # Анхны танигчийн нэрийг гараар бичихгүй — `recognizer` дээр нэг эх
        # сурвалж бий. Хоёр газарт бичвэл анхны утга солиход салж эхэлнэ.
        values = {
            "stt_provider": self._names.get(
                self.provider_var.get(), recognizer.DEFAULT_PROVIDER
            )
        }
        for key, variable in self.vars.items():
            values[key] = variable.get().strip()
        return values

    def sync(self) -> None:
        """Нэмэлт талбаруудыг харуулах/нуух.

        Төлөв нь аль хэдийн зөв бол юу ч хийхгүй: багцлалт өөрчлөх нь фокусын
        эвент төрүүлдэг ба тэр нь эргээд энэ функцийг дуудвал цонх мөчлөгт
        орж гацна.
        """
        wanted = (
            self._names.get(self.provider_var.get(), recognizer.DEFAULT_PROVIDER)
            != recognizer.DEFAULT_PROVIDER
        )
        if wanted == self._shown:
            return
        self._shown = wanted
        if wanted:
            self.extra.pack(
                fill="x", padx=theme.PAGE_PAD_X, pady=(0, theme.GAP),
                before=self._tail,
            )
        else:
            self.extra.pack_forget()

    # ------------------------------------------------------------------
    def _field(self, parent, variable, secret: bool = False) -> tk.Entry:
        """Тохиргооны текстийн талбар — гармагц хадгална."""
        box, entry = rounded_entry(
            parent, variable, width=24, font=theme.UI_SMALL, secret=secret
        )
        box.pack()
        # Бичих бүрт биш, талбараас гармагц (эсвэл Enter дарахад) хадгална
        entry.bind("<FocusOut>", lambda _e: self._changed())
        entry.bind("<Return>", lambda _e: self._changed())
        return entry

    def _selected(self) -> None:
        """Танигч солигдлоо — талбаруудыг тааруулаад хэрэглэнэ."""
        self.sync()
        self._changed()

    def _changed(self) -> None:
        """FocusOut нь хуудас солиход ч дуудагддаг тул үнэхээр өөрчлөгдсөн
        үед л танигчийг дахин босгоно."""
        values = self.values()
        if values == self._applied:
            return
        self._applied = values
        self._on_change(values)
