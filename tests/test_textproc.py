"""Текст цэгцлэх логикийн тест.

Ажиллуулах:  .venv\\Scripts\\python.exe tests\\test_textproc.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import _console  # noqa: F401 - кирилл гаралтыг UTF-8 болгоно


from monspeech.textproc import (
    Formatter,
    edit_text,
    vocabulary_hint,
    label_actions,
    parse_actions,
    choose_alternative,
    clean_speech,
    format_replacements,
    learn_corrections,
    match_action,
    parse_replacements,
    spell_numbers,
)

fails = []


def check(label, got, want):
    ok = got == want
    if not ok:
        fails.append(f"{label}: got {got!r} want {want!r}")
    print(("ok  " if ok else "FAIL"), label, "->", repr(got))


f = Formatter()
check("энгийн", f.format("сайн байна уу"), ("Сайн байна уу ", 0))
# Тусдаа ирсэн "цэг" нь өмнөх хэсгийн үлдээсэн зайг устгана (backspace=1)
check("цэг тусдаа хэсэг", f.format("цэг"), (". ", 1))
check("шинэ өгүүлбэр том үсэг", f.format("өнөөдөр сайхан байна"), ("Өнөөдөр сайхан байна ", 0))
# Өмнөх хэсэг цэгээр төгсөөгүй тул үргэлжлэл гэж үзнэ
check(
    "нэг хэсэг дотор цэг",
    f.format("би ирлээ цэг чи хаана байна асуултын тэмдэг"),
    ("би ирлээ. Чи хаана байна? ", 0),
)
check("шинэ мөр", f.format("шинэ мөр дараагийн мөр"), ("\nДараагийн мөр ", 1))
f.reset()
check("таслал дунд", f.format("нэг таслал хоёр таслал гурав"), ("Нэг, хоёр, гурав ", 0))
f.reset()
check("хаалт", f.format("тэмдэглэл хаалт нээх чухал хаалт хаах"), ("Тэмдэглэл (чухал) ", 0))
f.reset()
check("англи команд", f.format("hello comma world period"), ("Hello, world. ", 0))
check("хоосон", f.format("   "), ("", 0))

f2 = Formatter(auto_space=False, auto_capitalize=False)
check("тохиргоо унтраасан", f2.format("сайн уу цэг"), ("сайн уу.", 0))

f3 = Formatter(voice_punctuation=False)
check("дуут цэг унтраалттай", f3.format("сайн уу цэг"), ("Сайн уу цэг ", 0))

f4 = Formatter(replacements={"клауд": "Claude", "хоёр": "2"})
check("үг солих", f4.format("клауд бол сайн хоёр"), ("Claude бол сайн 2 ", 0))
f4.reset()
check("үг солих тэмдэгттэй", f4.format("клауд, тийм"), ("Claude, тийм ", 0))

mapping = parse_replacements("клауд=Claude\n# сэтгэгдэл\n\nбуруу = зөв\nмуу\n")
check("толь задлах", mapping, {"клауд": "Claude", "буруу": "зөв"})
check("толь бичих", format_replacements(mapping), "буруу=зөв\nклауд=Claude")

# --- олон үгтэй хэллэг солих ---
f6 = Formatter(replacements={"сайн байна уу": "Сайн байцгаана уу", "клауд": "Claude"})
check(
    "хэллэг солих",
    f6.format("сайн байна уу клауд"),
    ("Сайн байцгаана уу Claude ", 0),
)
f6.reset()
check("хэллэг таарахгүй бол хэвээр", f6.format("сайн уу"), ("Сайн уу ", 0))

# --- дуут үйлдэл (зөвхөн дангаар нь хэлсэн үед) ---
# --- дуут товчлол ---
f7 = Formatter(snippets={"миний хаяг": "Улаанбаатар хот, 1-р хороо"})
check(
    "товчлол тэлнэ",
    f7.format("надад миний хаяг руу илгээ"),
    ("Надад Улаанбаатар хот, 1-р хороо руу илгээ ", 0),
)
f7.reset()
check("товчлолгүй үг хэвээр", f7.format("миний ном"), ("Миний ном ", 0))

# --- засвараас сурах ---
check("нэг үг сурна", learn_corrections("клауд код бичлээ", "Claude код бичлээ"),
      {"клауд": "Claude"})
check("урт зөрвөл сурахгүй", learn_corrections("нэг хоёр", "нэг хоёр гурав"), {})
check("хэт олон зөрвөл сурахгүй",
      learn_corrections("өөр өөр өөр өөр", "нэг хоёр гурав дөрөв"), {})
check("зөвхөн том үсэг бол сурахгүй",
      learn_corrections("сайн байна уу", "Сайн байна уу"), {})
check("хоёр үг сурна",
      learn_corrections("клауд болон монспич", "Claude болон Monspeech"),
      {"клауд": "Claude", "монспич": "Monspeech"})

# --- чигчлүүр цэвэрлэх ---
check("утгагүй чимээ", clean_speech("ааа маргааш уулзъя"), "маргааш уулзъя")
check("урт чимээ", clean_speech("аааааа тийм"), "тийм")
check("ммм", clean_speech("ммм за яахав тэгье"), "тэгье")
check("эхний за", clean_speech("за маргааш уулзъя"), "маргааш уулзъя")
check("за тэгээд", clean_speech("за тэгээд ажил эхэллээ"), "ажил эхэллээ")
check("юу гэх вэ", clean_speech("юу гэх вэ ойлгомжтой байна"), "ойлгомжтой байна")
check("дунд байх за хэвээр", clean_speech("тэгвэл за гэж хэлээрэй"), "тэгвэл за гэж хэлээрэй")
check("иш татсан за хэвээр", clean_speech("за гэж хэлээд явлаа"), "за гэж хэлээд явлаа")
check("иш татсан яахав хэвээр", clean_speech("яахав гэсэн бодол"), "яахав гэсэн бодол")
check("дунд байх тэгээд хэвээр", clean_speech("уулзаад тэгээд яръя"), "уулзаад тэгээд яръя")

# Жинхэнэ бөөмийг хэзээ ч хасахгүй
check("байна уу хэвээр", clean_speech("сайн байна уу"), "сайн байна уу")
check("мөн үү хэвээр", clean_speech("энэ мөн үү"), "энэ мөн үү")
check("тийм ээ хэвээр", clean_speech("тийм ээ зөв"), "тийм ээ зөв")

check("давхардсан үг", clean_speech("би би би явлаа"), "би явлаа")
check("чангатгах давталт хэвээр", clean_speech("маш маш сайн"), "маш маш сайн")
check("тэмдэгтэй давталт", clean_speech("тийм тийм."), "тийм.")

check("өөрийгөө засах", clean_speech("5 цагт үгүй ээ 6 цагт"), "6 цагт")
check("биш ээ", clean_speech("даваа гаригт биш ээ мягмар гаригт"), "мягмар гаригт")
check(
    "цэгийн өмнөх өгүүлбэр хэвээр",
    clean_speech("би явлаа цэг 5 цагт үгүй ээ 6 цагт"),
    "би явлаа цэг 6 цагт",
)
check("дан үгүй бол таслахгүй", clean_speech("тийм үү үгүй юу"), "тийм үү үгүй юу")
check("дан биш бол таслахгүй", clean_speech("энэ ном биш байна"), "энэ ном биш байна")

check("зөвхөн чигчлүүр бол хоосон", clean_speech("ааа ммм"), "")
check("зөвхөн за бол хэвээр", clean_speech("за"), "за")
check("хоосон оролт", clean_speech(""), "")
check("хэвийн өгүүлбэр хөндөгдөхгүй",
      clean_speech("маргааш 3 цагт хурал болно"), "маргааш 3 цагт хурал болно")

# --- тооны үгийг цифр болгох ---
check("хорин гурав", spell_numbers("хорин гурван цагт уулзъя"), "23 цагт уулзъя")
check("оны тоо", spell_numbers("хоёр мянга хорин зургаан он"), "2026 он")
check("мянга есөн зуун", spell_numbers("мянга есөн зуун ерэн зургаа"), "1996")
check("зуут хүрэх", spell_numbers("хоёр зуун тавин найм"), "258")
check("саяар", spell_numbers("зургаан сая таван зуун мянга"), "6500000")
check("тодотгол хэлбэр", spell_numbers("долоон хоног болно"), "7 хоног болно")
check("хоёр орон", spell_numbers("арван хоёр"), "12")
check("цэг наалдана", spell_numbers("хорин гурав."), "23.")
check("хоёр тоо тусдаа", spell_numbers("дөрвөн цаг гучин минут"), "4 цаг 30 минут")

# ЭРГЭЛЗВЭЛ ХӨНДӨХГҮЙ — ганцаараа өдөр тутмын утгатай үгс
check("ер нь хэвээр", spell_numbers("ер нь тэгье"), "ер нь тэгье")
check("сая (дөнгөж) хэвээр", spell_numbers("сая хэлсэн шүү"), "сая хэлсэн шүү")
check("нэг л хэвээр", spell_numbers("нэг л удаа"), "нэг л удаа")
check("тав тухтай хэвээр", spell_numbers("тав тухтай"), "тав тухтай")
# Дэс тоо: «хорин нэгдүгээр» бол 20 биш, 21-ийн хагас — эвдэхээс татгалзана
check("дэс тоог эвдэхгүй", spell_numbers("хорин нэгдүгээр зуун"), "хорин нэгдүгээр зуун")
# Цуваанд орвол эргэлзээгүй тул хөрвүүлнэ
check("цуваанд нэг ч хөрвөнө", spell_numbers("хорин нэг"), "21")
# Тооны БҮТЭЦ биш бол хөндөхгүй: нэмэгдэхүүн бүр өмнөхөөсөө жижиг байх ёстой
check("тоолж байгааг нийлүүлэхгүй", spell_numbers("нэг хоёр гурав"), "нэг хоёр гурав")
check("зуун өмнөх нь нэгж байна", spell_numbers("хорин зуун"), "хорин зуун")
check("гацсан давталт", spell_numbers("хорин хорин"), "хорин хорин")
check("тооны үггүй өгүүлбэр", spell_numbers("би маргааш ирнэ"), "би маргааш ирнэ")

# Тооны үгээр ЭХЭЛДЭГ дуут командыг идэж болохгүй: «гурван цэг» → «…»,
# «хоёр цэг» → «:». Идвэл «3» + «цэг» болж, эцэст нь «3.» гэж бичигдэнэ.
check("гурван цэг команд хэвээр", spell_numbers("гурван цэг"), "гурван цэг")
check("хоёр цэг команд хэвээр", spell_numbers("хоёр цэг"), "хоёр цэг")
check("команд дунд байсан ч", spell_numbers("тийм гурван цэг за"), "тийм гурван цэг за")
check("команд биш бол хөрвөнө", spell_numbers("гурван цаг"), "3 цаг")

fc = Formatter(auto_space=False, auto_capitalize=False)


def commanded(raw):
    fc.reset()
    return fc.format(spell_numbers(raw))[0]


check("гурван цэг тэмдэг болно", commanded("гурван цэг"), "…")
check("хоёр цэг тэмдэг болно", commanded("хоёр цэг"), ":")

# --- хүний нэрийг ойролцоогоор таних ---
fn = Formatter(
    auto_space=False,
    auto_capitalize=False,
    names={"Чимэгсайхан": "чимээ сайхан", "Дашдорж": "", "Болд": ""},
)


def named(raw):
    fn.reset()
    return fn.format(raw)[0]


check("яг таг", named("чимэгсайхан ирлээ"), "Чимэгсайхан ирлээ")
# Танигч нэрийг хоёр үг болгож хуваасан ч нэг нэр болно
check("хоёр үгээр сонсогдсон", named("чимэг сайхан ирлээ"), "Чимэгсайхан ирлээ")
check("гараар өгсөн хувилбар", named("чимээ сайхан ирлээ"), "Чимэгсайхан ирлээ")
# Нөхцөл залгасан хэлбэрийг хадгална — толь үүнийг барьж чаддаггүй байсан
check("нөхцөлтэй", named("чимэгсайхантай уулзлаа"), "Чимэгсайхантай уулзлаа")
check("харьяалахын нөхцөл", named("чимэгсайхны ном"), "Чимэгсайханы ном")
check("дагавар хадгалагдана", named("дашдоржид өгсөн"), "Дашдоржид өгсөн")
check("цэг наалдана", named("чимэгсайхан."), "Чимэгсайхан.")
check("дараагийн үгийг залгихгүй", named("дашдорж яриад байна"), "Дашдорж яриад байна")

# ЭРГЭЛЗВЭЛ ХӨНДӨХГҮЙ: богино нэр зөвхөн яг таг таарна. «Болд» нь «болно»,
# «болж» гэсэн өдөр тутмын үгнээс ганц үсгээр зөрдөг тул ойролцоо тааруулбал
# хэвийн яриа нэр болж эхэлнэ.
check("богино нэр яг таг", named("болд ирлээ"), "Болд ирлээ")
check("болно хэвээр", named("болно гэж хэлсэн"), "болно гэж хэлсэн")
check("болж хэвээр", named("болж байна уу"), "болж байна уу")
check("нэрийн хэсэг ганцаараа хэвээр", named("сайхан өдөр"), "сайхан өдөр")
check("нэргүй өгүүлбэр", named("би маргааш ирнэ"), "би маргааш ирнэ")

# Хоёроос олон үгтэй нэр ч ажиллах ёстой — цонхны урт нь бичсэн нэрсээс
# хамаарна, эс бөгөөс хэрэглэгчийн нэмсэн нэр чимээгүй ажиллахгүй байна
fn3 = Formatter(auto_space=False, auto_capitalize=False, names={"Ган Эрдэнэ Бат": ""})
fn3.reset()
check("гурван үгтэй нэр", fn3.format("ган эрдэнэ бат ирлээ")[0], "Ган Эрдэнэ Бат ирлээ")

# Эхний тэмдэгтийг ч хадгална (`_replace_word`-ийн адил)
fn.reset()
check("эхний хашилт үлдэнэ", fn.format('"чимэгсайхан ирлээ')[0], '"Чимэгсайхан ирлээ')

# Нэр нь хувилбар сонголтод ч жин болно
check(
    "нэртэй хувилбар сонгогдоно",
    choose_alternative(
        ["чимээ сайхан ирлээ", "чимэгсайхан ирлээ"], names={"Чимэгсайхан": ""}
    ),
    "чимэгсайхан ирлээ",
)
check("хоосон оролт", spell_numbers(""), "")

# --- хувилбар сонгох ---
DICT = {"клауд": "Claude"}
check("хувилбаргүй бол хоосон", choose_alternative([], DICT), "")
check("ганц хувилбар", choose_alternative(["нэг"], DICT), "нэг")
check(
    "толинд буй үгтэй хувилбарыг дэвшүүлнэ",
    choose_alternative(["клоуд код", "клауд код"], DICT),
    "клауд код",
)
check(
    "зөв бичиглэлтэй хувилбар мөн адил",
    choose_alternative(["клоуд код", "Claude код"], DICT),
    "Claude код",
)
check(
    "зөв бичиглэл буруугаас илүү жинтэй",
    choose_alternative(["клауд код", "Claude код"], DICT),
    "Claude код",
)
check(
    "нотолгоогүй бол эрэмбэ хэвээр",
    choose_alternative(["нэг хоёр", "гурав дөрөв"], DICT),
    "нэг хоёр",
)
check("толь хоосон бол эрэмбэ хэвээр", choose_alternative(["нэг", "хоёр"], {}), "нэг")
check(
    "тэнцвэл эхнийх нь хожино",
    choose_alternative(["клауд нэг", "клауд хоёр"], DICT),
    "клауд нэг",
)
check(
    "цэг таслалтай ч таарна",
    choose_alternative(["клоуд.", "клауд."], DICT),
    "клауд.",
)
check(
    "дуут товчлол ч оноо өгнө",
    choose_alternative(["минийх аяг", "миний хаяг"], {}, {"миний хаяг": "УБ хот"}),
    "миний хаяг",
)
check(
    "олон үгтэй толь бүхэлдээ таарна",
    choose_alternative(
        ["клод код бичье", "клауд код бичье"], {"клауд код": "Claude Code"}
    ),
    "клауд код бичье",
)

check(
    "түүхэнд батлагдсан үг давуу",
    choose_alternative(["надад хайрцаг өг", "надад харцаг өг"], history=["харцаг"]),
    "надад харцаг өг",
)
check(
    "түүх толийг дийлэхгүй",
    choose_alternative(
        ["клод код", "клауд код"], {"клауд": "Claude"}, history=["клод"]
    ),
    "клауд код",
)
check("түүхгүй бол эрэмбэ хэвээр", choose_alternative(["нэг", "хоёр"]), "нэг")

formatter = Formatter()
formatter.remember("харцаг")
check(
    "Formatter түүхээ өөрөө эзэмшинэ",
    formatter.choose(["надад хайрцаг өг", "надад харцаг өг"]),
    "надад харцаг өг",
)

check(
    "бичигдсэн цэг ухралтыг зогсооно",
    clean_speech("Хурал 3 цагт болно. Үгүй ээ 4 цагт болно."),
    "Хурал 3 цагт болно. 4 цагт болно.",
)
check(
    "бичигдсэн таслал ч хил болно",
    clean_speech("Хурал 3 цагт болно, үгүй ээ 4 цагт болно"),
    "Хурал 3 цагт болно, 4 цагт болно",
)
check(
    "хил байхгүй бол өмнөх нь бүхэлдээ хаягдана",
    clean_speech("5 цагт үгүй ээ 6 цагт"),
    "6 цагт",
)
check("үгийн араас «аа» бол бөөм", clean_speech("явъя аа"), "явъя аа")
check("үгийн араас «өө» бол бөөм", clean_speech("өгье өө"), "өгье өө")
check("эхэнд байвал чимээ", clean_speech("аа тэгэхээр маргааш"), "тэгэхээр маргааш")
check("сунгасан «ааа» хаана ч чимээ", clean_speech("за ааа маргааш уулзъя"), "маргааш уулзъя")

# --- preview нь дотоод төлвөө хөндөхгүй ---
peek = Formatter(auto_capitalize=True)
first = peek.preview("сайн байна уу")
second = peek.preview("сайн байна уу")
check("preview давтахад ижил", first, second)
check("preview форматтай ижил", peek.format("сайн байна уу"), first)

# --- Өгүүлбэр бүрд цэг ---
period = Formatter(auto_capitalize=True)
check("төгсгөлд цэг", period.format("маргааш уулзъя", end_sentence=True), ("Маргааш уулзъя. ", 0))
check(
    "дараагийн өгүүлбэр том үсгээр",
    period.format("тэгье", end_sentence=True),
    ("Тэгье. ", 0),
)
check(
    "аль хэдийн цэгтэй бол давхарлахгүй",
    Formatter().format("за цэг", end_sentence=True),
    ("За. ", 0),
)
check(
    "мөр таслалын араас цэг тавихгүй",
    Formatter(auto_space=False).format("за шинэ мөр", end_sentence=True),
    ("За" + chr(10), 0),
)
check("унтраалттай бол хэвээр", Formatter().format("за"), ("За ", 0))

check("буцаах команд", match_action("буцаа"), ("undo", ""))
check("цэгтэй ч таних", match_action("Устга."), ("undo", ""))
check("өгүүлбэр дунд байвал үйлдэл биш", match_action("энэ файлыг устга"), None)
check("энгийн үг", match_action("сайн байна уу"), None)
check("давтах команд", match_action("давтаад бич"), ("repeat", ""))
check("хуулах команд", match_action("хуулж ав"), ("copy", ""))
check("зогсоох команд", match_action("зогс"), ("stop", ""))
check("тоотой буцаах", match_action("хоёр удаа буцаа"), ("undo", "2"))
check("«удаа»-гүй ч болно", match_action("гурав буцаа"), ("undo", "3"))
check("цифрээр хэлсэн ч", match_action("2 давт"), ("repeat", "2"))
check("тоо дэмждэггүй үйлдэл", match_action("хоёр удаа зогс"), None)
check("тоо нь өгүүлбэрийн эхэнд л", match_action("буцаа хоёр"), None)
check("хоосон", match_action("  ...  "), None)

# --- Дуут засварын грамматик ---
check("үг устгах", match_action("үг устга"), ("drop_words", ""))
check("тоотой устгах", match_action("сүүлийн гурван үгийг устга"), ("drop_words", "3"))
check("англиар", match_action("delete last 2 words"), ("drop_words", "2"))
check("том үсэг", match_action("том үсэг болго"), ("capitalize", ""))
check("жижиг үсэг", match_action("жижгээр болго"), ("lowercase", ""))
check("зай авах", match_action("зайг ав"), ("no_space", ""))
# Чөлөөт текст авдаг заавар нь ЗӨВХӨН команд горимд — энгийн бичилтэд
# «оронд нь …» гэж хэлэхэд текст засагдах ёсгүй
check("энгийн бичилтэд орлуулахгүй", match_action("оронд нь Claude"), None)
check("команд горимд орлуулна", match_action("оронд нь Claude", command=True), ("replace_word", "Claude"))
check("том үсэг хадгалагдав", match_action("Оронд нь Monspeech", command=True), ("replace_word", "Monspeech"))
check("энгийн өгүүлбэр хэвээр", match_action("үг хэлэх нь чухал"), None)

check("сүүлийн үг хаягдав", edit_text("нэг хоёр гурав ", "drop_words", "1"), "нэг хоёр ")
check("хоёр үг хаягдав", edit_text("нэг хоёр гурав ", "drop_words", "2"), "нэг ")
check("бүгд хаягдвал хоосон", edit_text("нэг хоёр ", "drop_words", "5"), "")
check("том үсэг болов", edit_text("сайн байна ", "capitalize"), "сайн Байна ")
check("тэмдэгт хөндөгдөхгүй", edit_text("сайн байна. ", "capitalize"), "сайн Байна. ")
check("жижиг үсэг болов", edit_text("сайн Байна ", "lowercase"), "сайн байна ")
check("аль хэдийн тийм бол хоосон", edit_text("сайн Байна ", "capitalize"), None)
check("зай авагдав", edit_text("сайн байна ", "no_space"), "сайн байна")
check("зайгүй бол хийх зүйлгүй", edit_text("сайн байна", "no_space"), None)
check("сүүлийн үг солигдов", edit_text("клауд код. ", "replace_word", "Claude"), "клауд Claude. ")
check("хоосон текст", edit_text("", "capitalize"), None)
check("танихгүй засвар", edit_text("сайн ", "нислэг"), None)

# --- Танигч руу илгээх дохио ---
check(
    "нэрс эхэлж, толийн зөв тал дараа",
    vocabulary_hint(names={"Чимэгсайхан": ""}, replacements={"клауд": "Claude"}),
    "Чимэгсайхан, Claude",
)
check(
    "олон үгтэй нэр салгагдана",
    vocabulary_hint(names={"Улаанбаатар хот": ""}),
    "Улаанбаатар, хот",
)
check("давхардал хаягдана", vocabulary_hint(names={"Claude": ""}, replacements={"к": "claude"}), "Claude")
check("хэт богино үг оролцохгүй", vocabulary_hint(names={"я": "", "Батаа": ""}), "Батаа")
check("хоосон толь", vocabulary_hint(), "")
check(
    "хязгаараас хэтрэхгүй",
    len(vocabulary_hint(names={f"Нэр{index}": "" for index in range(200)}, limit=40)) <= 40,
    True,
)
check(
    "сүүлийн текстээс үг нэмнэ",
    vocabulary_hint(recent=["Monspeech сайхан ажиллаж байна"], limit=40),
    "Monspeech, сайхан, ажиллаж, байна",
)

# --- Хэрэглэгчийн нэмсэн үйлдэл ---
mine = parse_actions(
    "\n".join(
        ["цуцал=буцаах", "дахин уншуул=repeat", "хачин=нисэх", "=буцаах"]
    )
)
check("зөв мөрүүд л үлдэнэ", mine, {"цуцал": "undo", "дахин уншуул": "repeat"})
check("хэрэглэгчийн үйлдэл ажиллана", match_action("цуцал", mine), ("undo", ""))
check("тоо нь ч ажиллана", match_action("хоёр удаа цуцал", mine), ("undo", "2"))
check("дотоод нь хэвээр", match_action("буцаа", mine), ("undo", ""))
check("толинд байхгүй бол үйлдэл биш", match_action("хачин", mine), None)
check("монголоор буцаана", label_actions(mine)["цуцал"], "буцаах")

print()
print("FAILED" if fails else "ALL PASS")
for line in fails:
    print(" ", line)
sys.exit(1 if fails else 0)
