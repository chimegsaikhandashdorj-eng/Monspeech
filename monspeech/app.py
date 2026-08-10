"""Monspeech — ярианы текстийг курсор байгаа газарт шивэх desktop апп.

Микрофоныг шууд уншиж, Google Web Speech рүү илгээнэ (хөтөч оролцохгүй).
Товчийг дарж байх үед сонсоод, суллахад текст тэр дор нь орно.

Үүрэг хуваарилалт: цонх нь `window.py`, таних дамжлага нь `pipeline.py`,
ганц хуулбар барих нь `instance.py`. Энэ модуль тэдгээрийг холбож,
хэрэглэгчийн үйлдэлд хариу үзүүлнэ.
"""

from __future__ import annotations

import ctypes
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk

from .audio import MIN_THRESHOLD, Recorder
from .config import Config
from .history import InsertionHistory
from .hotkeys import HotkeyManager, parse_combo, pretty
from .instance import ShowListener, already_running, request_show
from .logging_setup import LOG_PATH, get as get_logger
from .overlay import WaveOverlay
from .pipeline import RecognitionWorker
from .recognizer import Recognizer
from .store import TranscriptStore, UsageStats
from .textproc import Formatter, learn_corrections, parse_replacements
from .tray import Tray
from .window import CODE_TO_NAME, ControlWindow
from .winfocus import TargetWindow

log = get_logger("app")

KEEPALIVE_SECONDS = 20  # урт яриан дунд холболт хуучрахаас сэргийлнэ
QUEUE_WARN = 2
QUEUE_LIMIT = 10
HOTKEY_KEYS = ("ptt_key", "ptt_key_alt", "hotkey", "undo_key")


class MonspeechApp:
    def __init__(self) -> None:
        self.cfg = Config.load()
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.segments: queue.Queue = queue.Queue()
        self.listening = False
        self.insertions = InsertionHistory()
        self._level = 0.0
        self._pending = 0
        self._active_lang = self.cfg["lang"]
        self._last_prewarm = 0.0

        self.transcripts = TranscriptStore()
        self.stats = UsageStats()
        self.formatter = Formatter(
            auto_space=self.cfg["auto_space"],
            auto_capitalize=self.cfg["auto_capitalize"],
            voice_punctuation=self.cfg["voice_punctuation"],
            replacements=self.cfg["replacements"],
            snippets=self.cfg["snippets"],
        )
        self.recognizer = Recognizer(lang=self.cfg["lang"])
        self.target = TargetWindow()
        self.recorder = Recorder(
            on_segment=self._on_segment,
            on_level=self._on_level,
            on_error=self._on_audio_error,
            device_index=self._device_index(),
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
        # Аппыг гараар нээсэн бол хүн удирдлагын самбарыг харахыг хүсэж байна
        self.root.after(0, self.show_window)
        self.recognizer.prewarm_async()
        log.info("апп эхэллээ (хэл=%s)", self.cfg["lang"])

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
    def _device_index(self):
        index = int(self.cfg["mic_index"])
        return None if index < 0 else index

    @staticmethod
    def list_microphones() -> tuple[list[str], list[int]]:
        names = ["Системийн үндсэн"]
        indexes = [-1]
        try:
            import pyaudio

            pa = pyaudio.PyAudio()
            try:
                for i in range(pa.get_device_count()):
                    info = pa.get_device_info_by_index(i)
                    if int(info.get("maxInputChannels", 0)) > 0:
                        names.append(str(info.get("name", f"#{i}"))[:38])
                        indexes.append(i)
            finally:
                pa.terminate()
        except Exception:  # noqa: BLE001 - жагсаалт гаргаж чадахгүй ч апп ажиллана
            pass
        return names, indexes

    # ------------------------------------------------------------------
    # Дуу таних дамжлага
    # ------------------------------------------------------------------
    def _on_segment(self, pcm: bytes, final: bool) -> None:
        self.segments.put((pcm, self._active_lang))
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
        handlers = self._event_handlers
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "quit":
                    self.quit()
                    return
                handler = handlers.get(kind)
                if handler is None:
                    log.warning("танихгүй эвент: %s", kind)
                    continue
                handler(payload)
        except queue.Empty:
            pass
        self.ui.set_level(self._level, self.listening)
        self._keepalive()
        self.stats.save()
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
        message = (
            "Итгэлтэй таньж чадсангүй — дахин хэлнэ үү"
            if reason == "low_confidence"
            else "Таньж чадсангүй — дахин хэлнэ үү"
        )
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

    def on_mic_changed(self, index: int) -> None:
        self.cfg["mic_index"] = index
        self.recorder.device_index = None if index < 0 else index
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
        self.cfg.save()

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
        self.cfg.save()

    def _insert_mode(self) -> str:
        """Энэ цонхонд clipboard ажилладаггүй бол шууд бичих горимд шилжинэ."""
        if self.cfg["type_mode"]:
            return "type"
        title = (self.target.title() or "").lower()
        for marker in self.cfg["type_mode_apps"]:
            if marker and marker.lower() in title:
                return "type"
        return "paste"

    def remember_type_mode_app(self) -> str:
        """Одоогийн цонхыг "шууд бичих" жагсаалтад нэмнэ."""
        title = self.target.title()
        if not title:
            return "Цонх тодорхойгүй байна."
        marker = title.split(" - ")[-1].strip()[:40] or title[:40]
        apps = list(self.cfg["type_mode_apps"])
        if marker.lower() in [a.lower() for a in apps]:
            return f"«{marker}» аль хэдийн жагсаалтад байна."
        apps.append(marker)
        self.cfg["type_mode_apps"] = apps
        self.cfg.save()
        return f"«{marker}» цонхонд одооноос шууд бичнэ."

    def on_snippets_changed(self, raw: str) -> int:
        mapping = parse_replacements(raw)
        self.cfg["snippets"] = mapping
        self.formatter.set_snippets(mapping)
        self.cfg.save()
        self.ui.set_detail(f"{len(mapping)} товчлол хадгалагдлаа.")
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
        self._active_lang = lang or self.cfg["lang"]
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
        except tk.TclError:  # цонх хаагдаж байх агшин таарч болно
            pass

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
