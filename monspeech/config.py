"""Хэрэглэгчийн тохиргоог диск дээр хадгалах."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

CONFIG_DIR = Path(os.path.expandvars(r"%AppData%")) / "Monspeech"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULTS: dict[str, Any] = {
    "lang": "mn-MN",
    # Үндсэн горим: Win+Alt-ыг дарж байх үед сонсоод, суллахад текст орно
    "ptt_enabled": True,
    "ptt_key": "<cmd>+<alt>",
    # Урт бичихэд: нэг дарж асаагаад, дахин дарж унтраана
    "hotkey": "<f9>",
    "auto_space": True,
    "restore_clipboard": True,
    "type_mode": False,
    "auto_capitalize": True,
    "voice_punctuation": True,
    # Ярианы чигчлүүр («ааа», эхний «за», давталт, өөрийгөө засах) хасах
    "clean_speech": True,
    "wave_overlay": True,
    "tray_enabled": True,
    # Windows асахад автоматаар ажиллах. Үнэний эх сурвалж нь бүртгэл (autostart.py)
    # — апп эхлэхдээ тэндээс уншиж энэ утгыг тааруулна.
    "start_with_windows": False,
    "mic_index": -1,
    "replacements": {},
    # Дуут товчлол: "миний хаяг" → бүтэн хаяг
    "snippets": {},
    # Буруу таньсныг түүхэн дээр зассан үед толинд өөрөө нэмэх
    "learn_corrections": True,
    # Ctrl+V хүлээж авдаггүй аппуудыг санаж, тэнд шууд бичих
    "type_mode_apps": [],
    # Аппаар ялгах хэл: цонхны гарчгийн хэсэг → хэлний код.
    # Жишээ: {"Visual Studio Code": "en-US", "Messenger": "mn-MN"}
    "lang_apps": {},
    # Аюулгүйн хязгаар: товч гацсан ч энэ хугацааны дараа бичлэг зогсоно
    "max_recording_seconds": 300,
    # Чимээгүй завсрыг өгүүлбэрийн төгсгөл гэж үзэх хугацаа
    "silence_hold": 0.7,
    # Бичлэг зогссоны дараа микрофоныг ийм удаан нээлттэй барина. Микрофон
    # нээхэд эхний дуу ирэх хүртэл ~0.7 сек болдог тул дараалсан бичилтүүд
    # шууд эхэлдэг. 0 бол бүр болих (микрофоны заалт тэр дор нь унтарна).
    "mic_keep_open_seconds": 45,
    # Итгэлцэл нь үүнээс доош бол текстийг оруулахгүй
    "min_confidence": 0.45,
    # Сүүлийн оруулгыг буцаах товчлуур.
    # Win+Alt дээр товч НЭМСЭН хослол болгож болохгүй: Win+Alt дарангуутаа
    # бичлэг эхэлчихдэг тул хагас бичлэг үлдэнэ. Тиймээс огт давхцахгүй
    # хослолуудыг анхны утга болгов.
    "undo_key": "<ctrl>+<alt>+z",
    # Хоёрдогч хэл (өөр товчлуураар)
    "ptt_key_alt": "<cmd>+<shift>",
    "lang_alt": "en-US",
    # Итгэлцэл бага БӨГӨӨД үр дүн нь кирилл биш байвал хоёрдогч хэлээр нэг удаа
    # дахин асуух. Тодорхойгүй үед л хоёр дахь хүсэлт явна.
    "detect_language": True,
    # Аль танигчаар таних: "google" (үнэгүй, түлхүүргүй) эсвэл "openai"
    # (хэрэглэгчийн өөрийн үйлчилгээ). Доорх гурав нь зөвхөн "openai"-д.
    "stt_provider": "google",
    "stt_url": "",
    "stt_model": "",
    # ⚠️ Түлхүүр энд ил бичигдэнэ — апп нууц хадгалах сан ашигладаггүй
    "stt_key": "",
    # Эхлэхдээ GitHub-аас шинэ хувилбар гарсан эсэхийг шалгах (IP харагдана)
    "check_updates": True,
    # Анх ажиллуулахад танилцуулах карт харуулсан эсэх
    "onboarded": False,
    # Өнгөний сэдэв: "dark" эсвэл "light". Виджетүүд өнгөө импортын үед
    # тогтоодог тул солиход апп дахин эхлэх шаардлагатай (цонхонд сануулна).
    "theme": "dark",
}

# Тоон утгуудын зөвшөөрөгдөх хүрээ. Гараар засаад хэт том утга бичихэд апп
# хачирхалтай биеэ авч явахаас сэргийлж, анхны утга руу нь буцаана.
RANGES: dict[str, tuple[float, float]] = {
    "mic_index": (-1, 128),
    "max_recording_seconds": (10, 3600),
    "silence_hold": (0.1, 5.0),
    "mic_keep_open_seconds": (0, 600),
    "min_confidence": (0.0, 1.0),
}


def _acceptable(key: str, value: Any) -> bool:
    """Уншсан утга анхны утгынхаа төрөл, хүрээнд багтаж байна уу."""
    default = DEFAULTS[key]
    if isinstance(default, bool):
        return isinstance(value, bool)
    if isinstance(default, (int, float)):
        # bool нь int-ийн удамшил тул тусад нь хаана; 1 ба 1.0-ыг адил үзнэ
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return False
        low, high = RANGES.get(key, (float("-inf"), float("inf")))
        return low <= value <= high
    return isinstance(value, type(default))


class Config(dict):
    """dict шиг ажиллах тохиргоо — өөрчлөөд `save()` дуудна."""

    @classmethod
    def load(cls) -> "Config":
        # Гүн хуулбар: эс бөгөөс `snippets`, `type_mode_apps` зэрэг нь DEFAULTS-
        # тэй нэг объект болж, нэг дээр нь өөрчилсөн зүйл нөгөөд нь харагдана.
        cfg = cls(copy.deepcopy(DEFAULTS))
        try:
            raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cfg
        if isinstance(raw, dict):
            for key, value in raw.items():
                if key in DEFAULTS and _acceptable(key, value):
                    cfg[key] = value
        return cfg

    def save(self) -> str | None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(
                json.dumps(self, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            return str(exc)
        return None
