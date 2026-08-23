"""API түлхүүрийг Windows DPAPI-гаар шифрлэж хадгалах.

Яагаад: `config.json` нь `%AppData%` дотор ил харагддаг тул түлхүүрийг
ил текстээр бичвэл файлыг нээсэн хүн бүрт (backup sync, хуваалцсан
компьютер) нууц нь задрана. Windows-ийн DPAPI нь тухайн хэрэглэгчийн
нууц үгтэй холбоотой түлхүүрээр шифрлэдэг — ижил компьютер дээр өөр
хэрэглэгч, эсвэл файл хуулбарлагдсан өөр компьютер дээр тайлах боломжгүй.

Шийдэл: шинэ dependencyгүй (`ctypes` + `crypt32.dll`), шифрлэсэн өгөгдөл
нь `base64(dpapi-blob)` хэлбэрээр config-д хадгалагдана. Файлын хэлбэр:

    "stt_key": ""                      → түлхүүр байхгүй
    "stt_key": "dpapi:AbC123…"         → DPAPI-гаар шифрлэгдсэн
    "stq_key": "sk-…"                  → ХУУЧИН ил тектэй файл (доорхоор
                                          автоматаар шилжүүлэгдэнэ)

DPAPI бүтэлгүйтвэл (бүртгэлийн профайл эвдэрсэн гэх мэт) `decrypt` нь
`None` буцаана — дуудагч нь хоосон түлхүүртэй апп эхэлж, хэрэглэгч
түлхүүрээ дахин оруулна. Апп унахаас бүр дээр.
"""

from __future__ import annotations

import base64
import ctypes
from ctypes import wintypes

# config.json доторх шифрлэсэн утгын урд тэмдэглэгээ
PREFIX = "dpapi:"

# CRYPTPROTECT_UI_FORBIDDEN — сервер/үйлчилгээний хүрээнд UI дуудахгүй
_UI_FORBIDDEN = 0x1

_crypt32 = None


def _dll():
    """crypt32-ийн гарын үсгийг нэг удаа тодорхойлно."""
    global _crypt32
    if _crypt32 is None:
        dll = ctypes.WinDLL("crypt32")
        dll.CryptProtectData.argtypes = [
            ctypes.POINTER(_BLOB), wintypes.LPCWSTR, wintypes.LPVOID,
            wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
            ctypes.POINTER(_BLOB),
        ]
        dll.CryptProtectData.restype = wintypes.BOOL
        dll.CryptUnprotectData.argtypes = [
            ctypes.POINTER(_BLOB), ctypes.POINTER(wintypes.LPWSTR),
            wintypes.LPVOID, wintypes.DWORD, wintypes.LPVOID,
            wintypes.DWORD, ctypes.POINTER(_BLOB),
        ]
        dll.CryptUnprotectData.restype = wintypes.BOOL
        _crypt32 = dll
    return _crypt32


class _BLOB(ctypes.Structure):
    """CRYPT_INTEGER_BLOB — DPAPI-ийн өгөгдөл дамжуулах бүтэц."""

    _fields_ = [
        ("cbData", wintypes.DWORD),
        ("pbData", ctypes.POINTER(ctypes.c_byte)),
    ]


def _to_blob(data: bytes) -> _BLOB:
    buffer = ctypes.create_string_buffer(data, len(data))
    return _BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte)))


def _from_blob(blob: _BLOB) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def encrypt(plain: str) -> str:
    """Ил текстийг `dpapi:…` хэлбэрийн шифртэй мөр болгоно."""
    if not plain:
        return ""
    data = plain.encode("utf-8")
    out = _BLOB()
    ok = _dll().CryptProtectData(
        ctypes.byref(_to_blob(data)), None, None, 0, None, _UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        raise OSError("DPAPI шифрлэлт бүтсэнгүй")
    encoded = base64.b64encode(_from_blob(out)).decode("ascii")
    ctypes.windll.kernel32.LocalFree(out.pbData)
    return PREFIX + encoded


def decrypt(stored: str) -> str | None:
    """`dpapi:…` мөрийг тайлана. Бүтэлгүйтвэл `None` (апп унах ёсгүй)."""
    if not stored or not stored.startswith(PREFIX):
        return None
    try:
        raw = base64.b64decode(stored[len(PREFIX):], validate=True)
    except (ValueError, TypeError):
        return None
    out = _BLOB()
    ok = _dll().CryptUnprotectData(
        ctypes.byref(_to_blob(raw)), None, None, 0, None, _UI_FORBIDDEN,
        ctypes.byref(out),
    )
    if not ok:
        return None
    try:
        return _from_blob(out).decode("utf-8")
    except UnicodeDecodeError:
        return None
    finally:
        ctypes.windll.kernel32.LocalFree(out.pbData)


def is_encrypted(value: str) -> bool:
    return bool(value) and value.startswith(PREFIX)
