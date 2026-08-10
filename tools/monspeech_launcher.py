"""PyInstaller-ийн эхлэх цэг.

`monspeech/__main__.py` нь харьцангуй импорт (`from .app import ...`) ашигладаг
тул зөвхөн `python -m monspeech` гэж дуудахад ажиллана. Багцлагчид бие даасан
скрипт хэрэгтэй тул энэ жижиг эхлэлийг тусад нь бичив.
"""

from monspeech.app import main

raise SystemExit(main())
