"""Таньсан текстийг цэгцлэх.

Дөрвөн ажил энд байна:

* **Дуут цэг таслал, том үсэг, үг солих** (`Formatter`) — Google-ийн таних
  үйлчилгээ монгол хэл дээр цэг таслал тавьдаггүй тул хэрэглэгч "цэг",
  "таслал", "шинэ мөр" гэж дуудаж оруулна.
* **Ярианы чигчлүүр цэвэрлэх** (`clean_speech`) — «за ааа маргааш уулзъя»
  гэдгийг дүрмээр цэгцэлнэ. LLM хэрэггүй, офлайн, 0 мс.
* **Хувилбар сонгох** (`choose_alternative`, `Formatter.choose`) — үйлчилгээний
  буцаасан хэд хэдэн хувилбараас хэрэглэгчийн үгсийн санд нийцэхийг сонгоно.
* **Засвараас суралцах** (`learn_corrections`) — хэрэглэгчийн гараар зассан
  зөрүүг толины дүрэм болгоно.
"""

from __future__ import annotations

import re
from collections import deque
from collections.abc import Iterable

#: `Formatter` хэдэн батлагдсан өгүүлбэрийг санаж хувилбар сонгоход ашиглах вэ.
#: Богино зориуд: хэт урт бол хуучин сэдвийн үг өнөөдрийнхийг дийлж эхэлнэ.
HISTORY_MEMORY = 40

# Олон үгтэй командыг эхэнд нь тавих шаардлагагүй — уртаас нь эхлэн тааруулна.
VOICE_COMMANDS: dict[str, str] = {
    # монгол
    "цэг": ".",
    "таслал": ",",
    "цэг таслал": ";",
    "хоёр цэг": ":",
    "асуултын тэмдэг": "?",
    "анхаарлын тэмдэг": "!",
    "гурван цэг": "…",
    "зураас": "-",
    "хаалт нээх": "(",
    "хаалт хаах": ")",
    "хашилт": '"',
    "шинэ мөр": "\n",
    "мөр таслах": "\n",
    "шинэ догол": "\n\n",
    "шинэ догол мөр": "\n\n",
    # англи
    "period": ".",
    "full stop": ".",
    "comma": ",",
    "semicolon": ";",
    "colon": ":",
    "question mark": "?",
    "exclamation mark": "!",
    "ellipsis": "…",
    "dash": "-",
    "open paren": "(",
    "close paren": ")",
    "quote": '"',
    "new line": "\n",
    "newline": "\n",
    "new paragraph": "\n\n",
}

MAX_COMMAND_WORDS = max(len(k.split()) for k in VOICE_COMMANDS)

# Дуут үйлдлүүд. Аюулгүйн үүднээс зөвхөн хэлсэн зүйл нь ЗӨВХӨН энэ үг байвал
# ажиллана — "энэ файлыг устга" гэж бичүүлэхэд текст устахгүй байх ёстой.
VOICE_ACTIONS = {
    "буцаа": "undo",
    "устга": "undo",
    "болих": "undo",
    "буцаах": "undo",
    "undo": "undo",
    "scratch that": "undo",
}


def match_action(raw: str) -> str | None:
    """Хэлсэн зүйл бүхэлдээ дуут үйлдэл мөн эсэх."""
    phrase = " ".join(word.strip(_STRIP).lower() for word in raw.split() if word.strip(_STRIP))
    return VOICE_ACTIONS.get(phrase)

SENTENCE_ENDERS = ".!?…\n"
# Өмнөх зайг иддэг тэмдэгтүүд (үгэнд наалдана)
TIGHT_LEFT = ".,;:!?…)\n"
# Дараа нь зай тавихгүй тэмдэгтүүд (дараагийн үгэнд наалдана)
TIGHT_RIGHT = "(\"\n"

_STRIP = " \t.,;:!?…\"'()[]«»„“”"


# ----------------------------------------------------------------------
# Ярианы чигчлүүр цэвэрлэх
#
# Ярьж байгаа хүн бичиж байгаа хүн шиг ярьдаггүй: «за ааа маргааш уулзъя»
# гэдэг. Үүнийг LLM-гүйгээр, дүрмээр нь цэвэрлэнэ — саатал 0 мс, офлайн.
#
# Гол зарчим: ЭРГЭЛЗВЭЛ ХӨНДӨХГҮЙ. Буруу хассан үгийг хэрэглэгч анзаарахгүй
# өнгөрч болзошгүй тул жагсаалт бүрийг зориуд нарийсгасан.
# ----------------------------------------------------------------------

# Ухралт зогсоох бичигдсэн цэг таслал (`_is_boundary` хардаг).
_SENTENCE_END = (".", ",", ";", ":", "!", "?", "…")
_SPACE = " \t\"')]»“”"

