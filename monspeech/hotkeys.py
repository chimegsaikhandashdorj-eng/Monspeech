"""Глобал товчлуур — аль ч цонхноос ажиллана.

pynput-ийн `GlobalHotKeys` нь програмаар үүсгэсэн (injected) товчлуурыг үл
тоодог тул шалгахад бэрх, мөн push-to-talk-д тохирдоггүй. Иймд нэг л
Listener дээр өөрсдөө тааруулна.

Товчийг жиших нь энгийн харьцуулалт биш: `HotKey.parse("<space>")` нь
vk-код өгдөг бол listener нь `char=' '` -тэй товч илгээдэг; үсгэн товчинд
яг эсрэгээрээ болдог. Иймд товч бүрийг "боломжит бүх дүрс"-ийн олонлогоор
илэрхийлж, огтлолцлоор нь жишнэ.
"""

from __future__ import annotations

import ctypes
import threading
import time

from pynput import keyboard as pkeyboard

from .logging_setup import get as get_logger

log = get_logger("hotkeys")

Key = pkeyboard.Key

# Зүүн/баруун хувилбарыг ерөнхий товч руу нэгтгэнэ
ALIASES = {
    Key.ctrl_l: Key.ctrl,
    Key.ctrl_r: Key.ctrl,
    Key.alt_l: Key.alt,
    Key.alt_r: Key.alt,
    Key.alt_gr: Key.alt,
    Key.shift_l: Key.shift,
    Key.shift_r: Key.shift,
    Key.cmd_l: Key.cmd,
    Key.cmd_r: Key.cmd,
}

# Windows товчийг агуулсан хослолыг таних
WIN_IDS = frozenset({("vk", 0x5B), ("vk", 0x5C)})
# Тодорхойлогдоогүй виртуал товч — програмууд үл тоомсорлоно
FILLER_VK = 0x07
# Гацсан товчийг хэр олон удаа шалгах вэ
WATCH_INTERVAL = 0.7


def key_ids(key, listener=None) -> frozenset:
    """Товчийг таних боломжит бүх дүрсийг буцаана: vk-код ба/эсвэл тэмдэгт."""
    key = ALIASES.get(key, key)
    if isinstance(key, pkeyboard.Key):
        key = key.value

    vk = getattr(key, "vk", None)
    char = getattr(key, "char", None)

    if listener is not None:
        try:
            canonical = listener.canonical(key)
        except Exception:  # noqa: BLE001 - гэнэтийн товчинд унахгүй
            canonical = key
        char = char or getattr(canonical, "char", None)
        vk = vk or getattr(canonical, "vk", None)

    ids = set()
    if vk is not None:
        ids.add(("vk", vk))
    if char:
        lowered = char.lower()
        ids.add(("char", lowered))
        # Кирилл гарын layout дээр Z товч "з" тэмдэгт өгдөг тул зөвхөн
        # тэмдэгтээр жиших нь ажиллахгүй. Виртуал код нь layout-аас үл
        # хамаарч тогтмол тул латин үсэг/тоог кодоор нь ч тэмдэглэнэ.
        if len(lowered) == 1 and ("a" <= lowered <= "z" or "0" <= lowered <= "9"):
            ids.add(("vk", ord(lowered.upper())))
    if not ids:
        ids.add(("raw", repr(key)))
    return frozenset(ids)


# Хослолыг бичихэд ашиглах эрэмбэ
MODIFIER_ORDER = ["cmd", "ctrl", "alt", "shift"]


def describe_key(key) -> str | None:
    """Товчийг тохиргоонд бичих хэлбэрт хөрвүүлнэ: Key.f8 → "<f8>"."""
    key = ALIASES.get(key, key)
    if isinstance(key, pkeyboard.Key):
        return f"<{key.name}>"
    vk = getattr(key, "vk", None)
    # Латин үсэг, тоог layout-аас үл хамааран виртуал кодоор нь тодорхойлно
    if vk is not None and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
        return chr(vk).lower()
    char = getattr(key, "char", None)
    if char and char.isprintable() and not char.isspace():
        return char.lower()
    if vk is not None:
        return f"<{vk}>"
    return None


def combo_text(descriptions: list[str]) -> str:
    """Барьж авсан товчнуудыг жигд эрэмбээр нэг мөр болгоно."""
    modifiers, others = [], []
    for item in descriptions:
        name = item.strip("<>")
        (modifiers if name in MODIFIER_ORDER else others).append(item)
    modifiers.sort(key=lambda m: MODIFIER_ORDER.index(m.strip("<>")))
    seen, ordered = set(), []
    for item in modifiers + others:
        if item not in seen:
            seen.add(item)
            ordered.append(item)
    return "+".join(ordered)


