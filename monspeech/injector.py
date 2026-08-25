"""Текстийг идэвхтэй цонхны курсор байгаа газарт оруулах."""

from __future__ import annotations

import threading
import time

import pyperclip
from pynput.keyboard import Controller, Key, KeyCode

_keyboard = Controller()
_lock = threading.Lock()

# Ctrl+V-г заавал виртуал товчийн кодоор явуулна. Тэмдэгтээр ("v") илгээвэл
# pynput нь Unicode оролт болгодог бөгөөд кирилл гарын layout (mn-MN) дээр
# Ctrl-тэй хослохгүй — зүгээр л "v" үсэг бичигдэнэ.
_V_KEY = KeyCode.from_vk(0x56)


def _tap(*keys) -> None:
    """Товчлууруудыг зэрэг дарж, буцаан суллана."""
    for key in keys:
        _keyboard.press(key)
    for key in reversed(keys):
        _keyboard.release(key)


# Backspace бүрийн хооронд амрах хугацаа. Огт завсаргүй илгээвэл зарим апп
# (Word, хөтчийн засварлагч) товчийг алгасдаг; 10 мс нь 100 тэмдэгт устгахад
# бүтэн секунд зарцуулдаг байсан тул завсрыг богиносгож, урт устгалд бүр
# бүлэглэж илгээнэ.
BACKSPACE_GAP = 0.002
BACKSPACE_BURST = 20  # ийм олон тутамд нэг удаа арай уртаар амарна


def _backspace(count: int) -> None:
    for index in range(count):
        _tap(Key.backspace)
        time.sleep(0.02 if index and index % BACKSPACE_BURST == 0 else BACKSPACE_GAP)


def insert_text(
    text: str,
    restore_clipboard: bool = True,
    backspaces: int = 0,
    mode: str = "paste",
) -> None:
    """Тохиргооны дагуу paste эсвэл шууд бичих аргаар оруулна.

    Түгжээг ЭНД, бүх ажлын турш барина. Устгах ба бичих хоёрыг тусад нь
    түгжвэл хооронд нь өөр thread шургалж болно: дамжлага үр дүнгээ буулгаж
    байх зуур хэрэглэгч «буцаа» дарвал (`app._deliver` тус бүрдээ шинэ thread
    үүсгэдэг) устгалт нэгнийх, бичилт нөгөөгийнх болж текст эвдэрнэ.
    """
    with _lock:
        if mode == "type":
            if backspaces:
                _backspace(backspaces)
            _type(text)
        else:
            _paste(text, restore_clipboard, backspaces)


def paste_text(text: str, restore_clipboard: bool = True, backspaces: int = 0) -> None:
    """Clipboard-аар дамжуулж Ctrl+V хийнэ."""
    with _lock:
        _paste(text, restore_clipboard, backspaces)


def _paste(text: str, restore_clipboard: bool, backspaces: int) -> None:
    """Түгжээг дуудагч барьсан гэж үзнэ.

    Кирилл болон бусад Unicode тэмдэгт найдвартай ордог тул шууд
    "бичих"-ээс илүү энэ аргыг үндсэн болгосон. `backspaces` нь цэг
    таслалын өмнөх илүү зайг устгахад хэрэглэгдэнэ.
    """
    if not text and not backspaces:
        return
    if backspaces:
        _backspace(backspaces)
    if not text:
        return
    old = None
    if restore_clipboard:
        try:
            old = pyperclip.paste()
        except pyperclip.PyperclipException:
            old = None
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException:
        # Clipboard-ыг өөр програм түгжсэн бол шууд бичихийг оролдоно.
        _keyboard.type(text)
        return
    time.sleep(0.03)
    _tap(Key.ctrl, _V_KEY)
    time.sleep(0.25)
    if restore_clipboard and old is not None:
        try:
            pyperclip.copy(old)
        except pyperclip.PyperclipException:
            pass


def copy_to_clipboard(text: str) -> bool:
    """Текстийг clipboard руу хуулна. Clipboard түгжигдсэн бол `False`.

    Түгжээг барина: оруулалт clipboard-ыг ашиглаад буцаан сэргээдэг тул
    түүнтэй давхацвал хуулсан зүйл маань дарагдана.
    """
    if not text:
        return False
    with _lock:
        try:
            pyperclip.copy(text)
        except pyperclip.PyperclipException:
            return False
    return True


def type_text(text: str) -> None:
    """Шууд товчлуур дарж бичнэ (clipboard хөндөхгүй, гэхдээ удаан)."""
    with _lock:
        _type(text)


def _type(text: str) -> None:
    """Түгжээг дуудагч барьсан гэж үзнэ."""
    if not text:
        return
    _keyboard.type(text)
