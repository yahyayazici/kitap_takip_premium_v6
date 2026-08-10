"""Dijital Etüt mini test — üç aşamalı AI soru üretimi.

1) Planlama  2) Soru üretimi  3) Bağımsız ölçme-değerlendirme denetimi

Beş tip (mevcut sözleşme korunur):
1. temel      — orta seviye uygulama
2. kavrama    — günlük hayat yorumlama
3. uygulama   — tablo/veri/liste çıkarımı
4. yeni_nesil — çok aşamalı bağlam
5. kisisel    — önceki yanlışa göre kişiselleştirme

Meta soru, tek adımlı ezber ve bağlamdan bağımsız “hikâye süsü” reddedilir.
Banka yedeği AI başarısızlığında akışı bozmaz.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from takip.ai_gateway import ai_json_uret, ai_llm_aktif_mi, onbellekten_al, onbellege_yaz
from takip.konu_destek_models import KonuKatalogu, KonuSorusu

logger = logging.getLogger(__name__)

_AI_SURUM = "v6-uc-asamali"
_QC_ESIK = 85
_MAX_DENEME = 3

SORU_TUR_SIRASI = (
    "temel",
    "kavrama",
    "uygulama",
    "yeni_nesil",
    "kisisel",
)

SORU_TUR_ETIKET = {
    "temel": "Temel",
    "kavrama": "Kavrama",
    "uygulama": "Uygulama",
    "yeni_nesil": "Yeni nesil",
    "kisisel": "Kişisel pekiştirme",
}

# Slot → plan hedefi (prompt + QC)
_SLOT_PLAN = {
    "temel": {
        "hedef": "Konunun temel kavramlarını yoklayan orta seviye uygulama sorusu",
        "zorluk": "orta",
        "baglam_zorunlu": False,
        "yeni_nesil_min": 1,
    },
    "kavrama": {
        "hedef": "Günlük hayat bağlamında yorumlama sorusu",
        "zorluk": "orta-üst",
        "baglam_zorunlu": True,
        "yeni_nesil_min": 2,
    },
    "uygulama": {
        "hedef": "Tablo, veri, liste, grafik veya şema üzerinden çıkarım sorusu",
        "zorluk": "orta-üst",
        "baglam_zorunlu": True,
        "yeni_nesil_min": 3,
        "veri_zorunlu": True,
    },
    "yeni_nesil": {
        "hedef": "Birden fazla bilgi ve işlem basamağı gerektiren yeni nesil soru",
        "zorluk": "zor",
        "baglam_zorunlu": True,
        "yeni_nesil_min": 3,
    },
    "kisisel": {
        "hedef": "Önceki yanlışa göre kişiselleştirilmiş, güçlü çeldiricili bağlam sorusu",
        "zorluk": "zor",
        "baglam_zorunlu": True,
        "yeni_nesil_min": 3,
    },
}

_YAZAR_ROL = """
Sen, Türkiye'de ortaokul düzeyinde eğitim veren; MEB öğretim programına, LGS soru
mantığına, ölçme-değerlendirme ilkelerine ve bağlam temelli yeni nesil soru yazımına
hâkim uzman bir soru yazarı ve ölçme-değerlendirme uzmanısın.

Görevin basit bilgi soruları hazırlamak değildir. Talebenin bilgiyi gerçek veya
gerçekçi bir bağlam içinde kullanmasını; metin, tablo, veri, görsel betimleme,
günlük hayat durumu veya çok aşamalı çıkarımlar üzerinden düşünmesini gerektiren
nitelikli sorular üretmektir.

Sorular ezber bilgisini değil; okuduğunu anlama, ilişki kurma, yorumlama, çıkarım
yapma, problem çözme ve bilgiyi yeni bir durumda kullanma becerilerini ölçmelidir.

