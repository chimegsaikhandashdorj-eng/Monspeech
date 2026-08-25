"""Удирдлагын цонхны тест — sidebar + 7 хуудасны бүтэц зөв ажиллаж байна уу.

Жинхэнэ Tk цонх үүсгэдэг (дэлгэцээс гадуур, тунгалаг) тул зөвхөн дэлгэцтэй
орчинд ажиллана. Дэлгэцгүй бол чимээгүй алгасна.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_window.py
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


import datetime
import tkinter as tk

from monspeech import animate, config as config_module, mics, theme
from monspeech.config import Config
from monspeech.samples import HardSampleStore

# Хөдөлгөөнийг унтраана. Энэ тест нь өнгө, бүтэц зөв эсэхийг шалгадаг ба
# шилжилт нь ЭХЭЛСЭН агшинд утга нь хуучин байдаг — тэр нь хөдөлгөөний зөв
# зан төлөв, гэхдээ энд шалгаж буй зүйл биш. Хөдөлгөөнөө өөрийг нь
# `test_animate.py` тусад нь шалгана.
animate.enabled = False

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(f"{'ok  ' if ok else 'FAIL'} {label} -> {got!r}")


def shown(widget):
    """Виджет эцэгтээ багцлагдсан эсэх.

    `winfo_ismapped()`-ийг ашиглахгүй: тэр нь зурагдсан эсэхийг хэлдэг тул
    `update()` хэзээ дуудагдсанаас хамаарч хэлбэлзэнэ. Багцлагчаас асуувал
    зорилго нь тодорхой — «энэ виджетийг харуулахаар тавьсан уу».
    """
    return bool(widget.winfo_manager())


class Stats:
    data = {"words": 0, "seconds_spoken": 0.0}
    today_words = 0
    average_ms = 0.0

    def __init__(self):
        self.usages = {
            "openai": {"seconds": 900.0, "requests": 12, "today": 300.0, "month": 900.0},
            "google": {"seconds": 60.0, "requests": 3, "today": 60.0, "month": 60.0},
        }

    def usage(self, provider):
        return self.usages.get(
            provider, {"seconds": 0.0, "requests": 0, "today": 0.0, "month": 0.0}
        )


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
        self.samples = HardSampleStore(directory=Path(tempfile.mkdtemp()))
        self.saved_replacements = None
        self.saved_snippets = None
        self.tuning = {}
        self.marker = "Notepad"
        self.repasted = None
        self.copied = None

    @staticmethod
    def microphones():
        return [mics.SYSTEM, mics.Mic(3, "Микрофон (Realtek)")]

    def toggle(self):
        pass

    def repaste(self, text):
        self.repasted = text

    def copy_text(self, text):
        self.copied = text

    def open_log(self):
        pass

    def remember_type_mode_app(self):
        return "«Notepad» цонхонд одооноос шууд бичнэ."

    def remember_no_clean_app(self):
        return "«Obsidian» цонхонд одооноос үгчлэн бичнэ."

    def on_lang_changed(self, code):
        self.cfg["lang"] = code

    def on_alt_lang_changed(self, code):
        self.cfg["lang_alt"] = code

    def on_mic_changed(self, mic):
        mic.save_to(self.cfg)

    def on_theme_changed(self, code):
        self.cfg["theme"] = code

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

    def on_names_changed(self, raw):
        self.saved_names = raw
        return raw.count("=")

    def on_lang_apps_changed(self, raw):
        from monspeech.textproc import parse_replacements

        self.cfg["lang_apps"] = parse_replacements(raw)
        return len(self.cfg["lang_apps"])

    def on_actions_changed(self, raw):
        from monspeech.textproc import parse_actions

        self.cfg["actions"] = parse_actions(raw)
        return len(self.cfg["actions"])

    def on_transcript_language_changed(self, entry, language):
        entry["lang"] = language
        entry["language_corrected"] = True
        return f"Хэл батлагдлаа: {language}."

    # --- Цонхны дүрэм: жинхэнэ `MonspeechApp`-ийн методуудыг зээлнэ.
    # Импортыг дуудлагын үед хийнэ — Tk байхгүй орчинд энэ файл эхэндээ
    # `monspeech.app`-ыг татах ёсгүй (тэр нь цонх, tray-г дагуулж ирнэ).
    def _rules_api(self, name, *args):
        from monspeech.app import MonspeechApp

        self.RULE_LISTS = MonspeechApp.RULE_LISTS
        return getattr(MonspeechApp, name)(self, *args)

    def current_window_marker(self):
        return self.marker

    def window_rules(self):
        return self._rules_api("window_rules")

    def window_rule(self, marker):
        return self._rules_api("window_rule", marker)

    def set_window_rule(self, marker, kind, value):
        return self._rules_api("set_window_rule", marker, kind, value)

    def remove_window_rule(self, marker):
        return self._rules_api("remove_window_rule", marker)

    def open_releases(self):
        self.opened_releases = True

    def copy_diagnostics(self):
        return "Мэдээллийг хууллаа"

    def clear_samples(self):
        self.samples.clear()
        return "Жишээнүүдийг устгалаа."

    def finish_onboarding(self):
        self.cfg["onboarded"] = True

    def on_stt_changed(self, values):
        self.cfg.update(values)
        return f"Танигч: {values['stt_provider']}"


try:
    root = tk.Tk()
except tk.TclError as exc:  # дэлгэцгүй орчин
    print(f"алгаслаа (Tk нээгдсэнгүй: {exc})")
    raise SystemExit(0) from None

# Дэлгэцээс гадуур байрлуулна — `withdraw()` биш. Шалтгаан: withdraw хийсэн
# цонхны хүүхдүүд map хийгддэггүй тул `event_generate` тэдэнд хүрэхгүй, товчлуурын
# шалгалт санамсаргүй унана. Гадуур байрлуулбал эвент бодитоор дамжина.
root.geometry("1000x700+-3000+-3000")
try:
    root.attributes("-alpha", 0.0)  # map хийгдсэн ч бүрэн үл үзэгдэх
except tk.TclError:
    pass  # энэ платформ дэмжихгүй бол дэлгэцээс гадуур байрлал хангалттай

from monspeech.window import (  # noqa: E402 - Tk шалгасны дараа
    NAV,
    SETTINGS_NAV,
    ControlWindow,
    unknown_language_codes,
)

app = FakeApp()
ui = ControlWindow(root, app)
root.update()

# --- Бүтэц: 6 үндсэн цэс, 6 хуудас; Тохиргоо тусдаа цонх ---
check("цэсний тоо", len(ui.nav), 6)
check("хуудасны тоо", len(ui.pages), 6)
check("тохиргооны хуудасны тоо", len(ui.settings.pages), 4)
check("эхний хуудас идэвхтэй", ui.page_index, 0)
check("зөвхөн нэг хуудас харагдана", sum(shown(p) for p in ui.pages), 1)
check("тохиргооны цонх эхэндээ нуугдсан", str(ui.settings.win.state()), "withdrawn")
check("лого sidebar-ын толгойд", shown(ui.logo), True)
check("хайлтын талбар хассан", not hasattr(ui, "search"), True)

# --- Цэс сонгох ---
ui.select(1)
root.update()
check("сонгосон хуудас", ui.pages[1].title, "Толь")
check("сонгосон хуудас харагдав", shown(ui.pages[1]), True)
check("өмнөх хуудас нуугдав", shown(ui.pages[0]), False)

# --- Тохиргооны цонх нээх/хаах ---
ui.open_settings(2)
root.update()
check("тохиргооны цонх нээгдэв", str(ui.settings.win.state()), "normal")
check("тохиргооны хэсэг сонгогдов", ui.settings.pages[ui.settings.page_index].title, "Товчлуур")
check("тохиргоонд зөвхөн нэг хэсэг харагдана", sum(shown(p) for p in ui.settings.pages), 1)
ui.settings.select(1)
check("хэсэг сэлгэв", ui.settings.pages[ui.settings.page_index].title, "Бичилт")
ui.settings.hide()
check("тохиргооны цонх хаагдав", str(ui.settings.win.state()), "withdrawn")

# --- Хүрээгүй popover: гадна товшиход хаагдана ---
check("системийн гарчиггүй", int(ui.settings.win.overrideredirect()), 1)
# Товч дээрх ЖИНХЭНЭ товшилтын дарааллыг event_generate-аар дуурайна:
# виджетийн холбоос (нээх) → bind_all (хаагч) ийм дарааллаар ажилладаг.
ui.settings_button.event_generate("<Button-1>")
root.update()
check("нээгдэв", str(ui.settings.win.state()), "normal")
check("өнцөг бөөрөнхийлсөн", ui.settings._region_size != (0, 0), True)
sidebar_labels = [
    w.cget("text") for w in ui.settings.sidebar.winfo_children()
    if isinstance(w, tk.Label)
]
check("хувилбарын бичиг хассан", all("Monspeech" not in t for t in sidebar_labels), True)
check("хэсгийн гарчиг үлдсэн", "ТОХИРГОО" in sidebar_labels, True)
# Үндсэн цонхны виджет дээрх товшилт — bind_all-аар дамжин нуугдана
ui.orb.event_generate("<Button-1>")
root.update()
check("гадна товшиход шууд хаагдав", str(ui.settings.win.state()), "withdrawn")
# Доторх товшилт цонхыг хаахгүй
ui.settings_button.event_generate("<Button-1>")
root.update()
ui.settings.nav[0].event_generate("<Button-1>")
root.update()
check("дотор товшиход үлдэнэ", str(ui.settings.win.state()), "normal")
# Тохиргоо товч дахин дарахад хаагдана (toggle)
ui.settings_button.event_generate("<Button-1>")
root.update()
check("товчоор нь хаагдав (toggle)", str(ui.settings.win.state()), "withdrawn")

# --- Ctrl+1..6 ---
# Синтетик товчлуурын эвент ашиглахгүй: тэр нь OS-ийн фокустай виджет рүү
# очдог тул дэлгэцээс гадуурх тунгалаг цонхонд найдваргүй (хэмжсэн: багц
# дотор 8 удаагийн 2-т унасан). Холбоос холбогдсон эсэх, тэр нь зөв хуудас
# сонгодог эсэх хоёр л бидний хяналтад.
for number in range(1, len(NAV) + 1):
    if not root.bind(f"<Control-Key-{number}>"):
        fails.append(f"Ctrl+{number} холбогдоогүй")
check("Ctrl+1..6 бүгд холбогдсон", len(fails), 0)
ui.select(1)
root.update()
check("Ctrl+2-ын байрлал → Толь", ui.pages[ui.page_index].title, "Толь")

# --- Чагтууд бүгд бүртгэгдсэн ---
check("чагтын тоо", len(ui.toggles), 23)
check("толийн дохионы чагт", "vocabulary_boost" in ui.toggles, True)
check("хоёр дарахын чагт", "double_tap_enabled" in ui.toggles, True)
check("чимээ дарах чагт", "noise_suppression" in ui.toggles, True)
check("ярианы илрүүлэгчийн чагт", "vad" in ui.toggles, True)
check("хэцүү жишээний чагт", "save_hard_audio" in ui.toggles, True)
check("унтраалттай үед тэмдэглэнэ", ui.samples_var.get(), "Унтраалттай")
check("автомат цэгийн чагт", "auto_period" in ui.toggles, True)
check("хэл сэжиглэх чагт", "detect_language" in ui.toggles, True)
check("нарийвчлалын чагт", "language_accuracy_mode" in ui.toggles, True)
check("үгчлэн чагт", "verbatim_mode" in ui.toggles, True)
check("шинэчлэл шалгах чагт", "check_updates" in ui.toggles, True)
check("Windows-тай хамт эхлүүлэх чагт", "start_with_windows" in ui.toggles, True)
check("долгион чагт", "wave_overlay" in ui.toggles, True)
check("чигчлүүр цэвэрлэх чагт", "clean_speech" in ui.toggles, True)

# --- Гулсуурууд (өмнө нь combobox байсан) ---
check("гулсуурын тоо", len(ui.sliders), 6)
check("дээд хугацааны гулсуур", "max_recording_seconds" in ui.sliders, True)
check("урьдчилсан буферийн гулсуур", "preroll_seconds" in ui.sliders, True)
ui.sliders["silence_hold"].set(0.9)
ui.sliders["silence_hold"]._settled()
check("гулсуур тохиргоог дамжуулсан", round(app.tuning["silence_hold"], 2), 0.9)
check("гулсуурын заалт", ui.sliders["silence_hold"].readout.cget("text"), "0.9 сек")
ui.sliders["min_confidence"].set(-5)
check("хүрээнээс гаралгүй хумигдсан", ui.sliders["min_confidence"].value, 0.0)

# --- Товчлуур ---
check(
    "товчлуурын мөрүүд",
    sorted(ui.keycaps),
    ["command_key", "hotkey", "ptt_key", "ptt_key_alt", "undo_key", "variant_key"],
)

# --- Толь: мөр мөрөөр засварлах ---
ui.select(1)
root.update()
check("толийн мөр ачаалагдсан", len(ui.pairs._rows), 1)
check("толийн утга", ui.pairs.mapping(), {"клауд": "Claude"})
ui.pairs.add_row("монспич", "Monspeech")
root.update()
check("мөр нэмэгдсэн", ui.pairs.mapping()["монспич"], "Monspeech")
ui._save_dictionary(ui.pairs.mapping())
check("толь хадгалагдсан", "монспич=Monspeech" in (app.saved_replacements or ""), True)

# --- Нэрсийн таб ---
ui._dictionary_tab(1)
root.update()
check(
    "нэрсийн баганын шошго",
    (ui.pairs.head_a.cget("text"), ui.pairs.head_b.cget("text")),
    ("НЭР", "СОНСОГДДОГ ХУВИЛБАР (ЗААВАЛ БИШ)"),
)
ui.pairs.add_row("Чимэгсайхан", "чимээ сайхан")
root.update()
ui._save_dictionary(ui.pairs.mapping())
check("нэр хадгалагдсан", "Чимэгсайхан=чимээ сайхан" in (app.saved_names or ""), True)

# --- Толины сүүлийн таб: аппаар ялгах хэл ---
ui._dictionary_tab(3)
root.update()
check("аппын хэлний таб хоосон", ui.pairs.mapping(), {})
check(
    "баганын шошго солигдов",
    tuple(ui.pairs._labels),
    ("Цонхны нэрний хэсэг", "Хэлний код"),
)
ui.pairs.add_row("Visual Studio Code", "en-US")
root.update()
ui._save_dictionary(ui.pairs.mapping())
check("аппын хэл хадгалагдсан", app.cfg["lang_apps"], {"Visual Studio Code": "en-US"})

# Танихгүй хэлний кодыг чимээгүй хүлээж авахгүй
check(
    "танихгүй код илэрнэ",
    unknown_language_codes({"Notepad": "xx-YY", "Code": "en-US"}),
    ["xx-YY"],
)
check("бүгд танигдвал хоосон", unknown_language_codes({"Code": "en-US"}), [])

# --- Дуут үйлдлийн таб ---
ui._dictionary_tab(4)
root.update()
check(
    "үйлдлийн баганын шошго",
    tuple(ui.pairs._labels),
    ("Хэлэх үг", "Юу хийх"),
)
ui.pairs.add_row("цуцал", "буцаах")
ui.pairs.add_row("нэрээ хэл", "жиншгүй үйлдэл")
root.update()
ui._save_dictionary(ui.pairs.mapping())
check("үйлдэл хадгалагдсан", app.cfg["actions"], {"цуцал": "undo"})

# Дискэн дээрх дотоод нэрийг цонхонд монголоор нь харуулна
ui._dictionary_tab(4)
root.update()
check("шошготой харагдана", ui.pairs.mapping(), {"цуцал": "буцаах"})

ui._dictionary_tab(0)
root.update()

# --- Хэрэглээ ба зардал ---
app.cfg["stt_provider"] = "openai"
app.cfg["stt_cost_per_minute"] = 0.006
ui.refresh_stats()
check(
    "зардал ойролцоогоор гарна",
    ui.usage_var.get(),
    "өнөөдөр 5.0 мин · энэ сар 15.0 мин · нийт 12 хүсэлт · ~$0.09",
)

# Google үнэгүй тул зардал харуулахгүй
app.cfg["stt_provider"] = "google"
ui.refresh_stats()
check("үнэгүй танигчид зардал алга", "$" in ui.usage_var.get(), False)

# Хараахан хэрэглээгүй танигч
app.cfg["stt_provider"] = "deepgram"
ui.refresh_stats()
check("хэрэглээгүй бол хэлнэ", ui.usage_var.get(), "Хараахан хүсэлт явуулаагүй")
app.cfg["stt_provider"] = "google"

# --- Хөрвүүлэх: тусдаа хуудас ---
ui.select(3)
root.update()
check("хөрвүүлэх хуудас нэр", ui.pages[3].title, "Хөрвүүлэх")
check("файлын явцын мөр бэлдсэн", isinstance(ui.file_progress, tk.StringVar), True)

# --- Аппууд: цонх бүрийн дүрэм ---
# Өмнөх тестүүд «Visual Studio Code»-ыг Толь дээрээс нэмсэн — цэвэр эхэлнэ.
app.cfg["lang_apps"] = {}
ui.select(5)
root.update()
check("аппын хуудас нэрлэгдсэн", ui.pages[5].title, "Аппууд")
check("сүүлийн цонх харагдав", ui.app_marker_var.get(), "Notepad")
check("эхэндээ дүрэмгүй", ui.app_lang_var.get(), "Үндсэн")

# Хэл сонгоход `lang_apps` руу очно
ui.app_lang_var.set("English (US)")
ui._app_lang_changed()
check("хэлний дүрэм хадгалагдав", app.cfg["lang_apps"], {"Notepad": "en-US"})

# Чагтууд нь жагсаалтуудыг удирдана
ui._app_rule_changed("type_mode", True)
check("шууд бичих жагсаалт", app.cfg["type_mode_apps"], ["Notepad"])
ui._app_rule_changed("no_clean", True)
check("цэвэрлэхгүй жагсаалт", app.cfg["no_clean_apps"], ["Notepad"])

# Гурван тохиргоо нэг мөр болж нэгдэнэ
rules = app.window_rules()
check("нэг апп нэг мөр", len(rules), 1)
check(
    "дүрмүүд нэгтгэгдэв",
    (rules[0]["marker"], rules[0]["lang"], rules[0]["type_mode"], rules[0]["no_clean"]),
    ("Notepad", "en-US", True, True),
)

# Устгахад гурвуулаа арилна
ui._remove_rule("Notepad")
check("бүх дүрэм устав", app.window_rules(), [])
check("хэл ч устав", app.cfg["lang_apps"], {})
check("жагсаалтууд ч цэвэрлэгдэв", app.cfg["type_mode_apps"] + app.cfg["no_clean_apps"], [])

ui.select(0)
root.update()

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
ui.history_box.selection_set(0)
ui._mark_language("en-US")
check("түүхээс хэл батална", ui._history_rows[0]["lang"], "en-US")
check("хэл зассан тэмдэг", ui._history_rows[0]["language_corrected"], True)

# --- Төлөв: робот ба тоон самбар ---
ui.select(0)
root.update()
ui.set_state("listening", "Сонсож байна", "Тавихад орно")
check("роботын төлөв", ui.orb.mode, "listening")
check("sidebar-ын төлөв", ui.state_var.get(), "Сонсож байна")
check("товчны бичиг", ui.action_button.cget("text"), "Зогсоох")

# Сонсож байх үед капсул өөрөө акцентаар дүрэлзэх ба товч хүрээт хэлбэртээ
# буцна — хоёр тод юм зэрэгцвэл аль нь ч анхаарал татахгүй.
check("сонсоход капсул дүүрнэ", ui.pill.fill, theme.ACCENT)
check("капсул дээрх бичиг уншигдана", ui.pill_label.cget("fg"), theme.ON_ACCENT)
check("сонсоход товч хүрээт болно", ui.action_button._primary, False)

ui.set_state("ready", "Бэлэн", "")
check("бэлэн болоход робот амарна", ui.orb.mode, "idle")
check("тайлбар анхны утгадаа буцсан", ui.hint_var.get(), ui.default_hint)
check("бэлэн капсул ногооролно", ui.pill.fill, theme.OK_SOFT)
check("бэлэн бичиг ногоон", ui.pill_label.cget("fg"), theme.OK)
check("бэлэн үед товч дүүрнэ", ui.action_button._primary, True)
check("товчны бичиг буцав", ui.action_button.cget("text"), "Эхлүүлэх")

ui.set_state("error", "Алдаа", "")
check("алдааны капсул", ui.pill.fill, theme.DANGER_SOFT)
check("капсулын цэг бичигтэйгээ нэг өнгөтэй", ui.pill_dot.cget("bg"), theme.DANGER_SOFT)
ui.set_state("ready", "Бэлэн", "")

# Хэлний чипийг акцентаар ДҮҮРГЭХГҮЙ: энэ сэдвийн акцент цайвар тул түүн дээр
# `TEXT` тавьбал 2.7:1 болно. Сонголтыг хүрээгээр л ялгана.
active = ui.lang_chips[app.cfg["lang"]]
inactive = next(c for k, c in ui.lang_chips.items() if k != app.cfg["lang"])
check("сонгосон чип дүүрээгүй", active._fill, theme.PANEL2)
check("сонгосон чипийн хүрээ акцент", active._border, theme.ACCENT)
check("сонгоогүй чип бүдэг", inactive.cget("fg"), theme.MUTED)

# --- Төлөв: сүүлийн бичвэрүүд ---
from monspeech.window import RECENT_ROWS, clip, day_label  # noqa: E402

today = datetime.date.today().isoformat()
check("өнөөдрийн шошго", day_label(f"{today}T09:10:00"), "Өнөөдөр")
yesterday = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
check("өчигдрийн шошго", day_label(f"{yesterday}T09:10:00"), "Өчигдөр")
check("хуучин огноо", day_label("2026-08-11T14:52:00"), "08-11")
check("огноогүй мөр", day_label(""), "")
check("гэмтсэн огноо", day_label("тэнэг"), "")

check("богино текст хэвээр", clip("сайн уу"), "сайн уу")
check("урт текст тайрагдана", len(clip("а" * 200)) <= 58, True)
check("тайрсныг тэмдэглэнэ", clip("а" * 200).endswith("…"), True)
check("олон зай нэг болно", clip("сайн   уу\n\nбайна"), "сайн уу байна")

check("мөрийн тоо", len(ui.recent_rows), 2)
check("хамгийн ихдээ таван мөр", RECENT_ROWS, 5)

# Мөрийн үйлдлүүд жинхэнэ аппын методыг дуудаж байна уу
check(
    "мөр давхар товшилт хүлээж авна",
    bool(ui.recent_rows[0].bind("<Double-Button-1>")),
    True,
)
check("мөр гарын фокус авна", ui.recent_rows[0].cget("takefocus"), "1")
ui._repaste_entry({"text": "хурлын тэмдэглэл"})
check("дахин буулгах үйлдэл", app.repasted, "хурлын тэмдэглэл")
ui._copy_entry({"text": "invoice before Friday"})
check("хуулах үйлдэл", app.copied, "invoice before Friday")

# Түүх цэвэрлэхэд Төлөв хуудас ч хоосорно — хоёр жагсаалт нэг эх сурвалжтай
ui.clear_history()
root.update()
check("цэвэрлэхэд мөр үлдээгүй", len(ui.recent_rows), 0)
check("хоосон үед ч цонх бүтэн", ui.recent_body.winfo_exists(), True)

app.transcripts.entries = [
    {"text": "буцаад ирлээ", "at": f"{today}T08:00:00"},
]
ui.refresh_history()
root.update()
check("шинэ бичвэр мөр болов", len(ui.recent_rows), 1)

ui.set_detail("Микрофон солигдлоо.")
check("доод мөрөнд мэдэгдэл", ui.detail_var.get(), "Микрофон солигдлоо.")

ui._remember_type_mode_app()
check("шууд бичих холбоос", ui.detail_var.get(), "«Notepad» цонхонд одооноос шууд бичнэ.")
ui._remember_no_clean_app()
check("цэвэрлэхгүй холбоос", ui.detail_var.get(), "«Obsidian» цонхонд одооноос үгчлэн бичнэ.")

# --- Бичилтийн урьдчилан харах ---
ui.select(2)
root.update()
check("урьдчилан харах эхэлдэг", ui.preview_var.get().startswith("␣өнөөдрийн"), True)
ui.toggles["auto_capitalize"]._clicked()
root.update()
check("том үсэг асаахад тусав", ui.preview_var.get().startswith("␣Өнөөдрийн"), True)
ui.toggles["verbatim_mode"]._clicked()
root.update()
check(
    "үгчлэн preview хувиргахгүй",
    ui.preview_var.get(),
    "␣за ааа өнөөдрийн хурал гурван цагт болно цэг",
)
ui.toggles["verbatim_mode"]._clicked()

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

# --- Sidebar: үндсэн цэс, доод бүлэг ---
check("Тохиргоо доод бүлэгт", ui.settings_button.master is ui.utility, True)
check("тусламжын мөр байна", ui.help_button.label.cget("text"), "Алдаа мэдээлэх")
check("тусламж доод бүлэгт", ui.help_button.master is ui.utility, True)
check("шинэчлэлийн тэмдэг Тохиргоо дээр", ui.settings_button.badge, True)
check("үндсэн цэс тэмдэггүй", sum(b.badge for b in ui.nav), 0)
ui.open_settings()
check("цонх нээхэд тэмдэг арилсан", ui.settings_button.badge, False)
ui.settings.hide()

# --- Танигч: нэмэлт талбарууд зөвхөн өөрийн үйлчилгээнд гарна ---
check("анхандаа талбарууд нуугдсан", shown(ui.stt.extra), False)
check("гурван талбар бэлдсэн", sorted(ui.stt.vars), ["stt_key", "stt_model", "stt_url"])
ui.stt.provider_var.set("Өөрийн үйлчилгээ (OpenAI-нийцтэй)")
ui.stt._selected()
root.update()
check("сонгоход талбарууд гарсан", shown(ui.stt.extra), True)
check("тохиргоо хадгалагдсан", app.cfg["stt_provider"], "openai")
ui.stt.vars["stt_url"].set("https://example.test/v1/audio/transcriptions")
ui.stt._changed()
check("хаяг хадгалагдсан", app.cfg["stt_url"], "https://example.test/v1/audio/transcriptions")
ui.stt.provider_var.set("Google (үнэгүй, түлхүүргүй)")
ui.stt._selected()
root.update()
check("буцаад нуугдсан", shown(ui.stt.extra), False)
check("буцаад google болсон", app.cfg["stt_provider"], "google")

# --- Sidebar хумих ---
ui.toggle_sidebar()
root.update()
check("хумигдсан өргөн", ui.sidebar.cget("width"), 58)
check("шошго нуугдсан", shown(ui.nav[0].label), False)
check("лого жижигрэв", ui.logo.cget("image") != "" and ui.logo.cget("image") is not None, True)
ui.toggle_sidebar()
root.update()
check("буцаж нээгдсэн", ui.sidebar.cget("width"), 208)
check("шошго эргэж ирсэн", shown(ui.nav[0].label), True)

# --- Цэсний нэрс дизайны дагуу ---
check(
    "цэсний нэрс",
    [name for _, name in NAV],
    ["Төлөв", "Толь", "Түүх", "Хөрвүүлэх", "Хэрэглээ", "Аппууд"],
)
check(
    "тохиргооны хэсгүүд",
    [name for _, name in SETTINGS_NAV],
    ["Яриа", "Бичилт", "Товчлуур", "Нэмэлт"],
)

# --- Хэрэглээний хуудас: тоон карт, багана, халив ---
ui.select(4)
root.update()
check("хэрэглээний хуудас нэр", ui.pages[4].title, "Хэрэглээ")
check("хурдын карт бүртгэгдсэн", isinstance(ui.speed_var, tk.StringVar), True)
check("халив зурагдсан", len(ui.heat_canvas.find_all()) > 0, True)
check("багана зурагдсан", len(ui.bars_canvas.find_all()) > 0, True)
check("гарагын шошго Ням эхэлнэ", ui.WEEKDAY_LABELS[0], "Ня")
check("тасралтын хамгийн урт тооцоологдсон", "ХАМГИЙН УРТ" in ui.best_streak_var.get() or ui.best_streak_var.get() == "", True)
# Хоосон статистикт хуудас унах ёсгүй, халив хоосон биш (хоосон нүд ч зурагдана)
check("хурд хоосон үед —", ui.speed_var.get(), "—")

# --- Тасралтын тооцоолол (цэвэр функц, Tk шаардахгүй) ---
import datetime as _dt  # noqa: E402

from monspeech.window import _streaks  # noqa: E402

today = _dt.date.today()
three_days = {str(today - _dt.timedelta(days=offset)): 10 for offset in range(3)}
check("гурван хоногийн тасралт", _streaks(three_days), (3, 3))
three_days[str(today)] = 0  # өнөөдөр хараахан бичээгүй — тасралт өчигдрөөс
check("өнөөдөр хоосон бол өчигдрөөс тоолно", _streaks(three_days), (2, 2))
gap = {
    str(today - _dt.timedelta(days=5)): 10,
    str(today - _dt.timedelta(days=4)): 10,
    str(today - _dt.timedelta(days=1)): 5,
    str(today): 5,
}
check("завсарласны дараах тасралт", _streaks(gap), (2, 2))
check("хоосон өгөгдөл", _streaks({}), (0, 0))

# --- Гарын фокус: Tab-аар хүрч, хүрсэн нь харагдана ---
# Хулганагүй хүн зөвхөн Tab-аар явна. Хүрч болдоггүй товч, эсвэл хүрсэн ч
# хаана байгаа нь харагддаггүй бол уг удирдлага тэдэнд байхгүйтэй адил.
ui.select(1)
root.update()
toggle = ui.toggles["detect_language"]
check("унтраалганд Tab хүрнэ", int(toggle.cget("takefocus")), 1)
# Tk нь `Label`-д суурилсан удирдлагад фокусын хүрээг ОГТ зурдаггүй
# (пикселээр баталсан) тул унтраалга өөрөө зурна — төлөв нь солигдож,
# зураг нь дахин зурагдана.
check("унтраалга фокус мэднэ", toggle._focused, False)
toggle._set_focus(True)
check("фокус тэмдэглэгдэв", toggle._focused, True)
check("фокустай зураг өөр", toggle.cget("image") != "", True)
toggle._set_focus(False)

# Товчлуур ажиллаж байгааг ХОЛБООСООР шалгана, синтетик эвентээр биш.
# Шалтгаан: `event_generate` нь эвентийг OS-ийн фокустай виджет рүү чиглүүлдэг
# бөгөөд дэлгэцээс гадуурх тунгалаг цонх фокусыг найдвартай авдаггүй — хэмжихэд
# багц дотор 8 удаагийн 2-т унасан. Холбоос байгаа эсэх, дуудагдахдаа юу
# хийдэг нь бидний хяналтад байгаа зүйл; эвент хүргэлт бол Tk-гийн ажил.
check("зай холбогдсон", bool(toggle.bind("<space>")), True)
check("Enter холбогдсон", bool(toggle.bind("<Return>")), True)
before = toggle.value
toggle._clicked()
check("товчлуурын зохицуулагч унтраалгыг эргүүлнэ", toggle.value, not before)
toggle._clicked()
check("буцаад анхны утга", toggle.value, before)

nav = ui.nav[0]
check("цэсэнд Tab хүрнэ", int(nav.cget("takefocus")), 1)
check("цэсний дүрс тусдаа зогсоол биш", int(nav.icon.cget("takefocus")), 0)

check("гулсуурт хүрээ бий", int(ui.sliders["silence_hold"].canvas.cget("highlightthickness")) > 0, True)

# --- Сэдэв сонгох ---
check("сэдвийн сонголт бий", ui.theme_var.get(), "Харанхуй")
ui.theme_var.set("Гэрэлтэй")
ui._theme_changed()
check("сэдэв тохиргоонд хадгалагдав", app.cfg["theme"], "light")
ui.theme_var.set("Харанхуй")
ui._theme_changed()
check("буцаад харанхуй", app.cfg["theme"], "dark")

# --- Гүйлгэгч гарч ирэхэд агуулгын өргөн хэлбэлзэхгүй ---
# Урт тайлбартай мөр нэмэхэд өмнө нь цонх хоёр өргөний хооронд төгсгөлгүй
# эргэлдэж гацдаг байв: гүйлгэгч зай эзэлж → агуулга нарийсч → тайлбар нэмэлт
# мөрөнд шилжиж → агуулга уртсаж → гүйлгэгч хэрэгтэй хэвээр. `place`-ээр
# давхарласны дараа өргөн нь гүйлгэгчээс хамаарахаа болих ёстой.
from monspeech.widgets import Card  # noqa: E402 - Tk шалгасны дараа

page = ui.settings.pages[3]
before = page.body.winfo_width()
card = Card(page.body)
for index in range(12):
    card.row(
        f"Урт тайлбартай мөр {index}",
        "Энэ бол зориуд урт тайлбар: гүйлгэгч гарч ирэхэд мөр таслалт нь "
        "өөрчлөгдөж, агуулгын өндөр солигдох ёстой байсан тохиолдлыг дуурайна.",
    )
root.update()
check("гүйлгэгч хэрэгтэй болсон", page._bar_shown, True)
check("агуулгын өргөн хэвээр", page.body.winfo_width(), before)

# Хэд дахин update хийхэд ч тогтвортой — эргэлдэж байвал энд өөрчлөгдөнө
widths = set()
for _ in range(5):
    root.update()
    widths.add(page.body.winfo_width())
check("давтан update-д тогтвортой", len(widths), 1)

root.destroy()

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
