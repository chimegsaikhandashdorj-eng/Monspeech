"""Шинэ хувилбар гарсан эсэхийг шалгах.

Тараагдсан апп нь өөрийгөө шинэчилж чаддаг байх ёстой — эс бөгөөс хэрэглэгч
хуучин хувилбар дээрээ мөнхөд үлдэнэ. Сервер тэжээхгүйн тулд GitHub-ийн
Releases-ийг эх сурвалж болгов: төлбөргүй, бүртгэлгүй, түлхүүргүй.

Апп өөрөө татаж суулгахгүй — зөвхөн мэдэгдээд, хэрэглэгчийг Releases хуудас руу
хүргэнэ. Автоматаар солих нь гарын үсэг зурагдаагүй файлыг чимээгүй солих
гэсэн үг бөгөөд антивирус ч, хэрэглэгч ч үүнд итгэх ёсгүй.

Нууцлал: шалгалт нь GitHub рүү хүсэлт явуулна (IP хаяг харагдана). Тиймээс
«Нэмэлт» хуудсанд унтраалгатай.
"""

from __future__ import annotations

import http.client
import json
import re
import threading

from .logging_setup import get as get_logger

log = get_logger("update")

OWNER = "chimegsaikhandashdorj-eng"
REPO = "Monspeech"
API_HOST = "api.github.com"
API_PATH = f"/repos/{OWNER}/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{OWNER}/{REPO}/releases/latest"

# Богино: энэ шалгалт хэрэглэгчийг хүлээлгэх ёсгүй. Амжаагүй бол чимээгүй өнгөрнө.
TIMEOUT = 6.0

_NUMBERS = re.compile(r"\d+")


def parse_version(text: str) -> tuple[int, ...]:
    """«v1.2.3», «1.2.3-beta» зэргээс тоонуудыг гаргана.

    Тоо олдохгүй бол `()` — ийм утгыг хэзээ ч «шинэ» гэж үзэхгүй.
    """
    return tuple(int(part) for part in _NUMBERS.findall(text or ""))


def is_newer(latest: str, current: str) -> bool:
    """`latest` нь `current`-ээс шинэ үү.

    Урт нь зөрвөл богиныг нь тэгээр гүйцээнэ: «1.2» < «1.2.1», «1.2» == «1.2.0».
    """
    new, old = parse_version(latest), parse_version(current)
    if not new or not old:
        return False
    size = max(len(new), len(old))
    new += (0,) * (size - len(new))
    old += (0,) * (size - len(old))
    return new > old


def _parse(body: str) -> str | None:
    """Releases API-ийн хариунаас хувилбарын шошгыг авна."""
    try:
        data = json.loads(body)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("draft") or data.get("prerelease"):
        return None
    tag = data.get("tag_name") or data.get("name")
    return str(tag).strip() if tag else None


def latest_tag() -> str | None:
    """Хамгийн сүүлийн хувилбарын шошго. Ямар нэг зүйл бүтэлгүйтвэл `None`."""
    conn = None
    try:
        conn = http.client.HTTPSConnection(API_HOST, timeout=TIMEOUT)
        conn.request(
            "GET",
            API_PATH,
            headers={
                "Accept": "application/vnd.github+json",
                # GitHub нь User-Agent-гүй хүсэлтийг 403-аар буцаадаг
                "User-Agent": f"Monspeech/{REPO}",
            },
        )
        response = conn.getresponse()
        body = response.read().decode("utf-8", "replace")
        if response.status != 200:
            log.info("шинэчлэл шалгах: %d хариу", response.status)
            return None
        return _parse(body)
    except (OSError, http.client.HTTPException) as exc:
        log.info("шинэчлэл шалгаж чадсангүй: %s", exc)
        return None
    finally:
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


def check_async(current: str, on_newer) -> None:
    """Дэвсгэрт шалгаад, ШИНЭ хувилбар байвал л `on_newer(шошго)` дуудна.

    Дуудлага нь ажлын thread дээр болно — цонх хөндөх бол дараалалаар дамжуулна.
    Шинэ юм байхгүй, эсвэл сүлжээгүй бол огт дуудагдахгүй: хэрэглэгчийг
    «шинэчлэл байхгүй» гэсэн мэдэгдлээр залхаах нь утгагүй.
    """

    def run() -> None:
        tag = latest_tag()
        if tag and is_newer(tag, current):
            log.info("шинэ хувилбар: %s (одоогийнх %s)", tag, current)
            on_newer(tag)

    threading.Thread(target=run, daemon=True).start()