def parse_combo(combo: str) -> tuple[frozenset, ...]:
    """`<ctrl>+<alt>+<space>` мэтийг товч бүрийн дүрсүүд болгоно."""
    keys = pkeyboard.HotKey.parse(combo)
    if not keys:
        raise ValueError(combo)
    return tuple(key_ids(key) for key in keys)


def combo_pressed(combo: tuple[frozenset, ...], pressed: set) -> bool:
    """Хослолын бүх товч дарагдсан эсэх."""
    return bool(combo) and all(ids & pressed for ids in combo)


def combo_has_win(combo: tuple[frozenset, ...]) -> bool:
    return any(ids & WIN_IDS for ids in combo)


def is_superset(bigger: tuple[frozenset, ...], smaller: tuple[frozenset, ...]) -> bool:
    """`bigger` нь `smaller`-ийн бүх товчийг агуулаад дээр нь илүү товчтой юу?

    Ингэснээр Win+Alt+Shift дарахад Win+Alt давхар ажиллахгүй.
    """
    if len(bigger) <= len(smaller):
        return False
    remaining = list(bigger)
    for ids in smaller:
        match = next((other for other in remaining if other & ids), None)
        if match is None:
            return False
        remaining.remove(match)
    return True


def swallow_start_menu() -> None:
    """Win товч суллахад Start цэс нээгдэхээс сэргийлнэ.

    Windows нь Win-ийг дангаар нь дарж тавихад л Start-ыг нээдэг. Win дарагдсан
    хэвээр байхад хоосон товч илгээвэл "өөр товч дарагдсан" гэж тооцож,
    цэсээ нээхээ болино. Alt-ыг дангаар тавихад аппын цэсийн мөр идэвхжиж,
    дараагийн Ctrl+V-г залгидаг — энэ нь түүнээс ч хамгаална.
    """
    try:
        user32 = ctypes.windll.user32
        user32.keybd_event(FILLER_VK, 0, 0, 0)
        user32.keybd_event(FILLER_VK, 0, 2, 0)  # KEYEVENTF_KEYUP
    except OSError:
        pass


# Хажуугийн товчнуудын бүлгүүд. pynput нь заримдаа нэгдсэн код (VK_MENU),
# заримдаа зөвхөн зүүн талынхыг (VK_LSHIFT) өгдөг; Win товчинд нэгдсэн код огт
# байхгүй. Аль нэгийг нь дарсан бол хослол дарагдсанд тооцох ёстой — эс бөгөөс
# баруун Shift/Win дарж байхад "суллагдсан" гэж буруу шийднэ.
SIDE_GROUPS = [
    (0x10, 0xA0, 0xA1),  # Shift
    (0x11, 0xA2, 0xA3),  # Ctrl
    (0x12, 0xA4, 0xA5),  # Alt
    (0x5B, 0x5C),  # Win
]
_VK_GROUP = {vk: group for group in SIDE_GROUPS for vk in group}


def physical_vks(combo: tuple[frozenset, ...]) -> list[list[int]]:
    """Товч бүрийг физикээр шалгахад ямар vk-кодуудыг харах вэ."""
    groups = []
    for ids in combo:
        vks = {value for kind, value in ids if kind == "vk"}
        if not vks:
            continue  # физикээр шалгах боломжгүй товч — алгасна
        expanded: set[int] = set()
        for vk in vks:
            expanded.update(_VK_GROUP.get(vk, (vk,)))
        groups.append(sorted(expanded))
    return sorted(groups)


def physically_down(combo: tuple[frozenset, ...]) -> bool:
    """Хослолын товчнууд яг одоо физикээр дарагдсан байна уу?

    Товч суллах эвент алдагдвал (дэлгэц түгжигдэх, UAC цонх, hook саатах)
    аппыг мөнхөд сонсож үлдэхээс сэргийлнэ.
    """
    try:
        user32 = ctypes.windll.user32
    except OSError:
        return True
    for vks in physical_vks(combo):
        if not any(user32.GetAsyncKeyState(vk) & 0x8000 for vk in vks):
            return False
    return True


class Binding:
    """Нэг товчлуурын холбоос."""

    def __init__(self, name: str, combo_text: str, on_press=None, on_release=None) -> None:
        self.name = name
        self.text = combo_text
        self.combo = parse_combo(combo_text)
        self.on_press = on_press
        self.on_release = on_release
        self.active = False

    @property
    def holds(self) -> bool:
        """Дарж барих төрлийн эсэх (суллахад үйлдэл хийдэг)."""
        return self.on_release is not None


NAMES = {"cmd": "Win", "esc": "Esc"}


def pretty(combo: str) -> str:
    parts = []
    for part in combo.split("+"):
        name = part.strip().strip("<>")
        if name:
            parts.append(NAMES.get(name, name.capitalize()))
    return " + ".join(parts)