Kritik kural: Bağlam çıkarıldığında soru hiçbir şey kaybetmiyorsa, o soru gerçek
bir bağlam temelli soru değildir.
""".strip()

_DENETCI_ROL = """
Sen bağımsız bir ölçme-değerlendirme uzmanısın. Verilen soruyu yeniden yazmaya
başlamadan önce ölçütlere göre tarafsız biçimde denetle. Soru yazarı gibi davranma;
yalnızca denetle, puanla ve onayla veya reddet.
""".strip()

_META_KALIPLAR = re.compile(
    r"(temel kavram|en sık yapılan hata|pekiştir|etkili yöntem|"
    r"soru gelme olasılığı|zayıfsan|hiç çalışmamak|yalnızca ezber|"
    r"sınavda hiç|konuyu atlamak|cevap anahtarına|konuyu hiç çalış|"
    r"nasıl çalışmalı|videoyu izleyip|yukarıdakilerin hepsi|hiçbiri|"
    r"aşağıdaki görsele göre|yukarıdaki (şekil|görsel|grafiğe))",
    re.I,
)

_COK_BASIT = re.compile(
    r"^(?:\d+\s*(?:ile|/|:)\s*\d+|[\d²³⁰¹²]+)\s*",
    re.I,
)

_GORSEL_ATIF = re.compile(
    r"(görsele göre|şekle göre|yukarıdaki (şekil|görsel|grafik)|aşağıdaki görsel)",
    re.I,
)


def _ai_anahtar(konu: KonuKatalogu, talebe_id: int | None = None) -> str:
    taban = f"konu-{konu.pk}-{_AI_SURUM}-{konu.sinif_seviyesi}"
    if talebe_id:
        return f"{taban}-t{talebe_id}"
    return taban


def _soru(
    tur: str,
    metin: str,
    a: str,
    b: str,
    c: str,
    d: str,
    dogru: str,
    aciklama: str,
) -> dict[str, Any]:
    return {
        "soru_turu": tur,
        "soru_metni": metin.strip(),
        "secenek_a": a.strip(),
        "secenek_b": b.strip(),
        "secenek_c": c.strip(),
        "secenek_d": d.strip(),
        "dogru_secenek": dogru.upper()[:1],
        "aciklama": aciklama.strip(),
    }


def _meta_soru_mu(soru: dict) -> bool:
    metin = f"{soru.get('soru_metni', '')} {soru.get('secenek_a', '')}"
    return bool(_META_KALIPLAR.search(metin))


def _kalite_ok(soru: dict, *, tur: str, siki: bool = False) -> bool:
    """siki=True: AI çıktısı. siki=False: banka yedeği (akış bozulmasın)."""
    if not isinstance(soru, dict):
        return False
    metin = (soru.get("soru_metni") or "").strip()
    if len(metin) < (50 if siki else 35):
        return False
    if _meta_soru_mu(soru):
        return False
    dogru = str(soru.get("dogru_secenek", "")).upper()[:1]
    if dogru not in {"A", "B", "C", "D"}:
        return False
    for k in ("secenek_a", "secenek_b", "secenek_c", "secenek_d"):
        if len((soru.get(k) or "").strip()) < 1:
            return False
    if not siki:
        return True
    slot = _SLOT_PLAN.get(tur, {})
    if slot.get("baglam_zorunlu") and len(metin) < 140:
        return False
    if tur in {"uygulama", "yeni_nesil", "kisisel"} and _COK_BASIT.match(metin):
        if len(metin) < 120:
            return False
    if _GORSEL_ATIF.search(metin) and "|" not in metin and "\n-" not in metin:
        return False
    return True


# ---------------------------------------------------------------------------
# Sınıf + konu anahtarlı banka — AI yoksa yedek
# ---------------------------------------------------------------------------

def _banka_oran() -> list[dict]:
    return [
        _soru(
            "temel",
            "Sınıf kutlamasında bir pasta 12 eşit dilime ayrılmıştır. Ayşe 4 dilim, "
            "kalan dilimleri Ali yemiştir.\n\n"
            "Ayşe’nin yediği dilimin Ali’nin yediğine oranı sadeleştirilmiş haliyle hangisidir?",
            "1/2",
            "1/3",
            "2/3",
            "3/4",
            "A",
            "Ayşe 4, Ali 8 → 4/8 = 1/2.",
        ),
        _soru(
            "kavrama",
            "Market alışverişinde Elif kg başına aynı fiyattan elma almaktadır. "
            "Aldığı miktar arttıkça ödediği ücret de aynı oranda artmaktadır.\n\n"
            "Bu durum hangi orantı türüne örnektir?",
            "Ters orantı; çünkü süre azalır",
            "Doğru orantı; biri artarken diğeri aynı oranda artar",
            "Orantısız ilişki; fiyat değişmez",
            "Yalnızca kesirlerle açıklanan durum",
            "B",
            "Miktar ve ücret birlikte aynı oranda artıyorsa doğru orantıdır.",
        ),
        _soru(
            "uygulama",
            "Sınıf yoklaması şöyle kaydedilmiştir:\n\n"
            "| Grup | Sayı |\n"
            "| --- | --- |\n"
            "| Kız | 15 |\n"
            "| Erkek | ? |\n\n"
            "Kızların erkeklere oranı 3/5’tir. Aynı orana göre erkek sayısı kaçtır?",
            "9",
            "20",
            "25",
            "30",
            "C",
            "3/5 = 15/e → 3e = 75 → e = 25.",
        ),
        _soru(
            "yeni_nesil",
            "Okul kooperatifi gezi için minibüs kiralar. Kayıt defterinde şunlar vardır:\n\n"
            "| Minibüs sayısı | Taşınan öğrenci |\n"
            "| --- | --- |\n"
            "| 1 | 14 |\n"
            "| 3 | 42 |\n\n"
            "Aynı oran korunarak 5 minibüs kiralanırsa kaç öğrenci taşınabilir?",
            "56",
            "60",
            "70",
            "84",
            "C",
            "1 minibüs → 14 öğrenci; 5 × 14 = 70. Tablodaki 3→42 oranı da bunu doğrular.",
        ),
        _soru(
            "kisisel",
            "Emre, 2/3 = 8/x orantısını çözerken «payları ve paydaları kendi içinde "
            "topladım» diyerek x = 13 bulmuştur.\n\n"
            "Emre’nin hatası nedir ve doğru x nedir?",
            "İçler dışlar yapılmalı; x = 12",
            "Paydalar toplanmalı; x = 11",
            "Oran ters çevrilmeli; x = 6",
            "Sonuç doğrudur; x = 13",
            "A",
            "2·x = 3·8 → x = 12. Toplama ile orantı çözülmez.",
        ),
    ]


def _banka_kesir() -> list[dict]:
    return [
        _soru(
            "temel",
            "Doğum günü pastası 8 eşit dilime kesilmiştir. Zeynep pastanın 3/8’ini "
            "arkadaşlarıyla paylaşmıştır.\n\n"
            "Pastanın kalan kısmı hangisidir?",
            "3/8",
            "5/8",
            "1/2",
            "1/8",
            "B",
            "1 − 3/8 = 5/8.",
        ),
        _soru(
            "kavrama",
            "Spor kulübünde su molası için bardaklar yarıya kadar doldurulacaktır. "
            "Antrenör «Her bardak 1/2 dolu olsun» demiştir.\n\n"
            "Aşağıdaki kesirlerden hangisi bu dolulukla aynı büyüklüktedir?",
            "2/5",
            "3/6",
            "3/8",
            "2/6",
            "B",
            "3/6 sadeleştirilince 1/2 olur.",
        ),
        _soru(
            "uygulama",
            "Kantin defterinde bir şişenin durumu şöyle yazılmıştır:\n\n"
            "| Durum | Miktar (litre) |\n"
            "| --- | --- |\n"
            "| Başlangıç | 4/5 |\n"
            "| İçilen | 1/5 |\n\n"
            "Şişede kalan miktar kaç litredir?",
            "1/5",
            "2/5",
            "3/5",
            "4/5",
            "C",
            "4/5 − 1/5 = 3/5.",
        ),
        _soru(
            "yeni_nesil",
            "Okul kantininde 1 litre ayran satılmaktadır. Elif önce 1/4 litresini, "
            "ardından kalanın 1/3’ünü içmiştir.\n\n"
            "Şişede kalan ayran miktarı kaç litredir?",
            "1/2",
            "1/3",
            "1/4",
            "2/3",
            "A",
            "1 − 1/4 = 3/4; kalanın 1/3’ü = 1/4 içilir; kalan 1/2.",
        ),
        _soru(
            "kisisel",
            "Mert, 1/2 + 1/4 işleminde paydaları eşitlemeden payları toplayıp 2/6 "
            "bulmuştur.\n\n"
            "Doğru yaklaşım ve sonuç nedir?",
            "Paydalar eşitlenir; sonuç 3/4",
            "Paylar çarpılır; sonuç 1/8",
            "Mert haklıdır; sonuç 2/6",
            "Sonuç 1/2’dir",
            "A",
            "2/4 + 1/4 = 3/4.",
        ),
    ]


def _banka_paragraf() -> list[dict]:
    return [
        _soru(
            "temel",
            "Okul dergisinde şu cümle yer almıştır:\n\n"
            "«Düzenli kitap okumak kelime dağarcığını geliştirir ve hayal gücünü besler.»\n\n"
            "Bu cümlede yazarın asıl vurguladığı düşünce hangisidir?",
            "Kitapların fiyatlarının düşmesi gerektiği",
            "Kitap okumanın zihinsel gelişime katkı sağladığı",
            "Ödevlerin daha az verilmesi gerektiği",
            "Kütüphanelerin yalnızca hafta sonu açık olması",
            "B",
            "Cümle okumanın kelime ve hayal gücüne katkısını vurgular.",
        ),
        _soru(
            "kavrama",
            "Kütüphanede sınıfça okunan kısa metinde yazar önce yağmurlu bir sabahı "
            "anlatır, sonra mahalledeki çocukların sokakta kâğıt gemi yüzdürdüğünü "
            "yazar. Metnin sonunda ise «Bazen en eğlenceli oyunlar, en basit "
            "malzemelerle başlar.» der.\n\n"
            "Bu metin esas olarak ne hakkındadır?",
            "Yağmurun meteorolojik nedenleri",
            "Basit malzemelerle kurulan oyunun değeri",
            "Kâğıt geminin nasıl yapıldığı",
            "Mahalledeki dükkânların listesi",
            "B",
            "Son cümle ana vurguyu verir; metin basit oyunun değerini anlatır.",
        ),
        _soru(
            "uygulama",
            "Bir öğrenci aşağıdaki notları çıkarmıştır:\n\n"
            "| Parça bölümü | Notu |\n"
            "| --- | --- |\n"
            "| 1. cümle | Ormanlar oksijen üretir |\n"
            "| 2. cümle | Canlılara yuva olur, erozyonu önler |\n"
            "| 3. cümle | Bu nedenle ormanları korumak geleceğimizi korumaktır |\n\n"
            "Bu notlara göre parçanın ana düşüncesi hangisidir?",
            "Ormanlar yalnızca hayvanlar içindir",
            "Ormanlar önemlidir ve korunmalıdır",
            "Erozyon hiç meydana gelmez",
            "Oksijen sadece denizlerden gelir",
            "B",
            "«Bu nedenle» ile bağlanan sonuç cümlesi ana düşünceyi taşır.",
        ),
        _soru(
            "yeni_nesil",
            "Öğretmen tahtaya şu metni yazmıştır:\n\n"
            "«Sabahları erken kalkan Ege, önce kısa bir yürüyüş yapar. "
            "Sonra kahvaltısını eder ve ödevlerine başlar. Bu düzen sayesinde "
            "hem enerjik hisseder hem de derslerinde daha başarılı olur.»\n\n"
            "Metindeki neden-sonuç ilişkisine göre en uygun başlık hangisidir?",
            "Kahvaltı Çeşitleri",
            "Düzenli Günün Yararları",
            "Yürüyüş Ayakkabıları",
            "Ödevlerin Zorluğu",
            "B",
            "Düzenli alışkanlık → enerji ve başarı; başlık bunu yansıtır.",
        ),
        _soru(
            "kisisel",
            "Elif, paragraf sorularında çoğu zaman yalnızca ilk cümleye bakıp "
            "ana düşünceyi seçiyor. Aşağıdaki metinde ise ana düşünce sonda "
            "verilmiştir:\n\n"
            "«Sınıfça bir geri dönüşüm köşesi kurduk. Atık kâğıtları ayırdık, "
            "plastikleri ayrı bir kutuya koyduk. Böylece hem okulumuzu temiz "
            "tuttuk hem de doğaya katkı sağladık.»\n\n"
            "Elif’in tipik hatasını yapmadan doğru ana düşünceyi seçmesi için "
            "hangisini yapması gerekir?",
            "Paragrafı bütünüyle okuyup sonucun vurguladığı fikri bulmak",
            "Yalnızca ilk cümleyi okuyup işaretlemek",
            "En uzun şıkkı seçmek",
            "Başlık aramadan şıkları elemek",
            "A",
            "Ana düşünce sonda olabilir; tüm paragraf okunmalıdır.",
        ),
    ]


def _banka_madde() -> list[dict]:
    return [
        _soru(
            "temel",
            "Kahvaltıda sıcak çaya batırılan metal kaşık kısa sürede ısınır; "
            "tahta kaşık ise daha geç ısınır.\n\n"
            "Metal kaşığın hızla ısınması hangi özellikle açıklanır?",
            "Isı yalıtkanlığı",
            "Isı iletkenliği",
            "Elektrik yalıtkanlığı",
            "Saydamlık",
            "B",
            "Metaller ısıyı iyi iletir.",
        ),
        _soru(
            "kavrama",
            "Fen dersinde buz kalıpları oda sıcaklığında bırakılmış ve bir süre "
            "sonra su birikmiştir.\n\n"
            "Bu olay hangi hâl değişimidir?",
            "Donma",
            "Erime",
            "Yoğuşma",
            "Buharlaşma",
            "B",
            "Katı → sıvı = erime.",
        ),
        _soru(
            "uygulama",
            "Apartman yönetim kurulu kış öncesi şu tabloyu incelemiştir:\n\n"
            "| Uygulama | Beklenen etki |\n"
            "| --- | --- |\n"
            "| Dış cephe köpük yalıtımı | ? |\n"
            "| İnce cam | Isı kaybı artar |\n\n"
            "Köpük yalıtımının temel amacı nedir?",
            "Evi daha ağır yapmak",
            "Isı kaybını azaltmak",
            "Sesi artırmak",
            "Pencereleri kapatmak",
            "B",
            "Yalıtım ısı kaybını azaltır.",
        ),
        _soru(
            "yeni_nesil",
            "Fen laboratuvarında aynı sıcaklıktaki çay; metal, cam ve tahta "
            "kaplara konmuştur. Beş dakika sonra öğrenciler kapların dışına "
            "dikkatlice dokunmuştur.\n\n"
            "Hangi kabın dış yüzeyi daha sıcak hissedilir ve neden?",
            "Tahta; çünkü yalıtkandır",
            "Metal; çünkü ısıyı iyi iletir",
            "Cam; çünkü saydamdır",
            "Hepsi aynıdır; sıcaklık değişmez",
            "B",
            "Metal iletken olduğu için ısıyı dış yüzeye taşır.",
        ),
        _soru(
            "kisisel",
            "Can, «ısı» ile «sıcaklık»ın aynı şey olduğunu düşünerek soruyu "
            "yanlış yapmıştır.\n\n"
            "Doğru ayrım hangisidir?",
            "Isı enerjidir; sıcaklık bu enerjinin ölçüsüdür",
            "Sıcaklık enerjidir; ısı ölçü birimidir",
            "İkisi de yalnızca katılarda vardır",
            "Isı sadece yazın olur",
            "A",
            "Isı aktarılan enerjidir; sıcaklık ortalama kinetik enerji ölçüsüdür.",
        ),
    ]


_KONU_BANKASI: list[tuple[tuple[str, ...], Any]] = [
    (("oran", "orantı", "oranti"), _banka_oran),
    (("kesir",), _banka_kesir),
    (("paragraf", "anlam"), _banka_paragraf),
    (("madde", "ısı", "endüstri", "hal"), _banka_madde),
]


def _bankadan_sorular(konu: KonuKatalogu) -> list[dict] | None:
    ad = (konu.konu_ad or "").casefold()
    for anahtarlar, uretici in _KONU_BANKASI:
        if any(a in ad for a in anahtarlar):
            return list(uretici())
    return None


def _jenerik_baglam_sorular(konu: KonuKatalogu) -> list[dict]:
    s = konu.sinif_seviyesi
    b = konu.brans_etiket
    k = konu.konu_ad
    return [
        _soru(
            "temel",
            f"{s}. sınıf {b} dersinde «{k}» ile ilgili bir durumda önce hangi bilgi "
            f"netleştirilmelidir?",
            "Verilenler ve sorunun istediği",
            "Şıkların uzunluğu",
            "Soru numarası",
            "Öğretmenin adı",
            "A",
            "Önce verilen-istenen belirlenir.",
        ),
        _soru(
            "kavrama",
            f"«{k}» konusunda iki benzer örnekten doğru olanı ayırt ederken en güvenilir "
            f"yol hangisidir?",
            "Konu kuralını örneğe uygulamak",
            "Daha uzun cümleyi seçmek",
            "İlk şıkkı işaretlemek",
            "Konuyu atlamak",
            "A",
            "Kural örneğe uygulanarak ayırt edilir.",
        ),
        _soru(
            "uygulama",
            f"Bir öğrenci «{k}» ile ilgili günlük bir problemi çözerken işlemlerini "
            f"deftere adım adım yazmıştır. Bu yaklaşımın asıl yararı nedir?",
            "Hatayı bulmayı ve kontrolü kolaylaştırması",
            "Zaman kaybettirmesi",
            "Sonucu rastgele seçmesi",
            "Şıkları gizlemesi",
            "A",
            "Adım adım çözüm kontrolü sağlar.",
        ),
        _soru(
            "yeni_nesil",
            f"{s}. sınıf öğrencisi Elif, okulda «{k}» konusunu günlük hayatla "
            f"ilişkilendiren bir proje hazırlamaktadır. Projesinde bir durum anlatmış, "
            f"verileri tablolaştırmış ve sonuca ulaşmıştır.\n\n"
            f"Bu projenin ölçtüğü en üst düzey beceri hangisidir?",
            "Ezberlenen tanımı aynen yazmak",
            "Bilgiyi yeni bir bağlama uygulayıp yorumlamak",
            "Şıkları tahmin etmek",
            "Konuyu tamamen ezberlemek",
            "B",
            "Yeni nesil sorular bilgiyi bağlama taşımayı ölçer.",
        ),
        _soru(
            "kisisel",
            f"Ali, «{k}» sorularında sıkça işlemi yarım bırakıp şıklardan "
            f"yakın gördüğünü işaretlemektedir. Ali’ye en doğru öneri hangisidir?",
            "İşlemi bitirip sonucu şıklarla karşılaştırmak",
            "Hep A şıkkını seçmek",
            "Soruyu boş bırakmak",
            "Yalnızca videoya bakmak",
            "A",
            "Tam çözüm + şık kontrolü tipik hatayı azaltır.",
        ),
    ]


def _kural_tabanli_sorular(konu: KonuKatalogu, adet: int = 5) -> list[dict]:
    banka = _bankadan_sorular(konu) or _jenerik_baglam_sorular(konu)
    temiz = []
    for s in banka:
        tur = s.get("soru_turu") or "temel"
        if _kalite_ok(s, tur=tur):
            temiz.append(s)
    by_tur = {s["soru_turu"]: s for s in temiz}
    sirali = [by_tur[t] for t in SORU_TUR_SIRASI if t in by_tur]
    if len(sirali) < adet:
        sirali.extend([s for s in temiz if s not in sirali])
    return sirali[:adet]


# ---------------------------------------------------------------------------
# Üretim bağlamı (sınıf, kazanım, video, önceki yanlışlar)
# ---------------------------------------------------------------------------

def _uretim_baglami(konu: KonuKatalogu, talebe=None) -> dict[str, Any]:
    aciklama = (konu.aciklama or "").strip()
    kazanim = aciklama or (
        f"{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} dersinde "
        f"«{konu.konu_ad}» ile ilgili MEB kazanımlarını uygular."
    )
    unite = ""
    if aciklama and "—" in aciklama:
        unite = aciklama.split("—", 1)[0].strip()[:120]
    elif aciklama:
        unite = aciklama.split("\n", 1)[0].strip()[:120]
    if not unite:
        unite = f"{konu.brans_etiket} — {konu.konu_ad}"

    video_baslik = ""
    video_icerik = ""
    onceki_yanlislar: list[str] = []
    zorlandigi = ""
    basari = "bilinmiyor"
    onceki_sorular: list[str] = []

    if talebe is not None:
        from takip.konu_destek_models import KonuTestCevabi, KonuTestOturu, KonuVideoIzleme

        izleme = (
            KonuVideoIzleme.objects.filter(talebe=talebe, konu=konu)
            .select_related("video")
            .order_by("-baslama")
            .first()
        )
        if izleme:
            video_baslik = izleme.video_baslik or ""
            if izleme.video_id:
                video_icerik = (izleme.video.baslik or "")[:400]

        yanlislar = (
            KonuTestCevabi.objects.filter(
                oturum__talebe=talebe,
                oturum__konu=konu,
                dogru_mu=False,
            )
            .select_related("soru")
            .order_by("-id")[:8]
        )
        for y in yanlislar:
            onceki_yanlislar.append((y.soru.soru_metni or "")[:220])
            if hasattr(y.soru, "soru_turu") and y.soru.soru_turu:
                zorlandigi = y.soru.soru_turu

        oturumlar = KonuTestOturu.objects.filter(
            talebe=talebe, konu=konu, bitis__isnull=False
        ).order_by("-bitis")[:5]
        if oturumlar:
            ort = sum(float(o.basari_yuzde or 0) for o in oturumlar) / len(oturumlar)
            if ort >= 80:
                basari = "iyi"
            elif ort >= 50:
                basari = "orta"
            else:
                basari = "zayıf"

        onceki_sorular = list(
            KonuSorusu.objects.filter(konu=konu, aktif=True)
            .order_by("-id")
            .values_list("soru_metni", flat=True)[:12]
        )

    return {
        "sinif": str(konu.sinif_seviyesi),
        "ders": konu.brans_etiket,
        "unite": unite,
        "konu": konu.konu_ad,
        "kazanim": kazanim[:500],
        "basari_duzeyi": basari,
        "onceki_yanlislar": onceki_yanlislar or ["Kayıt yok — tipik kavram yanılgılarını hedefle"],
        "zorlandigi_soru_turu": zorlandigi or "bilinmiyor",
        "video_basligi": video_baslik or "Yok",
        "video_icerigi": video_icerik or "Video özeti yok; sınıf-konu-kazanımı esas al.",
        "onceki_sorular": [s[:180] for s in onceki_sorular],
    }


def _baglam_metni(baglam: dict[str, Any]) -> str:
    yanlislar = "\n".join(f"- {x}" for x in baglam["onceki_yanlislar"][:5])
    onceki = "\n".join(f"- {x}" for x in baglam["onceki_sorular"][:8]) or "- (yok)"
    return f"""
