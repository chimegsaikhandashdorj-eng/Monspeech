"""Хэрэглэгчийн түүхээс сурдаг bigram загвар ба хувилбар сонголтын шатлал."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401

from monspeech.langmodel import BigramModel, tokenize
from monspeech.textproc import Formatter, choose_alternative

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


# --- үг таслах ------------------------------------------------------
check("кирилл үгс", tokenize("Маргааш уулзъя."), ["маргааш", "уулзъя"])
check("цэг таслал унана", tokenize("тийм ээ, зөв!"), ["тийм", "ээ", "зөв"])
check("латин ба цифр", tokenize("Claude Code 5"), ["claude", "code", "5"])
check("хоосон", tokenize(""), [])

# --- сурах ба оноох -------------------------------------------------
model = BigramModel(minimum_tokens=4)
check("эхэндээ бэлэн биш", model.ready, False)
for _ in range(10):
    model.learn("би ажил дээрээ байна")
check("сурсны дараа бэлэн", model.ready, True)
check("үгийн тоо", model.tokens, 40)

seen = model.score("би ажил дээрээ байна")
unseen = model.score("би ажил дээр ээ байна")
check("сурсан дараалал өндөр оноотой", seen > unseen, True)
check("хоосон текст 0", model.score(""), 0.0)
check("огт сурaaгүй үг ч лог-0 болохгүй", model.score("зигзаг") < 0.0, True)

# Урт нь ганцаараа давуу тал болох ЁСГҮЙ — эс бөгөөс танигч үг гээсэн
# хувилбарыг үргэлж дэвшүүлнэ.
short = BigramModel(minimum_tokens=1)
for _ in range(10):
    short.learn("нэг хоёр гурав")
check(
    "уртаараа ялахгүй",
    short.score("нэг хоёр гурав") > short.score("нэг хоёр"),
    False,
)

# `clear` нь бүх тоололыг тэглэнэ
short.clear()
check("цэвэрлэсний дараа бэлэн биш", short.ready, False)
check("цэвэрлэсний дараа тоо 0", short.tokens, 0)

# --- нотолгооны шатлал ----------------------------------------------
trained = BigramModel(minimum_tokens=4)
for _ in range(10):
    trained.learn("хурал дээрээ уулзъя")

check(
    "загвар тэнцсэнийг ялгана",
    choose_alternative(
        ["хурал дээр ээ уулзъя", "хурал дээрээ уулзъя"], model=trained
    ),
    "хурал дээрээ уулзъя",
)
check(
    "толь загвараас дээгүүр",
    choose_alternative(
        ["хурал дээр ээ уулзъя", "хурал дээрээ уулзъя"],
        {"хурал дээр": "хурлын"},
        model=trained,
    ),
    "хурал дээр ээ уулзъя",
)
check(
    "сураагүй загвар эрэмбэ хөндөхгүй",
    choose_alternative(
        ["хурал дээр ээ уулзъя", "хурал дээрээ уулзъя"],
        model=BigramModel(minimum_tokens=10_000),
    ),
    "хурал дээр ээ уулзъя",
)
check(
    "загвар шийдээгүй бол түүх рүү унана",
    choose_alternative(
        ["надад хайрцаг өг", "надад харцаг өг"], history=["харцаг"], model=trained
    ),
    "надад харцаг өг",
)

# --- Formatter-ийн холболт ------------------------------------------
formatter = Formatter()
corpus = [
    "маргааш хурал дээрээ уулзъя",
    "би ажил дээрээ явлаа",
    "ширээн дээр ном байна",
    "энэ асуудал дээр ярилцъя",
    "тийм ээ зөв байна",
    "хурал дээрээ энэ тухай ярина",
]
# ~200 үг цуглах хүртэл давтана — загвар түүнээс өмнө дуугарахгүй
for _ in range(10):
    for line in corpus:
        formatter.remember(line)
check("Formatter загвараа тэжээнэ", formatter.model.ready, True)
check(
    "бодит түүхээр бичиглэл сонгоно",
    formatter.choose(["ажил дээр ээ явлаа", "ажил дээрээ явлаа"]),
    "ажил дээрээ явлаа",
)
check(
    "нотолгоогүй бол эрэмбэ хэвээр",
    formatter.choose(["огт мэдэхгүй үг нэг", "огт мэдэхгүй үг хоёр"]),
    "огт мэдэхгүй үг нэг",
)

# Сурaaгүй Formatter нь өмнөх зан төлөвөө хадгална (түүхийн нөөц зам)
cold = Formatter()
cold.remember("харцаг")
check(
    "хүйтэн эхлэлд түүх ажиллана",
    cold.choose(["надад хайрцаг өг", "надад харцаг өг"]),
    "надад харцаг өг",
)

print()
if fails:
    print("FAILED:")
    for line in fails:
        print(" ", line)
    raise SystemExit(1)
print("ALL PASS")
