"""Буруу таньсан дууг хадгалж, benchmark-ийн сан болгож ургуулах.

**Яагаад:** аппын танилтыг сайжруулах гэсэн өөрчлөлт бүр таамаг хэвээр үлддэг —
«надад дээрдсэн юм шиг санагдлаа» гэдгээс цааш хэмжих арга байдаггүй. Хэмжихийн
тулд «энэ дуу → энэ текст байх ёстой» гэсэн хос хэрэгтэй, тэр нь цуглуулахад
хамгийн уйтгартай зүйл.

Гэтэл хэрэглэгч тэр хосыг ӨДӨР БҮР үүсгэж байдаг: буруу таньсныг түүхэн дээр
засах, эсвэл Ctrl+Alt+Space дарж зөв хувилбар руу сэлгэх бүрд «дуу нь энэ,
зөв нь энэ» гэж хэлж байгаа хэрэг. Өмнө нь дуу нь тэр дор нь хаягддаг тул
зөвхөн толь л сурдаг байв. Одоо дуу нь үлдэж, `tools/make_manifest.py` түүнийг
benchmark-ийн manifest болгоно.

Мөн огт танигдаагүй, итгэлцэл багатай гэж хаягдсан дуунууд ч хадгалагдана —
тэдгээрт зөв хариу нь мэдэгдэхгүй тул гараар бичих шаардлагатай, гэхдээ яг
тэдгээр нь хамгийн хэцүү тохиолдлууд.

**Нууцлал:** энэ нь хэрэглэгчийн дууг диск дээр бичнэ гэсэн үг. Тиймээс
анхнаасаа УНТРААЛТТАЙ (`save_hard_audio`) — санаатай асаах ёстой. Асаалттай ч
хэмжээ нь хатуу хязгаартай, «Түүх → Цэвэрлэх»-тэй адил нэг товчоор устгагдана.
"""

from __future__ import annotations

import json
import threading
import wave
from datetime import datetime
from pathlib import Path

from .config import CONFIG_DIR
from .logging_setup import get as get_logger

log = get_logger("samples")

SAMPLES_DIR = CONFIG_DIR / "samples"
INDEX_NAME = "index.jsonl"

RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2

#: Дискэн дээрх дээд хэмжээ. 16 кГц PCM = 32 КБ/сек тул 300 файл × ~5 сек
#: ≈ 48 МБ. Хоёулангаас нь аль нь эхэлж дүүрнэ, тэрнээс нь хуучныг хаяна.
MAX_FILES = 300
MAX_BYTES = 128 * 1024 * 1024

#: Засвар хожим ирдэг (хэрэглэгч түүх нээж заслаа гэж бодоход) тул сүүлийн
#: хэдэн сегментийн дууг санах ойд барина. Дискэнд ЗӨВХӨН засагдсан нь очно.
MEMORY_BYTES = 16 * 1024 * 1024

#: Хадгалах шалтгаанууд. Файлын нэр, manifest-д тайлбар болж очно.
REASON_UNRECOGNIZED = "unrecognized"  # юу ч буцаагаагүй
REASON_LOW_CONFIDENCE = "low_confidence"  # итгэлцэл босгоос доогуур
REASON_CORRECTED = "corrected"  # хэрэглэгч зөвийг нь хэлсэн — алтан хос


