"""Panel asistanı — doğal dil analizi, site bağlamı, konuşma birleştirme."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from django.contrib.auth.models import User

from takip.models import SinifSube
from takip.permissions.scope import yetkili_talebeler
from takip.permissions.service import can, kullanici_birincil_rol_slug
from takip.panel_permissions import rol_etiketi
from takip.talebe_liste_raporu_service import erisilebilir_siniflar, sinif_etiketi_goster


@dataclass
class AnalizSonuc:
    birlesik_mesaj: str
    niyet: str = "bilinmiyor"
    siniflar: list[SinifSube] = field(default_factory=list)
    talebe_adi: str | None = None
    sinav_anahtar: str | None = None
    guven: float = 0.0
    aciklama: str = ""


def _normalize(text: str) -> str:
    text = text.lower().strip()
    for src, dst in {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}.items():
        text = text.replace(src, dst)
    return re.sub(r"\s+", " ", text)


def _sinif_numarasi(sinif_degeri: str) -> str:
    rakamlar = re.sub(r"\D", "", sinif_degeri or "")
    return rakamlar or sinif_degeri.strip()


def _yetkili_siniflar(user: User) -> list[SinifSube]:
    return list(erisilebilir_siniflar(yetkili_talebeler(user)))


def mesaj_birlestir(message: str, history: list[dict]) -> str:
    """Kısa takip cümlelerini önceki mesajla birleştir."""
    msg = (message or "").strip()
    if not msg or not history:
        return msg

    norm = _normalize(msg)
    takip_isareti = any(
        k in norm
        for k in (
            "sadece",
            "hepsi",
            "yine",
            "ama",
            "filtre",
            "sinif",
            "sinifi",
            "siniflar",
            "sube",
            "subesi",
            "onun",
            "bunun",
            "degil",
            "değil",
        )
    )
    kisa = len(msg.split()) <= 6

    if not (kisa or takip_isareti):
        return msg

    onceki = ""
    for item in reversed(history):
        if item.get("role") != "user":
            continue
        onceki_icerik = (item.get("content") or "").strip()
        if onceki_icerik and onceki_icerik != msg:
            onceki = onceki_icerik
            break

    if not onceki:
        return msg

    return f"{onceki} — {msg}"


def sinif_hedefleri_cikar(user: User, text: str) -> list[SinifSube]:
    if " — " in text:
        tail = text.split(" — ", 1)[-1].strip()
        tail_hedef = _sinif_hedefleri_ayristir(user, tail)
        if tail_hedef:
            return tail_hedef
    return _sinif_hedefleri_ayristir(user, text)


def _sinif_hedefleri_ayristir(user: User, text: str) -> list[SinifSube]:
    norm = _normalize(text)
    siniflar = _yetkili_siniflar(user)
    if not siniflar:
        return []

    def sinif_esles(num: str, sube: str | None = None) -> list[SinifSube]:
        hedef = []
        for s in siniflar:
            if _sinif_numarasi(s.sinif) != num:
                continue
            if sube and s.sube.upper() != sube.upper():
                continue
            hedef.append(s)
        return hedef

    # "5.sınıfların", "5. sınıflar sadece"
    if re.search(r"\d+\s*\.\s*siniflar", norm) or re.search(r"\d+\s*siniflar(?:in|in)?", norm):
        num_match = re.search(r"(\d+)\s*(?:\.\s*)?siniflar", norm)
        if num_match:
            return sinif_esles(num_match.group(1))

    # "5. sınıf", "5.sınıfın"
    grade_match = re.search(r"(\d+)\s*\.\s*sinif(?:in|in|un|un)?", norm)
    if grade_match:
        hedef = sinif_esles(grade_match.group(1))
        if hedef:
            return hedef

    # "5-a", "5/a", "5 a şubesi"
    spesifik = re.search(r"(\d+)\s*[-/.]\s*([a-z])\b", norm)
    if spesifik:
        hedef = sinif_esles(spesifik.group(1), spesifik.group(2).upper())
        if hedef:
            return hedef

    sube_match = re.search(r"(\d+)\s+([a-z])\s+sub", norm)
    if sube_match:
        hedef = sinif_esles(sube_match.group(1), sube_match.group(2).upper())
        if hedef:
            return hedef

    return []


def talebe_adi_cikar(text: str) -> str | None:
    norm = _normalize(text)
    patterns = (
        r"(?:talebe|ogrenci)\s+([a-z\s]{3,40})",
        r"([a-z]{2,20}(?:\s+[a-z]{2,20}){0,2})\s+(?:icin|hakkinda|profil|karne)",
        r"([a-z]{2,20}(?:\s+[a-z]{2,20}){0,2})\s+(?:nin|nin|nun|nun)\s",
    )
    stop = {"pdf", "rapor", "sonuc", "liste", "sinif", "sinifi", "okuma", "gönder", "gonder"}
    for pattern in patterns:
        match = re.search(pattern, norm)
        if match:
            ad = match.group(1).strip(" .,—-")
            if len(ad) >= 3 and ad not in stop:
                return ad
    return None


def site_bilgisi_ozeti(user: User) -> str:
    """LLM ve analiz için canlı site özeti."""
    siniflar = _yetkili_siniflar(user)
    sinif_metni = ", ".join(sinif_etiketi_goster(s) for s in siniflar[:24]) or "—"
    talebe_say = yetkili_talebeler(user).count()

    moduller = []
    for kod, ad in (
        ("raporlar", "Raporlar — okuma raporu (kurum geneli veya sınıf bazında PDF)"),
        ("egitim_kitap", "Kitaplar — kitap/zimmet takibi, talebe kitap karnesi PDF, talebe listesi PDF"),
        ("deneme", "Deneme — sınav sonuçları, sıralı sonuç PDF, bireysel sınav karnesi PDF"),
        ("ktt", "KTT — kazanım tarama testleri ve KTT raporu"),
        ("soru_takip", "Soru Takip — günlük çözülen soru kayıtları ve raporları"),
        ("program", "Program — kurum programı PDF"),
        ("imam_muezzin", "Görevler — imam/müezzin listesi PDF"),
        ("temizlik", "Görevler — temizlik listesi PDF"),
        ("yemekcilik", "Görevler — yemekçilik listesi PDF"),
        ("rehberlik", "Rehberlik — öğrenci görüşmeleri"),
        ("veli_iletisim", "İletişim — veli randevuları ve veli takip"),
    ):
        if can(user, kod, "view"):
            moduller.append(f"- {ad}")

    return (
        f"Rol: {rol_etiketi(user) or kullanici_birincil_rol_slug(user) or 'personel'}\n"
        f"Aktif talebe (yetki kapsamı): {talebe_say}\n"
        f"Sınıf/şubeler: {sinif_metni}\n"
        f"Erişebildiği modüller:\n" + ("\n".join(moduller) or "- (modül yetkisi yok)")
    )


_GENEL_SOHBET_KELIMELERI = (
    "naber",
    "naberr",
    "nbr",
    "ne haber",
    "ne var ne yok",
    "selam",
    "selamun aleykum",
    "aleykum selam",
    "merhaba",
    "mrb",
    "slm",
    "hey",
    "hello",
    "hi",
    "günaydın",
    "gunaydin",
    "iyi günler",
    "iyi gunler",
    "iyi akşamlar",
    "iyi aksamlar",
    "iyi geceler",
    "nasılsın",
    "nasilsin",
    "nasılsınız",
    "nasilsiniz",
    "naber nasilsin",
    "naber nasılsın",
    "ne yapıyorsun",
    "ne yapiyorsun",
    "teşekkür",
    "tesekkur",
    "teşekkürler",
    "tesekkurler",
    "sağol",
    "sagol",
    "sağ ol",
    "eyvallah",
    "eyv",
    "tamam",
    "peki",
    "anladım",
    "anladim",
    "süper",
    "super",
    "harika",
    "güzel",
    "guzel",
    "hoşça kal",
    "hosca kal",
    "görüşürüz",
    "gorusuruz",
    "bye",
    "bb",
    "kolay gelsin",
    "hayırlı işler",
    "hayirli isler",
    "nası gidiyor",
    "nasil gidiyor",
)

_PEDAGOJIK_SOHBET_KELIMELERI = (
    "basari",
    "analiz",
    "oner",
    "tavsiye",
    "nasil",
    "ne yapmal",
    "ne yapmam",
    "strategi",
    "gelisim",
    "takip et",
    "izleme",
    "degerlendir",
    "performans",
    "ne onerir",
    "rehberlik",
    "motivasyon",
    "veli",
    "gorusme",
    "görüşme",
)


_KONUSMA_ISARETLERI = (
    "konusalim",
    "konuşalım",
    "sohbet",
    "anlat",
    "anlatir misin",
    "anlatır mısın",
    "merak",
    "dusunuyorsun",
    "düşünüyorsun",
    "fikrin",
    "alakali",
    "alakalı",
    "hakkinda",
    "hakkında",
    "ile ilgili",
    "konusunda",
    "nedir",
    "ne demek",
    "acikla",
    "açıkla",
    "yardimci ol",
    "yardımcı ol",
    "biraz",
    "istersen",
    "olur mu",
    "misin",
    "mısın",
    "musun",
    "müsün",
)


def net_panel_komutu_mu(text: str) -> bool:
    """Açık PDF/rapor/veri isteği — sohbet değil."""
    norm = _normalize(text)
    if not norm:
        return False

    if any(k in norm for k in ("pdf", "indir", "excel", "listele", "karsilastir", "karsilastirma")):
        return True

    if any(
        k in norm
        for k in (
            "gonder",
            "gönder",
            "gonderebilir",
            "yollar misin",
            "gönderir misin",
            "gonderir misin",
            "istiyorum",
            "lazim",
            "alabilir miyim",
        )
    ):
        return True

    if "rapor" in norm and any(k in norm for k in ("gonder", "ver", "indir", "pdf", "istiyorum", "lazim")):
        return True
    if "okuma raporu" in norm or ("okuma" in norm and "rapor" in norm):
        return True

    if any(k in norm for k in ("kac talebe", "kac ogrenci", "talebe say", "aktif talebe var")):
        return True

    if re.search(r"\d+\s*[-/.]\s*[a-z]", norm) and any(
        k in norm for k in ("rapor", "pdf", "gonder", "liste", "okuma", "karne")
    ):
        return True

    if talebe_adi_cikar(text) and any(k in norm for k in ("pdf", "karne", "gonder", "profil karne", "bilgi ver")):
        return True

    if any(k in norm for k in ("talebe list", "ogrenci list", "liste pdf", "sinif list")):
        return True

    if any(k in norm for k in ("program pdf", "imam pdf", "temizlik pdf", "yemek pdf")):
        return True

    return False


def konusma_mi(text: str) -> bool:
    """Net panel komutu değilse sohbet say — varsayılan açık."""
    return bool((text or "").strip()) and not net_panel_komutu_mu(text)


def genel_sohbet_mi(text: str) -> bool:
    """Selamlaşma, hal hatır, teşekkür gibi günlük sohbet (panel komutu değil)."""
    norm = _normalize(text)
    if not norm or net_panel_komutu_mu(text):
        return False

    kelimeler = norm.split()
    if len(kelimeler) <= 8 and any(k in norm for k in _GENEL_SOHBET_KELIMELERI):
        return True

    if len(kelimeler) <= 3 and any(
        norm == k or norm.startswith(k + " ") or norm.endswith(" " + k)
        for k in ("selam", "merhaba", "naber", "hey", "mrb", "slm")
    ):
        return True

    return False


def sohbet_sorusu_mu(text: str) -> bool:
    """Günlük sohbet, pedagojik soru veya açık uçlu konuşma."""
    if net_panel_komutu_mu(text):
        return False
    norm = _normalize(text)
    if genel_sohbet_mi(text):
        return True
    if any(k in norm for k in _PEDAGOJIK_SOHBET_KELIMELERI):
        return True
    if any(k in norm for k in _KONUSMA_ISARETLERI):
        return True
    if any(k in norm for k in ("egitim", "takip", "ogrenci", "talebe", "okuma", "kitap", "sinav", "panel")):
        return True
    return konusma_mi(text)


def niyet_analizi(text: str) -> AnalizSonuc:
    norm = _normalize(text)
    sonuc = AnalizSonuc(birlesik_mesaj=text)

    if any(k in norm for k in ("yardim", "ne yapabilir", "neler yapabilir")):
        return AnalizSonuc(text, niyet="yardim", guven=0.95)

    skorlar: dict[str, float] = {}

    if ("okuma" in norm and "rapor" in norm) or "okuma raporu" in norm:
        skorlar["pdf_okuma"] = skorlar.get("pdf_okuma", 0) + 0.9
    if any(k in norm for k in ("kitap", "zimmet", "sayfa okun")) and "rapor" in norm:
        skorlar["pdf_okuma"] = skorlar.get("pdf_okuma", 0) + 0.5

    if any(k in norm for k in ("talebe list", "ogrenci list", "liste pdf", "sinif list")):
        skorlar["pdf_talebe_liste"] = 0.85
    if any(k in norm for k in ("etut", "etudum", "etutum", "grubum")) and any(
        k in norm for k in ("liste", "list", "ogrenci", "talebe", "pdf", "gonder", "ver", "at")
    ):
        skorlar["pdf_talebe_liste"] = max(skorlar.get("pdf_talebe_liste", 0), 0.92)

    if any(k in norm for k in ("profil karne", "profil karn", "karnesi", "kitap karn", "kitap karnesi")):
        skorlar["pdf_profil"] = 0.9

    if any(k in norm for k in ("sinav", "deneme", "sonuc", "siral", "karne")) and "profil" not in norm:
        skorlar["pdf_sinav"] = 0.75

    for pdf_id, keys in (
        ("pdf_program", ("program", "gunluk program")),
        ("pdf_imam", ("imam", "muezzin")),
        ("pdf_temizlik", ("temizlik",)),
        ("pdf_yemek", ("yemek", "yemekci", "mutfak")),
    ):
        if any(k in norm for k in keys) and any(
            k in norm for k in ("pdf", "rapor", "gonder", "ver", "indir", "gönder")
        ):
            skorlar[pdf_id] = 0.8

    if any(
        k in norm
        for k in (
            "kac talebe",
            "kac ogrenci",
            "talebe say",
            "kac aktif talebe",
            "aktif talebe var",
            "kac tane talebe",
        )
    ):
        skorlar["veri_talebe_say"] = 0.9

    if any(k in norm for k in ("okuma ozet", "kitap durum", "okuma durum", "zimmet say")):
        skorlar["veri_okuma"] = 0.85

    if talebe_adi_cikar(text) and any(k in norm for k in ("bilgi", "kim", "hakkinda", "detay")):
        skorlar["talebe_bilgi"] = 0.9

    eylem = any(
        k in norm
        for k in (
            "pdf",
            "indir",
            "gonder",
            "gönder",
            "ver",
            "rapor",
            "gonderir misin",
            "gönderir misin",
            "yollar misin",
            "lazim",
            "istiyorum",
            "alabilir miyim",
        )
    )
    if eylem:
        for key in list(skorlar):
            if key.startswith("pdf_"):
                skorlar[key] += 0.15

    if not skorlar and re.search(r"\d+\s*[-/.]\s*[a-z]", norm) and "sinif" in norm:
        skorlar["pdf_okuma"] = 0.55

    if genel_sohbet_mi(text):
        skorlar["sohbet_danisman"] = max(skorlar.get("sohbet_danisman", 0), 0.94)
    elif sohbet_sorusu_mu(text):
        skorlar["sohbet_danisman"] = max(skorlar.get("sohbet_danisman", 0), 0.86)
    elif konusma_mi(text) and not skorlar:
        skorlar["sohbet_danisman"] = 0.82

    if skorlar:
        en_iyi = max(skorlar, key=skorlar.get)
        if (
            konusma_mi(text)
            and en_iyi != "sohbet_danisman"
            and skorlar[en_iyi] < 0.72
        ):
            skorlar["sohbet_danisman"] = max(skorlar.get("sohbet_danisman", 0), 0.84)
            en_iyi = "sohbet_danisman"

    if skorlar:
        en_iyi = max(skorlar, key=skorlar.get)
        sonuc.niyet = en_iyi
        sonuc.guven = min(skorlar[en_iyi], 1.0)

    sonuc.talebe_adi = talebe_adi_cikar(text)
    return sonuc


def siniflari_coz(user: User, etiketler: list[str]) -> list[SinifSube]:
    """'5-A', '5/A', '5' gibi etiketleri kullanıcının yetkili sınıflarıyla eşleştirir."""
    siniflar = _yetkili_siniflar(user)
    eslesen: list[SinifSube] = []
    for etiket in etiketler or []:
        et = _normalize(str(etiket)).replace(" ", "").replace("/", "-")
        if not et:
            continue
        if et.isdigit():
            eslesen.extend(s for s in siniflar if _sinif_numarasi(s.sinif) == et)
            continue
        for s in siniflar:
            aday = _normalize(sinif_etiketi_goster(s)).replace(" ", "").replace("/", "-")
            if aday == et:
                eslesen.append(s)
    if not eslesen and etiketler:
        eslesen = sinif_hedefleri_cikar(user, " ".join(str(e) for e in etiketler))
    return list(dict.fromkeys(eslesen))


def analiz_et(user: User, message: str, history: list[dict] | None = None) -> AnalizSonuc:
    history = history or []
    birlesik = mesaj_birlestir(message, history)
    kural = niyet_analizi(birlesik)
    kural.birlesik_mesaj = birlesik
    kural.siniflar = sinif_hedefleri_cikar(user, birlesik)

    if not kural.siniflar:
        kural.siniflar = sinif_hedefleri_cikar(user, message)

    return kural
