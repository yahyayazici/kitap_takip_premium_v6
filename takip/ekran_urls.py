"""Dijital Duyuru Ekranı — yönetim paneli adresleri.

Bu yapılandırma iki yerde bağlanır:
* ana panelde ``/ekran/`` altında,
* ``ekran.<domain>`` alt alan adında ``/yonetim/`` altında.

``reverse()`` isteğin aktif urlconf'una göre doğru ön eki üretir; iki yüzey
aynı görünümleri paylaşır ama adresleri karışmaz.
"""

from django.urls import path

from takip import ekran_views

app_name = "ekran"

urlpatterns = [
    path("", ekran_views.dashboard, name="dashboard"),
    path("pano/<int:pk>/", ekran_views.pano, name="pano"),
    path("pano/<int:pk>/gonder/", ekran_views.pano_gonder, name="pano_gonder"),

    # —— Gelişmiş (menüde yok; pano üzerinden ulaşılır) ——
    path("ozet/", ekran_views.ozet, name="ozet"),

    # —— Tasarım ——
    path("tasarimlar/", ekran_views.tasarim_listesi, name="tasarim_listesi"),
    path("tasarimlar/yeni/", ekran_views.tasarim_olustur, name="tasarim_olustur"),
    path("tasarimlar/<int:pk>/", ekran_views.studyo, name="studyo"),
    path("tasarimlar/<int:pk>/sil/", ekran_views.tasarim_sil, name="tasarim_sil"),
    path("tasarimlar/<int:pk>/kopyala/", ekran_views.tasarim_kopyala, name="tasarim_kopyala"),
    path("tasarimlar/<int:pk>/onizleme/", ekran_views.tasarim_onizleme, name="tasarim_onizleme"),
    path("tasarimlar/<int:pk>/surumler/", ekran_views.surum_listesi, name="surum_listesi"),
    path("tasarimlar/<int:pk>/sahne/ekle/", ekran_views.sahne_ekle, name="sahne_ekle"),
    path("sahne/<int:pk>/sil/", ekran_views.sahne_sil, name="sahne_sil"),
    path("sahne/<int:pk>/kaydet/", ekran_views.sahne_kaydet_api, name="sahne_kaydet"),
    path("sahne/<int:pk>/veri/", ekran_views.sahne_veri_api, name="sahne_veri"),
    path("surum/<int:pk>/geri-yukle/", ekran_views.surum_geri_yukle_view, name="surum_geri_yukle"),

    # —— Şablonlar ——
    path("sablonlar/", ekran_views.sablon_listesi, name="sablon_listesi"),
    path("sablonlar/<int:pk>/uygula/", ekran_views.sablon_uygula, name="sablon_uygula"),
    path("sahne/<int:pk>/sablon-kaydet/", ekran_views.sablon_olarak_kaydet, name="sablon_kaydet"),
    path("sablonlar/<int:pk>/sil/", ekran_views.sablon_sil, name="sablon_sil"),

    # —— Medya ——
    path("medya/", ekran_views.medya_kutuphanesi, name="medya_kutuphanesi"),
    path("medya/yukle/", ekran_views.medya_yukle_api, name="medya_yukle"),
    path("medya/liste/", ekran_views.medya_liste_api, name="medya_liste"),
    path("medya/<int:pk>/sil/", ekran_views.medya_sil, name="medya_sil"),
    path("medya/<int:pk>/duzenle/", ekran_views.medya_duzenle, name="medya_duzenle"),
    path("medya/klasor/ekle/", ekran_views.klasor_ekle, name="klasor_ekle"),

    # —— Cihaz ve konum ——
    path("cihazlar/", ekran_views.cihaz_listesi, name="cihaz_listesi"),
    path("cihazlar/eslestir/", ekran_views.cihaz_eslestir, name="cihaz_eslestir"),
    path("cihazlar/durum/", ekran_views.cihaz_durum_api, name="cihaz_durum_api"),
    path("cihazlar/<int:pk>/", ekran_views.cihaz_detay, name="cihaz_detay"),
    path("cihazlar/<int:pk>/sil/", ekran_views.cihaz_sil, name="cihaz_sil"),
    path("cihazlar/<int:pk>/yenile/", ekran_views.cihaz_yenile, name="cihaz_yenile"),
    path("konumlar/", ekran_views.konum_listesi, name="konum_listesi"),
    path("konumlar/<int:pk>/sil/", ekran_views.konum_sil, name="konum_sil"),

    # —— Oynatma listesi ——
    path("listeler/", ekran_views.liste_listesi, name="liste_listesi"),
    path("listeler/<int:pk>/", ekran_views.liste_detay, name="liste_detay"),
    path("listeler/<int:pk>/sil/", ekran_views.liste_sil, name="liste_sil"),

    # —— Yayın planı ——
    path("yayinlar/", ekran_views.yayin_listesi, name="yayin_listesi"),
    path("yayinlar/<int:pk>/", ekran_views.yayin_detay, name="yayin_detay"),
    path("yayinlar/<int:pk>/yayinla/", ekran_views.yayin_yayinla, name="yayin_yayinla"),
    path("yayinlar/<int:pk>/durdur/", ekran_views.yayin_durdur, name="yayin_durdur"),
    path("yayinlar/<int:pk>/sil/", ekran_views.yayin_sil, name="yayin_sil"),

    # —— Acil duyuru ——
    path("acil/", ekran_views.acil_listesi, name="acil_listesi"),
    path("acil/<int:pk>/kapat/", ekran_views.acil_kapat, name="acil_kapat"),

    # —— Geçmiş ——
    path("gecmis/", ekran_views.gecmis, name="gecmis"),
]
