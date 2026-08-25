"""Хэрэглэгчийн өөрийн ярианаас сурдаг жижиг хэлний загвар (үгийн bigram).

Танигч нэг хэлсэн зүйлд хэд хэдэн хувилбар буцаадаг ба тэдгээр нь ихэвчлэн
нэг-хоёр үгээрээ л зөрдөг: «би ажил дээрээ» / «би ажил дээр ээ». Толь энэ
зөрүүг мэдэхгүй — хоёуланд нь толийн үг байхгүй тул оноо тэнцээд, үйлчилгээний
эрэмбэ хэвээр үлддэг. Гэтэл хэрэглэгч «ажил дээрээ» гэж өмнө нь зуун удаа
хэлсэн байдаг. Тэр мэдээлэл `history.jsonl`-д хэвтэж байхад ашиглагдахгүй байв.

Энэ модуль түүнийг ашиглана: батлагдсан текст бүрээс үгийн хос тоолж, хувилбар
бүрийг тэр тоололоор оноодог. Үүлэн ч, LLM ч, гуравдагч сан ч хэрэггүй —
цэвэр тоолол, найман хувилбарт ~1 мс.

Загвар диск дээр ТУСДАА хадгалагдахгүй: апп эхлэхдээ `history.jsonl`-оос
`Formatter.remember()`-ээр дамжуулан дахин баригдана. Ингэснээр хадгалах
формат, хувилбарын зөрүү, хуучирсныг цэвэрлэх гэсэн гурван асуудал огт
үүсэхгүй — үнэний эх сурвалж нэг л газар үлдэнэ.

Болгоомжлол: энэ загвар нь ЗӨВХӨН эрэмбэ солино, текст өөрчлөхгүй. Хангалттай
өгөгдөл цугларах хүртэл (`ready`) огт дуугарахгүй — цөөн жишээн дээр сурсан
загвар нь танигчийн эрэмбээс дор байх магадлалтай.
"""

from __future__ import annotations

import math
import re

#: Үг таслах загвар. `\w` нь кирилл, латин, цифрийг хамарна; цэг таслал,
#: хашилт унана — танигчийн хувилбарууд цэг таслалаараа ялгаатай байх нь бий,
#: тэр зөрүү нь утгын биш форматын асуудал тул онооны гадна үлдэх ёстой.
WORD = re.compile(r"\w+", re.UNICODE)

#: Өгүүлбэрийн эхлэлийг тэмдэглэх хиймэл үг. Ингэснээр эхний үг ч хосын
#: нөхцөлтэй болно — «Баярлалаа» гэж өгүүлбэр эхлүүлдэг хүнд энэ нь мэдэгдэнэ.
#: `WORD` нь тусгай тэмдэгт олдоггүй тул жинхэнэ үгтэй хэзээ ч давхцахгүй.
START = "\x02"

#: Интерполяцийн жин: хос → ганц үг → шал. Нийлбэр нь 1.0.
#: Шал нь тэгээс ЗААВАЛ их байх ёстой — эс бөгөөс огт сонсоогүй үг гарахад
#: `log(0)` болж, тэр хувилбар бүхэлдээ хасагдана.
BIGRAM_WEIGHT = 0.60
UNIGRAM_WEIGHT = 0.35
FLOOR_WEIGHT = 0.05

#: Үүнээс цөөн үг сурсан бол загвар дуугарахгүй. ~25–30 өгүүлбэр.
MIN_TOKENS = 200

#: Санах ойн дээд хязгаар. Хэтэрвэл нэг л удаа тохиолдсон хосуудыг хаяна —
#: тэдгээр нь ямар ч байсан магадлалын хувьд шалнаас ялгарахгүй.
MAX_BIGRAMS = 200_000


def tokenize(text: str) -> list[str]:
    """Текстийг харьцуулж болохуйц үгсэд хуваана (жижиг үсгээр, цэг таслалгүй)."""
    return WORD.findall(str(text).lower())