# Утгагүй чимээ — аль ч байрлалаас хасна.
# «ээ», «уу», «үү» ЗОРИУД БАЙХГҮЙ: эдгээр нь монгол хэлний жинхэнэ бөөм
# («тийм ээ», «байна уу», «мөн үү») тул хасвал өгүүлбэр эвдэрнэ.
#
# «аа», «өө» нь хоёр нүүртэй: өгүүлбэрийн эхэнд бол чимээ («аа тэгэхээр…»),
# үгийн АРААС бол эгшиг зохицлын бөөм («явъя аа», «өгье өө») — «ээ»-гийн
# хосууд. Ялгаа нь уртад: яг хоёр үсэг бол бөөм байж болно, гурав ба түүнээс
# дээш («ааа») бол сунгасан чимээ тул хаана ч байсан хасна.
_NOISE = re.compile(
    r"^(?:а{3,}|ө{3,}|э{3,}|м{2,}|и{2,}|u+m+|u+h+|e+r+m*|h+m+|a+h+)$"
)

# Эхэнд байвал чимээ, үгийн араас байвал бөөм.
_TRAILING_PARTICLE = re.compile(r"^(?:аа|өө)$")

# Зөвхөн ЭХЭНД байвал хасах чигчлүүр. Өгүүлбэр дундаас хасахгүй — «тэгээд»,
# «тэр» зэрэг нь дунд байхдаа утгатай байдаг.
LEADING_FILLERS: tuple[tuple[str, ...], ...] = (
    ("за", "тэгээд"),
    ("за", "яахав"),
    ("юу", "гэх", "вэ"),
    ("яахав",),
    ("за",),
)

# «Ингэж хэлье гэсэн юм... үгүй ээ, ингэж» гэдгийг таних тэмдэг. Ганц үгээр
# биш, ХОЁР ҮГЭЭР таана: дан «үгүй», «биш» нь өдөр тутмын үг тул тэднийг
# тэмдэг гэж үзвэл жинхэнэ өгүүлбэрийг таслах эрсдэлтэй.
CORRECTION_MARKERS: tuple[tuple[str, ...], ...] = (
    ("үгүй", "ээ"),
    ("биш", "ээ"),
    ("i", "mean"),
)

# Давталт хураахаас хамгаалах үгс — эдгээрийг давтах нь чангатгах утгатай.
EMPHASIS = frozenset({"маш", "их", "дэндүү", "асар", "нэн", "very", "really"})

# Эш татах үгс. «"За" гэж хэлээд явлаа» гэвэл «за» нь чигчлүүр биш, иш татсан
# үг — араас нь эдгээрийн аль нэг ирвэл хасахгүй.
QUOTE_MARKERS = frozenset({"гэж", "гээд", "гэсэн", "гэнэ", "гэдэг", "гэх", "гэвэл"})


def _core(word: str) -> str:
    return word.strip(_STRIP).lower()


def _starts_with(words: list[str], phrase: tuple[str, ...], index: int = 0) -> bool:
    if index + len(phrase) > len(words):
        return False
    return all(_core(words[index + i]) == part for i, part in enumerate(phrase))


def _drop_noise(words: list[str]) -> list[str]:
    out: list[str] = []
    for word in words:
        core = _core(word)
        if _NOISE.match(core):
            continue
        # «аа», «өө» нь өмнөө үг байвал бөөм тул үлдээнэ; өгүүлбэрийн эхэнд
        # эсвэл өмнөх нь өөрөө хилийн цэг таслал байвал чимээ гэж үзнэ.
        if _TRAILING_PARTICLE.match(core) and (not out or _is_boundary(out[-1])):
            continue
        out.append(word)
    return out


def _drop_leading(words: list[str]) -> list[str]:
    """Эхний чигчлүүрүүдийг дараалан хасна («за яахав тэгэхээр…»)."""
    changed = True
    while changed and words:
        changed = False
        for phrase in LEADING_FILLERS:
            if len(words) <= len(phrase) or not _starts_with(words, phrase):
                continue
            if _core(words[len(phrase)]) in QUOTE_MARKERS:
                continue  # иш татсан үг — чигчлүүр биш
            words = words[len(phrase) :]
            changed = True
            break
    return words


def _is_boundary(word: str) -> bool:
    """Ухралт энд зогсох ёстой юу.

    Хоёр хэлбэрийн цэг таслал байна: ХЭЛСЭН нь («цэг» гэж дуудсан, `VOICE_COMMANDS`)
    ба БИЧИГДСЭН нь («болно.» гэж танигчаас ирсэн). Танигч бүр эхнийхийг л
    буцаадаггүй — OpenAI бичиглэл, `en-US` хариу нь бэлэн цэг таслалтай ирдэг —
    тул хоёуланг нь хилээр тооцно.
    """
    if _core(word) in VOICE_COMMANDS:
        return True
    return word.rstrip(_SPACE).endswith(_SENTENCE_END)


