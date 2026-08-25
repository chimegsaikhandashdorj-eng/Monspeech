"""Товчлуурын тааруулах логикийн тест (жинхэнэ hook ашиглахгүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_hotkeys.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from pynput.keyboard import Key, KeyCode

from monspeech import hotkeys as hk
from monspeech.hotkeys import (
    HotkeyManager,
    combo_has_win,
    combo_text,
    describe_key,
    is_superset,
    parse_combo,
    physical_vks,
    pretty,
)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


def manager(accept_injected=True, **combos):
    events = []
    m = HotkeyManager(accept_injected=accept_injected)
    for name, combo in combos.items():
        combo_text = combo
        m.bind(
            name,
            combo_text,
            on_press=lambda n=name: events.append(f"{n}-down"),
            on_release=(lambda n=name: events.append(f"{n}-up")) if name.startswith("ptt") else None,
        )
    return m, events


# --- энгийн товч ---
m, events = manager(toggle="<f9>")
m._press(Key.f9)
m._release(Key.f9)
check("F9 нэг удаа", events, ["toggle-down"])

events.clear()
m._press(Key.f9)
m._press(Key.f9)  # Windows-ийн товч давтах
m._release(Key.f9)
check("дарж барихад давтахгүй", events, ["toggle-down"])

# --- Win+Alt push-to-talk ---
m, events = manager(ptt="<cmd>+<alt>")
m._press(Key.cmd_l)
check("зөвхөн Win дарахад ажиллахгүй", events, [])
m._press(Key.alt_l)
check("Win+Alt ажиллана", events, ["ptt-down"])
m._release(Key.alt_l)
check("Alt суллахад зогсоно", events, ["ptt-down", "ptt-up"])
m._release(Key.cmd_l)

events.clear()
m._press(Key.alt_r)
m._press(Key.cmd_r)
check("Alt→Win дараалал, баруун товч", events, ["ptt-down"])
m._release(Key.cmd_r)
check("Win суллахад зогсоно", events, ["ptt-down", "ptt-up"])
m._release(Key.alt_r)

# --- injected хамгаалалт ---
guarded, events = manager(accept_injected=False, toggle="<ctrl>+v")
guarded._press(Key.ctrl_l, True)
guarded._press(KeyCode.from_char("v"), True)
check("injected үл тоох", events, [])
guarded._press(Key.ctrl_l, False)
guarded._press(KeyCode.from_char("v"), False)
check("бодит даралт", events, ["toggle-down"])

# --- илүү тодорхой хослол давамгайлна ---
check("superset таних", is_superset(parse_combo("<cmd>+<alt>+<shift>"), parse_combo("<cmd>+<alt>")), True)
check("эсрэгээр биш", is_superset(parse_combo("<cmd>+<alt>"), parse_combo("<cmd>+<alt>+<shift>")), False)

m, events = manager(ptt="<cmd>+<alt>", ptt_alt="<cmd>+<alt>+<shift>")
m._press(Key.shift_l)
m._press(Key.cmd_l)
m._press(Key.alt_l)
check("зөвхөн урт хослол ажиллана", events, ["ptt_alt-down"])
m._release(Key.shift_l)
m._release(Key.alt_l)
m._release(Key.cmd_l)
check("суллахад нэг л удаа зогсоно", events, ["ptt_alt-down", "ptt_alt-up"])

# --- дутуу хослол ---
m, events = manager(toggle="<ctrl>+<alt>+<space>")
m._press(Key.ctrl_r)
m._press(Key.alt_l)
m._press(Key.space)
check("баруун/зүүн modifier", events, ["toggle-down"])
m._release(Key.space)
m._release(Key.alt_l)
m._release(Key.ctrl_r)
events.clear()
m._press(Key.ctrl_l)
m._press(Key.space)
check("дутуу хослол", events, [])

# --- гацсан товчийг өөрөө таних ---
m, events = manager(ptt="<cmd>+<alt>")
m._press(Key.cmd_l)
m._press(Key.alt_l)
events.clear()
hk.physically_down = lambda combo: True  # товч үнэхээр дарагдсан хэвээр
m.check_stuck()
check("дарагдсан хэвээр бол хөндөхгүй", events, [])
hk.physically_down = lambda combo: False  # хэрэглэгч аль хэдийн тавьсан
m.check_stuck()
check("гацсаныг илрүүлж зогсооно", events, ["ptt-up"])
m.check_stuck()
check("дахин давтахгүй", events, ["ptt-up"])
hk.physically_down = lambda combo: True

# --- буруу бичиглэл ба харагдац ---
try:
    parse_combo("хогхог")
    check("буруу бичиглэл", "алдаа гараагүй", "ValueError")
except (ValueError, KeyError) as exc:
    check("буруу бичиглэл", type(exc).__name__ in ("ValueError", "KeyError"), True)

# Win товчинд зүүн/баруунг хамарсан нэгдсэн код байдаггүй тул хоёуланг нь шалгана,
# эс бөгөөс баруун Win дарж байхад "суллагдсан" гэж буруу шийднэ.
check("Win-ийг зүүн, баруун хоёуланг нь шалгана",
      physical_vks(parse_combo("<cmd>+<alt>")),
      [[0x12, 0xA4, 0xA5], [0x5B, 0x5C]])
check("Shift-ийг хоёр талаас нь шалгана",
      physical_vks(parse_combo("<ctrl>+<shift>")),
      [[0x10, 0xA0, 0xA1], [0x11, 0xA2, 0xA3]])
# Үсгийг виртуал кодоор нь ч тэмдэглэдэг болсон тул физикээр шалгаж чадна
check("үсгэн товчийг ч шалгана",
      physical_vks(parse_combo("<ctrl>+<alt>+z")),
      [[0x11, 0xA2, 0xA3], [0x12, 0xA4, 0xA5], [0x5A]])

check("Win агуулсныг таних", combo_has_win(parse_combo("<cmd>+<alt>")), True)
check("F9-д Win байхгүй", combo_has_win(parse_combo("<f9>")), False)
check("pretty", pretty("<ctrl>+<alt>+<space>"), "Ctrl + Alt + Space")
check("pretty win", pretty("<cmd>+<alt>"), "Win + Alt")
check("pretty undo", pretty("<ctrl>+<alt>+z"), "Ctrl + Alt + Z")

# --- Кирилл layout дээр үсэгтэй хослол ажиллах ёстой ---
# Z товчийг дарахад "з" тэмдэгт ирдэг ч виртуал код нь 90 хэвээр байна
cyr = HotkeyManager(accept_injected=True)
fired = []
cyr.bind("undo", "<ctrl>+<alt>+z", on_press=lambda: fired.append("undo"))
cyr._press(Key.ctrl_l)
cyr._press(Key.alt_l)
cyr._press(KeyCode(vk=90, char="з"))  # кирилл layout дээрх Z
check("кирилл layout дээр z ажиллана", fired, ["undo"])

# --- Товчлуур барьж авах ---
captured = []
capture_mgr = HotkeyManager(accept_injected=True)
capture_mgr.bind("ptt", "<f8>", on_press=lambda: captured.append("БУРУУ: бүртгэл ажиллав"))
capture_mgr.capture(lambda combo: captured.append(combo))
capture_mgr._press(Key.cmd_l)
capture_mgr._press(Key.alt_l)
check("барьж авах үед бүртгэл ажиллахгүй", captured, [])
capture_mgr._release(Key.alt_l)
check("хослолыг барьж авсан", captured, ["<cmd>+<alt>"])
check("барих горим дууссан", capture_mgr.capturing, False)

captured.clear()
capture_mgr.capture(lambda combo: captured.append(combo))
capture_mgr._press(Key.esc)
capture_mgr._release(Key.esc)
check("Escape цуцална", captured, [None])

captured.clear()
capture_mgr.capture(lambda combo: captured.append(combo))
capture_mgr._press(Key.ctrl_l)
capture_mgr._press(KeyCode(vk=90, char="з"))
capture_mgr._release(Key.ctrl_l)
check("кирилл товчийг латинаар бичнэ", captured, ["<ctrl>+z"])

check("товчийн нэр", describe_key(Key.f8), "<f8>")
check("үсгийг кодоор нь", describe_key(KeyCode(vk=90, char="з")), "z")
check("эрэмбэ жигдрэнэ", combo_text(["<alt>", "<cmd>"]), "<cmd>+<alt>")

# ----------------------------------------------------------------------
# Хоёр дарж асаах
# ----------------------------------------------------------------------
def double_manager(combo="<ctrl>"):
    taps = []
    m = HotkeyManager(accept_injected=True)
    m.bind_double("double", combo, lambda: taps.append("double"))
    return m, taps


def tap(m, key):
    m._press(key)
    m._release(key)


m, taps = double_manager()
tap(m, Key.ctrl_l)
check("нэг дарахад юу ч болохгүй", taps, [])
tap(m, Key.ctrl_l)
check("хоёр дарахад ажиллана", taps, ["double"])

# Гурав дарахад дахин ажиллахгүй (гинж тэглэгдсэн)
tap(m, Key.ctrl_l)
check("гурав дахь нь шинэ гинж", taps, ["double"])

# Хослолын хэсэг байсан бол тооцохгүй: Ctrl+C
m, taps = double_manager()
m._press(Key.ctrl_l)
m._press(KeyCode.from_char("c"))
m._release(KeyCode.from_char("c"))
m._release(Key.ctrl_l)
tap(m, Key.ctrl_l)
check("Ctrl+C-ийн дараа ганц дарсан нь хоёр дарах биш", taps, [])

# Удаан барих нь дарж барих гэсэн үг — хоёр дарах биш
m, taps = double_manager()
m._press(Key.ctrl_l)
m._doubles[0].pressed_at -= 5.0  # 5 секунд барьсан мэт
m._release(Key.ctrl_l)
tap(m, Key.ctrl_l)
check("удаан барихыг тооцохгүй", taps, [])

# Хугацаа хэтэрсэн бол хоёр дахь нь шинэ эхлэл
m, taps = double_manager()
tap(m, Key.ctrl_l)
m._doubles[0].last_tap -= 5.0
tap(m, Key.ctrl_l)
check("удаашруулбал ажиллахгүй", taps, [])

# `clear()` нь хоёр дарахын холбоосыг ч авна
m, taps = double_manager()
m.clear()
tap(m, Key.ctrl_l)
tap(m, Key.ctrl_l)
check("цэвэрлэсний дараа ажиллахгүй", taps, [])


print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
