"""Кирилл гаралтыг Windows консол дээр ажиллуулах.

Windows дээр `sys.stdout` нь анхнаасаа cp1252 байдаг тул тестийн монгол хэл
дээрх шошго хэвлэхэд `UnicodeEncodeError` шидээд тест бүхэлдээ уначихдаг —
шалгаж буй код нь бүрэн зөв атал уналт харагдах нь хамгийн төөрөгдүүлсэн
хэлбэрийн алдаа. Импортлосон даруйдаа гаралтыг UTF-8 болгоно.

Тест бүр гуравдагч сангүй, бие даан ажилладаг байх ёстой тул энэ нь ганц
файлын жижиг модуль хэвээр — тестийн жинхэнэ туслах сан болгож өсгөх ёсгүй.
"""

from __future__ import annotations

import sys

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")
