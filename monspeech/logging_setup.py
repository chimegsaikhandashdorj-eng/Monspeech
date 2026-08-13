"""Файл руу бичих лог — "болсонгүй" гэсэн тохиолдлыг эргэж мөрдөх боломж.

Таньсан текстийг бүтнээр нь бичихгүй (зөвхөн урт, итгэлцэл) — нууцлалын үүднээс.
"""

from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import CONFIG_DIR

LOG_PATH = CONFIG_DIR / "monspeech.log"
_ready = False


def setup() -> logging.Logger:
    """Логыг нэг удаа тохируулна."""
    global _ready
    logger = logging.getLogger("monspeech")
    if _ready:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
    except OSError:
        # Файл руу бичиж чадахгүй бол ч апп ажиллана
        logger.addHandler(logging.NullHandler())

    _ready = True
    return logger


def get(name: str) -> logging.Logger:
    setup()
    return logging.getLogger(f"monspeech.{name}")


def install_crash_handler() -> None:
    """Баригдаагүй алдааг лог руу бичнэ.

    `.exe` нь консольгүй ажилладаг тул стандарт зан төлөв нь алдааг хаашаа ч
    бичихгүйгээр залгих явдал: хэрэглэгчийн хувьд «апп юу ч болоогүй юм шиг
    зогслоо» гэсэн үг. Тараагдсан аппад энэ нь хамгийн муу төрлийн алдаа —
    мэдээлэх юм үлдэхгүй.

    Гол thread (`sys.excepthook`) ба ажлын thread-үүдийг (`threading.excepthook`)
    хоёуланг нь барина. Tk-ийн callback дотор гарсан алдааг цонх өөрөө
    `report_callback_exception`-оор дамжуулдаг тул түүнийг апп холбоно.
    """
    logger = setup()
    previous = sys.excepthook

    def on_exception(kind, value, trace) -> None:
        if not issubclass(kind, KeyboardInterrupt):
            logger.critical("баригдаагүй алдаа", exc_info=(kind, value, trace))
        previous(kind, value, trace)

    def on_thread_exception(args) -> None:
        if not issubclass(args.exc_type, SystemExit):
            logger.critical(
                "thread «%s» дээр баригдаагүй алдаа",
                getattr(args.thread, "name", "?"),
                exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
            )

    sys.excepthook = on_exception
    threading.excepthook = on_thread_exception
