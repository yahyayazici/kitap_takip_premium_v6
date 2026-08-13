"""Etüt hocası kullanım rehberi — HTML/PDF üretimi."""

from __future__ import annotations

import base64
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import reverse
from django.utils import timezone

from config.branding import PANEL_MODULE_LABEL, PANEL_NAME, PANEL_ORG, PANEL_SHORT, PANEL_TAGLINE
from takip.pdf_utils import html_to_pdf


@dataclass(frozen=True)
class RehberSayfa:
    baslik: str
    yol: str
    ozet: str
    gorsel: str
    adimlar: tuple[str, ...] = ()
    maddeler: tuple[str, ...] = ()
    not_metni: str = ""


@dataclass(frozen=True)
class RehberMenu:
    anahtar: str
    dosya: str
    baslik: str
    giris: str
    sayfalar: tuple[RehberSayfa, ...]


def _s(
    baslik: str,
    yol: str,
    ozet: str,
    gorsel: str,
    *,
    adimlar: tuple[str, ...] = (),
    maddeler: tuple[str, ...] = (),
    not_metni: str = "",
) -> RehberSayfa:
    return RehberSayfa(baslik, yol, ozet, gorsel, adimlar, maddeler, not_metni)


REHBER_MENULER: tuple[RehberMenu, ...] = (
    RehberMenu(
        "menu_genel",
        "menu-genel.png",
        "Genel",
        "Günlük panel ve kurum genel işlemlerine hızlı erişim.",
        (
            _s(
                "Ana Sayfa — Günün özeti",
                "Genel → Ana Sayfa",
                "Giriş yaptığınızda /panel/ ana sayfası açılır. Üstte adınız, rolünüz (Etüt Mesulü) "
                "ve bugünün tarihi görünür. Dört özet kart günlük işlerinize hızlı bakış sağlar.",
                "02-panel-ozet.png",
                maddeler=(
                    "Etüt kapsamı: sorumlu olduğunuz sınıf ve talebe sayısı",
                    "İmam & müezzin: bugünün namaz görevlisi",
                    "Yemekçiler: sınıf bazında günlük yemekçi listesi",
                    "Namaza gelmeyenler: etüdünüzden bugün gelmeyen var mı",
                ),
            ),
            _s(
                "Ana Sayfa — Duyurular ve YÇT",
                "Genel → Ana Sayfa",
                "Sol tarafta kurum duyuruları kaydırılabilir kartlar halinde görünür. "
                "Sağ tarafta YÇT aylık takvim özeti vardır; Tam takvim ile ayrıntılı takvime gidersiniz.",
                "02-panel-duyuru.png",
            ),
            _s(
                "Ana Sayfa — Etüt ve dershane programı",
                "Genel → Ana Sayfa",
                "Ana sayfada haftalık program önizlemesi iki kart halinde sunulur: "
                "etüt planı ve dershane programı özeti.",
                "02-panel-etut.png",
                maddeler=(
                    "Etüt — haftalık plan: planlanan, tamamlanan, bekleyen saat sayıları",
                    "Dershane programı: etüt grubunuza atanmış derslerin haftalık özeti",
                    "Planı aç / Programı aç ile tam ekrana geçilir",
                ),
            ),
            _s(
                "Ana Sayfa — Hızlı menüler",
                "Genel → Ana Sayfa",
                "Renkli kutular en sık kullanılan modüllere tek tıkla gider. "
                "Rolünüze göre görünen menüler değişebilir.",
                "02-panel-kisayol.png",
                maddeler=(
                    "Kitap Takip, Talebeler, Etüt Grupları, Günlük Takip",
                    "Veli İletişim, Deneme, KTT, Görevler, Raporlar",
                    "Alttaki şeritte anlık sayılar (talebe, okuma, sınav) özetlenir",
                ),
            ),
            _s(
                "Ana Sayfa — Son aktiviteler",
                "Genel → Ana Sayfa",
                "Sayfanın alt bölümünde dört kart son kayıtları özetler; veri yoksa bilgi mesajı görünür.",
                "02-panel-alt.png",
                maddeler=(
                    "Akış: son sistem aktiviteleri",
                    "Rehberlik: son görüşmeler özeti",
                    "İletişim: son veli ve talebe görüşmeleri",
                    "Takvim: yaklaşan etkinlikler",
                ),
            ),
            _s(
                "YÇT — Yıllık çalışma takvimi",
                "Genel → YÇT",
                "Kurumun yıllık etkinlik ve plan takvimini görürsünüz. "
                "Sınav haftaları, izin günleri ve özel programlar burada takip edilir.",
                "genel-yct.png",
                adimlar=(
                    "Üst menü → Genel → YÇT",
                    "Takvimde ay ve hafta görünümü arasında geçiş yapın",
                    "Etkinlik detayına tıklayarak açıklamayı okuyun",
                ),
            ),
            _s(
                "Vazifelerim",
                "Genel → Vazifelerim",
                "Size atanan kurum vazifelerini ve son tarih hatırlatmalarını görürsünüz.",
                "genel-vazifelerim.png",
                maddeler=(
                    "Atanan görev adı ve açıklaması",
                    "Son tarih / tamamlanma durumu",
                    "Tamamlanan ve bekleyen vazifeler listesi",
                ),
            ),
            _s(
                "Cuma Durumu",
                "Genel → Cuma Durumu",
                "Cuma günü WhatsApp durum görseli oluşturma ve paylaşım ekranı. "
                "Kurum mesajını görsel olarak hazırlayıp veli gruplarına iletebilirsiniz.",
                "genel-cuma-durum.png",
                adimlar=(
                    "Cuma Stüdyosu ekranını açın",
                    "Metin ve görsel seçeneklerini düzenleyin",
                    "Önizlemeyi kontrol edip görseli indirin veya paylaşın",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_program",
        "menu-program.png",
        "Program",
        "Kurum günlük programı ve dershane ders programı.",
        (
            _s(
                "Programlar — Günlük Program",
                "Program → Programlar",
                "Kurumun resmi günlük programını görürsünüz: kalkış, namaz, ders, yemek, istirahat "
                "vb. saat dilimleri tek ekranda listelenir.",
                "program-programlar.png",
                maddeler=(
                    "Program Seç: hangi dönem programı görüntülenecek",
                    "Süre analizi: Günlük / Haftalık / Aylık / Yıllık dağılım",
                    "PDF İndir / Excel İndir — program çıktısı",
                    "Her satır: saat · faaliyet · kategori · süre (dk)",
                ),
            ),
            _s(
                "Dershane Programı",
                "Program → Dershane Programı",
                "Dershane saatlerinde hangi sınıf ve etüt grubunun hangi branş dersini, "
                "hangi öğretmenle alacağını haftalık tablo halinde görürsünüz.",
                "program-dershane-programi.png",
                maddeler=(
                    "Gün seçici: Pzt … Paz",
                    "Özet kartlar: Çakışma · Boş · Ders · Gün",
                    "Filtre: Sınıf · Etüt · Ders · Öğretmen",
                    "PDF / Excel / Kaydet — yetkinize göre",
                ),
                not_metni="Boş hücreler + Ders ile ders atanmamış slotları gösterir.",
            ),
        ),
    ),
    RehberMenu(
        "menu_gorevler",
        "menu-gorevler.png",
        "Görevler",
        "Günlük rotasyon görevleri.",
        (
            _s(
                "İmam / Müezzin",
                "Görevler → İmam / Müezzin",
                "Günlük namaz vazifelerini — hangi gün kimin imam, kimin müezzin olacağını — görürsünüz.",
                "gorevler-imam-muezzin.png",
                maddeler=(
                    "Bugünün görevi kartı: büyük puntoda imam ve müezzin isimleri",
                    "Liste Seç: farklı dönem listeleri arasında geçiş",
                    "Tablo: Tarih · Gün · İmam · Müezzin",
                    "PDF İndir — listeyi dosya olarak alma",
                ),
            ),
            _s(
                "Temizlik",
                "Görevler → Temizlik",
                "Temizlik mahallerinin hangi talebeye atandığını günlük olarak görürsünüz.",
                "gorevler-temizlik.png",
                maddeler=(
                    "Kat zimmeti: sorumlu olduğunuz kat bilgisi",
                    "Gün seçimi ve Göster düğmesi",
                    "Tablo: Kat / Alan · Sorumlu Talebe",
                    "PDF İndir",
                ),
                not_metni="Seçilen günde görev yoksa tablo boş görünür; bu normaldir.",
            ),
            _s(
                "Yemekçilik",
                "Görevler → Yemekçilik",
                "Yemek saatinde sınıf bazında hangi talebenin yemekçi olduğunu görürsünüz. "
                "Sistem otomatik rotasyon yapar; gerekirse görevli değiştirilir.",
                "gorevler-yemekcilik.png",
                maddeler=(
                    "Bugünkü Yemekçiler · Yemekçilik Takvimi · Sıralama Yönetimi",
                    "Önceki Gün / Sonraki Gün ile tarih gezinme",
                    "Sınıf kartları: görevli talebe adı ve şube",
                    "Görevliyi Değiştir açılır listesi",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_kitaplar",
        "menu-kitaplar.png",
        "Kitaplar",
        "Kitap kütüphanesi, zimmet ve okuma takibi.",
        (
            _s(
                "Kitap Ekle",
                "Kitaplar → Kitap Ekle",
                "Kurum kütüphanesine yeni bir eser tanımlarsınız. Kayıttan sonra zimmet, "
                "günlük okuma ve sınav adımlarına geçilir.",
                "kitaplar-kitap-ekle.png",
                adimlar=(
                    "Ad (zorunlu) — kitabın tam adını yazın",
                    "Yazar (isteğe bağlı)",
                    "Toplam sayfa (zorunlu) — okuma ilerlemesi buna göre hesaplanır",
                    "Kitabı Kaydet ile arşive ekleyin",
                ),
            ),
            _s(
                "Günlük Adet Gir",
                "Kitaplar → Günlük Adet Gir",
                "Talebelerin o gün kitapta ulaştığı son sayfayı toplu girersiniz. "
                "Okunan miktar otomatik hesaplanır.",
                "kitaplar-gunluk-adet.png",
                adimlar=(
                    "Üst özet kartlardan aktif kitap sayısını kontrol edin",
                    "Bugünkü Son Sayfa sütununu doldurun",
                    "Bütün Kayıtları Kaydet ile toplu kayıt yapın",
                ),
                not_metni="Aktif zimmet yoksa önce Kitap Zimmetle ile zimmet verin.",
            ),
            _s(
                "Sonuç Gir",
                "Kitaplar → Sonuç Gir",
                "Oluşturduğunuz kitap sınavlarına talebe bazında doğru / yanlış / boş sonuç girişi yaparsınız.",
                "kitaplar-sonuc-gir.png",
                adimlar=(
                    "Sınav listesinden ilgili sınavı seçin",
                    "Her talebe için sonuçları girin",
                    "Kaydet ile sonuçları sisteme yazın",
                ),
                not_metni="Sınav yoksa önce Sınav Oluştur ile sınav tanımlayın.",
            ),
            _s(
                "Zimmetleme",
                "Kitaplar → Zimmetleme",
                "Seçtiğiniz kitabı işaretlediğiniz talebelere tek işlemle zimmetlersiniz.",
                "kitaplar-zimmetleme.png",
                adimlar=(
                    "Kitap, zimmet tarihi ve hedef bitiş tarihini seçin",
                    "Aktif kitabı olan talebeleri atla seçeneğini kullanın",
                    "Talebe kartlarından grubu işaretleyin",
                    "Seçilen Talebelere Zimmetle ile tamamlayın",
                ),
            ),
            _s(
                "Sınav Oluştur",
                "Kitaplar → Sınav Oluştur",
                "Bir kitaba bağlı yeni sınav tanımı: ad, soru sayısı, tarih.",
                "kitaplar-sinav-olustur.png",
                adimlar=(
                    "Kitap seçin (zorunlu)",
                    "Sınav adı ve soru sayısını girin",
                    "Sınav tarihini seçin",
                    "Sınavı Oluştur — sonuçlar Sonuç Gir panelinden girilir",
                ),
            ),
            _s(
                "Okuma Raporları",
                "Kitaplar → Okuma Raporları",
                "Tarih, sınıf ve kitap durumuna göre okuma ve sınav özetini görürsünüz.",
                "kitaplar-okuma-raporlari.png",
                maddeler=(
                    "Başlangıç / Bitiş tarihi · Sınıf/Şube · Kitap Durumu",
                    "Raporu Getir · PDF İndir",
                    "Özet: Toplam Okunan · Aktif Kitap · Geçmiş Kitap · Sınavlar",
                    "Detay tablosu: Talebe · Kitap · Okunan · Toplam",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_egitim",
        "menu-egitim.png",
        "Eğitim",
        "Talebe, sınav ve etüt takip modülleri — etüt hocasının ana iş alanı.",
        (
            _s(
                "Talebeler",
                "Eğitim → Talebeler",
                "Etüt grubunuzdaki talebeleri kart görünümünde görürsünüz.",
                "egitim-talebeler.png",
                maddeler=(
                    "Talebe ara… ile hızlı filtreleme",
                    "Kart: Talebe No · Aktif Kitap · Etüt Hocası · Dini Ders",
                    "Profili Aç · Öğrenciyi düzenle",
                    "Excel İndir · Rapor Al",
                ),
            ),
            _s(
                "Deneme",
                "Eğitim → Deneme",
                "Kurum geneli deneme sınav sonuçlarını arşivden görürsünüz.",
                "egitim-deneme.png",
                maddeler=(
                    "Tablo: Tarih · Deneme · Sınıf · Sonuç",
                    "Satırdaki bağlantı ile detaya gidilir",
                ),
                not_metni="Henüz aktif deneme yoksa tablo boş görünür.",
            ),
            _s(
                "Akademik Takip",
                "Eğitim → Akademik Takip",
                "Talebenin akademik eksikliğine yönelik müdahaleleri kaydedersiniz.",
                "egitim-akademik-takip.png",
                maddeler=(
                    "Tek öğrenci / Tüm sınıf seçimi",
                    "Sınıf · Öğrenci · Müdahale Türü · Ders · Konu · Süre",
                    "Sağ panel: müdahale kayıtları ve sınıf filtresi",
                    "+ Yeni Kayıt ve Günlük · Rapor & Analiz",
                ),
            ),
            _s(
                "Haftalık Karneler",
                "Eğitim → Haftalık Karneler",
                "Branş öğretmenlerinin haftalık notlarının arşivi; talebe bazında karne PDF indirilir.",
                "egitim-haftalik-karneler.png",
                adimlar=(
                    "Aktif haftayı veya Haftalar ile geçmiş haftayı seçin",
                    "Her talebe için ders sayısı ve ortalamayı görün",
                    "PDF butonu ile bireysel haftalık karne indirin",
                ),
                not_metni="Notlar branş öğretmenleri tarafından girilir.",
            ),
            _s(
                "Namaz Yoklaması",
                "Eğitim → Namaz Yoklaması",
                "Günlük namaz yoklaması — isim okuyarak gelmeyeni işaretlersiniz.",
                "egitim-namaz-yoklamasi.png",
                adimlar=(
                    "Tarih seçin · Sabah / Öğle / İkindi / Akşam / Yatsı sekmesi",
                    "İsim oku — geleni geç, gelmeyene G işareti",
                    "T&T (takke/tesbih) · İ (izin) gerekirse işaretleyin",
                    "Bu Vakti Kaydet",
                ),
            ),
            _s(
                "KTT",
                "Eğitim → KTT",
                "Konu tarama testlerini görüntüler, sonuç girişine geçersiniz.",
                "egitim-ktt.png",
                maddeler=(
                    "+ KTT Ekle · Rapor & Analiz",
                    "Tablo: KTT Adı · Sınıf · Ders · Soru · Tarih · Katılım",
                    "Sonuçlar ve Detay bağlantıları",
                ),
            ),
            _s(
                "Soru Takip",
                "Eğitim → Soru Takip",
                "Talebe başına günlük soru çözüm sayısı kaydı. Net = Doğru − Yanlış/4.",
                "egitim-soru-takip.png",
                adimlar=(
                    "Sınıf/Şube ve tarih seçin",
                    "Talebe listesinden öğrenci seçin",
                    "Doğru / yanlış / boş sayılarını girin ve kaydedin",
                ),
            ),
            _s(
                "Haftalık Etüt Planı",
                "Eğitim → Haftalık Etüt Planı",
                "Etüt saatlerinde yapılacak etkinlikleri planlarsınız. Saatler admin tarafından tanımlıdır.",
                "egitim-haftalik-etut-plani.png",
                maddeler=(
                    "Hafta aralığı görünümü",
                    "Arşiv · PDF çıktı",
                ),
                not_metni="Admin saat tanımlamadıysa planlama ekranı boş kalır.",
            ),
            _s(
                "Dini Ders Takip",
                "Eğitim → Dini Ders Takip",
                "Atanan seviyenin konu listesinde talebe × konu ilerlemesini işaretlersiniz.",
                "egitim-dini-ders-takip.png",
                maddeler=(
                    "Dini Ders Seviyesi · Konu Listesi seçimi",
                    "Matris: ✓ Tamamlandı · Devam · ○ İşlenmedi",
                    "Konu Listesini Düzenle · Rapor",
                    "Sağ panel: Seviye Özeti ve genel ilerleme",
                ),
            ),
            _s(
                "Yazılı Takip",
                "Eğitim → Yazılı Takip",
                "Örnek yazılı sınav oluşturma ve puan girişi; gerçek okul notu ayrı takip edilir.",
                "egitim-yazili-takip.png",
                maddeler=(
                    "+ Hızlı ekle · Örnek yazılı · Gerçek okul notu",
                    "Örnek yazılılar listesi",
                    "Yeni kayıt ekleyin ile sınav tanımı",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_iletisim",
        "menu-iletisim.png",
        "İletişim",
        "Veli ve talebe iletişim kayıtları.",
        (
            _s(
                "Veli Randevuları",
                "İletişim → Veli Randevuları",
                "Planlanan veli görüşmelerinizi ve görüşme notlarınızı takip edersiniz.",
                "iletisim-veli-randevulari.png",
                maddeler=(
                    "Yaklaşan Randevular tablosu",
                    "Tarih · Saat · Öğrenci · Veli · Konu · Durum",
                ),
                not_metni="Randevu yoksa tablo boş görünür.",
            ),
            _s(
                "Veli & Talebe İletişim",
                "İletişim → Veli & Talebe İletişim",
                "Veli ve talebe görüşme kayıtlarını talebe bazında tutarsınız.",
                "iletisim-veli-talebe.png",
                adimlar=(
                    "Öğrenci ara… ile talebe bulun",
                    "Talebe kartına tıklayarak rehberlik paneline geçin",
                    "Görüşme notu ekleyin ve geçmiş kayıtları inceleyin",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_disiplin",
        "menu-disiplin.png",
        "Disiplin & Takip",
        "Disiplin ve günlük takip modülleri.",
        (
            _s(
                "Pazar İzin Dönüşü",
                "Disiplin & Takip → Pazar İzin Dönüşü",
                "Pazar izninden dönen talebelerin geliş durumunu kaydedersiniz.",
                "disiplin-pazar-izin-donusu.png",
                maddeler=(
                    "Durum: GELDİ · İZİNLİ · GEÇ GELDİ · GELMEDİ",
                    "Beklenen Giriş saati — gecikme dakikası buna göre hesaplanır",
                    "Raporlar ve PDF",
                    "Yoklamayı Kaydet",
                ),
            ),
            _s(
                "Günlük Takip",
                "Disiplin & Takip → Günlük Takip",
                "Etüt yoklaması — gelmeyenleri işaretlersiniz; işaretsiz olanlar etütte var sayılır.",
                "disiplin-gunluk-takip.png",
                maddeler=(
                    "Etüt yoklaması: Devamsız kutusu ile işaretleme",
                    "Özet: kaç öğrenci · kaç etütte · kaç devamsız",
                    "Yoklamayı Kaydet",
                    "Günlük Kayıtlar: geçmiş kayıtlara filtre ile bakma",
                ),
            ),
        ),
    ),
    RehberMenu(
        "menu_kurum",
        "menu-kurum.png",
        "Kurum",
        "Kurumsal finans modülleri (rolünüze göre görünür).",
        (
            _s(
                "Finans Yönetimi",
                "Kurum → Finans Yönetimi",
                "Kurum aidat, taksit ve tahsilat takibi. Etüt hocası yalnızca kendi grubunun tahsilatını girer.",
                "kurum-finans-yonetimi.png",
                maddeler=(
                    "Özet kartlar: Toplam Alacak · Tahsil Edilen · Bekleyen · Vadesi Geçmiş",
                    "Öğrenci finans listesi ve filtreler",
                    "Raporlar",
                ),
                not_metni="Bu modül rolünüze göre görünmeyebilir.",
            ),
            _s(
                "Öğretmen Ödeme",
                "Kurum → Öğretmen Ödeme",
                "Branş öğretmenlerinin ders saati girişi ve ödeme dönemleri.",
                "kurum-ogretmen-odeme.png",
                maddeler=(
                    "Yeni dönem: Öğretmen · Başlangıç / Bitiş · Notlar",
                    "Tabloyu Oluştur",
                    "Ödeme dönemleri listesi · Ödeme Raporları",
                ),
                not_metni="Dönem oluşturma yetkisi rolünüze bağlıdır.",
            ),
        ),
    ),
)


def _rehber_gorsel_dizini() -> Path:
    return settings.BASE_DIR / "static" / "images" / "rehber"


def rehber_gorsel_data_uri(dosya: str) -> str:
    """PNG/JPEG dosyasını PDF'e gömülü data URI olarak döndürür."""
    if not dosya:
        return ""
    path = _rehber_gorsel_dizini() / dosya
    if not path.is_file():
        return ""
    mime, _ = mimetypes.guess_type(path.name)
    if not mime:
        mime = "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def rehber_gorsel_file_uri(dosya: str) -> str:
    """Görsel dosyasını WeasyPrint/xhtml2pdf için file:// URI olarak döndürür."""
    if not dosya:
        return ""
    path = _rehber_gorsel_dizini() / dosya
    if not path.is_file():
        return ""
    return path.resolve().as_uri()


def _tum_gorsel_dosyalari() -> set[str]:
    dosyalar = {"01-giris.png"}
    for menu in REHBER_MENULER:
        dosyalar.add(menu.dosya)
        for sayfa in menu.sayfalar:
            if sayfa.gorsel:
                dosyalar.add(sayfa.gorsel)
    return dosyalar


def rehber_gorsel_haritasi() -> dict[str, str]:
    """Dosya adı → file:// URI (PDF motorları data: URI'yi güvenilir işlemez)."""
    return {dosya: rehber_gorsel_file_uri(dosya) for dosya in _tum_gorsel_dosyalari()}


def rehber_menuler_context() -> list[dict]:
    harita = rehber_gorsel_haritasi()
    menuler: list[dict] = []
    for menu in REHBER_MENULER:
        sayfalar = [
            {
                "baslik": sayfa.baslik,
                "yol": sayfa.yol,
                "ozet": sayfa.ozet,
                "adimlar": sayfa.adimlar,
                "maddeler": sayfa.maddeler,
                "not_metni": sayfa.not_metni,
                "gorsel": harita.get(sayfa.gorsel, ""),
            }
            for sayfa in menu.sayfalar
        ]
        menuler.append(
            {
                "baslik": menu.baslik,
                "giris": menu.giris,
                "gorsel": harita.get(menu.dosya, ""),
                "sayfalar": sayfalar,
                "sayfa_sayisi": len(sayfalar),
            }
        )
    return menuler


def _rehber_panel_giris_url(request: HttpRequest) -> str:
    """Rehber PDF'de her zaman canlı panel adresi (localhost değil)."""
    base = getattr(settings, "PANEL_PUBLIC_URL", "").strip().rstrip("/")
    if not base:
        base = "https://cinilisarayproje.com"
    return f"{base}{reverse('login')}"


def ogretmen_bilgilendirme_pdf_html(request: HttpRequest) -> str:
    panel_giris_url = _rehber_panel_giris_url(request)
    logo_path = settings.BASE_DIR / "static" / "images" / "cinili-saray-logo-white.png"
    if logo_path.is_file():
        logo_uri = logo_path.resolve().as_uri()
    else:
        logo_uri = request.build_absolute_uri(static("images/cinili-saray-logo-white.png"))

    harita = rehber_gorsel_haritasi()
    menuler = rehber_menuler_context()
    toplam_modul_sayfa = sum(len(m["sayfalar"]) for m in menuler)

    return render_to_string(
        "ogretmen_bilgilendirme_pdf.html",
        {
            "panel_org": PANEL_ORG,
            "panel_name": PANEL_NAME,
            "panel_short": PANEL_SHORT,
            "panel_module": PANEL_MODULE_LABEL,
            "panel_tagline": PANEL_TAGLINE,
            "panel_giris_url": panel_giris_url,
            "logo_url": logo_uri,
            "giris_gorsel": harita.get("01-giris.png", ""),
            "menuler": menuler,
            "tarih": timezone.localdate(),
            "hedef_kitle": "Etüt Hocaları",
            "toplam_modul_sayfa": toplam_modul_sayfa,
        },
        request=request,
    )


def ogretmen_bilgilendirme_pdf_olustur(request: HttpRequest) -> bytes | None:
    html = ogretmen_bilgilendirme_pdf_html(request)
    return html_to_pdf(html, base_url=request.build_absolute_uri("/"))
