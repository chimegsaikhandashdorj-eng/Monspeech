r"""Monspeech-ийн монгол–англи танилтыг бодит WAV сангаар хэмжинэ.

Жишээ:
  .venv\Scripts\python.exe tools\benchmark_language.py benchmarks\manifest.jsonl
  .venv\Scripts\python.exe tools\benchmark_language.py benchmarks\manifest.jsonl --accuracy
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from monspeech import recognizer  # noqa: E402
from monspeech.config import Config  # noqa: E402
from monspeech.language_router import LanguageRouter  # noqa: E402
from monspeech.store import TranscriptStore  # noqa: E402
from monspeech.textproc import Formatter  # noqa: E402


def _distance(left: list[str], right: list[str]) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(
                min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b))
            )
        previous = current
    return previous[-1]


def error_rate(expected: str, actual: str, *, characters: bool) -> float:
    if characters:
        left = list(" ".join(expected.lower().split()))
        right = list(" ".join(actual.lower().split()))
    else:
        left = expected.lower().split()
        right = actual.lower().split()
    return _distance(left, right) / max(1, len(left))


def _pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as handle:
        if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
            raise ValueError("WAV нь mono, 16-bit PCM байх ёстой")
        rate = handle.getframerate()
        if rate != 16000:
            raise ValueError(f"WAV нь 16 кГц байх ёстой (одоогийнх {rate})")
        return handle.readframes(handle.getnframes()), rate


def _percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round((len(ordered) - 1) * ratio))]


def main() -> int:
    parser = argparse.ArgumentParser(description="Monspeech language/STT benchmark")
    parser.add_argument("manifest", type=Path, help="JSONL manifest")
    parser.add_argument(
        "--accuracy",
        action="store_true",
        help="Монгол, англи хоёрыг зэрэг танина",
    )
    parser.add_argument(
        "--choose",
        action="store_true",
        help=(
            "Хувилбар сонгогчийг асаана (толь + хэлний загвар + түүх). "
            "Үүнгүйгээр танигчийн ЭХНИЙ хувилбар хэмжигдэнэ — хоёуланг нь "
            "ажиллуулж WER-ийг харьцуулбал сонгогчийн үнэ цэн гарна."
        ),
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Үр дүнг JSON болгож бичнэ (хоёр ажиллалтыг харьцуулахад)",
    )
    args = parser.parse_args()

    manifest = args.manifest.resolve()
    rows = []
    for number, line in enumerate(manifest.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        item = json.loads(line)
        if not item.get("audio") or not item.get("text") or not item.get("language"):
            raise ValueError(f"{number}-р мөрд audio, text, language заавал байна")
        rows.append(item)
    if not rows:
        print("Manifest хоосон байна.")
        return 2

    cfg = Config.load()
    provider = recognizer.create(cfg)
    chooser = None
    if args.choose:
        # Аппынхтай ЯГ ижил байдлаар бэлдэнэ: толь, товчлол, нэрс тохиргооноос,
        # хэлний загвар нь түүхээс. Эс бөгөөс хэмжилт нь жинхэнэ хэрэглээнээс
        # өөр нөхцөлд явна.
        formatter = Formatter(
            replacements=cfg["replacements"],
            snippets=cfg["snippets"],
            names=cfg["names"],
        )
        for entry in TranscriptStore().entries:
            if entry.get("mode") != "verbatim":
                formatter.remember(str(entry.get("text") or ""))
        chooser = formatter.choose
        print(
            f"сонгогч: асаалттай (хэлний загвар "
            f"{'бэлэн' if formatter.model.ready else 'сураагүй'}, "
            f"{formatter.model.tokens} үг)"
        )
    router = LanguageRouter(
        provider,
        factory=lambda language: recognizer.create(cfg, language),
        chooser=chooser,
    )
    timings: list[float] = []
    wers: list[float] = []
    cers: list[float] = []
    details: list[dict] = []
    languages = 0
    try:
        for index, item in enumerate(rows, 1):
            audio = (manifest.parent / item["audio"]).resolve()
            pcm, rate = _pcm(audio)
            expected = str(item["text"])
            expected_language = str(item["language"])
            hint = str(item.get("hint") or cfg["lang"])
            started = time.perf_counter()
            result = router.recognize(
                pcm,
                rate,
                hint=hint,
                configured=list(cfg["auto_languages"]),
                automatic=bool(item.get("automatic", True)),
                accuracy=bool(args.accuracy),
                minimum_confidence=float(cfg["min_confidence"]),
                margin=float(cfg["language_margin"]),
                choose_alternatives=bool(args.choose),
            )
            elapsed = (time.perf_counter() - started) * 1000
            actual = result.text
            wer = error_rate(expected, actual, characters=False)
            cer = error_rate(expected, actual, characters=True)
            language_ok = result.language == expected_language
            timings.append(elapsed)
            wers.append(wer)
            cers.append(cer)
            languages += int(language_ok)
            details.append(
                {
                    "audio": item["audio"],
                    "expected": expected,
                    "actual": actual,
                    "language": result.language,
                    "language_ok": language_ok,
                    "wer": wer,
                    "cer": cer,
                    "ms": elapsed,
                }
            )
            print(
                f"{index:03d} {'OK' if language_ok else 'LANG'} "
                f"{result.language or '?':5s} WER={wer:.1%} CER={cer:.1%} "
                f"{elapsed:.0f}ms  {audio.name}"
            )
    finally:
        router.close_extras()
        provider.close()

    print()
    print(f"Нийт: {len(rows)}")
    print(f"Хэл зөв: {languages / len(rows):.1%}")
    print(f"WER дундаж: {statistics.mean(wers):.1%}")
    print(f"CER дундаж: {statistics.mean(cers):.1%}")
    print(f"Latency p50/p95: {_percentile(timings, .50):.0f}/{_percentile(timings, .95):.0f} ms")

    if args.report:
        summary = {
            "manifest": str(manifest),
            "rows": len(rows),
            "accuracy_mode": bool(args.accuracy),
            "chooser": bool(args.choose),
            "language_accuracy": languages / len(rows),
            "wer": statistics.mean(wers),
            "cer": statistics.mean(cers),
            "p50_ms": _percentile(timings, 0.50),
            "p95_ms": _percentile(timings, 0.95),
            "per_row": details,
        }
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"Тайлан: {args.report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
