"""Dijital Etüt mini test — bağlam temelli / yeni nesil soru üretimi.

Ana yapı (her ders için aynı sözleşme):
1. temel      — kısa ama konu özünü ölçer
2. kavrama    — kavramı örnekle ayırt ettirir
3. uygulama   — işlem / uygulama
4. yeni_nesil — gerçek hayat bağlamı, uzun gövde, yorum
5. kisisel    — tipik öğrenci hatasına yönelik

Meta soru, aşırı kısa işlem ve sınıf dışı içerik reddedilir.
"""

from __future__ import annotations

import re
from typing import Any

from takip.ai_gateway import ai_json_uret, ai_llm_aktif_mi, onbellekten_al, onbellege_yaz
from takip.konu_destek_models import KonuKatalogu, KonuSorusu

_AI_SURUM = "v5-yeninesil"

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


def _ai_anahtar(konu: KonuKatalogu) -> str:
    return f"konu-{konu.pk}-{_AI_SURUM}-{konu.sinif_seviyesi}"


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


_META_KALIPLAR = re.compile(
    r"(temel kavram|en sık yapılan hata|pekiştir|etkili yöntem|"
    r"soru gelme olasılığı|zayıfsan|hiç çalışmamak|yalnızca ezber|"
    r"sınavda hiç|konuyu atlamak|cevap anahtarına|konuyu hiç çalış|"
    r"nasıl çalışmalı|videoyu izleyip)",
    re.I,
)

# Aşırı basit tek satır işlem (yeni nesil / uygulama için yetersiz örnekler)
_COK_BASIT = re.compile(
    r"^(?:\d+\s*(?:ile|/|:)\s*\d+|[\d²³⁰¹²]+)\s*",
    re.I,
)


def _meta_soru_mu(soru: dict) -> bool:
    metin = f"{soru.get('soru_metni', '')} {soru.get('secenek_a', '')}"
    return bool(_META_KALIPLAR.search(metin))


def _kalite_ok(soru: dict, *, tur: str) -> bool:
    if not isinstance(soru, dict):
        return False
    metin = (soru.get("soru_metni") or "").strip()
    if len(metin) < 40:
        return False
    if _meta_soru_mu(soru):
        return False
    dogru = str(soru.get("dogru_secenek", "")).upper()[:1]
    if dogru not in {"A", "B", "C", "D"}:
        return False
    for k in ("secenek_a", "secenek_b", "secenek_c", "secenek_d"):
        if len((soru.get(k) or "").strip()) < 1:
            return False
    if tur == "yeni_nesil":
        # Bağlam: en az iki cümle veya 120+ karakter
        if len(metin) < 120 and metin.count(".") + metin.count("?") < 2:
            return False
    if tur in {"uygulama", "yeni_nesil", "kisisel"} and _COK_BASIT.match(metin):
        # Tek başına "12 ile 18'in oranı..." gibi gövdesiz sorular reddedilir
        if len(metin) < 90:
            return False
    return True


# ---------------------------------------------------------------------------
# Sınıf + konu anahtarlı banka — her sette 5 tip zorunlu
# ---------------------------------------------------------------------------

