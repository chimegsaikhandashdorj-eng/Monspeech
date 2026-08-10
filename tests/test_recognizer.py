"""Таних хариуг задлах логикийн тест (сүлжээ хэрэггүй).

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_recognizer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from monspeech.recognizer import Recognizer

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


parse = Recognizer._parse

check("хоосон хариу", parse('{"result":[]}\n'), ("", 0.0))
check(
    "энгийн хариу",
    parse('{"result":[]}\n'
          '{"result":[{"alternative":[{"transcript":"сайн байна уу","confidence":0.94}]}],'
          '"result_index":0}\n'),
    ("сайн байна уу", 0.94),
)
check(
    "хамгийн магадлалтай хувилбарыг авна",
    parse('{"result":[{"alternative":[{"transcript":"нэг","confidence":0.8},'
          '{"transcript":"хоёр"}]}]}'),
    ("нэг", 0.8),
)
check(
    "итгэлцэл өгөөгүй бол 1.0",
    parse('{"result":[{"alternative":[{"transcript":"утга"}]}]}'),
    ("утга", 1.0),
)
check(
    "хоосон transcript алгасна",
    parse('{"result":[{"alternative":[{"transcript":"   "}]}]}\n'
          '{"result":[{"alternative":[{"transcript":"утга","confidence":0.5}]}]}'),
    ("утга", 0.5),
)
check("эвдэрсэн JSON", parse("{нэг хоёр\n"), ("", 0.0))
check("огт хоосон", parse(""), ("", 0.0))

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
