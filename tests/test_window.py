"""Удирдлагын цонхны тест — хайлт мөрүүдийг зөв нуугаад буцаадаг эсэх.

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


class Stats:
    def summary(self):
        return ""


class FakeApp:
    """ControlWindow-д хэрэгтэй хамгийн бага гадаргуу."""

    def __init__(self):
        config_module.CONFIG_PATH = Path(tempfile.mkdtemp()) / "config.json"
        self.cfg = Config.load()
        self.cfg["replacements"] = {"клауд": "Claude"}
        self.cfg["snippets"] = {"миний хаяг": "УБ"}
        self.stats = Stats()
        self.detail = ""

    @staticmethod
    def list_microphones():
        return ["Системийн үндсэн"], [-1]

    def toggle(self):
        pass

    def open_log(self):
        pass

    def remember_type_mode_app(self):
        return "«Notepad» цонхонд одооноос шууд бичнэ."


try:
    root = tk.Tk()
except tk.TclError as exc:  # дэлгэцгүй орчин
    print(f"алгаслаа (Tk нээгдсэнгүй: {exc})")
    raise SystemExit(0)

root.withdraw()  # тестийн явцад дэлгэц дээр гарахгүй

from monspeech.window import ControlWindow  # noqa: E402 - Tk шалгасны дараа

app = FakeApp()
ui = ControlWindow(root, app)
root.update()

# --- Хайлт нээлттэй хэсгийн агуулгыг алдахгүй байх ---
words = ui.words_section
words.toggle()  # хэрэглэгч "Үг солих"-ыг нээв
root.update()
check("нээхэд агуулга гарсан", bool(words.body.winfo_ismapped()), True)

ui.search_var.set("үг")
root.update()
check("хайлтад агуулга хэвээр", bool(words.body.winfo_ismapped()), True)

ui.search_var.set("")
root.update()
check("хайлт цэвэрлэхэд агуулга хэвээр", bool(words.body.winfo_ismapped()), True)

# --- Ердийн мөрүүд хайлтаар шүүгдэж, буцаж ирэх ---
lang_row = next(r for r in ui.rows if "language" in r["keywords"])
mic_row = next(r for r in ui.rows if "микрофон" in r["keywords"])

ui.search_var.set("микрофон")
root.update()
check("таарахгүй мөр нуугдсан", bool(lang_row["widget"].winfo_ismapped()), False)
check("таарсан мөр харагдсан", bool(mic_row["widget"].winfo_ismapped()), True)

ui.search_var.set("")
root.update()
check("цэвэрлэхэд бүх мөр эргэж ирсэн", bool(lang_row["widget"].winfo_ismapped()), True)
check("багцлах зай хадгалагдсан", lang_row["widget"].pack_info()["pady"], 4)

# --- Товчлуурын мөрийн зай өөр (5) хэвээр ---
hotkey_row = next(r for r in ui.rows if "push to talk" in r["keywords"])
check("товчлуурын мөрийн зай", hotkey_row["widget"].pack_info()["pady"], 5)

# --- Ашиглагдаагүй байсан "шууд бичих" боломж холбогдсон эсэх ---
type_row = next((r for r in ui.rows if "clipboard ажиллахгүй" in r["keywords"]), None)
check("шууд бичих мөр бүртгэгдсэн", type_row is not None, True)
ui._remember_type_mode_app()
check(
    "холбоос аппыг дуудсан",
    ui.status.detail_var.get(),
    "«Notepad» цонхонд одооноос шууд бичнэ.",
)

# --- Чагтууд бүгд бүртгэгдсэн ---
check("чагтын тоо", len(ui.toggles), 9)

root.destroy()

print()
if fails:
    print("FAILED:")
    for line in fails:
        print("  " + line)
    raise SystemExit(1)
print("ALL PASS")