Talebenin sınıfı: {baglam['sinif']}
Ders: {baglam['ders']}
Ünite: {baglam['unite']}
Konu: {baglam['konu']}
Kazanım: {baglam['kazanim']}
Talebenin mevcut başarı düzeyi: {baglam['basari_duzeyi']}
Zorlandığı soru türü: {baglam['zorlandigi_soru_turu']}
İzlediği video: {baglam['video_basligi']}
Video özeti veya transkripti: {baglam['video_icerigi']}
Talebenin daha önce yaptığı yanlışlar:
{yanlislar}
Daha önce gösterilen sorular (tekrarlama / yalnızca isim-sayı değiştirme YASAK):
{onceki}
""".strip()


# ---------------------------------------------------------------------------
# JSON → iç soru formatı
# ---------------------------------------------------------------------------

def _tablo_markdown(data: dict | list | None) -> str:
    if not data:
        return ""
    if isinstance(data, list):
        return "\n".join(f"- {x}" for x in data if str(x).strip())
    headers = data.get("headers") or []
    rows = data.get("rows") or []
    if not headers and not rows:
        return ""
    if not headers and rows:
        return "\n".join(" | ".join(str(c) for c in r) for r in rows)
    line1 = "| " + " | ".join(str(h) for h in headers) + " |"
    line2 = "| " + " | ".join("---" for _ in headers) + " |"
    body = [
        "| " + " | ".join(str(c) for c in row) + " |"
        for row in rows
    ]
    return "\n".join([line1, line2, *body])


def _json_sorudan_ic(satir: dict, *, tur: str) -> dict[str, Any] | None:
    opts = satir.get("options") or {}
    if isinstance(opts, dict):
        a = str(opts.get("A") or opts.get("a") or "").strip()
        b = str(opts.get("B") or opts.get("b") or "").strip()
        c = str(opts.get("C") or opts.get("c") or "").strip()
        d = str(opts.get("D") or opts.get("d") or "").strip()
    else:
        a = str(satir.get("secenek_a") or "").strip()
        b = str(satir.get("secenek_b") or "").strip()
        c = str(satir.get("secenek_c") or "").strip()
        d = str(satir.get("secenek_d") or "").strip()

    dogru = str(
        satir.get("correct_answer") or satir.get("dogru_secenek") or ""
    ).strip().upper()[:1]
    if dogru not in {"A", "B", "C", "D"}:
        return None

    context = (satir.get("context") or "").strip()
    qtext = (satir.get("question_text") or satir.get("soru_metni") or "").strip()
    data_md = _tablo_markdown(satir.get("data"))
    parcalar = [p for p in (context, data_md, qtext) if p]
    metin = "\n\n".join(parcalar).strip()
    if not metin:
        return None

    solution = (satir.get("solution") or satir.get("aciklama") or "").strip()
    return {
        "soru_turu": tur,
        "soru_metni": metin,
        "secenek_a": a[:500],
        "secenek_b": b[:500],
        "secenek_c": c[:500],
        "secenek_d": d[:500],
        "dogru_secenek": dogru,
        "aciklama": solution,
        "_meta": {
            "difficulty": satir.get("difficulty") or _SLOT_PLAN[tur]["zorluk"],
            "question_type": satir.get("question_type") or "",
            "cognitive_skill": satir.get("cognitive_skill") or "",
            "distractor_analysis": satir.get("distractor_analysis") or {},
            "learning_outcome": satir.get("learning_outcome") or "",
            "why_new_gen": satir.get("why_context_based")
            or satir.get("why_new_generation")
            or "",
            "context": context,
            "data_type": satir.get("data_type") or "",
        },
    }


def _sorular_benzersiz_mi(sorular: list[dict]) -> bool:
    normlar = []
    for s in sorular:
        n = re.sub(r"\W+", "", (s.get("soru_metni") or "").casefold())[:100]
        if not n:
            return False
        if n in normlar:
            return False
        normlar.append(n)
    return True


def _sunucu_set_dogrula(
    sorular: list[dict],
    adet: int = 5,
    *,
    siki: bool = True,
) -> bool:
    if len(sorular) != adet:
        return False
    turler = [s.get("soru_turu") for s in sorular]
    if len(set(turler)) < min(4, adet):
        return False
    for s in sorular:
        if not _kalite_ok(s, tur=s.get("soru_turu") or "temel", siki=siki):
            return False
    return _sorular_benzersiz_mi(sorular)


# ---------------------------------------------------------------------------
# Aşama 1 — Plan
# ---------------------------------------------------------------------------

def _asama_planla(baglam: dict[str, Any]) -> list[dict] | None:
    slot_ozet = "\n".join(
        f"{i}. {tur}: {_SLOT_PLAN[tur]['hedef']} | zorluk={_SLOT_PLAN[tur]['zorluk']}"
        for i, tur in enumerate(SORU_TUR_SIRASI, start=1)
    )
    prompt = f"""
