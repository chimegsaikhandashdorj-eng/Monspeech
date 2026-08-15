"""Микрофон сонгох, дахин олох логикийн тест (жинхэнэ микрофон хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_mics.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech import mics
from monspeech.mics import Mic

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


class FakePyAudio:
    """PyAudio-ийн зөвхөн хэрэгтэй хэсгийг дуурайна."""

    def __init__(self, devices):
        self.devices = devices  # [(нэр, сонсох суваг), ...]

    def get_device_count(self):
        return len(self.devices)

    def get_device_info_by_index(self, index):
        if index < 0 or index >= len(self.devices):
            raise OSError("invalid device index")
        name, channels = self.devices[index]
        return {"name": name, "maxInputChannels": channels}


# Windows дээр нэг физик микрофон MME/DirectSound/WASAPI-аар давхар гардаг
usual = FakePyAudio(
    [
        ("Sound Mapper", 2),
        ("Headset (AWEI)", 1),
        ("Speakers", 0),
        ("Headset (AWEI)", 1),  # DirectSound давхардал
    ]
)
# Чихэвч салахад MME-ийн «Sound Mapper» хүртэл сонсох суваггүй болдог
unplugged = FakePyAudio([("Sound Mapper", 0), ("Speakers", 0)])
# Дахин холбоход дугаар нь шилжсэн байна
moved = FakePyAudio([("Sound Mapper", 2), ("Webcam", 1), ("Headset (AWEI)", 1)])
# Windows нь нэрийг нь өөрчилсөн («2-» гэсэн угтвар нэмэгдэв)
renamed = FakePyAudio([("Sound Mapper", 2), ("Headset (2- AWEI)", 1)])

# --- Mic төрөл ---
check("үндсэн нь дугааргүй", mics.SYSTEM.is_default, True)
check("үндсэний нэр", mics.SYSTEM.label, mics.SYSTEM_LABEL)
check("нэр урт бол тайрна", len(Mic(1, "ө" * 60).label), mics.LABEL_LIMIT)
check("нэргүй бол дугаараар", Mic(4).label, "#4")

saved = {}
Mic(3, "Headset (AWEI)").save_to(saved)
check("тохиргоонд хоёулаа орно", saved, {"mic_index": 3, "mic_name": "Headset (AWEI)"})

# --- available ---
found = mics.available(usual)
check("эхнийх нь үргэлж үндсэн", found[0], mics.SYSTEM)
check("зөвхөн сонсдогийг нь", [m.name for m in found[1:]], ["Sound Mapper", "Headset (AWEI)"])
check("давхардсан нэрийг нэг л удаа", len(found), 3)
check("нэг нэрээс эхнийхийг нь", found[2].index, 1)
check("төхөөрөмжгүй бол ганц мөр", mics.available(unplugged), [mics.SYSTEM])

# --- resolve ---
headset = Mic(1, "Headset (AWEI)")
check("зөв дугаарыг хэвээр", mics.resolve(usual, headset), 1)
check("үндсэнийг хөндөхгүй", mics.resolve(usual, mics.SYSTEM), None)
check("шилжсэн дугаарыг нэрээр олно", mics.resolve(moved, headset), 2)
check("салсан төхөөрөмж → үндсэн", mics.resolve(unplugged, headset), None)
check("сонсдоггүй сонголт → үндсэн", mics.resolve(usual, Mic(2, "Speakers")), None)
check("хүрээнээс гарсан дугаар → үндсэн", mics.resolve(usual, Mic(9, "Алга")), None)
# Нэр өөрчлөгдсөн ч дугаар нь сонссоор байвал ажиллаж байгаа сонголтыг хаяхгүй
check("нэр зөрсөн ч ажиллаж байвал хэвээр", mics.resolve(renamed, headset), 1)
# Нэргүй хуучин тохиргоо
check("нэргүй хуучин тохиргоо", mics.resolve(usual, Mic(1)), 1)
check("нэргүй бөгөөд салсан", mics.resolve(unplugged, Mic(1)), None)

# --- load (хуучин тохиргоог нөхөх) ---
old = {"mic_index": 1, "mic_name": ""}
check("нэрийг нөхнө", mics.load(old, usual), Mic(1, "Headset (AWEI)"))
check("тохиргоог өөрөө бичихгүй", old["mic_name"], "")
check("нэр байвал хөндөхгүй", mics.load({"mic_index": 1, "mic_name": "Хэвээр"}, moved), Mic(1, "Хэвээр"))
check("үндсэн хэвээр", mics.load({"mic_index": -1, "mic_name": ""}, usual), mics.SYSTEM)
check(
    "салсан төхөөрөмжийн нэр олдохгүй",
    mics.load({"mic_index": 1, "mic_name": ""}, unplugged),
    Mic(1, ""),
)

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