class HardSampleStore:
    """Хэцүү тохиолдлын дууг WAV болгож, хажууд нь мэдээллийг JSONL-д бичнэ.

    Дуудагчид: `remember()` нь дамжлагын thread-ээс, `promote()` нь цонхны
    thread-ээс ирдэг тул дотроо түгжээтэй.
    """

    def __init__(
        self,
        directory: Path | None = None,
        enabled: bool = False,
        max_files: int = MAX_FILES,
        max_bytes: int = MAX_BYTES,
    ) -> None:
        self.directory = Path(directory or SAMPLES_DIR)
        self.enabled = bool(enabled)
        self.max_files = max_files
        self.max_bytes = max_bytes
        self._lock = threading.Lock()
        # `(entry, pcm)` — түлхүүр нь ОБЪЕКТ өөрөө. `id()` ашиглавал хогийн
        # цэвэрлэгээний дараа дугаар дахин ашиглагдаж, огт өөр таналтын дуу
        # буруу засварт наалдаж болно.
        self._recent: list[tuple[dict, bytes]] = []
        self._recent_bytes = 0
        # Файлын нэрийг давхардуулахгүй тоолуур. Цаг нь секундын нарийвчлалтай
        # тул нэг секундэд хоёр жишээ гарахад (сегмент цувж танигдах нь
        # ердийн зүйл) нэр нь мөргөлдөж, өмнөх дуу дарагдана.
        self._serial = 0
        self.entries: list[dict] = []
        self.load()

    # ------------------------------------------------------------------
    @property
    def index_path(self) -> Path:
        return self.directory / INDEX_NAME

    def load(self) -> None:
        entries: list[dict] = []
        try:
            with open(self.index_path, encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        item = json.loads(line)
                    except ValueError:
                        continue
                    if isinstance(item, dict) and item.get("file"):
                        entries.append(item)
        except OSError:
            pass
        self.entries = entries

    def set_enabled(self, enabled: bool) -> None:
        """Унтраахад санах ойд барьсан дууг ч тэр дор нь хаяна."""
        with self._lock:
            self.enabled = bool(enabled)
            if not self.enabled:
                self._recent.clear()
                self._recent_bytes = 0

    # ------------------------------------------------------------------
    def remember(self, pcm: bytes, entry: dict) -> None:
        """Таналтын дууг санах ойд барина (дискэнд ХАРААХАН бичихгүй).

        Хэрэглэгч хожим засвал `promote()` энэ дууг олж, зөв текстийн хамт
        хадгална. Засахгүй бол дуу нь чимээгүйхэн хаягдана.
        """
        if not self.enabled or not pcm or not isinstance(entry, dict):
            return
        with self._lock:
            self._recent.append((entry, pcm))
            self._recent_bytes += len(pcm)
            while self._recent and self._recent_bytes > MEMORY_BYTES:
                _, dropped = self._recent.pop(0)
                self._recent_bytes -= len(dropped)

    def promote(self, entry: dict, text: str) -> bool:
        """Засагдсан таналтын дууг зөв текстийн хамт хадгална.

        Дуу нь санах ойгоос гараад амжсан (маш хуучин засвар) бол `False` —
        энэ нь алдаа биш, зүгээр л боломж өнгөрсөн.
        """
        text = str(text or "").strip()
        if not self.enabled or not text or not isinstance(entry, dict):
            return False
        with self._lock:
            for index, (candidate, pcm) in enumerate(self._recent):
                if candidate is entry:
                    self._recent.pop(index)
                    self._recent_bytes -= len(pcm)
                    break
            else:
                return False
        return self.capture(
            pcm,
            REASON_CORRECTED,
            text=text,
            heard=str(entry.get("text") or ""),
            language=str(entry.get("lang") or ""),
            provider=str(entry.get("provider") or ""),
            confidence=entry.get("confidence"),
        )

    def capture(
        self,
        pcm: bytes,
        reason: str,
        *,
        text: str = "",
        heard: str = "",
        language: str = "",
        provider: str = "",
        confidence: float | None = None,
    ) -> bool:
        """Дууг тэр дор нь WAV болгож бичнэ. Амжилттай эсэхийг буцаана.

        `text` нь МЭДЭГДЭЖ БАЙГАА зөв хариу (засварын үед). Хоосон бол
        manifest-д гараар бичих мөр болж очно.
        """
        if not self.enabled or not pcm:
            return False
        moment = datetime.now()
        # Нэр олгохоос эхлээд бичих хүртэл НЭГ түгжээн дор: дамжлагын thread
        # (танигдаагүй жишээ) ба цонхны thread (засвар) зэрэг дуудаж болно.
        with self._lock:
            name = self._unique_name(moment, reason)
            entry = {
                "file": name,
                "reason": reason,
                "text": text,
                "heard": heard,
                "lang": language,
                "provider": provider,
                "confidence": round(confidence, 4) if confidence is not None else None,
                "at": moment.isoformat(timespec="seconds"),
                "sec": round(len(pcm) / (RATE * SAMPLE_WIDTH), 2),
            }
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with wave.open(str(self.directory / name), "wb") as handle:
                    handle.setnchannels(CHANNELS)
                    handle.setsampwidth(SAMPLE_WIDTH)
                    handle.setframerate(RATE)
                    handle.writeframes(pcm)
                with open(self.index_path, "a", encoding="utf-8") as handle:
                    handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
            except OSError as exc:
                log.warning("дууны жишээ хадгалагдсангүй: %s", exc)
                return False
            self.entries.append(entry)
            self._prune()
        log.info("хэцүү жишээ хадгаллаа: %s (%.1f сек)", reason, entry["sec"])
        return True

    def _unique_name(self, moment: datetime, reason: str) -> str:
        """Давхардахгүй файлын нэр.

        Тоолуур нь процессын дотор өсдөг; дискэн дээр аль хэдийн байгаа нэр
        таарвал (аппыг дахин эхлүүлсний дараа) цааш нь алгасна. Мөргөлдвөл
        өмнөх дуу чимээгүйхэн дарагдах тул шалгалт нь заавал.
        """
        stamp = f"{moment:%Y%m%d-%H%M%S}"
        while True:
            name = f"{stamp}-{self._serial:04d}-{reason}.wav"
            self._serial += 1
            if not (self.directory / name).exists():
                return name

    # ------------------------------------------------------------------
    def _prune(self) -> None:
        """Хязгаараас хэтэрсэн хуучин файлуудыг устгана (түгжээн дор дуудна)."""
        sizes: dict[str, int] = {}
        for item in self.entries:
            try:
                sizes[item["file"]] = (self.directory / item["file"]).stat().st_size
            except OSError:
                sizes[item["file"]] = 0
        total = sum(sizes.values())
        removed = False
        while self.entries and (
            len(self.entries) > self.max_files or total > self.max_bytes
        ):
            item = self.entries.pop(0)
            total -= sizes.get(item["file"], 0)
            removed = True
            try:
                (self.directory / item["file"]).unlink()
            except OSError:
                pass
        if removed:
            self._rewrite()

    def _rewrite(self) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            with open(self.index_path, "w", encoding="utf-8") as handle:
                for item in self.entries:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("жишээний бүртгэл дахин бичигдсэнгүй: %s", exc)

    def clear(self) -> None:
        """Бүх хадгалсан дууг устгана («Түүх → Цэвэрлэх»-тэй адил)."""
        with self._lock:
            for item in self.entries:
                try:
                    (self.directory / item["file"]).unlink()
                except OSError:
                    pass
            self.entries = []
            self._recent.clear()
            self._recent_bytes = 0
            self._rewrite()

    # ------------------------------------------------------------------
    @property
    def count(self) -> int:
        return len(self.entries)

    def summary(self) -> str:
        """Цонхонд харуулах нэг мөр."""
        if not self.enabled:
            return "Унтраалттай"
        if not self.entries:
            return "Хараахан хадгалаагүй"
        ready = sum(1 for item in self.entries if item.get("text"))
        seconds = sum(float(item.get("sec") or 0.0) for item in self.entries)
        return f"{len(self.entries)} жишээ · {ready} нь зөв хариутай · {seconds:.0f} сек"
