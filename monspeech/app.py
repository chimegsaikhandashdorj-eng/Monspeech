"""Monspeech — ярианы текстийг курсор байгаа газарт шивэх desktop апп.

Микрофоныг шууд уншиж, Google Web Speech рүү илгээнэ (хөтөч оролцохгүй).
Товчийг дарж байх үед сонсоод, суллахад текст тэр дор нь орно.

Үүрэг хуваарилалт: цонх нь `window.py`, таних дамжлага нь `pipeline.py`,
ганц хуулбар барих нь `instance.py`. Энэ модуль тэдгээрийг холбож,
хэрэглэгчийн үйлдэлд хариу үзүүлнэ.
"""

from __future__ import annotations

import ctypes
import platform
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser

import pyperclip

from . import (
    __version__,
    animate,
    autostart,
    filetext,
    injector,
    mics,
    recognizer,
    textproc,
    update,
    winfocus,
)
from .audio import MIN_THRESHOLD, Recorder
from .config import Config
from .history import InsertionHistory
from .hotkeys import HotkeyManager, parse_combo, pretty
from .instance import ShowListener, already_running, request_show
from .mics import Mic
from .logging_setup import LOG_PATH, get as get_logger, install_crash_handler
from .overlay import WaveOverlay
from .pipeline import RecognitionWorker
from .samples import HardSampleStore
from .store import TranscriptStore, UsageStats
from .textproc import Formatter, learn_corrections, parse_actions, parse_replacements
from .tray import Tray
from .window import CODE_TO_NAME, ControlWindow, unknown_language_codes
from .winfocus import TargetWindow, activate

log = get_logger("app")

KEEPALIVE_SECONDS = 20  # урт яриан дунд холболт хуучрахаас сэргийлнэ
QUEUE_WARN = 2
QUEUE_LIMIT = 10


def _times(payload) -> int:
    """Эвентийн аргументыг давталтын тоо болгоно (эвдэрсэн бол 1).

    Товчлуураар ирэхэд `None`, дуут командаар ирэхэд "2" гэх мэт мөр байна.
    """
    try:
        return max(1, int(payload))
    except (TypeError, ValueError):
        return 1


HOTKEY_KEYS = (
    "ptt_key", "ptt_key_alt", "hotkey", "undo_key", "variant_key", "command_key",
)
# Цонх фокус аваагүй бол эдгээр хугацааны дараа дахин оролдоно. Windows нь
# өөр процесс сая ажилласан агшинд фокус солихыг хаадаг ба тэр хориг хэдэн зуун
# миллисекундын дараа суларна.
FOCUS_RETRY_MS = (250, 800)