#: Хоёр дарахын хооронд өнгөрөх дээд хугацаа (секунд).
DOUBLE_TAP_WINDOW = 0.45
#: Нэг «дарж авах» гэж тооцох дээд хугацаа. Үүнээс удаан барьсан бол энэ нь
#: дарж барих (push-to-talk) гэсэн үг тул хоёр дарахад тооцохгүй.
DOUBLE_TAP_HOLD = 0.4


class DoubleTap:
    """Нэг товчийг хоёр хурдан дарахыг ялгаж таних.

    Ctrl, Shift зэрэг товч нь өдөр бүр өөр хослолын хэсэг болж дарагддаг тул
    дараах хоёр нөхцөлийг ЗААВАЛ шаардана:

    * дарж байх зуур ӨӨР товч дарагдаагүй (Ctrl+C бол хоёр дарах биш),
    * богино дарсан (удаан барих нь push-to-talk).
    """

    def __init__(self, name: str, combo_text: str, on_double, window: float) -> None:
        self.name = name
        self.text = combo_text
        self.combo = parse_combo(combo_text)
        self.on_double = on_double
        self.window = window
        self.pressed_at = 0.0
        self.spoiled = False
        self.last_tap = 0.0

    def keys(self) -> set:
        """Хослолын БҮХ боломжит дүрс — «өөр товч» эсэхийг үүгээр шалгана."""
        return set().union(*self.combo) if self.combo else set()


