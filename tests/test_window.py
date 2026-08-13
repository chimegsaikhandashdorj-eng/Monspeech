"""Удирдлагын цонхны тест — sidebar + 7 хуудасны бүтэц зөв ажиллаж байна уу.

Жинхэнэ Tk цонх үүсгэдэг (харагдахгүй) тул зөвхөн дэлгэцтэй орчинд ажиллана.
Дэлгэцгүй бол чимээгүй алгасна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_window.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import tkinter as tk

from monspeech import config as config_module
from monspeech.config import Config

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def shown(widget):
    """Виджет эцэгтээ багцлагдсан эсэх.

    `winfo_ismapped()` нь withdraw хийсэн цонхны хүүхдүүдэд үргэлж худал
    буцаадаг тул тестэд тохирохгүй — багцлагчаас нь асууна.
    """
    return bool(widget.winfo_manager())


class Stats:
    data = {"words": 0, "seconds_spoken": 0.0}
    today_words = 0
    average_ms = 0.0


class Transcripts:
    def __init__(self):
        self.entries = [
            {"text": "хурлын тэмдэглэл", "at": "2026-08-11T14:52:00"},
            {"text": "invoice before Friday", "at": "2026-08-11T14:31:00"},
        ]

    def search(self, query):
        query = (query or "").strip().lower()
        return [e for e in self.entries if query in e["text"].lower()]

    def clear(self):
        self.entries = []


class FakeApp:
    """ControlWindow-д хэрэгтэй хамгийн бага гадаргуу."""

    def __init__(self):
        config_module.CONFIG_PATH = Path(tempfile.mkdtemp()) / "config.json"
        self.cfg = Config.load()
        self.cfg["replacements"] = {"клауд": "Claude"}
        self.cfg["snippets"] = {"миний хаяг": "УБ"}
        self.stats = Stats()
        self.transcripts = Transcripts()
        self.saved_replacements = None
        self.saved_snippets = None
        self.tuning = {}

    @staticmethod
    def list_microphones():
        return ["Системийн үндсэн", "Микрофон (Realtek)"], [-1, 3]

    def toggle(self):
        pass

    def open_log(self):
        pass

    def remember_type_mode_app(self):
        return "«Notepad» цонхонд одооноос шууд бичнэ."

    def on_lang_changed(self, code):
        self.cfg["lang"] = code

    def on_alt_lang_changed(self, code):
        self.cfg["lang_alt"] = code

    def on_mic_changed(self, index):
        self.cfg["mic_index"] = index

    def on_option_changed(self, key, value):
        self.cfg[key] = bool(value)

    def on_tuning_changed(self, key, value):
        self.tuning[key] = value

    def on_replacements_changed(self, raw):
        self.saved_replacements = raw
        return raw.count("=")

    def on_snippets_changed(self, raw):
        self.saved_snippets = raw
        return raw.count("=")

    def open_releases(self):
        self.opened_releases = True

    def copy_diagnostics(self):
        return "Мэдээллийг хууллаа"

    def finish_onboarding(self):
        self.cfg["onboarded"] = True

    def on_stt_changed(self, values):
        self.cfg.update(values)
        return f"Танигч: {values['stt_provider']}"


try:
    root = tk.Tk()
except tk.TclError as exc:  # дэлгэцгүй орчин
    print(f"алгаслаа (Tk нээгдсэнгүй: {exc})")
    raise SystemExit(0)

root.withdraw()  # тестийн явцад дэлгэц дээр гарахгүй

from monspeech.window import NAV, ControlWindow  # noqa: E402 - Tk шалгасны дараа

app = FakeApp()
ui = ControlWindow(root, app)
root.update()

# --- Бүтэц: 7 цэс, 7 хуудас ---
check("цэсний тоо", len(ui.nav), 7)
check("хуудасны тоо", len(ui.pages), 7)
check("эхний хуудас идэвхтэй", ui.page_index, 0)
check("зөвхөн нэг хуудас харагдана", sum(shown(p) for p in ui.pages), 1)

# --- Цэс сонгох ---
ui.select(3)
root.update()
check("сонгосон хуудас", ui.pages[3].title, "Товчлуур")
check("сонгосон хуудас харагдав", shown(ui.pages[3]), True)
check("өмнөх хуудас нуугдав", shown(ui.pages[0]), False)

# --- Ctrl+1..7 ---
root.event_generate("<Control-Key-5>")
root.update()
check("Ctrl+5 → Толь", ui.pages[ui.page_index].title, "Толь")

# --- Хайлт нь навигацийн туслах ---
ui.search_var.set("микрофон")
root.update()
check("хайлтын самбар гарсан", shown(ui.results), True)
found = [w for w in ui.results.inner.winfo_children()]
check("илэрц олдсон", len(found) > 0, True)
ui._go_from_search(1)
root.update()
check("илэрц дээр дарахад цэс солигдов", ui.pages[ui.page_index].title, "Яриа")
check("хайлт цэвэрлэгдэв", ui.search_var.get(), "")
check("хайлтын самбар хаагдав", shown(ui.results), False)

ui.search_var.set("ийм тохиргоо байхгүй")
root.update()
check("илэрцгүй мэдэгдэл", len(ui.results.inner.winfo_children()), 1)
ui.search_var.set("")
root.update()

# --- Чагтууд бүгд бүртгэгдсэн ---
check("чагтын тоо", len(ui.toggles), 12)
check("шинэчлэл шалгах чагт", "check_updates" in ui.toggles, True)
check("Windows-тай хамт эхлүүлэх чагт", "start_with_windows" in ui.toggles, True)
check("долгион чагт", "wave_overlay" in ui.toggles, True)
check("чигчлүүр цэвэрлэх чагт", "clean_speech" in ui.toggles, True)

# --- Гулсуурууд (өмнө нь combobox байсан) ---
check("гулсуурын тоо", len(ui.sliders), 4)
check("дээд хугацааны гулсуур", "max_recording_seconds" in ui.sliders, True)
ui.sliders["silence_hold"].set(0.9)
ui.sliders["silence_hold"]._settled()
check("гулсуур тохиргоог дамжуулсан", round(app.tuning["silence_hold"], 2), 0.9)
check("гулсуурын заалт", ui.sliders["silence_hold"].readout.cget("text"), "0.9 сек")
ui.sliders["min_confidence"].set(-5)
check("хүрээнээс гаралгүй хумигдсан", ui.sliders["min_confidence"].value, 0.0)

# --- Товчлуур ---
check("товчлуурын мөрүүд", sorted(ui.keycaps), ["hotkey", "ptt_key", "ptt_key_alt", "undo_key"])

# --- Толь: мөр мөрөөр засварлах ---
ui.select(4)
root.update()
check("толийн мөр ачаалагдсан", len(ui.pairs._rows), 1)
check("толийн утга", ui.pairs.mapping(), {"клауд": "Claude"})
ui.pairs.add_row("монспич", "Monspeech")
root.update()
check("мөр нэмэгдсэн", ui.pairs.mapping()["монспич"], "Monspeech")
ui._save_dictionary(ui.pairs.mapping())
check("толь хадгалагдсан", "монспич=Monspeech" in (app.saved_replacements or ""), True)

# --- Хоёр дахь хэл цонхноос сонгогдоно ---
check("одоогийн хоёр дахь хэл", ui.alt_lang_var.get(), "English (US)")
ui.alt_lang_var.set("Русский")
ui.app.on_alt_lang_changed("ru-RU")
check("тохиргоонд хадгалагдсан", app.cfg["lang_alt"], "ru-RU")

# --- Хэл хурдан солих (Төлөв хуудас) ---
ui.select(0)
root.update()
ui._quick_lang("en-US")
check("хэл солигдсон", app.cfg["lang"], "en-US")
check("сонголт combobox-т тусав", ui.lang_var.get(), "English (US)")

# --- Түүх нь тусдаа цонх биш, хуудас болов ---
ui.show_history()
root.update()
check("түүхийн хуудас", ui.pages[ui.page_index].title, "Түүх")
check("түүхийн мөрүүд", ui.history_box.size(), 2)
ui.history_query.set("invoice")
root.update()
check("түүхийн хайлт", ui.history_box.size(), 1)
ui.history_query.set("")
root.update()

# --- Төлөв: робот ба тоон самбар ---
ui.select(0)
root.update()
ui.set_state("listening", "Сонсож байна", "Тавихад орно")
check("роботын төлөв", ui.orb.mode, "listening")
check("sidebar-ын төлөв", ui.state_var.get(), "Сонсож байна")
check("товчны бичиг", ui.action_button.cget("text"), "Зогсоох")
ui.set_state("ready", "Бэлэн", "")
check("бэлэн болоход робот амарна", ui.orb.mode, "idle")
check("тайлбар анхны утгадаа буцсан", ui.hint_var.get(), ui.default_hint)

ui.set_detail("Микрофон солигдлоо.")
check("доод мөрөнд мэдэгдэл", ui.detail_var.get(), "Микрофон солигдлоо.")

ui._remember_type_mode_app()
check("шууд бичих холбоос", ui.detail_var.get(), "«Notepad» цонхонд одооноос шууд бичнэ.")

# --- Бичилтийн урьдчилан харах ---
ui.select(2)
root.update()
check("урьдчилан харах эхэлдэг", ui.preview_var.get().startswith("␣Өнөөдрийн"), True)
ui.toggles["auto_capitalize"]._clicked()
root.update()
check("том үсэг унтраахад тусав", ui.preview_var.get().startswith("␣өнөөдрийн"), True)

# --- Анх ажиллуулахад танилцуулга гарна, дараа нь дахин гарахгүй ---
check("танилцуулга гарсан", shown(ui.welcome), True)
ui._finish_welcome()
root.update()
check("товшсоны дараа алга болсон", ui.welcome, None)
check("дахин гарахгүй гэж тэмдэглэсэн", app.cfg["onboarded"], True)

# --- Шинэ хувилбар олдвол мэдэгдэнэ ---
check("эхэндээ товч нуугдсан", shown(ui.update_button), False)
ui.show_update("v9.9.9")
root.update()
check("хувилбарын мөр солигдсон", "v9.9.9" in ui.version_var.get(), True)
check("шинэчлэх товч гарсан", shown(ui.update_button), True)

# --- Танигч: нэмэлт талбарууд зөвхөн өөрийн үйлчилгээнд гарна ---
check("анхандаа талбарууд нуугдсан", shown(ui.stt_extra), False)
check("гурван талбар бэлдсэн", sorted(ui.stt_vars), ["stt_key", "stt_model", "stt_url"])
ui.stt_var.set("Өөрийн үйлчилгээ (OpenAI-нийцтэй)")
ui._stt_selected()
root.update()
check("сонгоход талбарууд гарсан", shown(ui.stt_extra), True)
check("тохиргоо хадгалагдсан", app.cfg["stt_provider"], "openai")
ui.stt_vars["stt_url"].set("https://example.test/v1/audio/transcriptions")
ui._stt_changed()
check("хаяг хадгалагдсан", app.cfg["stt_url"], "https://example.test/v1/audio/transcriptions")
ui.stt_var.set("Google (үнэгүй, түлхүүргүй)")
ui._stt_selected()
root.update()
check("буцаад нуугдсан", shown(ui.stt_extra), False)
check("буцаад google болсон", app.cfg["stt_provider"], "google")

# --- Sidebar хумих ---
ui.toggle_sidebar()
root.update()
check("хумигдсан өргөн", ui.sidebar.cget("width"), 58)
check("шошго нуугдсан", shown(ui.nav[0].label), False)
ui.toggle_sidebar()
root.update()
check("буцаж нээгдсэн", ui.sidebar.cget("width"), 208)
check("шошго эргэж ирсэн", shown(ui.nav[0].label), True)

# --- Цэсний нэрс дизайны дагуу ---
check(
    "цэсний нэрс",
    [name for _, name in NAV],
    ["Төлөв", "Яриа", "Бичилт", "Товчлуур", "Толь", "Түүх", "Нэмэлт"],
)

root.destroy()

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