def _banka_oran() -> list[dict]:
    return [
        _soru(
            "temel",
            "Bir pastanın 12 diliminden 4’ünü Ayşe, kalanını Ali yiyor. "
            "Ayşe’nin yediği dilimin Ali’nin yediğine oranı sadeleştirilmiş haliyle hangisidir?",
            "1/2",
            "1/3",
            "2/3",
            "3/4",
            "A",
            "Ayşe 4, Ali 8 dilim → 4/8 = 1/2.",
        ),
        _soru(
            "kavrama",
            "Aşağıdaki durumlardan hangisi «doğru orantı»ya örnektir?",
            "İşçi sayısı arttıkça işin bitiş süresi azalır",
            "Alınan elma kg’ı arttıkça ödenen ücret aynı oranda artar",
            "Hız arttıkça aynı yolu alma süresi artar",
            "Depodaki su azaldıkça musluk sayısı artar",
            "B",
            "Biri artarken diğeri aynı oranda artıyorsa doğru orantıdır.",
        ),
        _soru(
            "uygulama",
            "Bir okulda kızların erkeklere oranı 3/5’tir. Sınıfta 15 kız vardır. "
            "Aynı orana göre erkek sayısı kaçtır?",
            "9",
            "20",
            "25",
            "30",
            "C",
            "3/5 = 15/e → 3e = 75 → e = 25.",
        ),
        _soru(
            "yeni_nesil",
            "Okul kooperatifi gezi için minibüs kiralayacaktır. 1 minibüs 14 öğrenci "
            "almaktadır. 3 minibüsle 42 öğrenci taşınabilmiştir.\n\n"
            "Öğrenci işleri, aynı oranla 5 minibüs kiralandığında kaç öğrencinin "
            "taşınabileceğini hesaplamaktadır. Doğru sonuç hangisidir?",
            "56",
            "60",
            "70",
            "84",
            "C",
            "1 minibüs → 14 öğrenci; 5 × 14 = 70.",
        ),
        _soru(
            "kisisel",
            "Emre, 2/3 = 8/x orantısını çözerken «payları ve paydaları kendi içinde "
            "topladım» diyerek x = 13 bulmuştur. Emre’nin hatası nedir ve doğru x nedir?",
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
            "Zeynep pastanın 3/8’ini paylaştı. Pastanın kalanı hangisidir?",
            "3/8",
            "5/8",
            "1/2",
            "1/8",
            "B",
            "1 − 3/8 = 5/8.",
        ),
        _soru(
            "kavrama",
            "Aşağıdaki kesirlerden hangisi 1/2 ile aynı büyüklüktedir?",
            "2/5",
            "3/6",
            "3/8",
            "2/6",
            "B",
            "3/6 = 1/2.",
        ),
        _soru(
            "uygulama",
            "Bir şişede 4/5 litre meyve suyu vardır. 1/5 litre içilirse kaç litre kalır?",
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
            "1 − 1/4 = 3/4; 3/4’ün 1/3’ü = 1/4 içilir; kalan 3/4 − 1/4 = 1/2.",
        ),
        _soru(
            "kisisel",
            "Mert, 1/2 + 1/4 işleminde paydaları toplamadan payları toplayıp 2/6 bulmuştur. "
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
            "«Düzenli kitap okumak kelime dağarcığını geliştirir ve hayal gücünü "
            "besler.» Bu cümlede asıl vurgulanan nedir?",
            "Kitap fiyatları",
            "Kitap okumanın yararları",
            "Okul ödevleri",
            "Kütüphane saatleri",
            "B",
            "Ana düşünce kitap okumanın yararlarıdır.",
        ),
        _soru(
            "kavrama",
            "Bir paragrafın «ne hakkında» olduğu sorusunun kısa cevabı hangisidir?",
            "Ana düşünce",
            "Konu",
            "Başlık zorunluluğu",
            "Yazarın kimliği",
            "B",
            "Konu: ne anlatıldığıdır.",
        ),
        _soru(
            "uygulama",
            "«Ormanlar oksijen üretir, canlılara yuva olur ve erozyonu önler. "
            "Bu nedenle ormanları korumak geleceğimizi korumaktır.»\n"
            "Bu parçanın ana düşüncesi hangisidir?",
            "Ormanlar yalnızca hayvanlar içindir",
            "Ormanlar önemlidir ve korunmalıdır",
            "Erozyon hiç olmaz",
            "Oksijen sadece denizden gelir",
            "B",
            "Parça ormanların önemini ve korunmasını vurgular.",
        ),
        _soru(
            "yeni_nesil",
            "Öğretmen tahtaya şu metni yazmıştır:\n\n"
            "«Sabahları erken kalkan Ege, önce kısa bir yürüyüş yapar. "
            "Sonra kahvaltısını eder ve ödevlerine başlar. Bu düzen sayesinde "
            "hem enerjik hisseder hem de derslerinde daha başarılı olur.»\n\n"
            "Bu paragraf için en uygun başlık hangisidir?",
            "Kahvaltı Çeşitleri",
            "Düzenli Günün Yararları",
            "Yürüyüş Ayakkabıları",
            "Ödevlerin Zorluğu",
            "B",
            "Metin düzenli günün olumlu etkisini anlatır.",
        ),
        _soru(
            "kisisel",
            "Elif, bir paragraf sorusunda yalnızca ilk cümleye bakıp ana düşünceyi "
            "seçmiştir; oysa ana düşünce sonda verilmiştir. Elif’in hatası nedir?",
            "Paragrafı bütünüyle okumadan karar vermek",
            "Şıkları okumak",
            "Başlık aramak",
            "Yardımcı düşünceyi bulmak",
            "A",
            "Ana düşünce girişte veya sonda olabilir; tüm paragraf okunmalıdır.",
        ),
    ]


