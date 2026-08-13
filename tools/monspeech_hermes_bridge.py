#!/usr/bin/env python
"""Monspeech ↔ Hermes гүүр.

Monspeech-ийн танигдсан текстийг Hermes-т дамжуулж, хариуг нь Windows
clipboard-д тавина — дурын цонхонд буулгах боломжтой.

Хэрэглээ:
  python monspeech_hermes_bridge.py last
        сүүлийн танигдсан текстүүдийг харуулах

  python monspeech_hermes_bridge.py ask "<текст>"
        нэг удаа Hermes-ээс асуух; хариу clipboard-д орж тухайн үед хэвлэгдэнэ

  python monspeech_hermes_bridge.py voicelog
        өнөөдрийн шинэ дуут тэмдэглэлийг Obsidian-ийн daily note-д нэмэх
        (давхарлахгүй — cursor файлтай)

  python monspeech_hermes_bridge.py watch [--trigger "асуулт"] [--all]
        history.jsonl-г тасралтгүй ажиглана. Шинэ мөр бүр:
          --trigger "үг"   зөвхөн тэр үгээр эхэлсэн (эсвэл агуулсан) мөрийг
                           Hermes-т явуулна, "үг"-ийг текстээс авч хаяна.
          --all            бүх шинэ мөрийг Hermes-т явуулна.
        Хариуг clipboard-д хийгээд REPLY_LOG-д нэмж бичнэ.

  Ctrl+C дарж зогсооно.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

CONFIG_DIR = Path(os.path.expandvars(r"%AppData%")) / "Monspeech"
HISTORY = CONFIG_DIR / "history.jsonl"
REPLY_LOG = CONFIG_DIR / "hermes_replies.log"
HERMES_CMD = ["hermes", "chat", "-Q", "-q"]
DEFAULT_TRIGGER = "асуулт"
# OpenRouter free-ийн хязгаарлалт/алдаа гарахад найдвартай retry хийх fallback
GOOGLE_FALLBACK = ["--provider", "google", "-m", "gemini-2.5-flash"]
# Daily note-ийн хавтас хүн бүрт өөр. Тохируулах: `MONSPEECH_DAILY_DIR` орчны
# хувьсагч. Тавиагүй бол Obsidian-ий түгээмэл байрлалыг таамаглана — `voicelog`
# ажиллуулахад олдохгүй бол алдаа мэдэгдэнэ.
OBSIDIAN_DAILY = Path(
    os.environ.get("MONSPEECH_DAILY_DIR")
    or Path(os.path.expandvars(r"%USERPROFILE%")) / "Documents/Obsidian Vault/01_DAILY"
)
VOICELOG_CURSOR = CONFIG_DIR / "voicelog_cursor.txt"
VOICELOG_HEADER = "## 🎙 Дуут тэмдэглэл"


def read_entries() -> list[dict]:
    entries: list[dict] = []
    try:
        with open(HISTORY, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except ValueError:
                    continue
                if isinstance(item, dict) and item.get("text"):
                    entries.append(item)
    except OSError as exc:
        print(f"[анхааруулга] түүх уншигдсангүй: {exc}", file=sys.stderr)
    return entries


def _run_hermes(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=300,
        )
    except Exception as exc:  # noqa: BLE001
        return 1, f"[hermes дуудалт бүтэлгүйтэв] {exc}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    return proc.returncode, "\n".join(x for x in (out, err) if x)


def _looks_failed(text: str) -> bool:
    for pat in (
        "HTTP 4", "HTTP 5", "Rate limit", "rate limit",
        "Authentication Fails", "API call failed", "бүтэлгүйтэв",
    ):
        if pat in text:
            return True
    return False


def _clean(text: str) -> str:
    """'Warning: ...', 'session_id: ...' гэх үйлчилгээний мөрүүдийг арилгаж, зөвхөн агуулгыг үлдээнэ."""
    lines = [
        ln for ln in text.splitlines()
        if not ln.strip().startswith("Warning:")
        and not ln.strip().startswith("session_id:")
    ]
    cleaned = "\n".join(lines).strip()
    return cleaned or "(Hermes хоосон хариу буцаав — API хязгаарлагдсан байж болно)"


def hermes_ask(text: str) -> str:
    """Hermes-т асууж, цэвэр хариуг буцаана.

    Эхлээд үндсэн тохиргоогоор (ихэвчлэн OpenRouter). Хэрэв бүтэлгүйтвэл
    (хязгаарлалт/алдаа) Google gemini-2.5-flash-д нэг удаа retry болно.
    """
    rc, combined = _run_hermes([*HERMES_CMD, text])
    if rc != 0 or _looks_failed(combined):
        # Чухал: текст `-q`-ийн дараа шууд байх ёстой (argparse-д flag ирвэл алдаа гардаг)
        rc2, retry = _run_hermes([*HERMES_CMD, text, *GOOGLE_FALLBACK])
        if not (rc2 != 0 or _looks_failed(retry)):
            return _clean(retry)
    return _clean(combined)


def set_clipboard(text: str) -> tuple[bool, str]:
    """UTF-8 файлаар clipboard-д тавина (кодировкийн асуудлаас сэргийлнэ)."""
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    tmp = CONFIG_DIR / "_reply_tmp.txt"
    try:
        tmp.write_text(text, encoding="utf-8")
    except OSError as exc:
        return False, str(exc)
    ps = (
        "& { $t = Get-Content -Raw -Encoding UTF8 '" + str(tmp).replace("'", "''") + "'; "
        "Set-Clipboard -Value $t }"
    )
    try:
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       capture_output=True, timeout=30)
    except Exception as exc:  # noqa: BLE001
        return False, str(exc)
    return True, ""


def log_reply(q: str, reply: str) -> None:
    try:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {"q": q, "reply": reply[:4000], "at": time.strftime("%Y-%m-%dT%H:%M:%S")}
        with open(REPLY_LOG, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except OSError:
        pass


def cmd_last(_args) -> int:
    entries = read_entries()
    if not entries:
        print("Түүх хоосон байна.")
        return 0
    for e in entries[-8:]:
        print(f"[{e.get('at', '?')}] {e['text']}")
    return 0


def _append_daily_bullets(path: Path, bullets: list[str]) -> int:
    """Today-ийн note-д Дуут тэмдэглэл хэсэг дор bullet-үүд нэмнэ."""
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    block = "\n".join(bullets) + "\n"
    if VOICELOG_HEADER in content:
        idx = content.index(VOICELOG_HEADER)
        nl = content.find("\n", idx + len(VOICELOG_HEADER))
        insert_pos = nl + 1 if nl != -1 else len(content)
        content = content[:insert_pos] + block + content[insert_pos:]
    else:
        if content.strip():
            content = content.rstrip() + "\n\n" + VOICELOG_HEADER + "\n" + block
        else:
            content = VOICELOG_HEADER + "\n" + block
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return len(bullets)


def cmd_voicelog(_args) -> int:
    """Өнөөдрийн шинэ ярьсан зүйлсийг Obsidian daily note-д нэмнэ."""
    entries = read_entries()
    cursor = 0
    if VOICELOG_CURSOR.exists():
        try:
            cursor = int(VOICELOG_CURSOR.read_text(encoding="utf-8").strip())
        except ValueError:
            cursor = 0
    new = entries[cursor:]
    if not new:
        print("Шинэ дуут тэмдэглэл байхгүй.")
        return 0
    # Хавтсаа бичихээс ӨМНӨ шалгана: курсор урагшилчихаад бичиж чадахгүй бол
    # эдгээр тэмдэглэл дахин хэзээ ч гарахгүй.
    if not OBSIDIAN_DAILY.is_dir():
        print(
            f"Daily note-ийн хавтас олдсонгүй: {OBSIDIAN_DAILY}\n"
            "MONSPEECH_DAILY_DIR орчны хувьсагчаар зааж өгнө үү.",
            file=sys.stderr,
        )
        return 2
    bullets = [f"- 🗣 [{e.get('at', '')}] {e['text'].strip()}" for e in new if e.get("text", "").strip()]
    VOICELOG_CURSOR.write_text(str(len(entries)), encoding="utf-8")
    if not bullets:
        print("Шинэ мөрүүд хоосон байна.")
        return 0
    path = OBSIDIAN_DAILY / f"{date.today().isoformat()}.md"
    n = _append_daily_bullets(path, bullets)
    print(f"✓ {n} дуут тэмдэглэл → {path}")
    return 0


def cmd_ask(args) -> int:
    text = (args.text or "").strip()
    if not text:
        print("Хоосон текст. Жишээ: ask \"Сайн уу\"", file=sys.stderr)
        return 2
    print(f"→ Hermes-ээс асууж байна: {text}")
    reply = hermes_ask(text)
    print("\n" + ("─" * 50))
    print(reply)
    print("─" * 50)
    ok, err = set_clipboard(reply)
    log_reply(text, reply)
    if ok:
        print("✓ Хариу clipboard-д хуулагдлаа (дурын цонхонд Ctrl+V).")
    else:
        print(f"! Clipboard-д хуулах боломжгүй: {err}", file=sys.stderr)
    return 0


def cmd_watch(args) -> int:
    trigger = (args.trigger or "").strip().lower()
    pattern = None
    if not args.all and trigger:
        pattern = re.compile(re.escape(trigger), re.IGNORECASE)

    seen = len(read_entries())
    print(f"Ажиглаж байна: {HISTORY}")
    if pattern:
        print(f"Зөвхөн '{trigger}' агуулсан мөрийг Hermes-т явуулна. Ctrl+C = зогсоох.")
    else:
        print("Бүх шинэ мөрийг Hermes-т явуулна. Ctrl+C = зогсоох.")

    while True:
        time.sleep(1.0)
        entries = read_entries()
        new = entries[seen:]
        if not new:
            continue
        seen = len(entries)
        for e in new:
            text = e["text"].strip()
            if not text:
                continue
            if pattern:
                m = pattern.search(text)
                if not m:
                    print(f"(алгаслаа — triggerгүй) {text[:40]}")
                    continue
                text = (text[:m.start()] + text[m.end():]).strip()
            if not text:
                continue
            print(f"\n→ Hermes-ээс асууж байна: {text}")
            reply = hermes_ask(text)
            print(reply)
            ok, err = set_clipboard(reply)
            log_reply(text, reply)
            if ok:
                print("✓ Хариу clipboard-д хуулагдлаа.")
            else:
                print(f"! Clipboard алдаа: {err}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="monspeech_hermes_bridge", description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_last = sub.add_parser("last", help="сүүлийн танигдсан текстүүд")
    p_last.set_defaults(func=cmd_last)

    p_vl = sub.add_parser("voicelog", help="өнөөдрийн шинэ дуут тэмдэглэлийг Obsidian note-д нэмэх")
    p_vl.set_defaults(func=cmd_voicelog)

    p_ask = sub.add_parser("ask", help="нэг удаа асуух")
    p_ask.add_argument("text", help="асуух текст")
    p_ask.set_defaults(func=cmd_ask)

    p_watch = sub.add_parser("watch", help="history.jsonl-г ажиглах")
    p_watch.add_argument("--trigger", default=DEFAULT_TRIGGER, help="зөвхөн энэ үгтэй мөрийг явуулна")
    p_watch.add_argument("--all", action="store_true", help="бүх мөрийг явуулна")
    p_watch.set_defaults(func=cmd_watch)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