Aşağıdaki talebe/konu bilgilerine göre TAM 5 soruluk bir TEST PLANI hazırla.
Henüz soru metni yazma; yalnızca plan üret.

{_baglam_metni(baglam)}

Zorunlu dağılım:
{slot_ozet}

Zorluk dağılımı: 1 orta, 2 orta-üst, 2 zor.

Her plan maddesinde bağlam alanı kazanıma hizmet etmeli (okul, kütüphane, spor,
alışveriş, gezi, deney, çevre, teknoloji, beslenme vb.). Yaşa uygunsuz içerik YASAK.

JSON:
{{
  "plans": [
    {{
      "question_number": 1,
      "slot": "temel",
      "difficulty": "orta",
      "context_idea": "...",
      "data_idea": "yok veya tablo/liste özeti",
      "cognitive_skill": "uygulama",
      "target_misconception": "...",
      "distractor_logics": ["...", "...", "..."],
      "new_gen_features": ["...", "..."]
    }}
  ]
}}
"""
    sonuc = ai_json_uret(
        system=_YAZAR_ROL + "\nYalnızca geçerli JSON döndür.",
        user_prompt=prompt,
        temperature=0.35,
        max_tokens=2200,
    )
    if not sonuc:
        return None
    plans = sonuc.get("plans") or sonuc.get("plan") or []
    if not isinstance(plans, list) or len(plans) < 5:
        return None

    sirali: list[dict] = []
    for i, tur in enumerate(SORU_TUR_SIRASI):
        aday = None
        for p in plans:
            if not isinstance(p, dict):
                continue
            if str(p.get("slot") or "").strip().lower() == tur:
                aday = p
                break
            if int(p.get("question_number") or 0) == i + 1:
                aday = p
                break
        if not aday:
            aday = plans[i] if i < len(plans) and isinstance(plans[i], dict) else {}
        aday = dict(aday)
        aday["slot"] = tur
        aday["question_number"] = i + 1
        aday["difficulty"] = aday.get("difficulty") or _SLOT_PLAN[tur]["zorluk"]
        sirali.append(aday)
    return sirali


# ---------------------------------------------------------------------------
# Aşama 2 — Plana dayalı üretim (set veya tekil yeniden üretim)
# ---------------------------------------------------------------------------

def _soru_json_semasi_ornek() -> str:
    return """
{
  "question_number": 1,
  "context": "Bağlam metni",
  "data_type": "none|table|list|schema",
  "data": {"headers": ["..."], "rows": [["...", "..."]]},
  "question_text": "Soru kökü",
  "options": {"A": "...", "B": "...", "C": "...", "D": "..."},
  "correct_answer": "C",
  "solution": "Adım adım çözüm",
  "difficulty": "orta-üst",
  "question_type": "baglam_temelli",
  "cognitive_skill": "yorumlama_ve_cikarim",
  "learning_outcome": "Ölçülen kazanım",
  "distractor_analysis": {"A": "...", "B": "...", "D": "..."},
  "why_context_based": "Bağlam çıkarılırsa hangi bilgi kaybolur?"
}
""".strip()


def _asama_set_uret(
    baglam: dict[str, Any],
    planlar: list[dict[str, Any]],
) -> dict[str, dict] | None:
    """Plana göre 5 soruyu tek çağrıda üretir (plansız doğrudan üretim değil)."""
    plan_txt = []
    for p in planlar:
        plan_txt.append(
            f"{p.get('question_number')}. slot={p.get('slot')} "
            f"zorluk={p.get('difficulty')} bağlam={p.get('context_idea')} "
            f"veri={p.get('data_idea')} beceri={p.get('cognitive_skill')} "
            f"yanılgı={p.get('target_misconception')} "
            f"çeldirici={p.get('distractor_logics')}"
        )
    prompt = f"""
