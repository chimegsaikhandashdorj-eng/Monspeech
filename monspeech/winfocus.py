"""Цонхны фокус — текст зөв цонхонд очихыг батална."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes


class _GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("hwndActive", wintypes.HWND),
        ("hwndFocus", wintypes.HWND),
        ("hwndCapture", wintypes.HWND),
        ("hwndMenuOwner", wintypes.HWND),
        ("hwndMoveSize", wintypes.HWND),
        ("hwndCaret", wintypes.HWND),
        ("rcCaret", wintypes.RECT),
    ]


def cursor_position() -> tuple[int, int] | None:
    """Хулганы заагчийн байрлал."""
    try:
        point = wintypes.POINT()
        if ctypes.windll.user32.GetCursorPos(ctypes.byref(point)):
            return point.x, point.y
    except OSError:
        pass
    return None


def caret_position() -> tuple[int, int] | None:
    """Идэвхтэй цонхны текстийн курсорын байрлал (доод зах).

    Notepad, Word, Explorer зэрэг сонгодог цонхонд ажиллана. Chrome, UWP
    зэрэг өөрийн зурдаг апп мэдээлэл өгдөггүй тул None буцаана.
    """
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        info = _GUITHREADINFO()
        info.cbSize = ctypes.sizeof(info)
        if not user32.GetGUIThreadInfo(thread_id, ctypes.byref(info)):
            return None
        if not info.hwndCaret:
            return None
        point = wintypes.POINT(info.rcCaret.left, info.rcCaret.bottom)
        if not user32.ClientToScreen(info.hwndCaret, ctypes.byref(point)):
            return None
        if point.x <= 0 and point.y <= 0:
            return None
        return point.x, point.y
    except OSError:
        return None


def anchor_position() -> tuple[int, int]:
    """Заалт харуулах цэг: текстийн курсор, олдохгүй бол хулгана."""
    return caret_position() or cursor_position() or (100, 100)


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def monitor_work_area(x: int, y: int) -> tuple[int, int, int, int]:
    """Өгсөн цэгийг агуулах дэлгэцийн ажлын талбай (зүүн, дээд, баруун, доод).

    Tk-ийн `winfo_screenwidth` нь зөвхөн үндсэн дэлгэцийг мэддэг тул олон
    дэлгэцтэй үед Win32-оос асуух шаардлагатай.
    """
    try:
        user32 = ctypes.windll.user32
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]
        user32.MonitorFromPoint.restype = ctypes.c_void_p
        handle = user32.MonitorFromPoint(wintypes.POINT(x, y), 2)  # NEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if handle and user32.GetMonitorInfoW(ctypes.c_void_p(handle), ctypes.byref(info)):
            work = info.rcWork
            return work.left, work.top, work.right, work.bottom
    except OSError:
        pass
    # Боломжгүй бол виртуал дэлгэцийн бүх хүрээг ашиглана
    try:
        metrics = ctypes.windll.user32.GetSystemMetrics
        left, top = metrics(76), metrics(77)
        return left, top, left + metrics(78), top + metrics(79)
    except OSError:
        return 0, 0, 1920, 1080


def place_window(hwnd, x: int, y: int) -> bool:
    """Цонхыг дэлгэцийн координатаар байрлуулна (сөрөг утга ч зөв ажиллана)."""
    if not hwnd:
        return False
    try:
        HWND_TOPMOST = -1
        SWP_NOSIZE, SWP_NOACTIVATE = 0x0001, 0x0010
        return bool(
            ctypes.windll.user32.SetWindowPos(
                ctypes.c_void_p(hwnd), ctypes.c_void_p(HWND_TOPMOST),
                int(x), int(y), 0, 0, SWP_NOSIZE | SWP_NOACTIVATE,
            )
        )
    except OSError:
        return False


def foreground_window():
    try:
        return ctypes.windll.user32.GetForegroundWindow()
    except OSError:
        return None


def window_title(hwnd) -> str:
    try:
        buf = ctypes.create_unicode_buffer(512)
        ctypes.windll.user32.GetWindowTextW(hwnd, buf, 512)
        return buf.value
    except OSError:
        return ""


def activate(hwnd) -> bool:
    """Цонхыг идэвхжүүлнэ.

    Windows нь идэвхгүй процессоос SetForegroundWindow дуудахыг хориглодог тул
    хэд хэдэн аргыг дараалан оролдоно.
    """
    if not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        if not user32.IsWindow(hwnd):
            return False
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        if user32.SetForegroundWindow(hwnd) and user32.GetForegroundWindow() == hwnd:
            return True

        current = kernel32.GetCurrentThreadId()
        for _ in range(3):
            # ALT-ыг зөвхөн "суллах" эвентээр дарамдана: foreground түгжээг
            # тайлдаг ба keydown байхгүй тул цэс нээгдэхгүй.
            user32.keybd_event(0x12, 0, 0x0002, 0)  # VK_MENU, KEYEVENTF_KEYUP

            threads = set()
            for other in (user32.GetForegroundWindow(), hwnd):
                tid = user32.GetWindowThreadProcessId(other, None)
                if tid and tid != current:
                    threads.add(tid)
            attached = [t for t in threads if user32.AttachThreadInput(current, t, True)]
            try:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.SetActiveWindow(hwnd)
            finally:
                for tid in attached:
                    user32.AttachThreadInput(current, tid, False)
            if user32.GetForegroundWindow() == hwnd:
                return True

            user32.SwitchToThisWindow(hwnd, True)
            if user32.GetForegroundWindow() == hwnd:
                return True
            time.sleep(0.06)
        return False
    except OSError:
        return False


def probably_blocked(hwnd) -> bool:
    """Цонх өндөр эрхтэй (админ) процессынх эсэх.

    Windows-ийн UIPI нь бага эрхтэй процессоос өндөр эрхтэй цонх руу оролт
    илгээхийг хаадаг — текст чимээгүйгээр ордоггүй. Үүнийг урьдчилан таньж
    хэрэглэгчид хэлэх нь "юу ч болсонгүй" гэж эргэлзэхээс дээр.
    """
    if not hwnd:
        return False
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        PROCESS_QUERY_INFORMATION = 0x0400
        ERROR_ACCESS_DENIED = 5
        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION, False, pid.value)
        if handle:
            kernel32.CloseHandle(handle)
            return False
        return kernel32.GetLastError() == ERROR_ACCESS_DENIED
    except OSError:
        return False


class TargetWindow:
    """Товч дарсан агшны цонхыг тогтоож, текст очих хаяг болгож хадгална."""

    def __init__(self) -> None:
        self.hwnd = None

    def remember(self, skip=None) -> None:
        hwnd = foreground_window()
        if hwnd and hwnd != skip:
            self.hwnd = hwnd

    def title(self) -> str:
        return window_title(self.hwnd) if self.hwnd else ""

    def blocked(self) -> bool:
        return probably_blocked(self.hwnd)

    def ensure(self) -> bool:
        """Текст буулгахын өмнө зорилтот цонх идэвхтэй эсэхийг батална."""
        if not self.hwnd:
            return False
        if foreground_window() == self.hwnd:
            return True
        return activate(self.hwnd)
