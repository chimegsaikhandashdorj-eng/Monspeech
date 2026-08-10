"""Компьютер асахад Monspeech-ийг автоматаар ажиллуулах.

Windows-ийн бүртгэлийн `Run` түлхүүрт бичлэг нэмнэ. Гар аргаар `shell:startup`
хавтсанд товчлол хийхээс дээр: аппаас нэг чагтаар удирдана, `.exe` хэлбэрээр
тараахад ч ажиллана.

Бүртгэл нь үнэний эх сурвалж — тохиргооны файл биш. Хэрэглэгч бүртгэлээ гараар
цэвэрлэсэн байж болох тул апп эхлэхдээ `enabled()`-ээс асууж чагтаа тааруулна.
"""

from __future__ import annotations

import sys
import winreg
from pathlib import Path

from .logging_setup import get as get_logger

log = get_logger("autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "Monspeech"


def command() -> str:
    """Windows асахад ажиллуулах тушаал."""
    if getattr(sys, "frozen", False):
        # Багцалсан .exe — өөрийгөө шууд заана
        return f'"{Path(sys.executable)}"'
    # Эх кодоос ажиллаж байна. Run бичлэг нь ажлын хавтас тавьж өгдөггүй тул
    # `-m monspeech` дангаараа модулиа олохгүй. `Monspeech.bat` нь өөрөө хавтас
    # руугаа шилжээд pythonw сонгодог учир яг тохирно.
    launcher = Path(__file__).resolve().parent.parent / "Monspeech.bat"
    if launcher.exists():
        return f'"{launcher}"'
    return f'"{sys.executable}" -m monspeech'


def current(key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> str | None:
    """Бүртгэлд одоо бичигдсэн тушаал (байхгүй бол `None`)."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
            return str(value) or None
    except (OSError, ValueError):  # түлхүүр/утга байхгүй, эсвэл нэр нь буруу
        return None


def enabled(key_path: str = RUN_KEY, value_name: str = VALUE_NAME) -> bool:
    """ЭНЭ апп автоматаар эхлэхээр тохируулагдсан эсэх.

    Зөвхөн бичлэг байгаа эсэхийг харж болохгүй: ижил нэртэй бичлэг өөр програм
    эсвэл аппын хуучин байрлал руу заасан байж болно. Тэр тохиолдолд "асаалттай"
    гэж хэлэх нь хэрэглэгчийг төөрөгдүүлнэ — мөн чагтыг унтраахад бидний бус
    бичлэгийг устгачих эрсдэлтэй. Тушаал нь яг таарсан үед л асаалттай гэж үзнэ
    (аппыг өөр газар зөөвөл чагт унтарч, дахин асаахад шинэ зам бичигдэнэ)."""
    return current(key_path, value_name) == command()


def apply(
    on: bool, key_path: str = RUN_KEY, value_name: str = VALUE_NAME
) -> str | None:
    """Автомат эхлүүлэлтийг асаана/унтраана. Алдаа гарвал мессежийг буцаана."""
    try:
        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE
        ) as key:
            if on:
                target = command()
                previous = current(key_path, value_name)
                if previous and previous != target:
                    log.warning("өмнөх бичлэгийг сольж байна: %s", previous)
                winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, target)
                log.info("автомат эхлүүлэлт асаалаа: %s", target)
            else:
                previous = current(key_path, value_name)
                if previous is not None and previous != command():
                    # Ижил нэртэй ч өөр програмын бичлэг — хөндөхгүй
                    log.warning("бидний бус бичлэг тул хэвээр үлдээв: %s", previous)
                    return None
                try:
                    winreg.DeleteValue(key, value_name)
                except FileNotFoundError:
                    pass  # аль хэдийн байхгүй — хүссэн үр дүн нь ижил
                log.info("автомат эхлүүлэлт унтраалаа")
    except (OSError, ValueError) as exc:
        # Бүртгэл нь бичих эрхгүй, бодлогоор хаагдсан байх зэрэг шалтгаанаар
        # татгалзаж болно. Апп үүнээс болж унах ёсгүй — чагтаа буцаагаад
        # хэрэглэгчид шалтгааныг хэлнэ.
        log.error("автомат эхлүүлэлт тохируулагдсангүй: %s", exc)
        return f"Автомат эхлүүлэлт тохируулагдсангүй: {exc}"
    return None
