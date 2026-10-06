from django.urls import path

from takip import ekitap_views as v

app_name = "ekitap"

urlpatterns = [
    path("", v.liste, name="liste"),
    path("robots.txt", v.robots_txt, name="robots"),
    path("pin/", v.pin_giris, name="pin"),
    path("pin/cikis/", v.pin_cikis, name="pin_cikis"),
    path("kitap/<int:kitap_id>/", v.okuyucu, name="okuyucu"),
    path("kitap/<int:kitap_id>/akis/", v.ders_akisi_kaydet, name="ders_akisi_kaydet"),
    path("kitap/<int:kitap_id>/akis/<int:akis_id>/sil/", v.ders_akisi_sil, name="ders_akisi_sil"),
    path("sayfa/<int:sayfa_id>.webp", v.sayfa_gorseli, name="sayfa"),
    path("sayfa/<int:sayfa_id>-k.webp", v.sayfa_kucuk, name="sayfa_kucuk"),
    path("soru/<int:alan_id>.webp", v.soru_gorseli, name="soru_gorseli"),
    path("yonetim/", v.yonetim, name="yonetim"),
    path("yonetim/sorulari-bul/", v.sorulari_bul, name="sorulari_bul"),
    path("yonetim/giris/", v.yonetim_giris, name="yonetim_giris"),
    path("yonetim/cikis/", v.yonetim_cikis, name="yonetim_cikis"),
    path("yonetim/pin/", v.yonetim_pin, name="yonetim_pin"),
    path("yonetim/kitap/yeni/", v.kitap_yeni, name="kitap_yeni"),
    path("yonetim/kitap/<int:kitap_id>/", v.kitap_duzenle, name="kitap_duzenle"),
    path("yonetim/kitap/<int:kitap_id>/gorunurluk/", v.kitap_gorunurluk, name="kitap_gorunurluk"),
    path("yonetim/kitap/<int:kitap_id>/sil/", v.kitap_sil, name="kitap_sil"),
    path("yonetim/bolum/<int:bolum_id>/sil/", v.bolum_sil, name="bolum_sil"),
    path("yonetim/bolum/<int:bolum_id>/sorular/", v.soru_duzelt, name="soru_duzelt"),
    path("yonetim/bolum/<int:bolum_id>/sorular/kaydet/", v.soru_duzelt_kaydet, name="soru_duzelt_kaydet"),
    path("yonetim/bolum/<int:bolum_id>/yeniden-isle/", v.bolum_yeniden_isle, name="bolum_yeniden_isle"),
]
