# PyInstaller-ийн тохиргоо — ганц Monspeech.exe үүсгэнэ.
#
# Ажиллуулах:  powershell -NoProfile -File tools\build_exe.ps1
#
# Онцлох зүйлс:
#   * `assets` хавтсыг багцын дотор ЯГ ижил замаар байрлуулна. Апп нь дүрсээ
#     `<модулийн хавтас>/../assets/` гэж хайдаг бөгөөд багцалсан үед тэр зам нь
#     PyInstaller-ийн задалсан түр хавтас руу заана — өөрчлөх шаардлагагүй.
#   * pystray, pynput нь Windows-ийн хэрэгжүүлэлтээ ажиллах үедээ сонгодог тул
#     багцлагч өөрөө олж чаддаггүй. Гараар зааж өгнө.

from pathlib import Path

ROOT = Path(SPECPATH).parent

a = Analysis(
    [str(ROOT / "tools" / "monspeech_launcher.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / "assets"), "assets")],
    hiddenimports=[
        "pystray._win32",
        "pynput.keyboard._win32",
        "pynput.mouse._win32",
        # Танигчид нь `recognizer.create()` дотроос импортлогддог (тойрог
        # үүсэхээс сэргийлж). Багцлагч ийм импортыг олдог ч энд бичиж
        # баталгаажуулав — олдохгүй бол зөвхөн танигч солиход л унана.
        "monspeech.stt_google",
        "monspeech.stt_openai",
        # `vad.py` дотор try/except-ээр импортлогддог. Багцлагч ийм импортыг
        # олдог ч энд бичиж баталгаажуулав — олдохгүй бол .exe нь чимээгүйгээр
        # түвшингийн зам руу буцна (унахгүй, гэхдээ чанар нь хуучирна).
        "webrtcvad",
    ],
    # Өөрсдийн hook-ууд contrib-ийнхийг ОРЛОНО. `hook-webrtcvad.py`-г үзнэ үү:
    # стандарт hook нь `webrtcvad-wheels` түгээлтийн нэр дээр унадаг.
    hookspath=[str(ROOT / "tools" / "hooks")],
    runtime_hooks=[],
    # Хэрэглэгддэггүй хүнд сангуудыг хасаж, файлын хэмжээг багасгана
    excludes=[
        "numpy", "scipy", "pandas", "matplotlib", "PyQt5", "PyQt6",
        "PySide2", "PySide6", "IPython", "pytest", "setuptools", "pip",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="Monspeech",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX нь антивирусын хуурамч дохиог ихэсгэдэг
    runtime_tmpdir=None,
    console=False,  # цонхтой апп — консол гарч ирэхгүй
    icon=str(ROOT / "assets" / "monspeech.ico"),
)