def _apply_corrections(words: list[str]) -> list[str]:
    """«5 цагт үгүй ээ 6 цагт» → «6 цагт».

    Тэмдэг олдвол өмнөх хэсгийг хаяна — гэхдээ бүхлээр нь биш, зөвхөн хамгийн
    сүүлийн цэг таслалын дараах хэсгийг. Ингэснээр өмнөх бүтэн өгүүлбэр
    санамсаргүй устахгүй.
    """
    index = 0
    while index < len(words):
        marker = next(
            (m for m in CORRECTION_MARKERS if _starts_with(words, m, index)), None
        )
        if marker is None:
            index += 1
            continue
        boundary = -1
        for back in range(index - 1, -1, -1):
            if _is_boundary(words[back]):
                boundary = back
                break
        words = words[: boundary + 1] + words[index + len(marker) :]
        index = boundary + 1
    return words


def _collapse_repeats(words: list[str]) -> list[str]:
    """«би би би явлаа» → «би явлаа». Чангатгах давталтыг хөндөхгүй.

    Давтагдсанаас СҮҮЛЧИЙНХИЙГ нь үлдээнэ: цэг таслал сүүлийн үгэнд наалддаг
    тул эхнийхийг үлдээвэл «тийм тийм.» → «тийм» болж цэг нь алга болно.
    """
    out: list[str] = []
    for word in words:
        core = _core(word)
        if out and core and core == _core(out[-1]) and core not in EMPHASIS:
            out[-1] = word
            continue
        out.append(word)
    return out


#: Кирилл үсгийн хүрээ (монгол өргөтгөлүүд болох ө, ү багтана).
_CYRILLIC = re.compile(r"[Ѐ-ӿ]")
#: Латин үсэг.
_LATIN = re.compile(r"[A-Za-z]")


def looks_foreign(text: str) -> bool:
    """Монголоор таньсан гэж хэлж буй текст үнэндээ кирилл биш байна уу.

    Танигч `mn-MN`-ээр асуухад англи яриаг сонсвол латинаар бичсэн үр дүн
    буцаадаг. Тоо, цэг таслал ганцаараа шийдэхгүй тул ҮСЭГ л тоологдоно:
    үсэг огт байхгүй бол «мэдэхгүй» гэж үзээд худал буцаана (эргэлзвэл
    хөндөхгүй).
    """
    cyrillic = len(_CYRILLIC.findall(text))
    latin = len(_LATIN.findall(text))
    if not latin:
        return False
    return latin > cyrillic


# ----------------------------------------------------------------------
# Тооны үгийг цифр болгох
#
# Google `mn-MN` нь тоог бараг үргэлж ҮГЭЭР буцаадаг: «хорин гурван цагт»,
# «хоёр мянга хорин зургаан он». Бичихэд эдгээр нь цифр байх ёстой. Монгол
# тоо нэрийн бүтэц бол энгийн нэмэх/үржих дүрэм тул LLM хэрэггүй — 0 мс,
# офлайн, `clean_speech`-тэй ижил гүн ухаан.
# ----------------------------------------------------------------------

#: Үндсэн ба тодотгол хэлбэр хоёуланг нь: «гурав», «гурван» хоёулаа 3.
NUMBER_WORDS: dict[str, int] = {
    "нэг": 1, "нэгэн": 1,
    "хоёр": 2,
    "гурав": 3, "гурван": 3,
    "дөрөв": 4, "дөрвөн": 4,
    "тав": 5, "таван": 5,
    "зургаа": 6, "зургаан": 6,
    "долоо": 7, "долоон": 7,
    "найм": 8, "найман": 8,
    "ес": 9, "есөн": 9,
    "арав": 10, "арван": 10,
    "хорь": 20, "хорин": 20,
    "гуч": 30, "гучин": 30,
    "дөч": 40, "дөчин": 40,
    "тавь": 50, "тавин": 50,
    "жар": 60, "жаран": 60,
    "дал": 70, "далан": 70,
    "ная": 80, "наян": 80,
    "ер": 90, "ерэн": 90,
    "зуу": 100, "зуун": 100,
    "мянга": 1000, "мянган": 1000,
    "сая": 1_000_000,
    "тэрбум": 1_000_000_000,
}