def _banka_madde() -> list[dict]:
    return [
        _soru(
            "temel",
            "Sıcak çaydanlığa dokunan metal kaşık hızla ısınır. Bu durum metalin "
            "hangi özelliği ile açıklanır?",
            "Isı yalıtkanlığı",
            "Isı iletkenliği",
            "Elektrik yalıtkanlığı",
            "Saydamlık",
            "B",
            "Metaller ısıyı iyi iletir.",
        ),
        _soru(
            "kavrama",
            "Buzun suya dönüşmesi hangi hâl değişimidir?",
            "Donma",
            "Erime",
            "Yoğuşma",
            "Buharlaşma",
            "B",
            "Katı → sıvı = erime.",
        ),
        _soru(
            "uygulama",
            "Kışın evlerin dış cephesine köpük yalıtım yapılır. Bu uygulamanın "
            "temel amacı nedir?",
            "Evi daha ağır yapmak",
            "Isı kaybını azaltmak",
            "Sesı artırmak",
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
            "yanlış yapmıştır. Doğru ayrım hangisidir?",
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
    """Banka yoksa bile 5 tipli, sınıf+konu bağlamlı yedek set."""
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
    # Tip sırasına göre diz
    by_tur = {s["soru_turu"]: s for s in temiz}
    sirali = [by_tur[t] for t in SORU_TUR_SIRASI if t in by_tur]
    if len(sirali) < adet:
        sirali.extend([s for s in temiz if s not in sirali])
    return sirali[:adet]


def _llm_sorulari_uret(konu: KonuKatalogu, adet: int = 5) -> list[dict] | None:
    if not ai_llm_aktif_mi():
        return None

    anahtar = _ai_anahtar(konu)
    onbellek = onbellekten_al("konu_destek_test", anahtar)
    if onbellek and isinstance(onbellek.get("sorular"), list):
        adaylar = []
        for s in onbellek["sorular"]:
            if not isinstance(s, dict):
                continue
            tur = s.get("soru_turu") or "temel"
            if _kalite_ok(s, tur=tur):
                adaylar.append(s)
        if len(adaylar) >= adet:
            return adaylar[:adet]

    system = (
        "Sen MEB ortaokul müfredatına ve LGS tarzı yeni nesil soru yazımına hakim bir öğretmensin. "
        "Yalnızca geçerli JSON döndür. "
        "YASAK: meta sorular (nasıl çalışmalı, temel kavram nedir, en sık hata). "
        "YASAK: tek satırlık aşırı basit işlem sorusu (özellikle yeni_nesil için). "
        "Her soru sınıf seviyesine uygun, tek doğru cevaplı olsun."
    )
    prompt = f"""
{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} — «{konu.konu_ad}» için tam 5 soru üret.

Zorunlu soru_turu sırası (her birinden TAM 1 tane):
1) temel
2) kavrama
3) uygulama
4) yeni_nesil  — gerçek hayat bağlamı, en az 2-3 cümle senaryo, sonra soru
5) kisisel     — tipik öğrenci yanlışına göre

yeni_nesil kuralları:
- Bağlam uydurma ama mantıklı olsun (okul, market, yol, laboratuvar vb.)
- Sayısal derslerde veriyi senaryoya göm
- Şıklar gerçek cevaplar olsun

JSON:
{{
  "sorular": [
    {{
      "soru_turu": "temel",
      "soru_metni": "...",
      "secenek_a": "...",
      "secenek_b": "...",
      "secenek_c": "...",
      "secenek_d": "...",
      "dogru_secenek": "A",
      "aciklama": "Kısa çözüm"
    }}
  ]
}}
"""
    llm = ai_json_uret(system=system, user_prompt=prompt, temperature=0.45, max_tokens=3200)
    if not llm or not isinstance(llm.get("sorular"), list):
        return None

    toplanan: dict[str, dict] = {}
    for satir in llm["sorular"]:
        if not isinstance(satir, dict):
            continue
        tur = str(satir.get("soru_turu") or "").strip().lower()
        if tur not in SORU_TUR_SIRASI:
            # sıraya göre ata
            for t in SORU_TUR_SIRASI:
                if t not in toplanan:
                    tur = t
                    break
        dogru = str(satir.get("dogru_secenek", "A")).strip().upper()[:1]
        if dogru not in {"A", "B", "C", "D"}:
            dogru = "A"
        aday = {
            "soru_turu": tur,
            "soru_metni": (satir.get("soru_metni") or "").strip(),
            "secenek_a": (satir.get("secenek_a") or "").strip() or "—",
            "secenek_b": (satir.get("secenek_b") or "").strip() or "—",
            "secenek_c": (satir.get("secenek_c") or "").strip() or "—",
            "secenek_d": (satir.get("secenek_d") or "").strip() or "—",
            "dogru_secenek": dogru,
            "aciklama": (satir.get("aciklama") or "").strip(),
        }
        if not _kalite_ok(aday, tur=tur):
            continue
        if tur not in toplanan:
            toplanan[tur] = aday

    if len(toplanan) < 4:
        return None

    # Eksik tipleri bankadan tamamla
    yedek = {s["soru_turu"]: s for s in _kural_tabanli_sorular(konu, 5)}
    sirali = []
    for tur in SORU_TUR_SIRASI:
        if tur in toplanan:
            sirali.append(toplanan[tur])
        elif tur in yedek:
            sirali.append(yedek[tur])

    if len(sirali) < adet:
        return None

    onbellege_yaz("konu_destek_test", anahtar, {"sorular": sirali})
    return sirali[:adet]


def _sorulari_kaydet(konu: KonuKatalogu, ham_sorular: list[dict]) -> list[KonuSorusu]:
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


def _havuz_sifirla(konu: KonuKatalogu) -> None:
    """Eski basit/meta soruları kapat; yeni nesil sete yer aç."""
    for soru in konu.sorular.filter(aktif=True):
        metin = soru.soru_metni or ""
        kapat = bool(_META_KALIPLAR.search(metin))
        if len(metin) < 50:
            kapat = True
        if _COK_BASIT.match(metin.strip()) and len(metin) < 90:
            kapat = True
        # Eski kısa banka soruları
        if metin.startswith("12 ile 18") or metin.startswith("2/3 = 8/x"):
            kapat = True
        if kapat:
            soru.aktif = False
            soru.save(update_fields=["aktif"])


def konu_ai_sorulari_hazirla(konu: KonuKatalogu, hedef: int = 5) -> tuple[list[KonuSorusu], str]:
    _havuz_sifirla(konu)

    mevcut = list(konu.sorular.filter(aktif=True).order_by("sira", "id")[:hedef])
    # Havuzda 5 tip yoksa yeniden üret
    if len(mevcut) >= hedef:
        # Hâlâ basit kaldıysa yenile
        zayif = sum(1 for s in mevcut if len(s.soru_metni or "") < 70)
        if zayif <= 1:
            return mevcut[:hedef], "havuz"
        for s in mevcut:
            s.aktif = False
            s.save(update_fields=["aktif"])
        mevcut = []

    llm = _llm_sorulari_uret(konu, adet=hedef)
    kaynak = "ai"
    if not llm:
        llm = _kural_tabanli_sorular(konu, adet=hedef)
        kaynak = "kural"

    yeni = _sorulari_kaydet(konu, llm)
    return yeni[:hedef], kaynak