Aşağıdaki PLANI uygulayarak tam 5 soruluk testi üret. Plana sadık kal.
Plansız rastgele soru yazma. Yalnızca JSON döndür.

{_baglam_metni(baglam)}

PLAN:
{chr(10).join(plan_txt)}

Kurallar:
- 3. soru (uygulama) mutlaka table veya list data içermeli.
- En az 3 soru gerçek bağlam temelli / yeni nesil olsun.
- Bağlam çıkarıldığında soru bozulmalı; süs hikâye YASAK.
- Olmayan görsele atıf YASAK; tablo/liste markdown data olarak ver.
- Çeldiriciler rastgele olmasın; «hepsi/hiçbiri» YASAK.
- Video yalnızca yardımcı; temel sınıf+konu+kazanımdır.
- Sorular birbirinin cevabını açık etmesin; önceki soruları kopyalama.

Çıktı:
{{
  "test_title": "{baglam['sinif']}. Sınıf {baglam['ders']} – {baglam['konu']}",
  "grade": {baglam['sinif'] if str(baglam['sinif']).isdigit() else 0},
  "lesson": "{baglam['ders']}",
  "topic": "{baglam['konu']}",
  "learning_outcome": "{baglam['kazanim'][:180].replace(chr(34), "'")}",
  "questions": [ ... tam 5 soru, her biri şu şemada: {_soru_json_semasi_ornek()} ]
}}
"""
    sonuc = ai_json_uret(
        system=_YAZAR_ROL + "\nYalnızca geçerli JSON döndür. Planı uygula.",
        user_prompt=prompt,
        temperature=0.45,
        max_tokens=4500,
    )
    if not sonuc or not isinstance(sonuc.get("questions"), list):
        return None

    toplanan: dict[str, dict] = {}
    for i, tur in enumerate(SORU_TUR_SIRASI):
        aday_json = None
        for q in sonuc["questions"]:
            if not isinstance(q, dict):
                continue
            if int(q.get("question_number") or 0) == i + 1:
                aday_json = q
                break
        if aday_json is None and i < len(sonuc["questions"]):
            aday_json = sonuc["questions"][i] if isinstance(sonuc["questions"][i], dict) else None
        if not aday_json:
            continue
        ic = _json_sorudan_ic(aday_json, tur=tur)
        if ic and _kalite_ok(ic, tur=tur, siki=True):
            toplanan[tur] = ic
    return toplanan if len(toplanan) >= 3 else None


def _asama_soru_uret(
    baglam: dict[str, Any],
    plan: dict[str, Any],
    *,
    tur: str,
    onceki_metinler: list[str],
    red_notu: str = "",
) -> dict[str, Any] | None:
    onceki = "\n".join(f"- {m[:160]}" for m in onceki_metinler[-8:]) or "- (yok)"
    red_blok = f"\nÖNCEKİ DENEME REDDEDİLDİ. Düzelt:\n{red_notu}\n" if red_notu else ""
    veri_notu = ""
    if _SLOT_PLAN[tur].get("veri_zorunlu"):
        veri_notu = (
            "Bu soruda data_type 'table' veya 'list' olmalı ve data dolu gelmeli. "
            "Olmayan görsele atıf YASAK.\n"
        )

    prompt = f"""
