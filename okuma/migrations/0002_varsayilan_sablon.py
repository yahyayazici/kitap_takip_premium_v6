from django.db import migrations


def sablon_ekle(apps, schema_editor):
    OptikSablon = apps.get_model("okuma", "OptikSablon")
    # Çinili Saray kurumsal LGS formu (90 soru): okuyucu çıktısı 150 karakter/satır.
    OptikSablon.objects.get_or_create(
        ad="Çinili Saray Kurumsal LGS (90 soru)",
        defaults=dict(
            kodlama="cp1254",
            numara_bas=20,
            numara_uzunluk=6,
            kitapcik_bas=26,
            sinif_bas=27,
            sinif_uzunluk=1,
            sube_bas=28,
            sube_uzunluk=1,
            ad_bas=29,
            ad_uzunluk=22,
            cevap_bas=51,
            aciklama="Numara 20–25, kitapçık 26, sınıf 27, şube 28, ad soyad 29–50, cevaplar 51'den itibaren "
            "(Türkçe 20, Sosyal 10, Din 10, İngilizce 10, Matematik 20, Fen 20).",
        ),
    )


class Migration(migrations.Migration):
    dependencies = [("okuma", "0001_initial")]
    operations = [migrations.RunPython(sablon_ekle, migrations.RunPython.noop)]
