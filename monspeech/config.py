"""Хэрэглэгчийн тохиргоог диск дээр хадгалах."""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

from . import secret

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
    # Анхдагчаар УНТРААЛТТАЙ: таньсан текстийг гараа хүрэлгүй том үсэг
    # болгоход хэрэглэгч дараа нь өөрөө засах шаардлага үүсдэг. Хүсвэл
    # «Бичилт → Том үсгээр эхлүүлэх»-ээс асаана.
    "auto_capitalize": False,
    "voice_punctuation": True,
    # Сегмент бүрийн (чимээгүй завсар эсвэл товч суллах) төгсгөлд цэг тавих.
    # Анхдагчаар УНТРААЛТТАЙ: хэлээгүй тэмдэгтийг өөрөө нэмэх нь зарим хүнд
    # (жагсаалт, чат бичих) саад болно.
    "auto_period": False,
    # Тооны үгийг цифр болгох: «хорин гурван цагт» → «23 цагт»
    "voice_numbers": True,
    # Ярианы чигчлүүр («ааа», эхний «за», давталт, өөрийгөө засах) хасах
    "clean_speech": True,
    # Танигчийн эхний transcript-ийг утгын хувиргалтгүй буулгана. Зөвхөн
    # сегментүүдийн хоорондын зайг `auto_space` тусад нь удирдана.
    "verbatim_mode": False,
    # Интерфейсийн шилжилтүүд (цэс, унтраалга, товч, Тохиргооны цонх).
    # Унтраавал бүх зүйл тэр дор нь солигдоно — удаан машин, эсвэл
    # хөдөлгөөнд мэдрэг хүнд.
    "animations": True,
    "wave_overlay": True,
    "tray_enabled": True,
    # Windows асахад автоматаар ажиллах. Үнэний эх сурвалж нь бүртгэл (autostart.py)
    # — апп эхлэхдээ тэндээс уншиж энэ утгыг тааруулна.
    "start_with_windows": False,
    "mic_index": -1,
    # Сонгосон микрофоны нэр. PyAudio-ийн дугаар нь төхөөрөмж салгаж холбоход
    # шилждэг тул зөвхөн дугаарт найдаж болохгүй — нэрээр нь дахин олно.
    "mic_name": "",
    "replacements": {},
    # Дуут товчлол: "миний хаяг" → бүтэн хаяг
    "snippets": {},
    # Хэрэглэгчийн нэмсэн дуут үйлдэл: {хэлэх хэллэг: "undo"|"repeat"|"copy"|"stop"}.
    # Дотор суулгасан хэллэгүүд («буцаа», «давт»…) үүнээс үл хамаарч ажиллана.
    "actions": {},
    # Хүний нэрс: {Зөв нэр: "сонсогддог хувилбарууд, таслалаар"}. Зөв нэрийг
    # ойролцоо зайгаар тааруулдаг тул нэг бичихэд олон буруу хувилбарыг барина.
    "names": {},
    # Толио танигч руу «хүлээгдэж байгаа үгс» болгож илгээх. Зөвхөн Whisper-
    # төрлийн (OpenAI-нийцтэй) танигч дэмждэг; Google-д нөлөөгүй.
    "vocabulary_boost": True,
    # Буруу таньсныг түүхэн дээр зассан үед толинд өөрөө нэмэх
    "learn_corrections": True,
    # Ctrl+V хүлээж авдаггүй аппуудыг санаж, тэнд шууд бичих
    "type_mode_apps": [],
    # Үгчлэн бичүүлэх цонхнууд: тэнд «Чигчлүүр цэвэрлэх» хүчингүй болно
    "no_clean_apps": [],
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
    # Товч дарахаас өмнөх дууг хэдэн секундээр буцааж авах. Микрофон бэлэн
    # (нээлттэй) байх үед л ажиллана — 0 бол огт болих.
    "preroll_seconds": 0.6,
    # Илгээхийн өмнө орчны чимээг дарах (сэнс, кондиционер, гудамжны шуугиан).
    # Богино тооцоолол — нэмэлт сан ч, сүлжээ ч шаардахгүй.
    "noise_suppression": True,
    # Өгүүлбэрийн хилийг ярианы илрүүлэгчээр (WebRTC VAD) тогтоох. Унтраавал
    # хуучин зам — зөвхөн дууны түвшин. `webrtcvad` суугаагүй бол энэ утга
    # ямар ч байсан түвшингийн зам ажиллана (`vad.create()` өөрөө шийднэ).
    "vad": True,
    # Итгэлцэл нь үүнээс доош бол текстийг оруулахгүй
    "min_confidence": 0.45,
    # Хэцүү тохиолдлын дууг диск дээр хадгалах: огт танигдаагүй, итгэлцэл
    # багатай, эсвэл хэрэглэгч зассан таналтууд. `tools/make_manifest.py`
    # эдгээрээс benchmark-ийн сан үүсгэдэг — сайжруулалт бүрийг ХЭМЖИХ
    # цорын ганц арга.
    #
    # Анхнаасаа УНТРААЛТТАЙ: энэ нь хэрэглэгчийн дууг диск дээр бичнэ гэсэн
    # үг тул санаатай асаах ёстой. «Яриа → Хэцүү жишээ хадгалах».
    "save_hard_audio": False,
    # Сүүлийн оруулгыг буцаах товчлуур.
    # Win+Alt дээр товч НЭМСЭН хослол болгож болохгүй: Win+Alt дарангуутаа
    # бичлэг эхэлчихдэг тул хагас бичлэг үлдэнэ. Тиймээс огт давхцахгүй
    # хослолуудыг анхны утга болгов.
    "undo_key": "<ctrl>+<alt>+z",
    # Сүүлийн таналтыг танигчийн дараагийн хувилбараар солих товчлуур.
    # Ctrl+Alt дээр суурилсан — Win+Alt (бичлэг эхлүүлэх) дээр давхцахгүй.
    "variant_key": "<ctrl>+<alt>+<space>",
    # Команд горим: энэ товчийг дарж барин ярихад текст ОРОХГҮЙ, зөвхөн
    # дуут үйлдэл гүйцэтгэнэ. Win+Alt (бичлэг) дээр давхцах ёсгүй тул
    # Win+Ctrl — модификатор л ашигласан (үсэгтэй хослол дарж барихад
    # тэр үсэг зорилтот цонхонд бичигдчихнэ).
    "command_key": "<cmd>+<ctrl>",
    # Товчийг ХОЁР хурдан дарж бичлэг асаах/унтраах (F9-ийн оронд гар
    # байрлалаа алдалгүй). Анхдагчаар унтраалттай: Ctrl нь өдөр бүр өөр
    # хослолд ордог тул хэрэглэгч санаатай асаах ёстой.
    "double_tap_enabled": False,
    "double_tap_key": "<ctrl>",
    # Хоёрдогч хэл (өөр товчлуураар)
    "ptt_key_alt": "<cmd>+<shift>",
    "lang_alt": "en-US",
    # Монгол–англи хэлийг бичиг, үгийн сан, итгэлцэл, өмнөх хэлээр автоматаар
    # сонгох. False бол үндсэн/аппын профайлын хэлийг албадана.
    "detect_language": True,
    # True бол хоёр хэлийг зэрэг танина; False бол зөрүүтэй үед л дахин шалгана.
    "language_accuracy_mode": False,
    "auto_languages": ["mn-MN", "en-US"],
    # Хоёр хэлний оноо ойр байвал цонхны/сүүлийн хэлний дохиог дагах зай.
    "language_margin": 0.08,
    # Аль танигчаар таних: "google" (үнэгүй, түлхүүргүй) эсвэл "openai"
    # (хэрэглэгчийн өөрийн үйлчилгээ). Доорх гурав нь зөвхөн "openai"-д.
    "stt_provider": "google",
    "stt_url": "",
    "stt_model": "",
    # Хэрэглэгчийн түлхүүр. Дискэн дээр `dpapi:…` хэлбэрээр ШИФРЛЭГДЭН
    # хадгалагдана (secret.py — Windows DPAPI, шинэ dependencyгүй). Санах
    # ойд болон UI-д үргэлж ил текст байна; `load`/`save` хоёулаа
    # шифрлэлт/тайлалтыг автоматаар хийнэ. Хуучин ил текстийн файл нь
    # эхний хадгалалтаараа шифрлэгдсэн хэлбэр рүү автоматаар шилждэг.
    "stt_key": "",
    # Өөрийн танигчийн минутын үнэ (USD). Зөвхөн БАРАГЦААЛСАН тооцоо
    # харуулахад хэрэглэнэ — 0 бол зардлыг огт харуулахгүй. Whisper API-ийн
    # нийтэлсэн үнэ 0.006 USD/мин байсныг анхны утга болгов.
    "stt_cost_per_minute": 0.006,
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
    "preroll_seconds": (0.0, 2.0),
    "stt_cost_per_minute": (0.0, 10.0),
    "language_margin": (0.0, 0.5),
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
        # Түлхүүр файл дээр `dpapi:…` байвал тайлна; хуучин ил текст байвал хэвээр нь уншина
        raw_key = str(cfg.get("stt_key") or "")
        if secret.is_encrypted(raw_key):
            cfg["stt_key"] = secret.decrypt(raw_key) or ""
        else:
            cfg["stt_key"] = raw_key
        return cfg

    def save(self) -> str | None:
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            payload = dict(self)
            payload["stt_key"] = secret.encrypt(self["stt_key"])
            CONFIG_PATH.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        except OSError as exc:
            return str(exc)
        return None