#: ГАНЦААРАА зогсоход тооноос өөр, өдөр тутмын утга давамгайлдаг үгс.
#: Хоёр ба түүнээс дээш тооны үг дараалбал тоо гэдэг нь эргэлзээгүй тул
#: тэнд хөрвүүлнэ («хорин нэг» → 21), ганцаараа бол хэвээр үлдээнэ:
#:
#: * «нэг», «нэгэн» — тодорхойгүй өгүүлэгч («нэг л удаа», «нэг тийм»)
#: * «ер» — «ер нь»
#: * «сая» — «сая хэлсэн» (дөнгөж сая)
#: * «тав» — «тав тухтай»
#: * «зуун» — «хорин нэгдүгээр зуун» (зуун жил)
#: * «дал», «ная» — тоо болж ганцаараа бараг хэрэглэгддэггүй
AMBIGUOUS_ALONE = frozenset({"нэг", "нэгэн", "ер", "сая", "тав", "зуун", "дал", "ная"})

#: Дэс тоон дагавар («нэгдүгээр», «хоёрдугаар»). Тооны цуваа ийм үгээр
#: үргэлжилж байвал энэ нь нэг бүхэл дэс тоо: «хорин нэгдүгээр зуун» гэдгийн
#: «хорин» нь 20 биш, 21-ийн эхний хагас. Бүтнээр нь хөрвүүлж чадахгүй тул
#: хагасыг нь эвдэхээс татгалзаж, хэвээр үлдээнэ.
_ORDINAL_TAIL = re.compile(r"(?:дугаар|дүгээр)$")


def _compose(values: list[int]) -> int | None:
    """Тооны үгсийн утгыг нэг тоо болгоно. Бүтэц нь тоо биш бол `None`.

    Зуу, мянга, сая нь ҮРЖИГДЭХҮҮН, бусад нь нэмэгдэхүүн:
    «мянга есөн зуун ерэн зургаа» → 1000 + 9×100 + 90 + 6 = 1996.

    Бүтцийг ЗААВАЛ шалгана: жинхэнэ тоонд нэмэгдэхүүн бүр өмнөхөөсөө ЖИЖИГ
    байдаг. «нэг хоёр» гэдэг нь 3 биш — тоолж байгаа хүн, эсвэл дугаар
    уншиж байгаа хүн. Шалгалтгүй бол ийм яриа бүхэлдээ гуйвна.
    """
    total = 0
    current = 0
    last_added: int | None = None
    for value in values:
        if value >= 1000:
            total += max(current, 1) * value
            current = 0
            last_added = None
        elif value == 100:
            if current > 9:
                return None  # «хорин зуун» гэж байхгүй
            current = max(current, 1) * 100
            last_added = 100
        else:
            if last_added is not None and value >= last_added:
                return None
            current += value
            last_added = value
    return total + current


def spell_numbers(raw: str) -> str:
    """«хорин гурван цагт» → «23 цагт».

    ЭРГЭЛЗВЭЛ ХӨНДӨХГҮЙ: ганц үгээс тогтсон бөгөөд тэр нь `AMBIGUOUS_ALONE`-д
    байвал хэвээр үлдээнэ. Тооны үгэнд наалдсан цэг таслалыг цифрт шилжүүлнэ.
    Нөхцөл залгасан хэлбэр («гуравт», «хоёрын») толинд байхгүй тул хөндөгдөхгүй.
    """
    words = raw.split()
    out: list[str] = []
    index = 0
    while index < len(words):
        start = index
        run: list[int] = []
        while index < len(words):
            value = NUMBER_WORDS.get(_core(words[index]))
            if value is None:
                break
            run.append(value)
            index += 1
        if not run:
            out.append(words[index])
            index += 1
            continue
        if len(run) == 1 and _core(words[start]) in AMBIGUOUS_ALONE:
            out.append(words[start])
            continue
        if index < len(words) and _ORDINAL_TAIL.search(_core(words[index])):
            out.extend(words[start:index])  # дэс тооны хагасыг эвдэхгүй
            continue
        value = _compose(run)
        if value is None:
            out.extend(words[start:index])  # тооны бүтэц биш — хэвээр
            continue
        head, tail = words[start], words[index - 1]
        prefix = head[: len(head) - len(head.lstrip(_STRIP))]
        suffix = tail[len(tail.rstrip(_STRIP)) :]
        out.append(f"{prefix}{value}{suffix}")
    return " ".join(out)


def clean_speech(raw: str) -> str:
    """Ярианы чигчлүүрийг хасаж, бичихэд тохирох хэлбэрт оруулна.

    Дөрвөн алхам: утгагүй чимээ → эхний чигчлүүр → өөрийгөө засах → давталт.
    Юу ч үлдэхгүй бол хоосон буцаана (дуудагч нь «зөвхөн чигчлүүр сонсогдлоо»
    гэж мэдэгдэнэ) — санамсаргүй чимээг текст болгож оруулахгүй.
    """
    words = raw.split()
    if not words:
        return ""
    words = _collapse_repeats(_apply_corrections(_drop_leading(_drop_noise(words))))
    return " ".join(words)


