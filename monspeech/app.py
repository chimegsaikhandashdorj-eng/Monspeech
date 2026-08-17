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

from . import __version__, autostart, mics, recognizer, update, winfocus
from .audio import MIN_THRESHOLD, Recorder
from .config import Config
from .history import InsertionHistory
from .hotkeys import HotkeyManager, parse_combo, pretty
from .instance import ShowListener, already_running, request_show
from .mics import Mic
from .logging_setup import LOG_PATH, get as get_logger, install_crash_handler
from .overlay import WaveOverlay
from .pipeline import RecognitionWorker
from .store import TranscriptStore, UsageStats
from .textproc import Formatter, learn_corrections, parse_replacements
from .tray import Tray
from .window import CODE_TO_NAME, ControlWindow, unknown_language_codes
from .winfocus import TargetWindow, activate

log = get_logger("app")

KEEPALIVE_SECONDS = 20  # урт яриан дунд холболт хуучрахаас сэргийлнэ
QUEUE_WARN = 2
QUEUE_LIMIT = 10
HOTKEY_KEYS = ("ptt_key", "ptt_key_alt", "hotkey", "undo_key")
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
        self._active_lang = self.cfg["lang"]
        self._active_clean = bool(self.cfg["clean_speech"])
        self._last_prewarm = 0.0

        self.transcripts = TranscriptStore()
        self.stats = UsageStats()
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
        )

        self.root = tk.Tk()
        self.root.title("Monspeech")
        self.root.attributes("-topmost", True)
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
        )
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
        self.segments.put((pcm, self._active_lang, self._active_clean))
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
            "undo": lambda _: self.undo_last(),
            "toggle": lambda _: self.toggle(),
            "ptt": self._on_ptt,
            "captured": lambda payload: self.ui.finish_capture(*payload),
            "show": lambda _: self.show_window(),
        }

    def _on_recognized(self, payload) -> None:
        text, _entry = payload
        self.ui.set_detail(text)
        self.ui.refresh_history()
        self.ui.refresh_stats()
        if self.cfg["wave_overlay"] and not self.listening:
            self.overlay.flash(text)

    def _on_pending(self, delta) -> None:
        self._pending = max(0, self._pending + int(delta))
        self._after_pending_change()

    def _on_audio_failure(self, message) -> None:
        self.stop()
        self._fail(str(message))

    def _on_ptt(self, payload) -> None:
        lang, pressed = payload
        self.start(lang) if pressed else self.stop()

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
        if not self.listening and not self._pending:
            if self.overlay.mode != "message":
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
        self.worker.recognizer = self.recognizer
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
        if key == "ptt_enabled":
            self._bind_hotkeys()
        elif key == "tray_enabled":
            self._apply_tray_setting()
        elif key == "wave_overlay" and not value:
            self.overlay.hide()
        elif key == "start_with_windows":
            self._apply_autostart_setting(bool(value))
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
        if not self.cfg["clean_speech"]:
            return False
        return self._match_window(self.cfg["no_clean_apps"]) is None

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

    def on_names_changed(self, raw: str) -> int:
        mapping = parse_replacements(raw)
        self.cfg["names"] = mapping
        self.formatter.set_names(mapping)
        self.cfg.save()
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
        self.transcripts.replace(entry, corrected)
        if not self.cfg["learn_corrections"]:
            return "Түүх зассан."
        learned = learn_corrections(heard, corrected)
        if not learned:
            return "Түүх зассан (сурах үг олдсонгүй)."
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
        self.ui.refresh_words()
        pairs = ", ".join(f"{k} → {v}" for k, v in learned.items())
        log.info("толинд нэмэгдлээ: %s", pairs)
        return f"Сурлаа: {pairs}"

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
            if self.cfg["ptt_enabled"]:
                self.hotkeys.bind(
                    "ptt",
                    self.cfg["ptt_key"],
                    on_press=lambda: self.events.put(("ptt", (self.cfg["lang"], True))),
                    on_release=lambda: self.events.put(("ptt", (self.cfg["lang"], False))),
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

    def undo_last(self) -> None:
        item = self.insertions.take_last()
        if not item:
            self.ui.set_detail("Буцаах зүйл алга.")
            if self.cfg["wave_overlay"]:
                self.overlay.flash("Буцаах зүйл алга", kind="warning")
            return
        text, count = item
        log.info("буцаалаа: %d тэмдэгт", count)
        self._deliver("", count, remember=False)
        self.ui.set_detail(f"Буцаалаа ({count} тэмдэгт).")
        if self.cfg["wave_overlay"]:
            self.overlay.flash("Буцаалаа", kind="warning")

    # ------------------------------------------------------------------
    # Удирдлага
    # ------------------------------------------------------------------
    def toggle(self) -> None:
        self.stop() if self.listening else self.start()

    def start(self, lang: str | None = None) -> None:
        if self.listening:
            return
        # Товч дарсан агшны цонх бол текст очих ёстой цонх
        self.target.remember(skip=int(self.root.winfo_id()) if self.root.winfo_exists() else None)
        # Хоёрдогч товчлуураар шууд заасан хэл нь аппын профайлаас дээгүүр —
        # хэрэглэгч зориуд дарсан бол түүнийг нь дийлэхгүй.
        self._active_lang = lang or self._window_lang()
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
