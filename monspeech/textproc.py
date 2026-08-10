"""Таньсан текстийг цэгцлэх: дуут цэг таслал, том үсэг, үг солих.

Google-ийн таних үйлчилгээ монгол хэл дээр цэг таслал тавьдаггүй тул
хэрэглэгч "цэг", "таслал", "шинэ мөр" гэж дуудаж оруулна.
"""

from __future__ import annotations

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
    ) -> None:
        self.auto_space = auto_space
        self.auto_capitalize = auto_capitalize
        self.voice_punctuation = voice_punctuation
        self._set_replacements(replacements)
        self.set_snippets(snippets)
        self.reset()

    def _set_replacements(self, replacements: dict[str, str] | None) -> None:
        self.replacements = {k.strip().lower(): v for k, v in (replacements or {}).items()}
        self._max_replacement_words = max(
            (len(key.split()) for key in self.replacements), default=1
        )

    def set_snippets(self, snippets: dict[str, str] | None) -> None:
        """Дуут товчлол: хэлсэн хэллэгийг урт бэлэн текстээр солино."""
        self.snippets = {k.strip().lower(): v for k, v in (snippets or {}).items()}
        self._max_snippet_words = max((len(key.split()) for key in self.snippets), default=1)

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