Tek bir çoktan seçmeli soru üret (A-B-C-D). Yalnızca JSON döndür.

{_baglam_metni(baglam)}

Hedef zorluk seviyesi: {plan.get('difficulty') or _SLOT_PLAN[tur]['zorluk']}
Soru slotu / türü: {tur}
Slot hedefi: {_SLOT_PLAN[tur]['hedef']}
Plan:
- Bağlam fikri: {plan.get('context_idea', '')}
- Veri fikri: {plan.get('data_idea', '')}
- Düşünme becerisi: {plan.get('cognitive_skill', '')}
- Hedef yanılgı: {plan.get('target_misconception', '')}
- Çeldirici mantıkları: {plan.get('distractor_logics', [])}
- Yeni nesil özellikleri: {plan.get('new_gen_features', [])}

{veri_notu}
Video yardımcı kaynaktır; sorunun temeli sınıf + konu + kazanımdır.
Yanlış seçenekler rastgele olmasın; her biri belirli öğrenci hatasına dayansın.
«Yukarıdakilerin hepsi / Hiçbiri» YASAK.
Bu testte daha önce üretilen soruları tekrarlama:
{onceki}
{red_blok}
JSON şeması:
{_soru_json_semasi_ornek()}
"""
    sonuc = ai_json_uret(
        system=_YAZAR_ROL + "\nYalnızca geçerli JSON döndür. Tek soru üret.",
        user_prompt=prompt,
        temperature=0.5,
        max_tokens=2200,
    )
    if not sonuc or not isinstance(sonuc, dict):
        return None
    if "questions" in sonuc and isinstance(sonuc["questions"], list) and sonuc["questions"]:
        sonuc = sonuc["questions"][0]
    return _json_sorudan_ic(sonuc, tur=tur)


# ---------------------------------------------------------------------------
# Aşama 3 — Bağımsız denetim
# ---------------------------------------------------------------------------

def _asama_denetle(
    baglam: dict[str, Any],
    soru: dict[str, Any],
    *,
    tur: str,
) -> dict[str, Any]:
    """QC sonucu: approved bool, score int, reasons list, raw dict."""
    meta = soru.get("_meta") or {}
    prompt = f"""
Aşağıdaki soruyu bağımsız ölçme-değerlendirme uzmanı olarak denetle.
Yeniden yazma; yalnızca değerlendir.

Sınıf: {baglam['sinif']}
Ders: {baglam['ders']}
Konu: {baglam['konu']}
Kazanım: {baglam['kazanim']}
Slot: {tur} — {_SLOT_PLAN[tur]['hedef']}
Beklenen zorluk: {_SLOT_PLAN[tur]['zorluk']}

SORU METNİ:
{soru.get('soru_metni')}

A) {soru.get('secenek_a')}
B) {soru.get('secenek_b')}
C) {soru.get('secenek_c')}
D) {soru.get('secenek_d')}
Doğru cevap (üretici): {soru.get('dogru_secenek')}
Çözüm: {soru.get('aciklama')}
Üreticinin «neden bağlam temelli» açıklaması: {meta.get('why_new_gen', '')}