class BigramModel:
    """Батлагдсан текстээс сурч, хувилбарыг оноодог тоолол.

    Нэг thread дээр (`Formatter`-ийн эзэн) л ажиллана гэж үзсэн — түгжээгүй.
    """

    def __init__(self, minimum_tokens: int = MIN_TOKENS) -> None:
        self.minimum_tokens = minimum_tokens
        self.clear()

    def clear(self) -> None:
        self._unigrams: dict[str, int] = {}
        self._bigrams: dict[tuple[str, str], int] = {}
        # Нөхцөл болсон үгийн нийт тоо. Ганц үгийн тооллоос ТУСДАА хэрэгтэй:
        # `START` нь `_unigrams`-д ордоггүй, мөн өгүүлбэрийн сүүлийн үг нь
        # нөхцөл болж хэзээ ч гарахгүй.
        self._contexts: dict[str, int] = {}
        self._tokens = 0

    # ------------------------------------------------------------------
    @property
    def ready(self) -> bool:
        """Эрэмбэ солихыг зөвшөөрөхүйц хангалттай өгөгдөл цугласан эсэх."""
        return self._tokens >= self.minimum_tokens

    @property
    def tokens(self) -> int:
        return self._tokens

    def learn(self, text: str) -> None:
        """Нэг батлагдсан өгүүлбэрийг тоололд нэмнэ."""
        words = tokenize(text)
        if not words:
            return
        previous = START
        for word in words:
            self._unigrams[word] = self._unigrams.get(word, 0) + 1
            pair = (previous, word)
            self._bigrams[pair] = self._bigrams.get(pair, 0) + 1
            self._contexts[previous] = self._contexts.get(previous, 0) + 1
            previous = word
        self._tokens += len(words)
        if len(self._bigrams) > MAX_BIGRAMS:
            self._prune()

    def _prune(self) -> None:
        """Нэг удаа тохиолдсон хосуудыг хаяна (магадлалд нөлөөгүй, санах ойд их).

        `_contexts`-ыг үлдсэн хосуудаас дахин бодно — эс бөгөөс нөхцөлийн
        нийлбэр нь тоологдож үлдсэн хосуудынхаас их болж, магадлал нь
        системтэйгээр дутуу гарна.
        """
        self._bigrams = {pair: n for pair, n in self._bigrams.items() if n > 1}
        contexts: dict[str, int] = {}
        for (previous, _), count in self._bigrams.items():
            contexts[previous] = contexts.get(previous, 0) + count
        self._contexts = contexts

    # ------------------------------------------------------------------
    def _probability(self, previous: str, word: str) -> float:
        """Интерполяцилсан магадлал. ҮРГЭЛЖ тэгээс их (шалтай тул)."""
        floor = 1.0 / (len(self._unigrams) + 1)
        bigram = 0.0
        context = self._contexts.get(previous, 0)
        if context:
            bigram = self._bigrams.get((previous, word), 0) / context
        unigram = self._unigrams.get(word, 0) / self._tokens if self._tokens else 0.0
        return BIGRAM_WEIGHT * bigram + UNIGRAM_WEIGHT * unigram + FLOOR_WEIGHT * floor

    def score(self, text: str) -> float:
        """Дундаж лог-магадлал (үг тутамд). Их нь дээр, үргэлж сөрөг тоо.

        Үгийн тоонд хуваах нь ЗААВАЛ: эс бөгөөс богино хувилбар нь зүгээр л
        цөөн сөрөг гишүүн нэмснийхээ хүчээр үргэлж ялж, танигч сүүлийн үгийг
        нь гээсэн хувилбарыг сонгодог болно.
        """
        words = tokenize(text)
        if not words:
            return 0.0
        total = 0.0
        previous = START
        for word in words:
            total += math.log(self._probability(previous, word))
            previous = word
        return total / len(words)
