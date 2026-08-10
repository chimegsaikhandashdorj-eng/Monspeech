"""Ганц хуулбар барих ба ажлын ширээний дүрсээс "цонхоо нээ" гэж дуудах.

Ажиллаж байхад дүрс дээр дахин товшиход шинэ хуулбар нээх нь товчлуурыг
давхардуулж, микрофоныг булаалддаг. Оронд нь нэрлэсэн Windows event ашиглан
ажиллаж байгаа хуулбарт дохио өгөөд шинэ процесс шууд гарна.
"""

from __future__ import annotations

import ctypes
import threading
from ctypes import wintypes

from .logging_setup import get as get_logger

log = get_logger("instance")

MUTEX_NAME = "Global\\MonspeechSingleInstance"
SHOW_EVENT_NAME = "Local\\MonspeechShowWindow"
EVENT_MODIFY_STATE = 0x0002
WAIT_OBJECT_0 = 0x00000000
ERROR_ALREADY_EXISTS = 183
ASFW_ANY = -1  # фокус авах эрхийг дурын процесст өгнө
SHOW_POLL_MS = 400  # дохио хүлээхдээ ийм алхмаар сэрнэ (гарахад л хэрэгтэй)


def already_running() -> bool:
    """Хоёр хуулбар зэрэг ажиллавал товчлуур давхар ажиллана."""
    try:
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return kernel32.GetLastError() == ERROR_ALREADY_EXISTS
    except OSError:
        return False


def _kernel32():
    """Дохионы функцуудын гарын үсгийг тодорхойлсон kernel32."""
    dll = ctypes.windll.kernel32
    dll.CreateEventW.restype = wintypes.HANDLE
    dll.CreateEventW.argtypes = [
        wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR
    ]
    dll.OpenEventW.restype = wintypes.HANDLE
    dll.OpenEventW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    dll.SetEvent.argtypes = [wintypes.HANDLE]
    dll.CloseHandle.argtypes = [wintypes.HANDLE]
    dll.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    return dll


def request_show() -> bool:
    """Ажиллаж байгаа хуулбарт "цонхоо нээ" гэж хэлнэ."""
    try:
        dll = _kernel32()
        handle = dll.OpenEventW(EVENT_MODIFY_STATE, False, SHOW_EVENT_NAME)
        if not handle:
            return False
        try:
            # Windows зөвхөн урд байгаа процесст фокус авахыг зөвшөөрдөг —
            # тэр эрхээ ажиллаж байгаа хуулбартаа шилжүүлнэ
            ctypes.windll.user32.AllowSetForegroundWindow(ASFW_ANY)
            return bool(dll.SetEvent(handle))
        finally:
            dll.CloseHandle(handle)
    except OSError:
        return False


class ShowListener:
    """Ажлын ширээний дүрс дээр дахин товшиход цонхыг урд нь гаргана.

    Шинэ процесс `request_show()`-оор нэрлэсэн дохио өгөөд шууд гарна; энэ
    thread дохиог сонсоод аппын цонхыг нээх эвент илгээнэ.
    """

    def __init__(self, on_signal) -> None:
        self._on_signal = on_signal
        self._handle = None
        self._thread: threading.Thread | None = None
        self._running = False

    def start(self) -> None:
        try:
            dll = _kernel32()
            self._handle = dll.CreateEventW(None, False, False, SHOW_EVENT_NAME)
        except OSError as exc:  # noqa: BLE001 - дохиогүй ч апп ажиллана
            log.error("цонх нээх дохио үүсгэгдсэнгүй: %s", exc)
            return
        if not self._handle:
            log.error("цонх нээх дохио үүсгэгдсэнгүй")
            return
        self._running = True
        self._thread = threading.Thread(target=self._wait_loop, daemon=True)
        self._thread.start()

    def _wait_loop(self) -> None:
        dll = ctypes.windll.kernel32
        while self._running:
            handle = self._handle
            if handle is None:
                return
            if dll.WaitForSingleObject(handle, SHOW_POLL_MS) == WAIT_OBJECT_0:
                if self._running:
                    self._on_signal()

    def stop(self) -> None:
        self._running = False
        handle, self._handle = self._handle, None
        if not handle:
            return
        dll = ctypes.windll.kernel32
        dll.SetEvent(handle)  # хүлээлтийг тэр дор нь тасална
        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None
        dll.CloseHandle(handle)