Ölçütler (her biri için kısa not):
1. Sınıf seviyesine uygun mu?
2. MEB kazanımını gerçekten ölçüyor mu?
3. Yalnızca ezber veya tek işlem mi?
4. Bağlam çözümün anlamlı parçası mı?
5. En az iki aşamalı düşünme var mı?
6. Yalnızca bir kesin doğru cevap var mı?
7. Cevap anahtarı ve çözüm doğru mu? (Kendin çöz)
8. Çeldiriciler gerçek öğrenci hatalarına dayanıyor mu?
9. Eksik veya gereksiz bilgi var mı?
10. Dil / yazım doğru mu?
11. Önceki soruların isim-sayı değişmiş kopyası mı?
12. Sınıf üstü bilgi gerektiriyor mu?

Puanlar (toplam 100):
- kazanim_uyumu: 20
- baglam_kalitesi: 20
- akil_yurutme: 20
- celdirici: 15
- teknik_dogruluk: 15
- dil: 10

RED (herhangi biri varsa approved=false):
- Toplam < 85
- Birden fazla doğru cevap
- Cevap anahtarı hatalı
- Kazanımla uyumsuz
- Yalnızca tek adımlı basit işlem
- Bağlam çıkarıldığında soru hiçbir şey kaybetmiyorsa
- Olmayan görsel/tabloya atıf