class HotkeyManager:
    """Хэд хэдэн товчлуурыг нэг hook дээр удирдана."""

    def __init__(self, accept_injected: bool = False) -> None:
        # Өөрсдийн Ctrl+V зэрэг оролт товчлуурыг дахин асаахаас сэргийлнэ
        self.accept_injected = accept_injected

        self._listener: pkeyboard.Listener | None = None
        self._pressed: set = set()
        self._bindings: list[Binding] = []
        self._lock = threading.Lock()
        self._watch_stop = threading.Event()
        self._watch_thread: threading.Thread | None = None
        self._capture: dict | None = None
        self._doubles: list[DoubleTap] = []

    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Бүх холбоосыг устгана. Дарагдсан хэвээр байсныг нь эхлээд зогсооно."""
        with self._lock:
            actions = [
                b.on_release for b in self._bindings if b.active and b.on_release
            ]
            for binding in self._bindings:
                binding.active = False
            self._bindings = []
            self._doubles = []
            self._pressed.clear()
        # Хэрэглэгчийн callback-ийг түгжээнээс гадна дуудна — эс бөгөөс тэр
        # дотроосоо `bind()` дуудвал өөрөө өөрийгөө түгжинэ.
        for action in actions:
            action()

    def bind_double(
        self, name: str, combo_text: str, on_double, window: float = DOUBLE_TAP_WINDOW
    ) -> None:
        """Товчийг хоёр хурдан дарахад дуудагдах холбоос нэмнэ."""
        watcher = DoubleTap(name, combo_text, on_double, window)  # түгжээнээс гадна задална
        with self._lock:
            self._doubles.append(watcher)

    def bind(self, name: str, combo_text: str, on_press=None, on_release=None) -> None:
        """Товчлуур нэмнэ. Буруу бичиглэлд `ValueError` шиднэ."""
        binding = Binding(name, combo_text, on_press, on_release)  # түгжээнээс гадна задална
        with self._lock:
            self._bindings.append(binding)

    def start(self) -> None:
        if self._listener is None:
            self._listener = pkeyboard.Listener(on_press=self._press, on_release=self._release)
            self._listener.start()
        if self._watch_thread is None:
            self._watch_stop.clear()
            self._watch_thread = threading.Thread(target=self._watch_loop, daemon=True)
            self._watch_thread.start()

    def stop(self) -> None:
        self._watch_stop.set()
        self._watch_thread = None
        if self._listener:
            self._listener.stop()
            self._listener = None
        with self._lock:
            self._pressed.clear()

    # ------------------------------------------------------------------
    def _matched(self) -> list[Binding]:
        """Одоо бүрэн дарагдсан хослолууд (илүү тодорхойг нь эхэнд)."""
        matched = [b for b in self._bindings if combo_pressed(b.combo, self._pressed)]
        return sorted(matched, key=lambda b: len(b.combo), reverse=True)

    # ------------------------------------------------------------------
    def capture(self, on_done) -> None:
        """Дараагийн товчлуурын хослолыг барьж авна (бүртгэлүүд түр зогсоно).

        `on_done(combo_text)` — хэрэглэгч товчоо суллахад дуудагдана.
        `None` дамжуулбал цуцалсан гэсэн үг.
        """
        with self._lock:
            self._capture = {"on_done": on_done, "keys": []}

    def cancel_capture(self) -> None:
        with self._lock:
            capture, self._capture = self._capture, None
        if capture and capture["on_done"]:
            capture["on_done"](None)

    @property
    def capturing(self) -> bool:
        """Яг одоо шинэ товчлуур барьж авах горимд байна уу."""
        return self._capture is not None

    def _capture_press(self, key) -> None:
        description = describe_key(key)
        if description and description not in self._capture["keys"]:
            self._capture["keys"].append(description)

    def _capture_release(self):
        """Товч суллагдмагц хослолыг эцэслэнэ."""
        capture, self._capture = self._capture, None
        keys = capture["keys"]
        if not keys or keys == ["<esc>"]:
            return capture["on_done"], None
        return capture["on_done"], combo_text(keys)

    # ------------------------------------------------------------------
    def _press(self, key, injected=False) -> None:
        if injected and not self.accept_injected:
            return
        with self._lock:
            if self._capture is not None:
                self._capture_press(key)
                return
            self._pressed |= key_ids(key, self._listener)
            self._track_double_press()
            matched = self._matched()
            actions = []
            for binding in matched:
                # Илүү тодорхой хослол дарагдсан бол богиныг нь ажиллуулахгүй
                if any(is_superset(other.combo, binding.combo) for other in matched):
                    if binding.active and binding.on_release:
                        binding.active = False
                        actions.append(binding.on_release)
                    continue
                if binding.active:
                    continue
                binding.active = True
                if combo_has_win(binding.combo):
                    swallow_start_menu()
                if binding.on_press:
                    actions.append(binding.on_press)
        for action in actions:
            action()

    def _release(self, key, injected=False) -> None:
        if injected and not self.accept_injected:
            return
        finished = None
        actions: list = []
        with self._lock:
            if self._capture is not None:
                finished = self._capture_release()
            else:
                self._pressed -= key_ids(key, self._listener)
                actions = self._track_double_release() + self._deactivate_unheld()
        if finished:
            on_done, combo = finished
            if on_done:
                on_done(combo)
            return
        for action in actions:
            action()

    def _track_double_press(self) -> None:
        """Дарагдсан товчийг хоёр дарах хэмжүүрт бүртгэнэ (түгжээ дотор)."""
        now = time.monotonic()
        for watcher in self._doubles:
            keys = watcher.keys()
            if not combo_pressed(watcher.combo, self._pressed):
                # Хослол нь бүрдээгүй атлаа өөр товч дарагдсан — хэрэв энэ
                # хооронд хүлээгдэж байсан бол тэр нь хослолын хэсэг байжээ.
                if watcher.pressed_at:
                    watcher.spoiled = True
                continue
            if self._pressed - keys:
                watcher.spoiled = True  # Ctrl+C гэх мэт — хоёр дарах биш
                continue
            if not watcher.pressed_at:
                watcher.pressed_at = now
                watcher.spoiled = False

    def _track_double_release(self) -> list:
        """Товч суллагдлаа — хоёр дахь дарах мөн эсэхийг шийднэ (түгжээ дотор)."""
        now = time.monotonic()
        actions = []
        for watcher in self._doubles:
            if not watcher.pressed_at or combo_pressed(watcher.combo, self._pressed):
                continue
            held = now - watcher.pressed_at
            spoiled = watcher.spoiled
            watcher.pressed_at = 0.0
            watcher.spoiled = False
            if spoiled or held > DOUBLE_TAP_HOLD:
                watcher.last_tap = 0.0  # гинжийг тасална
                continue
            if watcher.last_tap and now - watcher.last_tap <= watcher.window:
                watcher.last_tap = 0.0
                if watcher.on_double:
                    actions.append(watcher.on_double)
                continue
            watcher.last_tap = now
        return actions

    def _deactivate_unheld(self) -> list:
        """Хослол нь задарсан холбоосуудыг унтраана (түгжээ дотор дуудна)."""
        actions = []
        for binding in self._bindings:
            if binding.active and not combo_pressed(binding.combo, self._pressed):
                binding.active = False
                if binding.on_release:
                    actions.append(binding.on_release)
        return actions

    # ------------------------------------------------------------------
    def _watch_loop(self) -> None:
        """Товч суллах эвент алдагдсан эсэхийг тогтмол шалгана."""
        while not self._watch_stop.wait(WATCH_INTERVAL):
            self.check_stuck()

    def check_stuck(self) -> list:
        """Дарагдсан гэж бодож буй боловч физикээр суллагдсан товчийг цэвэрлэнэ."""
        actions = []
        with self._lock:
            for binding in self._bindings:
                if not binding.active or not binding.holds:
                    continue
                if not physically_down(binding.combo):
                    log.warning("товч '%s' суллагдсаныг мэдээгүй тул албаар зогсоов", binding.text)
                    binding.active = False
                    self._pressed -= set().union(*binding.combo)
                    if binding.on_release:
                        actions.append(binding.on_release)
        for action in actions:
            action()
        return actions
