"""Монгол–англи LanguageRouter-ийн цэвэр unit тест (сүлжээ хэрэггүй)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401

from monspeech.language_router import (
    LanguageRouter,
    infer_text_language,
    merge_code_switch,
    script_fit,
)
from monspeech.recognizer import ProviderCapabilities, RecognitionError, RecognitionResult

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


class FakeProvider:
    name = "fake"
    capabilities = ProviderCapabilities()

    def __init__(self, lang, answers, calls):
        self.lang = lang
        self.answers = answers
        self.calls = calls

    def recognize(self, _pcm, _rate, lang):
        self.calls.append(lang)
        answer = self.answers[lang]
        if isinstance(answer, Exception):
            raise answer
        return RecognitionResult(*answer, language=lang, provider=self.name)

    def prewarm_async(self):
        pass

    def close(self):
        pass


def router(answers, primary="mn-MN"):
    calls = []

    def make(lang):
        return FakeProvider(lang, answers, calls)

    return LanguageRouter(make(primary), make), calls


def recognize(item, hint="mn-MN", accuracy=False):
    return item.recognize(
        b"audio",
        16000,
        hint=hint,
        configured=["mn-MN", "en-US"],
        automatic=True,
        accuracy=accuracy,
        minimum_confidence=0.45,
    )


check("кириллээс монгол", infer_text_language("өнөөдөр хуралтай"), "mn-MN")
check("латинаас англи", infer_text_language("hello world"), "en-US")
check("хоёр бичиг холилдсон", infer_text_language("өнөөдөр meeting байна"), "mixed")
check("англи бичиг монголд нийцэхгүй", script_fit("hello", "mn-MN"), 0.0)

# Өндөр confidence буруу хэл гэдэг нь дахин шалгахгүй байх шалтгаан биш.
item, calls = router(
    {
        "mn-MN": (["hello world"], 0.98),
        "en-US": (["hello world"], 0.90),
    }
)
result = recognize(item)
check("өндөр confidence буруу бичгийг шалгасан", calls, ["mn-MN", "en-US"])
check("англи сонгосон", result.language, "en-US")

# Хоёр чиглэл ижил ажиллана: англи hint дээр кирилл гарвал монголоор шалгана.
item, calls = router(
    {
        "en-US": (["маргааш уулзъя"], 0.92),
        "mn-MN": (["маргааш уулзъя"], 0.88),
    },
    primary="en-US",
)
result = recognize(item, hint="en-US")
check("англиас монгол руу шалгасан", calls, ["en-US", "mn-MN"])
check("монгол сонгосон", result.language, "mn-MN")

# Accuracy үед эхний үр дүн тодорхой байсан ч хоёр хэл хоёулаа явна.
item, calls = router(
    {
        "mn-MN": (["сайн байна уу"], 0.95),
        "en-US": (["sign baina uu"], 0.80),
    }
)
result = recognize(item, accuracy=True)
check("accuracy хоёр хүсэлт", sorted(calls), ["en-US", "mn-MN"])
check("accuracy монгол", result.language, "mn-MN")

# Нөгөө хүсэлт унасан ч анхны transcript алдагдахгүй.
item, calls = router(
    {
        "mn-MN": (["hello"], 0.2),
        "en-US": RecognitionError("тасрав"),
    }
)
result = recognize(item)
check("fallback эхний текст", result.text, "hello")

# Native auto-language provider-д forced language дамжихгүй.
class AutoProvider(FakeProvider):
    capabilities = ProviderCapabilities(auto_language=True, confidence=False, code_switching=True)

    def recognize(self, _pcm, _rate, lang):
        self.calls.append(lang)
        return RecognitionResult(["hello world"], None, "en-US", self.name)


auto_calls = []
auto = LanguageRouter(AutoProvider("mn-MN", {}, auto_calls))
check("native auto үр дүн", recognize(auto).language, "en-US")
check("native auto sentinel", auto_calls, ["auto"])

check(
    "code-switch болгоомжтой нэгтгэл",
    merge_code_switch(
        "өнөөдөр стэнд meeting байна",
        "today standup meeting baina",
    ),
    "өнөөдөр standup meeting байна",
)
check("нотолгоогүй бол нэгтгэхгүй", merge_code_switch("сайн байна", "sign baina"), "")

print()
if fails:
    print("FAILED:")
    for line in fails:
        print(" ", line)
    raise SystemExit(1)
print("ALL PASS")