# ----------------------------------------------------------------------
# Хүний нэрийг ойролцоогоор таних
#
# Танигч нэрийг тогтмол нэг янзаар буруу сонсдоггүй: «Чимэгсайхан» нь нэг
# удаа «чимэг сайхан», нөгөө удаа «чимээ сайхан», бас «чимэгсайхны» гэж
# ирнэ. Толь нь ЯГ ТАГ таарсныг л сольдог тул хувилбар бүрд мөр нэмэх
# шаардлагатай болдог — эцэс төгсгөлгүй. Иймд нэрсийг тусад нь, ойролцоо
# зайгаар нь тааруулна.
# ----------------------------------------------------------------------

#: Ойролцоо тааруулгад оруулах хамгийн богино нэр. «Болд» гэх богино нэр нь
#: өдөр тутмын үгээс ганц үсгээр зөрдөг («болно», «болж») тул түүнийг зөвхөн
#: ЯГ ТАГ таарвал солино — эс бөгөөс хэвийн яриа нэр болж эхэлнэ.
FUZZY_MIN_LENGTH = 6
#: Нэрийн араас үлдэж болох нөхцөлийн дээд урт («-тай», «-ыгаа»).
MAX_NAME_SUFFIX = 5
#: Нэр хэдэн үг болж сонсогдож болох вэ («чимэг сайхан» = 2).
MAX_NAME_WORDS = 2
#: Хувилбар сонголтод нэр өгөх оноо — хэрэглэгч өөрөө бичсэн тул тольтой тэнцүү.
NAME_SCORE = 3


def _name_key(text: str) -> str:
    """Нэрийг харьцуулах хэлбэрт: жижиг үсэг, тэмдэггүй, зайгүй."""
    return "".join(w.strip(_STRIP).lower() for w in text.split() if w.strip(_STRIP))


def _prefix_distance(pattern: str, text: str) -> tuple[int, int]:
    """`pattern`-ийг `text`-ийн ЭХЛЭЛД тааруулах хамгийн бага засварын зай.

    `(зай, таарсан урт)` буцаана — үлдсэн хэсэг нь нөхцөлийн дагавар болно.
    Ердийн Левенштейн нь бүтэн үгтэй жишдэг тул «Чимэгсайхантай» гэсэн
    нөхцөлтэй хэлбэрийг хол гэж үзээд алддаг. Энэ хувилбар нь дагаварыг
    торгодоггүй: аль ч байрлалд төгсөж болно.
    """
    previous = list(range(len(text) + 1))
    for i, pattern_char in enumerate(pattern, start=1):
        current = [i]
        for j, text_char in enumerate(text, start=1):
            current.append(
                min(
                    previous[j] + 1,  # текстийн үсгийг алгасах
                    current[j - 1] + 1,  # нэрийн үсгийг алгасах
                    previous[j - 1] + (pattern_char != text_char),
                )
            )
        previous = current
    # Хамгийн бага зай; тэнцвэл УРТ таарсныг сонгоно (дагавар нь богино байх
    # тусам «нэр байх магадлал» өндөр).
    best = min(range(len(previous)), key=lambda j: (previous[j], -j))
    return previous[best], best


