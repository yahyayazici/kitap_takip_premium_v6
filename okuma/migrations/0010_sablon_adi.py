from django.db import migrations

ESKI = "Çinili Saray Kurumsal LGS (90 soru)"
YENI = "Çinili Saray optik formu"


def adlandir(apps, schema_editor):
    OptikSablon = apps.get_model("okuma", "OptikSablon")
    # Ad, formun fiziksel düzenidir; ders/soru sayısı deneme türünden gelir.
    OptikSablon.objects.filter(ad=ESKI).update(
        ad=YENI,
        aciklama="Kurumun tek optik formu. Numara 20–25, kitapçık 26, sınıf 27, şube 28, ad soyad 29–50, "
        "cevaplar 51'den itibaren. Hangi dersin hangi kutularda olduğu ve kaç soru okunacağı "
        "seçilen deneme türünden gelir (90 ya da 75 soru).",
    )


def geri(apps, schema_editor):
    apps.get_model("okuma", "OptikSablon").objects.filter(ad=YENI).update(ad=ESKI)


class Migration(migrations.Migration):
    dependencies = [("okuma", "0009_oturum_bazli_okuma")]
    operations = [migrations.RunPython(adlandir, geri)]