class MonspeechApp:
    def __init__(self) -> None:
        self.cfg = Config.load()
        # Автомат эхлүүлэлтийн үнэний эх сурвалж нь бүртгэл — хэрэглэгч түүнийг
        # гараар цэвэрлэсэн байж болох тул чагтаа тэндээс тааруулна
        self.cfg["start_with_windows"] = autostart.enabled()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.segments: queue.Queue = queue.Queue()
        self.listening = False
        self.insertions = InsertionHistory()
        self._level = 0.0
        self._pending = 0
        # Сүүлийн таналтын хувилбарууд: {"items": [...], "index": 0, "entry": {...}}.
        # Товчоор ээлжлүүлэхэд л хэрэглэнэ, дараагийн таналтад дарагдана.
        self._variants: dict | None = None
        self._active_lang = self.cfg["lang"]
        self._active_clean = bool(self.cfg["clean_speech"])
        self._active_auto = bool(self.cfg["detect_language"])
        self._active_verbatim = bool(self.cfg["verbatim_mode"])
        # Энэ бичлэг команд горимынх эсэх (тусдаа товчлуураар эхэлсэн)
        self._active_command = False
        self._last_prewarm = 0.0
        # Файл хөрвүүлэлт явж байна уу. `transcribe_file` энэ талбарыг эхний
        # мөрөндөө уншдаг тул ЭНД заавал үүсгэнэ — эс бөгөөс анхны товшилт
        # `AttributeError` шидэж, хөрвүүлэлт хэзээ ч эхлэхгүй.
        self._file_busy = False

        self.transcripts = TranscriptStore()
        self.stats = UsageStats()
        # Хэцүү тохиолдлын дуу — сайжруулалтыг ХЭМЖИХ сан. Анхнаасаа
        # унтраалттай (хэрэглэгчийн дууг диск дээр бичдэг тул).
        self.samples = HardSampleStore(enabled=bool(self.cfg["save_hard_audio"]))
        self.formatter = Formatter(
            auto_space=self.cfg["auto_space"],
            auto_capitalize=self.cfg["auto_capitalize"],
            voice_punctuation=self.cfg["voice_punctuation"],
            replacements=self.cfg["replacements"],
            snippets=self.cfg["snippets"],
            names=self.cfg["names"],
        )
        # Өмнөх ажиллагааны түүхээр үрээнэ — эс бөгөөс хувилбар сонгох жин
        # апп нээх бүрд тэгээс эхэлнэ.
        for entry in self.transcripts.entries:
            if entry.get("mode") != "verbatim":
                self.formatter.remember(str(entry.get("text") or ""))
        self.recognizer = recognizer.create(self.cfg)
        self.target = TargetWindow()
        # Хуучин тохиргоонд нэр байхгүй тул эхлэхдээ нэг удаа нөхнө — эс бөгөөс
        # «нэрээр нь олох» нь микрофоноо дахин сонгосон хүнд л ажиллана.
        mic = mics.load(self.cfg)
        if mic != mics.Mic(int(self.cfg["mic_index"]), str(self.cfg["mic_name"])):
            mic.save_to(self.cfg)
            self.cfg.save()
        self.recorder = Recorder(
            on_segment=self._on_segment,
            on_level=self._on_level,
            on_error=self._on_audio_error,
            mic=mic,
            max_seconds=float(self.cfg["max_recording_seconds"]),
            silence_hold=float(self.cfg["silence_hold"]),
            keep_open_seconds=float(self.cfg["mic_keep_open_seconds"]),
            preroll_seconds=float(self.cfg["preroll_seconds"]),
            vad_enabled=bool(self.cfg["vad"]),
        )

        # Хөдөлгөөнийг цонх БАРИХААС өмнө тохируулна: виджет бүр өөрийн
        # `Motion`-ыг үүсгэх үедээ энэ утгыг уншина.
        animate.enabled = bool(self.cfg["animations"])

        self.root = tk.Tk()
        self.root.title("Monspeech")
        # Бусад апптай адил жирийн цонх: өөр програм руу шилжвэл ард нь
        # орно. Курсорын доорх долгион (overlay) л байнга дээр байна — тэр
        # нь тусдаа, фокус авдаггүй цонх.
        self._set_window_icon()
        self.ui = ControlWindow(self.root, self)
        self.overlay = WaveOverlay(self.root, get_level=lambda: self._level)

        self.hotkeys = HotkeyManager()
        self._bind_hotkeys()

        self.tray = Tray(
            on_toggle=lambda: self.events.put(("toggle", None)),
            on_show=lambda: self.events.put(("show", None)),
            on_quit=lambda: self.events.put(("quit", None)),
        )
        if self.cfg["tray_enabled"]:
            self.tray.start()

        self.worker = RecognitionWorker(
            segments=self.segments,
            events=self.events,
            cfg=self.cfg,
            recognizer=self.recognizer,
            formatter=self.formatter,
            stats=self.stats,
            transcripts=self.transcripts,
            insertions=self.insertions,
            target=self.target,
            insert_mode=self._insert_mode,
            provider_factory=lambda language: recognizer.create(self.cfg, language),
            samples=self.samples,
        )
        # Сүүлийн таван батлагдсан/оруулсан хэл session эхлэхэд prior болно.
        for entry in self.transcripts.entries[-5:]:
            self.worker.router.confirm_language(str(entry.get("lang") or ""))
        self.worker.start()

        # Ажлын ширээний дүрс дээр дахин товшиход энэ цонх урд нь гарна
        self.show_listener = ShowListener(lambda: self.events.put(("show", None)))
        self.show_listener.start()

        self._event_handlers = self._handlers()
        self._refresh_status()
        self.root.after(50, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        # Цонхны callback дотор гарсан алдааг Tk нь консол руу бичээд өнгөрдөг —
        # `.exe`-д консол байхгүй тул мөрдөх юм үлдэхгүй болно
        self.root.report_callback_exception = self._on_tk_exception
        # Аппыг гараар нээсэн бол хүн удирдлагын самбарыг харахыг хүсэж байна
        self.root.after(0, self.show_window)
        self.recognizer.prewarm_async()
        if self.cfg["check_updates"]:
            update.check_async(
                __version__, lambda tag: self.events.put(("update", tag))
            )
        log.info("апп эхэллээ (хэл=%s)", self.cfg["lang"])

    def _on_tk_exception(self, kind, value, trace) -> None:
        """Цонхны алдаа — логлоод үргэлжилнэ (апп бүхэлдээ унах ёсгүй)."""
        log.critical("цонхны алдаа", exc_info=(kind, value, trace))
        try:
            self.ui.set_detail("Цонхонд алдаа гарлаа — дэлгэрэнгүйг логоос үзнэ үү.")
        except Exception:  # noqa: BLE001 — алдаа мэдээлэх үедээ дахин унахгүй
            pass

    def _set_window_icon(self) -> None:
        from pathlib import Path

        icon = Path(__file__).resolve().parent.parent / "assets" / "monspeech.ico"
        if icon.exists():
            try:
                self.root.iconbitmap(default=str(icon))
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Микрофон
    # ------------------------------------------------------------------
    @staticmethod
    def microphones() -> list[Mic]:
        """Сонгож болох микрофонууд — эхнийх нь үргэлж системийн үндсэн."""
        return mics.available()

    def _mic_notice(self) -> str:
        """Сонгосон микрофоны ОРОНД өөр төхөөрөмж нээгдсэн бол хэлэх үг.

        Чимээгүй шилжвэл хүн чихэвчээрээ ярьж байгаад суурин микрофоноор
        бичигдсэнээ мэдэхгүй өнгөрнө. Нэрээр нь олдсон бол (дугаар нь шилжсэн
        ч ЯГ тэр төхөөрөмж) дуугарах шаардлагагүй — логонд л үлдэнэ.
        """
        mic = self.recorder.mic
        if mic.is_default or self.recorder.active_index is not None:
            return ""
        return f"«{mic.label}» олдсонгүй — системийн үндсэн микрофоноор бичиж байна."

    # ------------------------------------------------------------------
    # Дуу таних дамжлага
    # ------------------------------------------------------------------
    def _on_segment(self, pcm: bytes, final: bool) -> None:
        # Хэл ба цэвэрлэгээний шийдвэрийг сегменттэй хамт явуулна: таних ажил
        # дуусах үед фокус өөр цонх дээр байвал буруу цонхны дүрэм үйлчилнэ.
        self.segments.put(
            (
                pcm,
                self._active_lang,
                self._active_clean,
                self._active_auto,
                self._active_verbatim,
                self._active_command,
            )
        )
        self.events.put(("pending", +1))

    def _on_level(self, level: float) -> None:
        self._level = level

    def _on_audio_error(self, message: str) -> None:
        self.events.put(("audio_error", message))

    # ------------------------------------------------------------------
    # Tk эвентүүд
    # ------------------------------------------------------------------
    def _handlers(self) -> dict:
        """Эвентийн нэр → хариу үйлдэл. Шинэ эвент нэмэхэд нэг мөр хангалттай."""
        return {
            "recognized": self._on_recognized,
            "pending": self._on_pending,
            "empty": lambda reason: self._handle_empty(str(reason)),
            "update": lambda tag: self.ui.show_update(str(tag)),
            "error": lambda message: self._fail(str(message)),
            "audio_error": self._on_audio_failure,
            # Дуут үйлдлүүд. `pipeline` нь үйлдлийн нэрийг эвент болгон
            # илгээдэг тул шинийг нэмэхэд энд нэг мөр нэмэхэд хангалттай.
            "undo": lambda times: self.undo_last(_times(times)),
            "repeat": lambda times: self.repeat_last(_times(times)),
            "copy": lambda _: self.copy_last(),
            "copied": self._on_copied,
            # Дуут засвар: сүүлийн оруулгыг бүтнээр нь дахин бичих замаар
            # хэрэгжинэ (курсор дээрх байдал ба аппын санамж зөрөхгүй).
            "drop_words": lambda count: self.edit_last("drop_words", count),
            "capitalize": lambda _: self.edit_last("capitalize"),
            "lowercase": lambda _: self.edit_last("lowercase"),
            "no_space": lambda _: self.edit_last("no_space"),
            "replace_word": lambda words: self.edit_last("replace_word", words),
            "variant": lambda _: self.cycle_variant(),
            "misdirected": self._on_misdirected,
            "file_progress": self._on_file_progress,
            "file_done": self._on_file_done,
            "command": self._on_command,
            "command_missed": self._on_command_missed,
            "stop": lambda _: self.stop(),
            "toggle": lambda _: self.toggle(),
            "ptt": self._on_ptt,
            "captured": lambda payload: self.ui.finish_capture(*payload),
            "show": lambda _: self.show_window(),
        }

    def _on_recognized(self, payload) -> None:
        text, entry, *rest = payload
        variants = rest[0] if rest else []
        # Хоёроос цөөн хувилбартай бол сэлгэх зүйл алга — төлвөө цэвэрлэнэ.
        self._variants = (
            {"items": list(variants), "index": 0, "entry": entry}
            if len(variants) > 1
            else None
        )
        language = str(entry.get("lang") or "")
        label = {"mn-MN": "MN", "en-US": "EN", "mixed": "MN+EN"}.get(
            language, language
        )
        confidence = entry.get("confidence")
        meta = label
        if confidence is not None:
            meta += f" {float(confidence) * 100:.0f}%"
        self.ui.set_detail(f"{text}  ·  {meta}" if meta else text)
        self.ui.refresh_history()
        self.ui.refresh_stats()
        if self.cfg["wave_overlay"] and not self.listening:
            self.overlay.flash(text)

    def _on_copied(self, length) -> None:
        self.ui.set_detail(f"Clipboard руу хууллаа ({int(length)} тэмдэгт).")
        if self.cfg["wave_overlay"]:
            self.overlay.flash("Хууллаа")

    def _on_misdirected(self, text) -> None:
        """Зорилтот цонх алга — текстийг хаясангүй, clipboard руу хуулна.

        Чимээгүй өнгөрөх нь хамгийн муу: хэрэглэгч ярьсан зүйл нь хаана ч
        гарахгүй бол алдагдсан гэж бодно. Түүхэнд аль хэдийн бичигдсэн тул
        энд зөвхөн хурдан гарц (Ctrl+V) санал болгоно.
        """
        content = str(text).strip()
        if content and injector.copy_to_clipboard(content):
            message = "Зорилтот цонх идэвхжсэнгүй — clipboard-д хууллаа (Ctrl+V)."
        else:
            message = "Зорилтот цонх идэвхжсэнгүй — текст Түүхэнд үлдлээ."
        log.warning("%s", message)
        self.ui.set_detail(message)
        if self.cfg["wave_overlay"]:
            self.overlay.flash("Цонх идэвхжсэнгүй", kind="warning")

    def _on_command(self, pressed) -> None:
        """Команд товчлуур дарагдсан/суллагдсан."""
        if pressed:
            self.start(command=True)
        else:
            self.stop()

    def _on_command_missed(self, phrase) -> None:
        heard = str(phrase).strip()
        log.info("команд танигдсангүй: %d тэмдэгт", len(heard))
        self.ui.set_detail(f"Танихгүй команд: «{heard}»")
        if self.cfg["wave_overlay"]:
            self.overlay.flash(f"«{heard}» — команд биш", kind="warning")

    def _on_file_progress(self, payload) -> None:
        index, total = payload
        self.ui.set_file_progress(f"Хөрвүүлж байна… {index}/{total}")

    def _on_file_done(self, payload) -> None:
        message, text = payload
        self.ui.set_file_progress(message)
        self.ui.set_detail(message)
        self.ui.refresh_history()
        if text and self.cfg["wave_overlay"]:
            self.overlay.flash("Хөрвүүлж дууслаа")

    def transcribe_file(self, path: str) -> None:
        """Аудио/видео файлыг дэвсгэрт хөрвүүлнэ (цонх царцахгүй).

        Үр дүнг эх файлын хажууд `.txt` болгож хадгална — урт бичлэгийн
        текстийг курсор руу шидэх нь утгагүй, харин файл нь хаана ч хэрэгтэй.
        Мөр бүрийг Түүхэнд ч нэмнэ: хайлт, толь сурах хоёр тэндээс ажиллана.
        """
        if self._file_busy:
            self.ui.set_detail("Өмнөх файл хараахан дуусаагүй байна.")
            return
        self._file_busy = True
        self.ui.set_file_progress("Файлыг уншиж байна…")
        threading.Thread(target=self._transcribe_file, args=(path,), daemon=True).start()

    def _transcribe_file(self, path: str) -> None:
        try:
            text = filetext.transcribe(
                path,
                self.recognizer,
                lang=str(self.cfg["lang"]),
                on_progress=lambda index, total: self.events.put(
                    ("file_progress", (index, total))
                ),
            )
            if not text.strip():
                self.events.put(("file_done", ("Файлаас текст гарсангүй.", "")))
                return
            for line in text.splitlines():
                if line.strip():
                    self.transcripts.add(line.strip(), str(self.cfg["lang"]))
            target = filetext.save_text(path, text)
            words = len(text.split())
            self.events.put(
                ("file_done", (f"Бэлэн: {words} үг → {target.name}", text))
            )
        except filetext.FileError as exc:
            self.events.put(("file_done", (str(exc), "")))
        except Exception as exc:  # noqa: BLE001 - файл хөрвүүлэлт аппыг унагахгүй
            log.exception("файл хөрвүүлэхэд алдаа")
            self.events.put(("file_done", (f"Хөрвүүлж чадсангүй: {exc}", "")))
        finally:
            self._file_busy = False

    def _on_pending(self, delta) -> None:
        self._pending = max(0, self._pending + int(delta))
        self._after_pending_change()

    def _on_audio_failure(self, message) -> None:
        self.stop()
        self._fail(str(message))

    def _on_ptt(self, payload) -> None:
        lang, pressed = payload
        self.start(str(lang) or None) if pressed else self.stop()

    def _drain_events(self) -> None:
        """Дарааллыг цэвэрлээд өөрийгөө дахин товлоно.

        Дахин товлолт нь ЗААВАЛ хийгдэнэ (`finally`). Энэ дуудлага хагас
        замдаа алдаагаар таслагдвал Tk нь алдааг логлоод залгина — апп амьд
        харагдсаар байгаад эвент боловсруулахаа БҮРМӨСӨН болино: таньсан текст
        гарахгүй, төлөв шинэчлэгдэхгүй, статистик хадгалагдахгүй. Нэг виджетийн
        алдаа аппыг бүхэлд нь ингэж унтраах ёсгүй тул хариу үйлдэл бүрийг
        тусад нь ч хамгаална.
        """
        handlers = self._event_handlers
        quitting = False
        try:
            while True:
                try:
                    kind, payload = self.events.get_nowait()
                except queue.Empty:
                    break
                if kind == "quit":
                    quitting = True  # цонх устаж байгаа тул дахин товлохгүй
                    self.quit()
                    return
                handler = handlers.get(kind)
                if handler is None:
                    log.warning("танихгүй эвент: %s", kind)
                    continue
                try:
                    handler(payload)
                except Exception:  # noqa: BLE001 - нэг эвент бусдыг зогсоохгүй
                    log.exception("«%s» эвент бүтэлгүйтлээ", kind)
            self.ui.set_level(self._level, self.listening)
            self._keepalive()
            self.stats.save()
        except Exception:  # noqa: BLE001
            log.exception("эвент дамжуулагчид алдаа гарлаа")
        finally:
            if not quitting:
                self.root.after(50, self._drain_events)

    def _after_pending_change(self) -> None:
        if not self.listening and not self._pending and self.overlay.mode != "message":
            self.overlay.hide()
        self._refresh_status()
        if self._pending >= QUEUE_LIMIT and self.listening:
            self.stop()
            self._fail("Сүлжээ хоцорч байна — бичлэгийг зогсоолоо.")

    def _handle_empty(self, reason: str) -> None:
        """Юу ч танигдаагүйг хэрэглэгчид мэдэгдэнэ (чимээгүй бүтэлгүйтэхгүй)."""
        if self.listening or self._pending:
            return  # урт ярианы дунд бол чимээгүй өнгөрнө
        messages = {
            "low_confidence": "Итгэлтэй таньж чадсангүй — дахин хэлнэ үү",
            "filler": "Зөвхөн чигчлүүр үг сонсогдлоо",
        }
        message = messages.get(reason, "Таньж чадсангүй — дахин хэлнэ үү")
        self.ui.set_detail(message)
        if self.cfg["wave_overlay"]:
            self.overlay.flash(message, kind="warning")

    def _keepalive(self) -> None:
        """Урт яриан дунд холболт хуучирч, саатал үүсгэхээс сэргийлнэ."""
        if not self.listening:
            return
        now = time.monotonic()
        if now - self._last_prewarm > KEEPALIVE_SECONDS:
            self._last_prewarm = now
            self.recognizer.prewarm_async()

    # ------------------------------------------------------------------
    # Төлөв
    # ------------------------------------------------------------------
    def _refresh_status(self) -> None:
        hint = f"{pretty(self.cfg['ptt_key'])} дарж бариад ярь"
        if self.listening:
            self.ui.set_state(
                "listening", "Сонсож байна", f"{pretty(self.cfg['ptt_key'])} тавихад орно"
            )
        elif self._pending > QUEUE_WARN:
            self.ui.set_state(
                "working", "Таниж байна", f"{self._pending} хэсэг хүлээгдэж байна"
            )
        elif self._pending:
            self.ui.set_state("working", "Таниж байна", "")
        else:
            self.ui.set_state("ready", "Бэлэн", hint)

    def _fail(self, message: str) -> None:
        log.warning("%s", message)
        self.ui.set_state("error", "Алдаа", message)
        if not self.root.winfo_viewable():
            self.tray.notify(message)

    def open_log(self) -> None:
        try:
            subprocess.Popen(["notepad.exe", str(LOG_PATH)])
        except OSError as exc:
            self.ui.set_detail(f"Лог нээгдсэнгүй: {exc}")

    def open_releases(self) -> None:
        try:
            webbrowser.open(update.RELEASES_URL)
        except OSError as exc:  # хөтөч байхгүй байж болно
            self.ui.set_detail(f"Хөтөч нээгдсэнгүй: {exc}")

    def diagnostics(self) -> str:
        """Алдаа мэдээлэхэд хавсаргах товч мэдээлэл.

        Хэрэглэгчийн ярианы текст, API түлхүүр энд ОРОХГҮЙ — хэн нэгэн рүү
        зүгээр хуулж явуулж болохуйц байх ёстой.
        """
        provider = self.cfg["stt_provider"]
        lines = [
            f"Monspeech {__version__}",
            f"Windows {platform.version()} ({platform.machine()})",
            f"Python {sys.version.split()[0]}"
            + (" (багцалсан)" if getattr(sys, "frozen", False) else ""),
            f"Танигч: {provider}" + (" (өөрийн хаягтай)" if self.cfg["stt_url"] else ""),
            f"Хэл: {self.cfg['lang']} / {self.cfg['lang_alt']}",
            # Сонгосон нь ба ҮНЭХЭЭР нээгдсэн нь: хоёр нь зөрсөн бол
            # төхөөрөмжийн дугаар шилжсэн гэсэн үг — оношилгооны гол мөр.
            # Төхөөрөмжийн нэр нь хүний нэр агуулж мэднэ («Dash's Buds») тул
            # энд зөвхөн дугаарууд орно — энэ текстийг хүн рүү явуулдаг.
            f"Микрофон: №{self.recorder.mic.index} → "
            + (
                f"нээгдсэн №{self.recorder.active_index}"
                if self.recorder.stream_open
                else "хаалттай"
            ),
            f"Толь: {len(self.cfg['replacements'])} үг, {len(self.cfg['snippets'])} товчлол",
            f"Лог: {LOG_PATH}",
        ]
        return "\n".join(lines)

    def copy_diagnostics(self) -> str:
        try:
            pyperclip.copy(self.diagnostics())
        except pyperclip.PyperclipException as exc:
            return f"Хуулж чадсангүй: {exc}"
        return "Мэдээллийг хууллаа — алдаа мэдээлэхдээ буулгана уу."

    def finish_onboarding(self) -> None:
        self.cfg["onboarded"] = True
        self.cfg.save()

    # ------------------------------------------------------------------
    # Цонхноос ирэх өөрчлөлтүүд
    # ------------------------------------------------------------------
    def on_lang_changed(self, code: str) -> None:
        self.cfg["lang"] = code
        self.recognizer.lang = code
        self._active_lang = code
        self.formatter.reset()
        self.cfg.save()
        self.ui.set_detail(f"Хэл: {CODE_TO_NAME.get(code, code)}")

    def on_alt_lang_changed(self, code: str) -> None:
        """Хоёрдогч товчлуураар ярих хэл. Товчлуурыг дахин холбох шаардлагагүй —
        холбоос нь дарах агшинд тохиргооноос уншдаг."""
        self.cfg["lang_alt"] = code
        self.cfg.save()
        self.ui.set_detail(
            f"{pretty(self.cfg['ptt_key_alt'])}: {CODE_TO_NAME.get(code, code)}"
        )

    def on_stt_changed(self, values: dict[str, str]) -> None:
        """Танигчийн тохиргоо солигдлоо — хуучныг хааж, шинийг нь босгоно.

        Ажлын thread нь `self.recognizer`-ыг зөвхөн уншдаг тул солих нь аюулгүй:
        сая эхэлсэн таних ажил хуучин объектоороо дуусаад, дараагийнх нь
        шинийг ашиглана.
        """
        for key, value in values.items():
            self.cfg[key] = value
        previous = self.recognizer
        self.recognizer = recognizer.create(self.cfg)
        try:
            previous.close()
        except Exception as exc:  # noqa: BLE001
            log.warning("хуучин танигчийг хаахад алдаа: %s", exc)
        self.worker.set_recognizer(
            self.recognizer,
            lambda language: recognizer.create(self.cfg, language),
        )
        self.recognizer.prewarm_async()
        self.cfg.save()
        title = dict(recognizer.titles()).get(
            self.cfg["stt_provider"], self.cfg["stt_provider"]
        )
        log.info("танигч солигдлоо: %s", self.cfg["stt_provider"])
        self.ui.set_detail(f"Танигч: {title}")

    def on_theme_changed(self, code: str) -> None:
        """Өнгөний сэдэв солигдлоо.

        Шууд хэрэглэж чадахгүй: виджетүүд өнгөө импортын үед анхны утга болгон
        авдаг тул зөвхөн дахин эхлүүлэхэд идэвхжинэ. Үүнийг шулуун хэлнэ —
        сольсон мөртлөө юу ч болохгүй бол хэрэглэгч эвдэрсэн гэж бодно.
        """
        self.cfg["theme"] = code
        self.cfg.save()
        log.info("сэдэв солигдлоо: %s (дахин эхлүүлэхэд идэвхжинэ)", code)
        self.ui.set_detail("Сэдэв хадгалагдлаа — дахин эхлүүлэхэд идэвхжинэ.")

    def on_mic_changed(self, mic: Mic) -> None:
        # Дугаарын хажуугаар нэрийг нь хадгална: чихэвч салгаж холбоход дугаар
        # шилждэг тул дараа нь нэрээр нь дахин олно (`mics.resolve`).
        mic.save_to(self.cfg)
        self.recorder.mic = mic
        self.recorder.close()  # шинэ төхөөрөмжөөр дахин нээгдэнэ
        self.cfg.save()
        self.ui.set_detail("Микрофон солигдлоо.")

    def on_option_changed(self, key: str, value: bool) -> None:
        """Чагт бүр тэр дороо үйлчлэх ёстой — дахин эхлүүлэх шаардлагагүй."""
        self.cfg[key] = bool(value)
        self.formatter.update(
            auto_space=self.cfg["auto_space"],
            auto_capitalize=self.cfg["auto_capitalize"],
            voice_punctuation=self.cfg["voice_punctuation"],
        )
        if key == "animations":
            animate.enabled = bool(value)
        if key == "vocabulary_boost":
            self.refresh_vocabulary()
        elif key == "double_tap_enabled":
            self._bind_hotkeys()
        if key == "ptt_enabled":
            self._bind_hotkeys()
        elif key == "tray_enabled":
            self._apply_tray_setting()
        elif key == "wave_overlay" and not value:
            self.overlay.hide()
        elif key == "start_with_windows":
            self._apply_autostart_setting(bool(value))
        elif key == "vad":
            self.recorder.set_vad(bool(value))
        elif key == "save_hard_audio":
            self.samples.set_enabled(bool(value))
            self.ui.refresh_samples()
        self.cfg.save()

    def _apply_autostart_setting(self, wanted: bool) -> None:
        """Бүртгэлд бичихэд амжилтгүй бол чагтыг үнэн байдалд нь буцаана."""
        error = autostart.apply(wanted)
        if not error:
            return
        self.cfg["start_with_windows"] = not wanted
        toggle = self.ui.toggles.get("start_with_windows")
        if toggle:
            toggle.set(self.cfg["start_with_windows"])
        self.ui.set_detail(error)

    def _apply_tray_setting(self) -> None:
        if self.cfg["tray_enabled"]:
            self.tray.start()
            self.tray.set_active(self.listening)
            if not self.tray.running:
                self.ui.set_detail("Tray дүрс ажиллуулж чадсангүй.")
        else:
            self.tray.stop()

    def on_tuning_changed(self, key: str, value) -> None:
        self.cfg[key] = value
        if key == "silence_hold":
            self.recorder.segmenter.silence_hold = float(value)
        elif key == "mic_keep_open_seconds":
            self.recorder.keep_open_seconds = float(value)
            if not value:
                self.recorder.close()
        elif key == "preroll_seconds":
            self.recorder.preroll_seconds = float(value)
        elif key == "max_recording_seconds":
            # Явж байгаа бичлэгт ч шууд үйлчилнэ
            self.recorder.max_seconds = float(value)
        self.cfg.save()

    def _match_window(self, markers) -> str | None:
        """Идэвхтэй цонхны гарчигт таарах эхний тэмдэг."""
        return winfocus.match_marker(self.target.title(), markers)

    def _insert_mode(self) -> str:
        """Энэ цонхонд clipboard ажилладаггүй бол шууд бичих горимд шилжинэ."""
        if self.cfg["type_mode"]:
            return "type"
        return "type" if self._match_window(self.cfg["type_mode_apps"]) else "paste"

    def _window_lang(self) -> str:
        """Идэвхтэй цонхонд тохирсон хэл, эс бөгөөс үндсэн хэл.

        Cursor дээр англиар, Messenger дээр монголоор бичдэг хүн товчлуураа
        сольж санахаа болино — цонх нь өөрөө хэлээ хэлнэ.
        """
        marker = self._match_window(self.cfg["lang_apps"])
        if marker is None:
            return str(self.cfg["lang"])
        return str(self.cfg["lang_apps"].get(marker) or self.cfg["lang"])

    def _window_clean(self) -> bool:
        """Энэ цонхонд ярианы чигчлүүрийг цэвэрлэх үү.

        Ерөнхий тохиргоо асаалттай ч зарим цонхонд ҮГЧЛЭН бичих хэрэгтэй
        байдаг (эш татах, ярианы тэмдэглэл) — тэднийг жагсаалтаар хасна.
        Хэлний адилаар шийдвэрийг товч дарсан агшинд гаргана: таних ажил
        дуусах үед фокус аль хэдийн өөр цонх дээр байж болно.
        """
        verbatim = bool(self.cfg.get("verbatim_mode", False)) or (
            self._match_window(self.cfg["no_clean_apps"]) is not None
        )
        return bool(self.cfg["clean_speech"]) and not verbatim

    def _window_verbatim(self) -> bool:
        """Глобал эсвэл цонхны дүрмээр бүрэн үгчлэн бичих эсэх."""

        if self.cfg["verbatim_mode"]:
            return True
        return self._match_window(self.cfg["no_clean_apps"]) is not None

    def _remember_window_in(self, key: str, label: str) -> str:
        """Одоогийн цонхны нэрийг заасан жагсаалтад нэмнэ."""
        title = self.target.title()
        if not title:
            return "Цонх тодорхойгүй байна."
        marker = title.split(" - ")[-1].strip()[:40] or title[:40]
        apps = list(self.cfg[key])
        if marker.lower() in [a.lower() for a in apps]:
            return f"«{marker}» аль хэдийн жагсаалтад байна."
        apps.append(marker)
        self.cfg[key] = apps
        self.cfg.save()
        return f"«{marker}» цонхонд одооноос {label}."

    #: Дүрмийн төрөл → тохиргооны түлхүүр. Жагсаалтын төрлүүд л энд байна;
    #: хэл нь толь (`lang_apps`) тул тусад нь.
    RULE_LISTS = {"type_mode": "type_mode_apps", "no_clean": "no_clean_apps"}

    def current_window_marker(self) -> str:
        """Товч дарсан агшны цонхны нэрнээс дүрэмд тохирох хэсгийг гаргана."""
        title = self.target.title()
        if not title:
            return ""
        return title.split(" - ")[-1].strip()[:40] or title[:40]

    def window_rules(self) -> list[dict]:
        """Гурван тусдаа жагсаалтыг апп тус бүрээр нэгтгэж харуулна.

        Хэрэглэгч «энэ цонхонд юу үйлчилж байна вэ» гэдгээ нэг дор харах
        ёстой — өмнө нь хэл нь Толинд, бусад нь Бичилт дээр тарсан байв.
        """
        rules: dict[str, dict] = {}

        def slot(marker: str) -> dict:
            return rules.setdefault(
                marker,
                {"marker": marker, "lang": "", "type_mode": False, "no_clean": False},
            )

        for marker, code in dict(self.cfg["lang_apps"]).items():
            slot(str(marker))["lang"] = str(code)
        for kind, key in self.RULE_LISTS.items():
            for marker in list(self.cfg[key]):
                slot(str(marker))[kind] = True
        return [rules[name] for name in sorted(rules, key=str.lower)]

    def window_rule(self, marker: str) -> dict:
        """Нэг аппын дүрэм (байхгүй бол хоосон утгууд)."""
        marker = (marker or "").strip().lower()
        for rule in self.window_rules():
            if rule["marker"].lower() == marker:
                return rule
        return {"marker": marker, "lang": "", "type_mode": False, "no_clean": False}

    def set_window_rule(self, marker: str, kind: str, value) -> str:
        """Нэг дүрмийг тавих/авах. Хоосон утга нь дүрмийг устгана."""
        marker = (marker or "").strip()
        if not marker:
            return "Цонх тодорхойгүй байна."
        if kind == "lang":
            mapping = {
                name: code
                for name, code in dict(self.cfg["lang_apps"]).items()
                if str(name).lower() != marker.lower()
            }
            if value:
                mapping[marker] = str(value)
            self.cfg["lang_apps"] = mapping
        else:
            key = self.RULE_LISTS[kind]
            apps = [a for a in self.cfg[key] if str(a).lower() != marker.lower()]
            if value:
                apps.append(marker)
            self.cfg[key] = apps
        self.cfg.save()
        log.info("«%s» цонхны дүрэм шинэчлэгдлээ (%s)", marker, kind)
        return f"«{marker}» дүрэм хадгалагдлаа."

    def remove_window_rule(self, marker: str) -> str:
        """Тухайн аппын БҮХ дүрмийг устгана."""
        marker = (marker or "").strip()
        if not marker:
            return "Цонх тодорхойгүй байна."
        self.set_window_rule(marker, "lang", "")
        for kind in self.RULE_LISTS:
            self.set_window_rule(marker, kind, False)
        return f"«{marker}» дүрэм устлаа."

    def remember_type_mode_app(self) -> str:
        """Одоогийн цонхыг «шууд бичих» жагсаалтад нэмнэ."""
        return self._remember_window_in("type_mode_apps", "шууд бичнэ")

    def remember_no_clean_app(self) -> str:
        """Одоогийн цонхыг «цэвэрлэхгүй» жагсаалтад нэмнэ."""
        return self._remember_window_in("no_clean_apps", "үгчлэн бичнэ")

    def on_snippets_changed(self, raw: str) -> int:
        mapping = parse_replacements(raw)
        self.cfg["snippets"] = mapping
        self.formatter.set_snippets(mapping)
        self.cfg.save()
        self.ui.set_detail(f"{len(mapping)} товчлол хадгалагдлаа.")
        return len(mapping)

    def on_actions_changed(self, raw: str) -> int:
        """Хэрэглэгчийн дуут үйлдлийн толь. Дамжлага нь `cfg`-ээс шууд уншина."""
        mapping = parse_actions(raw)
        self.cfg["actions"] = mapping
        self.cfg.save()
        self.ui.set_detail(f"{len(mapping)} дуут үйлдэл хадгалагдлаа.")
        return len(mapping)

    def on_names_changed(self, raw: str) -> int:
        mapping = parse_replacements(raw)
        self.cfg["names"] = mapping
        self.formatter.set_names(mapping)
        self.cfg.save()
        self.refresh_vocabulary()
        self.ui.set_detail(f"{len(mapping)} нэр хадгалагдлаа.")
        return len(mapping)

    def on_lang_apps_changed(self, raw: str) -> int:
        """Аппаар ялгах хэлний хүснэгт солигдлоо.

        Танихгүй хэлний кодыг чимээгүй хаяхгүй — хэрэглэгч бичсэн зүйл нь
        ажиллахгүй бол шалтгааныг нь хэлнэ.
        """
        mapping = parse_replacements(raw)
        unknown = unknown_language_codes(mapping)
        self.cfg["lang_apps"] = mapping
        self.cfg.save()
        if unknown:
            self.ui.set_detail(f"Танихгүй хэлний код: {', '.join(unknown)}")
        else:
            self.ui.set_detail(f"{len(mapping)} аппын хэл хадгалагдлаа.")
        return len(mapping)

    def on_transcript_corrected(self, entry: dict, corrected: str) -> str:
        """Түүхэн дэх мөрийг зассан — ялгааг нь толинд сурна."""
        heard = entry.get("text", "")
        # Дууг нь зөв текстийн хамт хадгална: benchmark-ийн хамгийн үнэ
        # цэнэтэй мөр нь ЯГ энэ — хүн буруу гэдгийг нь баталсан жишээ.
        # `replace()`-ийн ӨМНӨ: тэр нь `entry["text"]`-ийг дарж бичдэг тул
        # дараа нь дуудвал «юу сонссон» тал нь алдагдана.
        self.samples.promote(entry, corrected)
        self.transcripts.replace(entry, corrected)
        if not self.cfg["learn_corrections"]:
            return "Түүх зассан."
        learned = self._learn_pair(heard, corrected)
        if not learned:
            return "Түүх зассан (сурах үг олдсонгүй)."
        pairs = ", ".join(f"{k} → {v}" for k, v in learned.items())
        return f"Сурлаа: {pairs}"

    def clear_samples(self) -> str:
        """Хадгалсан хэцүү жишээг бүгдийг устгана."""
        self.samples.clear()
        log.info("хэцүү жишээнүүдийг цэвэрлэлээ")
        return "Жишээнүүдийг устгалаа."

    def refresh_vocabulary(self) -> None:
        """Толиос бэлдсэн дохиог ажиллаж байгаа танигчид тарааана.

        Танигчийг дахин бүтээхгүй: холболт, урьдчилсан дулаацуулалт хэвээр
        үлдэнэ — толь засах нь дараагийн бичлэгийг хойшлуулах ёсгүй.
        """
        hint = recognizer.vocabulary_for(self.cfg)
        try:
            self.recognizer.set_vocabulary(hint)
            self.worker.router.set_vocabulary(hint)
        except Exception as exc:  # noqa: BLE001 - дохиогүй ч танилт ажиллана
            log.warning("толийн дохиог шинэчилж чадсангүй: %s", exc)
            return
        log.info("толийн дохио: %d тэмдэгт", len(hint))

    def _learn_pair(self, heard: str, corrected: str) -> dict[str, str]:
        """Буруу/зөв хосоос ялгаатай үгсийг толинд нэмнэ. Нэмэгдсэнийг буцаана."""
        learned = learn_corrections(heard, corrected)
        if not learned:
            return {}
        mapping = dict(self.cfg["replacements"])
        mapping.update(learned)
        self.cfg["replacements"] = mapping
        self.formatter.update(
            auto_space=self.cfg["auto_space"],
            auto_capitalize=self.cfg["auto_capitalize"],
            voice_punctuation=self.cfg["voice_punctuation"],
            replacements=mapping,
        )
        self.cfg.save()
        self.refresh_vocabulary()
        self.ui.refresh_words()
        log.info("толинд нэмэгдлээ: %s", ", ".join(f"{k} → {v}" for k, v in learned.items()))
        return learned

    def on_transcript_language_changed(self, entry: dict, language: str) -> str:
        """Түүхээс баталсан хэлийг хадгалж, session-ийн auto prior-д сургана."""

        self.transcripts.set_language(entry, language)
        self.worker.router.confirm_language(language)
        label = CODE_TO_NAME.get(language, language)
        log.info("түүхийн хэлийг хэрэглэгч батлав: %s", language)
        return f"Хэл батлагдлаа: {label}."

    def on_replacements_changed(self, raw: str) -> int:
        mapping = parse_replacements(raw)
        self.cfg["replacements"] = mapping
        self.formatter.update(
            auto_space=self.cfg["auto_space"],
            auto_capitalize=self.cfg["auto_capitalize"],
            voice_punctuation=self.cfg["voice_punctuation"],
            replacements=mapping,
        )
        self.cfg.save()
        self.refresh_vocabulary()
        self.ui.set_detail(f"{len(mapping)} орлуулга хадгалагдлаа.")
        return len(mapping)

    def on_hotkey_changed(self, key: str, combo: str) -> str | None:
        """Шинэ товчлуурыг хадгална. Алдаатай бол мессеж буцаана."""
        try:
            parse_combo(combo)
        except (ValueError, KeyError):
            return f"'{combo}' товчлуурыг таньсангүй."
        for other in HOTKEY_KEYS:
            if other != key and self.cfg[other] == combo:
                return f"{pretty(combo)} аль хэдийн «{_key_label(other)}»-д ашиглагдаж байна."
        self.cfg[key] = combo
        self._bind_hotkeys()
        self.cfg.save()
        self.ui.set_detail(f"{_key_label(key)}: {pretty(combo)}")
        self._refresh_status()
        return None

    def begin_hotkey_capture(self, key: str) -> None:
        self.hotkeys.capture(lambda combo: self.events.put(("captured", (key, combo))))

    def cancel_hotkey_capture(self) -> None:
        self.hotkeys.cancel_capture()

    def repaste(self, text: str) -> None:
        self.ui.set_detail("2 секундын дотор курсороо тавь — дахин буулгана.")
        self.root.after(2000, lambda: self._deliver(text + " ", 0))

    # ------------------------------------------------------------------
    # Товчлуур
    # ------------------------------------------------------------------
    def _bind_hotkeys(self) -> None:
        try:
            self.hotkeys.clear()
            self.hotkeys.bind(
                "toggle", self.cfg["hotkey"], on_press=lambda: self.events.put(("toggle", None))
            )
            self.hotkeys.bind(
                "undo", self.cfg["undo_key"], on_press=lambda: self.events.put(("undo", None))
            )
            self.hotkeys.bind(
                "variant",
                self.cfg["variant_key"],
                on_press=lambda: self.events.put(("variant", None)),
            )
            if self.cfg["double_tap_enabled"]:
                # Гар байрлалаа алдалгүй асаах: Ctrl-ыг хоёр хурдан дарна.
                self.hotkeys.bind_double(
                    "double_tap",
                    self.cfg["double_tap_key"],
                    lambda: self.events.put(("toggle", None)),
                )
            self.hotkeys.bind(
                "command",
                self.cfg["command_key"],
                on_press=lambda: self.events.put(("command", True)),
                on_release=lambda: self.events.put(("command", False)),
            )
            if self.cfg["ptt_enabled"]:
                self.hotkeys.bind(
                    "ptt",
                    self.cfg["ptt_key"],
                    on_press=lambda: self.events.put(("ptt", ("", True))),
                    on_release=lambda: self.events.put(("ptt", ("", False))),
                )
                self.hotkeys.bind(
                    "ptt_alt",
                    self.cfg["ptt_key_alt"],
                    on_press=lambda: self.events.put(("ptt", (self.cfg["lang_alt"], True))),
                    on_release=lambda: self.events.put(("ptt", (self.cfg["lang_alt"], False))),
                )
            self.hotkeys.start()
        except Exception as exc:  # noqa: BLE001 - товчлуургүй ч апп ажиллана
            log.error("товчлуур бүртгэгдсэнгүй: %s", exc)
            self.ui.set_detail(f"Товчлуур бүртгэгдсэнгүй: {exc}")

    # ------------------------------------------------------------------
    # Текст оруулах
    # ------------------------------------------------------------------
    def _deliver(self, text: str, backspaces: int, remember: bool = True) -> None:
        """Текстийг тусдаа thread дээр оруулна.

        Зорилтот цонхыг идэвхжүүлэх нь хэдэн зуун миллисекунд авч болох тул
        Tk-ийн үндсэн thread дээр хийвэл цонх мэдэгдэхүйц царцана.
        """
        threading.Thread(
            target=lambda: self.worker.deliver(text, backspaces, remember),
            daemon=True,
        ).start()

    def undo_last(self, times: int = 1) -> None:
        """Сүүлийн `times` оруулгыг устгана.

        Оруулгууд курсор дээр зэрэгцээ байрлах тул нийт тэмдэгтийг НЭГ
        удаагийн устгалаар явуулна — олон thread ээлжлэн бичихээс сэргийлнэ.
        """
        count = 0
        taken = 0
        for _ in range(times):
            item = self.insertions.take_last()
            if not item:
                break
            count += item[1]
            taken += 1
        if not count:
            self.ui.set_detail("Буцаах зүйл алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Буцаах зүйл алга", kind="warning")
            return
        log.info("буцаалаа: %d оруулга, %d тэмдэгт", taken, count)
        self._deliver("", count, remember=False)
        suffix = f" ×{taken}" if taken > 1 else ""
        self.ui.set_detail(f"Буцаалаа{suffix} ({count} тэмдэгт).")
        if self.cfg["wave_overlay"]:
            self.overlay.flash(f"Буцаалаа{suffix}", kind="warning")

    def repeat_last(self, times: int = 1) -> None:
        """Сүүлд оруулсан текстийг дахин буулгана.

        Шинэ оруулга болгож санана — «давт» гэсний дараа «буцаа» гэвэл
        зөвхөн давтсан хувь нь устана.
        """
        text = self.insertions.last()
        if not text:
            self.ui.set_detail("Давтах зүйл алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Давтах зүйл алга", kind="warning")
            return
        repeated = text * times
        log.info("давтлаа: %d тэмдэгт", len(repeated))
        self._deliver(repeated, 0)
        suffix = f" ×{times}" if times > 1 else ""
        self.ui.set_detail(f"Давтлаа{suffix}.")
        if self.cfg["wave_overlay"]:
            self.overlay.flash(f"Давтлаа{suffix}")

    def cycle_variant(self) -> None:
        """Сүүлийн таналтыг танигчийн дараагийн хувилбараар солино.

        Дахин ярих шаардлагагүй: танигч 3-5 хувилбар буцаадаг ба өмнө нь
        зөвхөн эхнийхийг нь авч, үлдсэнийг хаядаг байсан.
        """
        state = self._variants
        if not state:
            self.ui.set_detail("Сэлгэх хувилбар алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Хувилбар алга", kind="warning")
            return
        items = state["items"]
        current = items[state["index"]]
        # Хэрэглэгч энэ хооронд өөр зүйл бичсэн бол хөндөхгүй: устгах тэмдэгтийн
        # тоо таарахгүй тул буруу текст устана.
        if self.insertions.last() != current:
            self._variants = None
            self.ui.set_detail("Текст өөрчлөгдсөн — хувилбар сэлгэсэнгүй.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Хувилбар сэлгэсэнгүй", kind="warning")
            return

        index = (state["index"] + 1) % len(items)
        state["index"] = index
        following = items[index]
        self.insertions.take_last()  # хуучин оруулгыг түүхээс гаргана
        self._deliver(following, len(current))
        shown = following.strip()
        log.info("хувилбар %d/%d сонголоо", index + 1, len(items))
        self.samples.promote(state["entry"], shown)  # `replace`-ийн ӨМНӨ
        self.transcripts.replace(state["entry"], shown)
        self.formatter.remember(shown)
        # Хэрэглэгч зориудаар сонгосон тул анхны хувилбарыг «буруу таньсан»
        # гэж үзэж толинд сурна. Үргэлж ЭХНИЙХЭЭС нь сурна — хоёр дахиас
        # гурав дахь руу шилжихэд завсрын алдаатай хос үлдэхгүй.
        if index and self.cfg["learn_corrections"]:
            self._learn_pair(items[0].strip(), shown)
        self.ui.refresh_history()
        self.ui.set_detail(f"Хувилбар {index + 1}/{len(items)}: {shown}")
        if self.cfg["wave_overlay"]:
            self.overlay.flash(shown)

    #: Дуут засварын нэр → хэрэглэгчид хэлэх богино тайлбар.
    EDIT_LABELS = {
        "drop_words": "Устгалаа",
        "capitalize": "Том үсэг болголоо",
        "lowercase": "Жижиг үсэг болголоо",
        "no_space": "Зайг авлаа",
        "replace_word": "Сольлоо",
    }

    def edit_last(self, kind: str, argument="") -> None:
        """Сүүлийн оруулгыг дуут заавраар засна.

        Засварыг ЯГ тэр оруулга дээр л хийнэ: хэрэглэгч энэ хооронд гараараа
        бичсэн бол хөндөхгүй — эс бөгөөс буруу тооны тэмдэгт устана.
        """
        text = self.insertions.last()
        if not text:
            self.ui.set_detail("Засах текст алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Засах текст алга", kind="warning")
            return
        changed = textproc.edit_text(text, kind, str(argument or ""))
        if changed is None or changed == text:
            self.ui.set_detail("Засах зүйл олдсонгүй.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Засах зүйл олдсонгүй", kind="warning")
            return
        self.insertions.take_last()
        self._deliver(changed, len(text))
        # Засварласан текст нь хувилбар сэлгэхтэй зөрчилдөнө — төлвийг хаяна.
        self._variants = None
        label = self.EDIT_LABELS.get(kind, "Заслаа")
        log.info("дуут засвар: %s (%d → %d тэмдэгт)", kind, len(text), len(changed))
        self.ui.set_detail(f"{label}: {changed.strip() or '—'}")
        if self.cfg["wave_overlay"]:
            self.overlay.flash(label)

    def copy_last(self) -> None:
        """Сүүлийн текстийг clipboard руу хуулна (курсорт юу ч оруулахгүй)."""
        text = self.insertions.last()
        if not text:
            self.ui.set_detail("Хуулах зүйл алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Хуулах зүйл алга", kind="warning")
            return
        self.copy_text(text)

    def copy_text(self, text: str) -> None:
        """Дурын текстийг clipboard руу хуулна (түүхийн мөр гэх мэт)."""
        text = (text or "").strip()
        if not text:
            return
        # Clipboard-ыг оруулалттай давхцуулахгүйн тулд ажлын thread дээр —
        # `insert_text` нь тэр л түгжээг барьдаг тул Tk царцаж болзошгүй.
        threading.Thread(
            target=lambda: self._copied(injector.copy_to_clipboard(text), text),
            daemon=True,
        ).start()

    def _copied(self, ok: bool, text: str) -> None:
        if ok:
            log.info("clipboard руу хууллаа: %d тэмдэгт", len(text.strip()))
            self.events.put(("copied", len(text.strip())))
        else:
            log.warning("clipboard руу хуулж чадсангүй")
            self.events.put(("error", "Clipboard завгүй байна — хуулж чадсангүй."))

    # ------------------------------------------------------------------
    # Удирдлага
    # ------------------------------------------------------------------
    def toggle(self) -> None:
        self.stop() if self.listening else self.start()

    def start(self, lang: str | None = None, command: bool = False) -> None:
        if self.listening:
            return
        # Товч дарсан агшны цонх бол текст очих ёстой цонх
        self.target.remember(skip=int(self.root.winfo_id()) if self.root.winfo_exists() else None)
        # Үндсэн товч/асаах горим auto; хоёрдогч товч тодорхой хэл албадана.
        self._active_lang = lang or self._window_lang()
        self._active_auto = lang is None and bool(self.cfg["detect_language"])
        self._active_verbatim = self._window_verbatim()
        self._active_command = command
        if command:
            self.ui.set_detail("Команд горим — үйлдлээ хэлнэ үү.")
        self._active_clean = self._window_clean()
        self.recorder.max_seconds = float(self.cfg["max_recording_seconds"])
        self.recorder.segmenter.silence_hold = float(self.cfg["silence_hold"])
        error = self.recorder.start()
        if error:
            self._fail(error)
            return
        self.formatter.reset()
        self._last_prewarm = time.monotonic()
        self.recognizer.prewarm_async()
        self.worker.prewarm_languages(self._active_lang, self._active_auto)
        self.listening = True
        self.tray.set_active(True)
        if self.cfg["wave_overlay"]:
            self.overlay.show()
        self._refresh_status()
        # Сонгосон микрофоны оронд өөр төхөөрөмж нээгдсэнийг чимээгүй өнгөрөөж
        # болохгүй — хүн ямар микрофоноор бичиж байгаагаа мэдэх ёстой
        notice = self._mic_notice()
        if notice:
            self.ui.set_detail(notice)
            if self.cfg["wave_overlay"]:
                self.overlay.flash(notice, kind="warning")
        # Админ эрхтэй цонхонд текст чимээгүйгээр ордоггүй — урьдчилан хэлнэ
        if self.target.blocked():
            warning = "Энэ цонх админ эрхтэй байж магадгүй — текст орохгүй байж болно."
            log.warning("%s (%s)", warning, self.target.title())
            self.ui.set_detail(warning)

    def stop(self) -> None:
        if not self.listening:
            return
        self.listening = False
        self.recorder.stop()
        peak = self.recorder.session_peak
        self._level = 0.0
        self.tray.set_active(False)
        if self._pending:
            self.overlay.set_processing(True)
        elif self.overlay.mode != "message":
            self.overlay.hide()
        self._refresh_status()
        if not self._pending and peak < MIN_THRESHOLD:
            message = "Дуу сонсогдсонгүй — микрофоноо шалгана уу"
            log.info("%s (дээд түвшин %.0f)", message, peak)
            self.ui.set_detail(message)
            if self.cfg["wave_overlay"]:
                self.overlay.flash(message, kind="warning")

    def show_window(self) -> None:
        """Далд эсвэл жижигрүүлсэн байсан ч удирдлагын самбарыг урд нь гаргана."""
        try:
            if self.root.state() == "iconic":
                self.root.state("normal")
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            hwnd = ctypes.windll.user32.GetParent(self.root.winfo_id()) or self.root.winfo_id()
        except (tk.TclError, OSError):  # цонх хаагдаж байх агшин таарч болно
            return
        # Ажлын ширээний дүрсээс ирсэн дохиогоор нээж байгаа бол дуудсан процесс
        # фокус өгөх эрхгүй байж болно (.exe хувилбарт ачаалагч нь өөрийгөө хүү
        # процесс болгон ажиллуулдаг тул эрх нь дамждаггүй). Иймд цонхоо өөрөө
        # урд нь гаргана — текст буулгахад ашигладаг тэр л аргачлал.
        if activate(hwnd):
            return
        # Аппыг эхлүүлсэн процесс (Explorer гэх мэт) гарах зуур Windows фокусыг
        # түр өөртөө барьж мэднэ. Богино хүлээгээд дахин оролдоно — `activate`
        # нь Tk-ийн thread дээр ~0.2 сек блоклодог тул шууд давтаж болохгүй.
        self._schedule_focus_retries(hwnd, FOCUS_RETRY_MS)

    def _schedule_focus_retries(self, hwnd, delays: tuple[int, ...]) -> None:
        if not delays:
            return
        self.root.after(delays[0], lambda: self._retry_focus(hwnd, delays[1:]))

    def _retry_focus(self, hwnd, remaining: tuple[int, ...]) -> None:
        try:
            if not self.root.winfo_viewable():
                return  # хооронд нь хэрэглэгч цонхыг хаачихсан байна
            if ctypes.windll.user32.GetForegroundWindow() == hwnd:
                return
        except (tk.TclError, OSError):
            return
        if not activate(hwnd):
            self._schedule_focus_retries(hwnd, remaining)

    def on_close(self) -> None:
        # Дүрс үнэхээр цагны хажууд байгаа эсэхийг шалгана — зөвхөн тохиргоог
        # харвал tray асаагүй байхад цонхыг нуугаад аппыг "алга болгож" мэднэ.
        if self.cfg["tray_enabled"] and self.tray.running:
            self.ui.hide_settings()  # Тохиргооны тусдаа цонх ч хамт нуугдана
            self.root.withdraw()
        else:
            self.quit()

    def quit(self) -> None:
        log.info("апп хаагдаж байна")
        self.stats.save(force=True)
        self.stop()
        self.recorder.close()
        self.overlay.destroy()
        self.cfg.save()
        self.hotkeys.stop()
        self.show_listener.stop()
        self.worker.stop()
        self.recognizer.close()
        self.tray.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def _key_label(key: str) -> str:
    return {
        "ptt_key": "Дарж барих",
        "ptt_key_alt": "Хоёр дахь хэл",
        "hotkey": "Асаах/унтраах",
        "undo_key": "Буцаах",
        "variant_key": "Хувилбар сэлгэх",
        "command_key": "Команд горим",
    }.get(key, key)


def main() -> int:
    install_crash_handler()
    if already_running():
        # Хоёр дахь хуулбар нээхгүй — ажиллаж байгаа цонхыг нь урд нь гаргана
        if request_show():
            return 0
        # pythonw-оор эхлүүлэхэд консол байхгүй тул нүдэнд харагдахаар мэдэгдэнэ
        print("Monspeech аль хэдийн ажиллаж байна.", file=sys.stderr)
        try:
            ctypes.windll.user32.MessageBoxW(
                None,
                "Monspeech аль хэдийн ажиллаж байна.\n\n"
                "Цагны хажууд байгаа долгион дүрс дээр товшиж цонхыг нээнэ үү.",
                "Monspeech",
                0x40,  # MB_ICONINFORMATION
            )
        except OSError:
            pass
        return 1
    app = MonspeechApp()
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
