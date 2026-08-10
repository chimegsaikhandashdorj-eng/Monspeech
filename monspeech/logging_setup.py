"""Файл руу бичих лог — "болсонгүй" гэсэн тохиолдлыг эргэж мөрдөх боломж.

Таньсан текстийг бүтнээр нь бичихгүй (зөвхөн урт, итгэлцэл) — нууцлалын үүднээс.
"""

from __future__ import annotations

import logging
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