class Formatter:
    """Дараалан ирэх өгүүлбэрүүдийг залгаж, зөв хэлбэрт оруулна.

    `format()` нь (буулгах текст, устгах тэмдэгтийн тоо) хосыг буцаана.
    Устгах тоо нь өмнө нь тавьсан зайг цэг таслалын өмнөөс авахад хэрэгтэй.
    """

    def __init__(
        self,
        auto_space: bool = True,
        auto_capitalize: bool = True,
        voice_punctuation: bool = True,
        replacements: dict[str, str] | None = None,
        snippets: dict[str, str] | None = None,
        names: dict[str, str] | None = None,
    ) -> None:
        self.auto_space = auto_space
        self.auto_capitalize = auto_capitalize
        self.voice_punctuation = voice_punctuation
        self._set_replacements(replacements)
        self.set_snippets(snippets)
        self.set_names(names)
        self._history: deque[str] = deque(maxlen=HISTORY_MEMORY)
        self.reset()

    def remember(self, text: str) -> None:
        """Батлагдсан текстийг санана — дараагийн хувилбар сонголтод жин болно."""
        text = text.strip()
        if text:
            self._history.append(text)

    def choose(self, alternatives: list[str]) -> str:
        """Таних хувилбаруудаас өөрийн үгсийн сан, түүхэнд хамгийн нийцэхийг сонгоно.

        Дуудагч толь, товчлол, түүхийг тус тусад нь мэдэх шаардлагагүй —
        бүгд энд байна.
        """
        return choose_alternative(
            alternatives, self.replacements, self.snippets, self._history, self.names
        )

    def _set_replacements(self, replacements: dict[str, str] | None) -> None:
        self.replacements = {k.strip().lower(): v for k, v in (replacements or {}).items()}
        self._max_replacement_words = max(
            (len(key.split()) for key in self.replacements), default=1
        )

    def set_snippets(self, snippets: dict[str, str] | None) -> None:
        """Дуут товчлол: хэлсэн хэллэгийг урт бэлэн текстээр солино."""
        self.snippets = {k.strip().lower(): v for k, v in (snippets or {}).items()}
        self._max_snippet_words = max((len(key.split()) for key in self.snippets), default=1)

    def set_names(self, names: dict[str, str] | None) -> None:
        """Хүний нэрс: `{Зөв нэр: "сонсогддог хувилбарууд"}`.

        Зөв нэр нь ойролцоо тааруулгын бай болно; хувилбарууд (таслалаар
        тусгаарласан, заавал биш) нь ЯГ ТАГ таарах нэмэлт түлхүүрүүд —
        ойролцоо тааруулга барьж чадахгүй хол зөрүүг хүн өөрөө зааж өгнө.
        """
        self.names = {k.strip(): v for k, v in (names or {}).items() if k.strip()}
        self._exact_names: dict[str, str] = {}
        self._fuzzy_names: list[tuple[str, str]] = []
        for correct, aliases in self.names.items():
            key = _name_key(correct)
            if not key:
                continue
            self._exact_names[key] = correct
            if len(key) >= FUZZY_MIN_LENGTH:
                self._fuzzy_names.append((key, correct))
            for alias in re.split(r"[,;]", aliases or ""):
                alias_key = _name_key(alias)
                if alias_key:
                    self._exact_names[alias_key] = correct

    def _match_name(self, words: list[str], index: int) -> tuple[str, int, str] | None:
        """Нэрийг таана: `(зөв бичлэг, идсэн үгийн тоо, нөхцөлийн дагавар)`.

        Урт цонхноос эхэлнэ: «чимэг сайхан» гэж хоёр үг болж сонсогдсоныг
        нэг нэр болгож нийлүүлэхийн тулд.
        """
        limit = min(MAX_NAME_WORDS, len(words) - index)
        for size in range(limit, 0, -1):
            window = [w.strip(_STRIP).lower() for w in words[index : index + size]]
            if not all(window):
                continue
            joined = "".join(window)
            exact = self._exact_names.get(joined)
            if exact:
                return exact, size, ""
            if len(joined) < FUZZY_MIN_LENGTH:
                continue
            for key, correct in self._fuzzy_names:
                distance, matched = _prefix_distance(key, joined)
                # Урт нэр илүү олон алдаа даана; богино нэр бараг даахгүй.
                if distance > max(1, len(key) // 5):
                    continue
                suffix = joined[matched:]
                if len(suffix) > MAX_NAME_SUFFIX:
                    continue  # нэр нь урт үгийн дотор таарчээ — нэр биш
                if size > 1 and suffix:
                    # Олон үгийг нийлүүлж байгаа тул үлдэгдэл гарах ёсгүй:
                    # «чимэгсайхан ирлээ» гэдгийн «ирлээ» нь нөхцөл биш,
                    # дараагийн үг. Богино цонхоор дахин оролдоно.
                    continue
                return correct, size, suffix
        return None

    def reset(self) -> None:
        """Шинэ өгүүлбэрийн эхнээс эхэлж байгаа мэт төлөвт оруулна."""
        self._sentence_start = True
        self._trailing_space = False

    def update(
        self,
        auto_space: bool,
        auto_capitalize: bool,
        voice_punctuation: bool,
        replacements: dict[str, str] | None = None,
        snippets: dict[str, str] | None = None,
    ) -> None:
        self.auto_space = auto_space
        self.auto_capitalize = auto_capitalize
        self.voice_punctuation = voice_punctuation
        if replacements is not None:
            self._set_replacements(replacements)
        if snippets is not None:
            self.set_snippets(snippets)

    # ------------------------------------------------------------------
    def _replace_word(self, word: str) -> str:
        """Хэрэглэгчийн толиор үг солих (тэмдэгтүүдийг нь хадгална)."""
        core = word.strip(_STRIP)
        if not core:
            return word
        new = self.replacements.get(core.lower())
        if new is None:
            return word
        head = word[: word.index(core)]
        tail = word[word.index(core) + len(core) :]
        return head + new + tail

    def _match_phrase(
        self, table: dict[str, str], max_words: int, words: list[str], index: int
    ) -> tuple[str, int] | None:
        """Хүснэгтээс хамгийн урт таарах хэллэгийг олно."""
        limit = min(max_words, len(words) - index)
        for size in range(limit, 0, -1):
            phrase = " ".join(w.strip(_STRIP).lower() for w in words[index : index + size])
            value = table.get(phrase)
            if value is not None:
                return value, size
        return None

    def _match_replacement(self, words: list[str], index: int) -> tuple[str, int] | None:
        """Дуут товчлол, дараа нь олон үгтэй орлуулгыг шалгана."""
        snippet = self._match_phrase(self.snippets, self._max_snippet_words, words, index)
        if snippet:
            return snippet
        if self._max_replacement_words < 2:
            return None
        limit = min(self._max_replacement_words, len(words) - index)
        for size in range(limit, 1, -1):
            phrase = " ".join(w.strip(_STRIP).lower() for w in words[index : index + size])
            value = self.replacements.get(phrase)
            if value is not None:
                return value, size
        return None

    def _match_command(self, words: list[str], index: int) -> tuple[str, int] | None:
        """index-ээс эхлэн хамгийн урт командыг тааруулна."""
        limit = min(MAX_COMMAND_WORDS, len(words) - index)
        for size in range(limit, 0, -1):
            phrase = " ".join(w.strip(_STRIP).lower() for w in words[index : index + size])
            punct = VOICE_COMMANDS.get(phrase)
            if punct is not None:
                return punct, size
        return None

    # ------------------------------------------------------------------
    def format(self, raw: str) -> tuple[str, int]:
        words = raw.split()
        if not words:
            return "", 0

        text = ""
        backspaces = 0
        index = 0

        def last() -> str:
            return text[-1] if text else ""

        while index < len(words):
            if self.voice_punctuation:
                match = self._match_command(words, index)
            else:
                match = None

            if match:
                punct, size = match
                index += size
                if punct in TIGHT_LEFT:
                    if last() == " ":
                        text = text[:-1]
                    elif not text and self._trailing_space:
                        # Өмнөх хэсэг зай үлдээсэн бол цэгийн өмнөөс нь устгана.
                        backspaces = 1
                        self._trailing_space = False
                elif text and last() not in TIGHT_RIGHT and last() != " ":
                    text += " "
                text += punct
                if punct in SENTENCE_ENDERS:
                    self._sentence_start = True
                continue

            # Нэр нь толиос ӨМНӨ: «чимэг сайхан» гэсэн хоёр үгийг нэг нэр
            # болгож нийлүүлэх нь тус тусад нь үг солихоос дээгүүр.
            named = self._match_name(words, index)
            if named:
                correct, size, ending = named
                tail_word = words[index + size - 1]
                index += size
                word = correct + ending + tail_word[len(tail_word.rstrip(_STRIP)) :]
            else:
                phrase = self._match_replacement(words, index)
                if phrase:
                    word, size = phrase
                    index += size
                else:
                    word = self._replace_word(words[index])
                    index += 1
            if text and last() not in TIGHT_RIGHT:
                text += " "
            if self.auto_capitalize and self._sentence_start:
                word = word[:1].upper() + word[1:]
            self._sentence_start = False
            text += word

        if not text:
            return "", backspaces

        if self.auto_space and not text.endswith("\n"):
            text += " "
            self._trailing_space = True
        else:
            self._trailing_space = False

        return text, backspaces


def parse_replacements(raw: str) -> dict[str, str]:
    """`буруу=зөв` мөр бүрээс толь үүсгэнэ."""
    result: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key:
            result[key] = value
    return result


def format_replacements(mapping: dict[str, str]) -> str:
    return "\n".join(f"{k}={v}" for k, v in sorted(mapping.items()))


# Хувилбар сонгоход өгөх оноо. Хэрэглэгч өөрөө бичсэн зүйл хамгийн жинтэй.
SNIPPET_SCORE = 3  # дуут товчлол — санаатай хэлдэг хэллэг
CORRECT_SCORE = 3  # толийн зөв тал — хэрэглэгчийн хүсдэг бичиглэл
HEARD_SCORE = 2  # толийн буруу тал — ямар ч байсан засагдана
# Түүхэнд өмнө нь батлагдсан үг. Хамгийн сул нотолгоо: хэрэглэгч зориуд
# бичээгүй, зүгээр л нэг удаа хэлсэн байж болно. Тиймээс толь, товчлолыг
# хэзээ ч дийлэхгүй — зөвхөн бусад нь тэнцэх үед л жинг хэлнэ.
HISTORY_SCORE = 1


def _vocabulary(
    replacements: dict[str, str],
    snippets: dict[str, str],
    history: Iterable[str] = (),
    names: dict[str, str] | None = None,
) -> tuple[dict[str, int], int]:
    """Хэрэглэгчийн үгсийн сан → `{хэллэг: оноо}` ба хамгийн урт хэллэгийн үгийн тоо."""
    table: dict[str, int] = {}

    def add(phrase: str, score: int) -> None:
        key = " ".join(w.strip(_STRIP).lower() for w in phrase.split() if w.strip(_STRIP))
        if key:
            table[key] = max(table.get(key, 0), score)

    # Түүх хамгийн сул нотолгоо тул хамгийн түрүүнд: толь, товчлол давхцвал
    # `max()`-аар тэдний өндөр оноо дийлнэ.
    for text in history:
        for word in text.split():
            add(word, HISTORY_SCORE)
    for phrase in snippets:
        add(phrase, SNIPPET_SCORE)
    for correct, aliases in (names or {}).items():
        add(correct, NAME_SCORE)
        for alias in re.split(r"[,;]", aliases or ""):
            add(alias, NAME_SCORE)
    for heard, correct in replacements.items():
        add(heard, HEARD_SCORE)
        add(correct, CORRECT_SCORE)
    return table, max((len(key.split()) for key in table), default=1)


def _vocabulary_score(text: str, table: dict[str, int], longest: int) -> int:
    """Текст хэрэглэгчийн үгсийн сантай хэр нийцэж байгааг оноогоор хэмжинэ."""
    words = text.split()
    total = 0
    index = 0
    while index < len(words):
        for size in range(min(longest, len(words) - index), 0, -1):
            phrase = " ".join(w.strip(_STRIP).lower() for w in words[index : index + size])
            score = table.get(phrase)
            if score is not None:
                total += score
                index += size
                break
        else:
            index += 1
    return total


def choose_alternative(
    alternatives: list[str],
    replacements: dict[str, str] | None = None,
    snippets: dict[str, str] | None = None,
    history: Iterable[str] = (),
    names: dict[str, str] | None = None,
) -> str:
    """Таних хувилбаруудаас хэрэглэгчийн үгсийн санд хамгийн сайн нийцэхийг сонгоно.

    Үйлчилгээ нэг хэлсэн зүйлд хэд хэдэн хувилбар буцаадаг ч өмнө нь зөвхөн
    эхнийхийг нь авдаг байсан — үлдсэн нь хариунд ирээд хаягддаг байв. Толиндоо
    «клауд=Claude» гэж нэмсэн хүн «Claude» гэж хэлэхэд эхний хувилбар нь «клоуд»
    гараад хоёр дахь нь «клауд» байх нь бий; тэр тохиолдолд хоёр дахийг нь
    сонгоно. Нэмэлт хүсэлт, нэмэлт саатал, нэмэлт төлбөр үүсэхгүй.

    Зөвхөн хэрэглэгчийн ӨӨРИЙН бичсэн үг (толь, дуут товчлол) болон түүхэнд
    өмнө нь батлагдсан үг оноо өгнө. Дуут командыг санаатай оруулаагүй: «цэг»
    гэж сонсогдсон бүхнийг дэвшүүлбэл жинхэнэ үгийг цэг болгож гээх эрсдэлтэй.
    Оноо тэнцвэл үйлчилгээний эрэмбэ хэвээр үлдэнэ — нотолгоогүй бол хөндөхгүй.
    """
    if not alternatives:
        return ""
    best = alternatives[0]
    if len(alternatives) < 2:
        return best
    table, longest = _vocabulary(replacements or {}, snippets or {}, history, names)
    if not table:
        return best
    best_score = _vocabulary_score(best, table, longest)
    for candidate in alternatives[1:]:
        score = _vocabulary_score(candidate, table, longest)
        if score > best_score:
            best, best_score = candidate, score
    return best


def learn_corrections(heard: str, corrected: str, limit: int = 6) -> dict[str, str]:
    """Буруу таньсан ба зассан хоёрыг жишиж, солих дүрэм гаргана.

    Хэрэглэгч түүхэн дэх мөрөө засахад ялгаатай үгсийг нь өөрөө сурна —
    гараар толь бөглөх шаардлагагүй болно. Урт нь зөрсөн, эсвэл хэт олон
    үг зөрсөн тохиолдолд юу ч сураагүй нь дээр (санамсаргүй дүрэм үүсгэхгүй).
    """
    heard_words = [w.strip(_STRIP) for w in heard.split() if w.strip(_STRIP)]
    fixed_words = [w.strip(_STRIP) for w in corrected.split() if w.strip(_STRIP)]
    if not heard_words or len(heard_words) != len(fixed_words):
        return {}

    learned: dict[str, str] = {}
    changes = 0
    for was, now in zip(heard_words, fixed_words):
        if was.lower() == now.lower():
            continue
        changes += 1
        if changes > limit:
            return {}
        learned[was.lower()] = now

    # Хэт олон үг зөрсөн бол энэ нь "засвар" биш, огт өөр өгүүлбэр.
    # (Зөрүүг тусад нь тоолно: ижил үг давтагдвал толь богиносоод хамгаалалт
    #  ажиллахгүй байсан. Богино өгүүлбэрт 2 үг засах нь хэвийн тул доод
    #  хязгаарыг 2 болгов.)
    if changes > max(2, (len(heard_words) + 1) // 2):
        return {}
    return learned
