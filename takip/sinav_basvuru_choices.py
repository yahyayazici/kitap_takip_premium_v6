"""Sınav başvuru formu seçenekleri."""

ISTANBUL = "İstanbul"

# İstanbul Avrupa yakası ilçeleri
ISTANBUL_ILCELERI = (
    "Arnavutköy",
    "Avcılar",
    "Bağcılar",
    "Bahçelievler",
    "Bakırköy",
    "Başakşehir",
    "Bayrampaşa",
    "Beşiktaş",
    "Beylikdüzü",
    "Beyoğlu",
    "Büyükçekmece",
    "Çatalca",
    "Esenler",
    "Esenyurt",
    "Eyüpsultan",
    "Fatih",
    "Gaziosmanpaşa",
    "Güngören",
    "Kağıthane",
    "Küçükçekmece",
    "Sarıyer",
    "Silivri",
    "Sultangazi",
    "Şişli",
    "Zeytinburnu",
)

ISTANBUL_ILCE_CHOICES = [("", "İlçe seçin")] + [
    (ad, ad) for ad in ISTANBUL_ILCELERI
]
