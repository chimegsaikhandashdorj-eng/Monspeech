"""Аль микрофоноор сонсохыг шийдэх: сонгох, хадгалах, дахин олох.

Энэ модуль байхын шалтгаан нь PyAudio-ийн төхөөрөмжийн дугаар ТОГТВОРГҮЙ явдал.
Чихэвч салгаж холбоход жагсаалт шинэчлэгдэж, өчигдрийн «1» өнөөдөр өөр зүйл —
эсвэл огт сонсдоггүй чанга яригч — болно. Тэр дугаараар нээхэд PortAudio нь
«Invalid number of channels» (-9998) гэж шиднэ: сонсох суваг нь тэг учраас.
Хэрэглэгчийн хувьд энэ нь «микрофон гэнэт ажиллахаа больсон» гэсэн үг.

Иймд микрофоныг дугаараар нь БИШ, дугаар+нэрээр нь санана (`Mic`) — нээх бүрд
дугаарыг нь одоогийн жагсаалттай тааруулна (`resolve`).

Дуудагч нь PyAudio-г огт мэдэхгүй: `available()` жагсаалт гаргаж, `load()`
тохиргооноос уншиж, `resolve()` нээх дугаарыг өгнө. Тестийн үед `pa`-г өөрөө
дамжуулж болох тул микрофон шаардахгүй.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

import pyaudio

from .logging_setup import get as get_logger

log = get_logger("mics")

# Цонхны жагсаалтад багтах урт. Нэрийг ЗӨВХӨН харуулахдаа тайрна — хадгалж,
# тааруулахдаа бүтнээр нь: тайрсан нэр хэзээ ч бүтэн нэртэй таарахгүй.
LABEL_LIMIT = 38
SYSTEM_LABEL = "Системийн үндсэн"
# Бичлэг моногоор явдаг (`audio.CHANNELS`). Энэ модуль `audio`-г импортлодоггүй
# — эргэлдсэн импорт үүсэхээс сэргийлж. Хоёр тоо салсан эсэхийг тест шалгана.
MIN_CHANNELS = 1


@dataclass(frozen=True)
class Mic:
    """Сонгосон микрофон: дугаар БА нэр хоёулаа.

    Дугаар нь хурдан (шууд нээнэ), нэр нь найдвартай (дугаар шилжсэн ч олдоно).
    Хоёуланг нь нэг зүйл болгон авч явснаар «нэгийг нь шинэчлээд нөгөөг нь
    мартах» алдаа гарах газаргүй болно.
    """

    index: int = -1  # -1 = системийн үндсэн төхөөрөмж
    name: str = ""  # хоосон = мэдэхгүй (хуучин тохиргоо)

    @property
    def is_default(self) -> bool:
        return self.index < 0

    @property
    def label(self) -> str:
        """Цонхонд харуулах нэр."""
        if self.is_default:
            return SYSTEM_LABEL
        return (self.name or f"#{self.index}")[:LABEL_LIMIT]

    def save_to(self, cfg) -> None:
        """Тохиргооны аль түлхүүрт орохыг зөвхөн энэ модуль мэднэ."""
        cfg["mic_index"] = self.index
        cfg["mic_name"] = self.name


SYSTEM = Mic()


# ----------------------------------------------------------------------
# PyAudio-тэй ярих (модулиас гадагш харагдахгүй)
# ----------------------------------------------------------------------
@contextmanager
def _session(pa=None):
    """Өгсөн PyAudio-г хэрэглэнэ; өгөөгүй бол өөрөө нээгээд хаана.

    Нээж чадахгүй бол `None` гарна — дуудагч бүр `try/except` бичихээс
    аврагдаж, «микрофон байхгүй» нь ердийн тохиолдол болно.
    """
    if pa is not None:
        yield pa
        return
    try:
        own = pyaudio.PyAudio()
    except Exception:  # noqa: BLE001 - PyAudio янз бүрийн алдаа шиднэ
        log.warning("PyAudio эхэлсэнгүй — микрофоны жагсаалт хоосон байна")
        yield None
        return
    try:
        yield own
    finally:
        try:
            own.terminate()
        except Exception:  # noqa: BLE001
            pass


def _count(pa) -> int:
    try:
        return int(pa.get_device_count())
    except Exception:  # noqa: BLE001
        return 0


def _info(pa, index: int) -> dict:
    try:
        return pa.get_device_info_by_index(index)
    except Exception:  # noqa: BLE001 - дугаар хүрээнээс гарсан бол шиднэ
        return {}


def _channels(pa, index: int) -> int:
    """Тухайн дугаарын төхөөрөмж хэдэн сувгаар СОНСОЖ чаддаг вэ."""
    if index < 0:
        return 0
    try:
        return int(_info(pa, index).get("maxInputChannels", 0))
    except (TypeError, ValueError):
        return 0


def _name(pa, index: int) -> str:
    return str(_info(pa, index).get("name", ""))


def _listens(pa, index: int) -> bool:
    return _channels(pa, index) >= MIN_CHANNELS


# ----------------------------------------------------------------------
# Гадагшаа гарах гурван үйлдэл
# ----------------------------------------------------------------------
def available(pa=None) -> list[Mic]:
    """Сонгож болох микрофонууд. Эхнийх нь ҮРГЭЛЖ системийн үндсэн.

    Нэг физик микрофон нь Windows дээр MME, DirectSound, WASAPI гэж 3-4 удаа
    давхар гарч ирдэг. Хэрэглэгчид ялгаагүй мөртлөө сонголтыг будлиулж, нэрээр
    нь олоход ч хоёрдмол болгодог тул нэг нэрээс эхнийхийг нь л үлдээнэ.
    """
    found = [SYSTEM]
    with _session(pa) as session:
        if session is None:
            return found
        seen: set[str] = set()
        for index in range(_count(session)):
            if not _listens(session, index):
                continue
            name = _name(session, index)
            if not name or name in seen:
                continue
            seen.add(name)
            found.append(Mic(index, name))
    return found


def load(cfg, pa=None) -> Mic:
    """Тохиргооноос уншина. Нэр нь хоосон бол (хуучин тохиргоо) нөхөж өгнө.

    Нөхөөгүй бол хуучин хэрэглэгчид «нэрээр нь олох» боломж хүртэхгүй, зөвхөн
    микрофоноо дахин сонгосны дараа идэвхжинэ. Дуудагч буцаж ирсэн `Mic`-ийг
    `save_to()`-оор бичиж, тохиргоог хадгалах эсэхээ өөрөө шийднэ.
    """
    mic = Mic(int(cfg["mic_index"]), str(cfg["mic_name"]))
    if mic.is_default or mic.name:
        return mic
    with _session(pa) as session:
        if session is None or not _listens(session, mic.index):
            return mic
        name = _name(session, mic.index)
    if name:
        log.info("хадгалсан микрофоны нэрийг нөхлөө: %s → «%s»", mic.index, name)
        return Mic(mic.index, name)
    return mic


def resolve(pa, mic: Mic) -> int | None:
    """Хадгалсан сонголтыг ОДООГИЙН жагсаалттай тааруулж, нээх дугаарыг өгнө.

    Дараалал нь санаатай:

    1. Нэрээр нь олдвол тэр дугаар — дугаар шилжсэн ч хэрэглэгчийн сонгосон
       ЯГ ТЭР төхөөрөмж рүү буцаж очно.
    2. Олдохгүй ч хадгалсан дугаар нь сонссоор байвал хэвээр нь. Windows нь
       төхөөрөмжийн нэрийг өөрчилдөг («Microphone (2- USB Audio)» → «3-»);
       ажиллаж байгаа сонголтыг зөвхөн нэр зөрсний төлөө хаяж болохгүй.
    3. Аль нь ч биш бол системийн үндсэн (`None`) — ажиллахгүй байхаас өөр
       микрофоноор ажилласан нь дээр.
    """
    if mic.is_default:
        return None
    if mic.name:
        for index in range(_count(pa)):
            if _listens(pa, index) and _name(pa, index) == mic.name:
                return index
    if _listens(pa, mic.index):
        return mic.index
    return None
