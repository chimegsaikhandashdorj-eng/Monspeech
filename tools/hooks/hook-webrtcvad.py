"""`webrtcvad-wheels`-ийн метадатаг зөв нэрээр нь олох.

`pyinstaller-hooks-contrib`-ийн стандарт hook нь `copy_metadata('webrtcvad')`
гэж дууддаг. Гэтэл бид `webrtcvad-wheels` санг ашигладаг: МОДУЛИЙН нэр нь
`webrtcvad` мөн боловч ТҮГЭЭЛТИЙН нэр нь өөр. Улмаас `copy_metadata` нь
`PackageNotFoundError` шидэж, hook файл өөрөө импортлогдож чадахгүй болж,
багцлалт бүхэлдээ зогсдог (алгасдаггүй — hook унах нь үхлийн алдаа).

Яагаад `webrtcvad-wheels`-ийг сонгосон бэ: жинхэнэ `webrtcvad` нь Windows дээр
бэлэн wheel-гүй тул C хөрвүүлэгч шаарддаг. `webrtcvad-wheels` нь яг ижил
модулийг бэлэн wheel-ээр тарааж, суулгацыг хялбар болгодог.

Метадата нь ажиллах үед огт хэрэггүй (`vad.py` зөвхөн `import webrtcvad` гэж
дууддаг, хувилбар асуудаггүй) тул олдсоныг нь авна, олдохгүй бол хоосон
үлдээнэ — багцлалт зогсох шалтгаан болох ёсгүй.

Энэ файл нь `monspeech.spec`-ийн `hookspath`-аар дамжин contrib-ийн hook-ийг
ОРЛОНО (хэрэглэгчийн hook нь илүү эрхтэй).
"""

from PyInstaller.utils.hooks import copy_metadata

datas = []
for _distribution in ("webrtcvad-wheels", "webrtcvad"):
    try:
        datas = copy_metadata(_distribution)
        break
    except Exception:  # noqa: BLE001 - аль ч нэр таарахгүй байж болно
        continue
