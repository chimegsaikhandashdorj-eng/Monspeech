"""Ярианы илрүүлэгч (VAD) — өгүүлбэрийн хил тогтоох нарийн арга.

Өмнө нь `Segmenter` дуутай эсэхийг ЗӨВХӨН RMS түвшингээр шийддэг байсан:
«босгоос чанга бол яриа». Энэ нь чимээгүй өрөөнд ажилладаг ч бодит нөхцөлд
хоёр талаас нь алддаг —

- **чимээ ярианд тооцогдоно**: гар товчлуурын товшилт, цаасны чимээ, хажуугийн
  ярианы бөөгнөрөл нь босго давдаг тул сегмент хэзээ ч төгсдөггүй;
- **яриа чимээнд тооцогдоно**: аяархан хэлсэн үг, өгүүлбэрийн сүүлийн үе
  («…юм», «…уу») босго давахгүй тул тайрагдана.

Хоёр дахь нь илүү үнэтэй: тайрагдсан үг танигчид огт хүрэхгүй тул засах ямар ч
боломжгүй. Түвшин нь ярианы шинжийг хэмждэггүй — зөвхөн чанга эсэхийг хэмждэг.

WebRTC-ийн VAD нь эсрэгээрээ давтамжийн бүтцээр («яриа мөн үү», «чанга уу» биш)
шийддэг тул хоёр алдааг хоёуланг нь мэдэгдэхүйц бууруулна. Google Meet, Zoom,
Chrome бүгд үүнийг ашигладаг; BSD лиценз, ~19 КБ, фрэймд ~0.1 мс.

**Заавал биш хамаарал.** Сан суугаагүй бол `create()` нь `None` буцааж,
`Segmenter` хуучин түвшингийн замаараа ажиллана — `pyaudiowpatch`, `audioop`
хоёртой яг ижил зарчим. Апп ямар ч тохиолдолд ажиллана.
"""

from __future__ import annotations

from .logging_setup import get as get_logger

log = get_logger("vad")

try:  # pragma: no cover - суулгасан эсэхээс хамаарна
    import webrtcvad
except ImportError:  # pragma: no cover
    webrtcvad = None

#: WebRTC зөвхөн эдгээр давтамжийг хүлээж авна.
SUPPORTED_RATES = frozenset({8000, 16000, 32000, 48000})

#: Фрэймийн урт. 10/20/30 мс-ийн аль нэг байх ёстой. 20 мс нь хариу үйлдэл ба
#: тогтвортой байдлын дундаж — 64 мс уншилтад бүтэн гурав багтана.
FRAME_MS = 20

#: 0 = хамгийн зөөлөн (илүү ихийг яриа гэнэ), 3 = хамгийн хатуу.
#: 2-ыг сонгосон учир: бичилтэд яриа алдах нь чимээ нэвтрэхээс үнэтэй, гэхдээ
#: 0–1 нь сэнсний гүнгэнээг ч яриа гэж үздэг тул сегмент хаагдахаа больдог.
AGGRESSIVENESS = 2

#: Уншилт дотор ийм хувь фрэйм яриа бол уншилт бүхэлдээ яриа. 64 мс-д бүтэн
#: гурван фрэйм ногддог тул 0.34 нь «гурвын нэг нь хангалттай» гэсэн үг —
#: үгийн ЭХЛЭЛ уншилтын сүүлд таарахад тайрагдахгүй байх нь чухал.
SPEECH_RATIO = 0.34

#: Сан байхгүйг нэг удаа л мэдэгдэнэ (`create` нь дуудагдсаар байдаг).
_warned = False


def available() -> bool:
    """WebRTC-ийн VAD ашиглах боломжтой эсэх."""
    return webrtcvad is not None


class WebRtcDetector:
    """Уншсан хэсгүүдийг фрэйм болгон хувааж, дуутай эсэхийг хэлнэ.

    Уншилтын урт (`CHUNK` = 1024 сэмпл = 64 мс) нь фрэймийн уртад бүхэлдээ
    хуваагддаггүй тул үлдэгдлийг дараагийн уншилт руу зөөнө — эс бөгөөс
    уншилт бүрийн сүүлээс хэдэн мс тогтмол хаягдана.
    """

    def __init__(
        self,
        rate: int = 16000,
        aggressiveness: int = AGGRESSIVENESS,
        ratio: float = SPEECH_RATIO,
    ) -> None:
        if webrtcvad is None:  # pragma: no cover
            raise RuntimeError("webrtcvad суугаагүй байна")
        if rate not in SUPPORTED_RATES:
            raise ValueError(f"дэмжигдэхгүй давтамж: {rate}")
        self.rate = rate
        self.ratio = ratio
        self._vad = webrtcvad.Vad(aggressiveness)
        self._frame_bytes = int(rate * FRAME_MS / 1000) * 2
        self._buffer = b""

    def reset(self) -> None:
        """Сегмент солигдоход дуусаагүй фрэймийг хаяна."""
        self._buffer = b""

    def feed(self, chunk: bytes) -> bool | None:
        """Хэсгийг нэмээд «яриа мөн үү» гэдгийг хэлнэ.

        Бүтэн фрэйм бүрдээгүй бол `None` — дуудагч тэр уншилтад түвшингийн
        шийдвэрээ хэрэглэнэ. Ингэснээр эхний хэдэн мс шийдвэргүй үлдэхгүй.
        """
        self._buffer += chunk
        size = self._frame_bytes
        if len(self._buffer) < size:
            return None
        voiced = 0
        frames = 0
        offset = 0
        while offset + size <= len(self._buffer):
            frame = self._buffer[offset : offset + size]
            offset += size
            frames += 1
            try:
                if self._vad.is_speech(frame, self.rate):
                    voiced += 1
            except Exception:  # noqa: BLE001 - pragma: no cover
                # Сан гэнэт татгалзвал бүхэл бичлэгийг унагаахгүй: шийдвэргүй
                # гэж мэдэгдээд түвшингийн зам руу буцаана.
                self._buffer = b""
                return None
        self._buffer = self._buffer[offset:]
        return voiced / frames >= self.ratio


def create(rate: int = 16000, enabled: bool = True):
    """Боломжтой бол илрүүлэгч, эс бөгөөс `None` (түвшингийн зам).

    Хэзээ ч алдаа шиднэ: дуудагч тал бүрийг шалгах шаардлагагүй байх ёстой —
    VAD байхгүй гэдэг нь ажиллахгүй гэсэн үг биш, зүгээр л нэг үеийн өмнөх
    зан төлөв гэсэн үг.
    """
    if not enabled:
        return None
    if webrtcvad is None:
        # Нэг л удаа: чагт асаалттай атал юу ч өөрчлөгдөөгүй байхад
        # шалтгааныг нь оношийн логоос олж болдог байх ёстой.
        global _warned
        if not _warned:
            _warned = True
            log.info("webrtcvad суугаагүй — сегментчилэл дууны түвшингээр явна")
        return None
    try:
        return WebRtcDetector(rate)
    except Exception as exc:  # noqa: BLE001
        log.warning("VAD үүсгэж чадсангүй, түвшингээр үргэлжилнэ: %s", exc)
        return None
