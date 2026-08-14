"""Аппын эхлэл.

⚠️ Сэдвийг цонхны модулиудаас ӨМНӨ идэвхжүүлнэ. Шалтгаан: виджетүүд өнгийг
функцийн анхны утга болгон авдаг (`bg: str = theme.PANEL` гэх мэт, 18 газар)
бөгөөд Python эдгээрийг ИМПОРТЫН үед нэг л удаа тогтоодог. Дараа нь сольсон ч
хожуу байна.
"""

from . import theme
from .config import Config

theme.apply(str(Config.load()["theme"]))

from .app import main  # noqa: E402 - сэдэв тогтсоны дараа импортлоно

raise SystemExit(main())