JSON:
{{
  "approved": true,
  "total_score": 90,
  "scores": {{
    "kazanim_uyumu": 18,
    "baglam_kalitesi": 18,
    "akil_yurutme": 18,
    "celdirici": 14,
    "teknik_dogruluk": 14,
    "dil": 8
  }},
  "reject_reasons": [],
  "context_essential": true,
  "answer_verified": true,
  "feedback_for_rewrite": ""
}}
"""
    sonuc = ai_json_uret(
        system=_DENETCI_ROL + "\nYalnızca geçerli JSON döndür.",
        user_prompt=prompt,
        temperature=0.15,
        max_tokens=1400,
    )
    if not sonuc or not isinstance(sonuc, dict):
        return {
            "approved": False,
            "total_score": 0,
            "reject_reasons": ["QC yanıtı alınamadı"],
            "feedback_for_rewrite": "Denetim yanıtı boş; soruyu yeniden ve daha net üret.",
        }

    score = int(sonuc.get("total_score") or 0)
    approved = bool(sonuc.get("approved"))
    reasons = list(sonuc.get("reject_reasons") or [])

    # Sunucu tarafı sert redler
    if score < _QC_ESIK:
        approved = False
        reasons.append(f"Toplam puan {_QC_ESIK} altında ({score})")
    if sonuc.get("context_essential") is False and _SLOT_PLAN[tur].get("baglam_zorunlu"):
        approved = False
        reasons.append("Bağlam çıkarıldığında soru kaybetmiyor")
    if sonuc.get("answer_verified") is False:
        approved = False
        reasons.append("Cevap anahtarı doğrulanamadı")
    if not _kalite_ok(soru, tur=tur, siki=True):
        approved = False
        reasons.append("Sunucu kalite kuralı başarısız")

    return {
        "approved": approved,
        "total_score": score,
        "reject_reasons": reasons,
        "feedback_for_rewrite": (sonuc.get("feedback_for_rewrite") or "").strip(),
        "scores": sonuc.get("scores") or {},
    }


def _red_kaydet(konu: KonuKatalogu, tur: str, nedenler: list[str], deneme: int) -> None:
    logger.warning(
        "konu_destek QC red konu=%s tur=%s deneme=%s neden=%s",
        konu.pk,
        tur,
        deneme,
        "; ".join(nedenler)[:400],
    )
    try:
        onbellege_yaz(
            tur="konu_destek_qc_red",
            anahtar=f"{konu.pk}-{tur}-{deneme}-{_AI_SURUM}",
            icerik={
                "konu_id": konu.pk,
                "tur": tur,
                "deneme": deneme,
                "nedenler": nedenler,
                "surum": _AI_SURUM,
            },
            yapay_zeka=True,
        )
    except Exception:  # noqa: BLE001 — kayıt akışı bozmasın
        pass


# ---------------------------------------------------------------------------
# Üç aşamalı üretim orkestrasyonu
# ---------------------------------------------------------------------------

def _llm_sorulari_uret(
    konu: KonuKatalogu,
    adet: int = 5,
    *,
    talebe=None,
) -> list[dict] | None:
    if not ai_llm_aktif_mi():
        return None

    talebe_id = getattr(talebe, "pk", None)
    anahtar = _ai_anahtar(konu, talebe_id)
    onbellek = onbellekten_al("konu_destek_test", anahtar)
    if onbellek and isinstance(onbellek.get("sorular"), list):
        adaylar = []
        for s in onbellek["sorular"]:
            if not isinstance(s, dict):
                continue
            tur = s.get("soru_turu") or "temel"
            if _kalite_ok(s, tur=tur):
                # meta alanlarını talebeye taşıma
                temiz = {k: v for k, v in s.items() if not k.startswith("_")}
                adaylar.append(temiz)
        if len(adaylar) >= adet and _sunucu_set_dogrula(
            adaylar[:adet], adet, siki=True
        ):
            return adaylar[:adet]

    baglam = _uretim_baglami(konu, talebe)
    planlar = _asama_planla(baglam)
    if not planlar:
        logger.warning("konu_destek plan üretilemedi konu=%s", konu.pk)
        return None

    plan_by_tur = {
        str(p.get("slot") or "").strip().lower(): p for p in planlar if isinstance(p, dict)
    }
    aday_havuz = _asama_set_uret(baglam, planlar) or {}

    onaylilar: dict[str, dict] = {}
    onceki_metinler: list[str] = list(baglam.get("onceki_sorular") or [])

    for tur in SORU_TUR_SIRASI[:adet]:
        plan = plan_by_tur.get(tur) or {
            "slot": tur,
            "question_number": SORU_TUR_SIRASI.index(tur) + 1,
            "difficulty": _SLOT_PLAN[tur]["zorluk"],
            "context_idea": f"{baglam['konu']} günlük hayat bağlamı",
            "data_idea": "table" if tur == "uygulama" else "yok",
            "cognitive_skill": "yorumlama",
            "target_misconception": "eksik işlem / kavram yanılgısı",
            "distractor_logics": ["eksik işlem", "ters yorum", "ara sonuç"],
        }
        red_notu = ""
        basarili = None
        # 1. deneme: set üretiminden gelen aday; sonrası tekil yeniden üretim
        for deneme in range(1, _MAX_DENEME + 1):
            if deneme == 1 and tur in aday_havuz:
                ham = aday_havuz[tur]
            else:
                ham = _asama_soru_uret(
                    baglam,
                    plan,
                    tur=tur,
                    onceki_metinler=onceki_metinler,
                    red_notu=red_notu,
                )
            if not ham or not _kalite_ok(ham, tur=tur, siki=True):
                red_notu = (
                    "Üretilen soru sunucu kalite kontrolünden geçmedi. "
                    "Daha uzun, bağlam temelli, tek adımlı olmayan soru yaz. "
                    "Bağlam çıkınca soru bozulmalı."
                )
                _red_kaydet(konu, tur, ["sunucu_kalite"], deneme)
                continue

            qc = _asama_denetle(baglam, ham, tur=tur)
            if qc["approved"] and qc["total_score"] >= _QC_ESIK:
                basarili = {k: v for k, v in ham.items() if k != "_meta"}
                basarili["_qc_score"] = qc["total_score"]
                break

            nedenler = qc.get("reject_reasons") or ["QC reddi"]
            _red_kaydet(konu, tur, nedenler, deneme)
            red_notu = qc.get("feedback_for_rewrite") or "; ".join(nedenler)
            if not red_notu:
                red_notu = (
                    "Bağlam zorunlu olsun; bağlam çıkınca soru bozulmalı. "
                    "Tek adımlı ezber sorusu yazma."
                )

        if basarili:
            onaylilar[tur] = basarili
            onceki_metinler.append(basarili["soru_metni"][:200])
        else:
            logger.error(
                "konu_destek: %s slotu %s denemede onaylanmadı konu=%s",
                tur,
                _MAX_DENEME,
                konu.pk,
            )

    # Eksik slotları bankadan doldur (hatalı AI sorusu GÖSTERİLMEZ)
    yedek = {s["soru_turu"]: s for s in _kural_tabanli_sorular(konu, 5)}
    sirali: list[dict] = []
    for tur in SORU_TUR_SIRASI[:adet]:
        if tur in onaylilar:
            s = dict(onaylilar[tur])
            s.pop("_qc_score", None)
            sirali.append(s)
        elif tur in yedek:
            sirali.append(yedek[tur])

    if len(sirali) < adet or not _sorular_benzersiz_mi(sirali):
        return None
    # Karışık AI+banka setinde sıkı doğrulama AI slotlarını zaten geçirdi
    if not _sunucu_set_dogrula(sirali, adet, siki=False):
        return None

    try:
        onbellege_yaz(
            tur="konu_destek_test",
            anahtar=anahtar,
            icerik={"sorular": sirali, "surum": _AI_SURUM, "baglam": {
                "sinif": baglam["sinif"],
                "konu": baglam["konu"],
                "basari": baglam["basari_duzeyi"],
            }},
            yapay_zeka=True,
        )
    except Exception:  # noqa: BLE001
        logger.exception("konu_destek onbellek yazılamadı")

    return sirali[:adet]


def _sorulari_kaydet(konu: KonuKatalogu, ham_sorular: list[dict]) -> list[KonuSorusu]:
    # Eski aktif havuzu kapat; aksi halde zayıf sorular sırada kalır.
    konu.sorular.filter(aktif=True).update(aktif=False)

    kayitlar: list[KonuSorusu] = []
    for index, satir in enumerate(ham_sorular, start=1):
        defaults = {
            "secenek_a": satir["secenek_a"][:500],
            "secenek_b": satir["secenek_b"][:500],
            "secenek_c": satir["secenek_c"][:500],
            "secenek_d": satir["secenek_d"][:500],
            "dogru_secenek": satir["dogru_secenek"],
            "aciklama": (satir.get("aciklama") or "").strip(),
            "sira": index,
            "aktif": True,
        }
        if hasattr(KonuSorusu, "soru_turu"):
            defaults["soru_turu"] = satir.get("soru_turu") or "temel"
        soru, _ = KonuSorusu.objects.update_or_create(
            konu=konu,
            soru_metni=satir["soru_metni"],
            defaults=defaults,
        )
        kayitlar.append(soru)
    return kayitlar


_ZAYIF_BANKA_IZLERI = (
    "Bir paragrafın «ne hakkında» olduğu sorusunun kısa cevabı",
    "«Düzenli kitap okumak kelime dağarcığını geliştirir ve hayal gücünü besler.» Bu cümlede asıl vurgulanan nedir?",
    "Elif, bir paragraf sorusunda yalnızca ilk cümleye bakıp ana düşünceyi seçmiştir; oysa ana düşünce sonda verilmiştir.",
)


def _havuz_sifirla(konu: KonuKatalogu) -> None:
    """Eski basit/meta / düşük kalite soruları kapat."""
    for soru in konu.sorular.filter(aktif=True):
        metin = soru.soru_metni or ""
        kapat = bool(_META_KALIPLAR.search(metin))
        if len(metin) < 70:
            kapat = True
        if _COK_BASIT.match(metin.strip()) and len(metin) < 90:
            kapat = True
        if metin.startswith("12 ile 18") or metin.startswith("2/3 = 8/x"):
            kapat = True
        if any(iz in metin for iz in _ZAYIF_BANKA_IZLERI):
            kapat = True
        # Tanım ezberi / meta seviye kısa kök
        if "kısa cevabı hangisidir" in metin.casefold():
            kapat = True
        if kapat:
            soru.aktif = False
            soru.save(update_fields=["aktif"])


def konu_ai_sorulari_hazirla(
    konu: KonuKatalogu,
    hedef: int = 5,
    *,
    talebe=None,
    yenile: bool = False,
) -> tuple[list[KonuSorusu], str]:
    _havuz_sifirla(konu)

    mevcut = list(konu.sorular.filter(aktif=True).order_by("sira", "id")[:hedef])

    def _havuz_kaliteli(sorular: list[KonuSorusu]) -> bool:
        if len(sorular) < hedef:
            return False
        zayif = sum(1 for s in sorular if len(s.soru_metni or "") < 90)
        baglamsiz = sum(
            1
            for s in sorular
            if (getattr(s, "soru_turu", "") in {"kavrama", "uygulama", "yeni_nesil", "kisisel"})
            and len(s.soru_metni or "") < 140
        )
        return zayif <= 1 and baglamsiz == 0

    if yenile and mevcut:
        for s in mevcut:
            s.aktif = False
            s.save(update_fields=["aktif"])
        mevcut = []

    # Ortak (kişisel olmayan) istek: kaliteli havuz varsa LLM'e gitme
    if talebe is None and not yenile and _havuz_kaliteli(mevcut):
        return mevcut[:hedef], "havuz"

    if talebe is None and mevcut and not _havuz_kaliteli(mevcut):
        for s in mevcut:
            s.aktif = False
            s.save(update_fields=["aktif"])

    llm = _llm_sorulari_uret(konu, adet=hedef, talebe=talebe)
    kaynak = "ai"
    if not llm:
        if talebe is not None and _havuz_kaliteli(
            list(konu.sorular.filter(aktif=True).order_by("sira", "id")[:hedef])
        ):
            return (
                list(konu.sorular.filter(aktif=True).order_by("sira", "id")[:hedef]),
                "havuz",
            )
        llm = _kural_tabanli_sorular(konu, adet=hedef)
        kaynak = "kural"

    yeni = _sorulari_kaydet(konu, llm)
    return yeni[:hedef], kaynak
