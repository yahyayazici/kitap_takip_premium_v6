from django.db import migrations

# Çinili Saray LGS optiği: formdaki ders blokları sabittir (90 kutu).
# (ders, oturum, 90'lık soru, 75'lik soru, formdaki kutu, katsayı, lgs_ders)
BLOKLAR = [
    ("Türkçe", "Sözel", 20, 15, 20, 4, "turkce"),
    ("{sosyal}", "Sözel", 10, 10, 10, 1, "inkilap"),
    ("Din Kültürü ve Ahlak Bilgisi", "Sözel", 10, 10, 10, 1, "din"),
    ("İngilizce", "Sözel", 10, 10, 10, 1, "yabanci_dil"),
    ("Matematik", "Sayısal", 20, 15, 20, 4, "matematik"),
    ("Fen Bilimleri", "Sayısal", 20, 15, 20, 4, "fen"),
]


def turleri_ekle(apps, schema_editor):
    OptikSablon = apps.get_model("okuma", "OptikSablon")
    DenemeTuru = apps.get_model("okuma", "DenemeTuru")
    DenemeTuruDers = apps.get_model("okuma", "DenemeTuruDers")
    sablon = OptikSablon.objects.filter(ad__startswith="Çinili Saray").first()
    if sablon is None:
        return
    sira = 0
    for sinif in ("5", "6", "7", "8"):
        sosyal = "T.C. İnkılap Tarihi ve Atatürkçülük" if sinif == "8" else "Sosyal Bilgiler"
        for toplam, idx in ((90, 2), (75, 3)):
            sira += 1
            tur, yeni = DenemeTuru.objects.get_or_create(
                ad=f"{sinif}. Sınıf · {toplam} soru",
                defaults={"sinif_seviyesi": sinif, "sablon": sablon, "sira": sira},
            )
            if not yeni:
                continue
            for i, blok in enumerate(BLOKLAR, start=1):
                DenemeTuruDers.objects.create(
                    tur=tur,
                    sira=i,
                    ders=blok[0].format(sosyal=sosyal),
                    oturum=blok[1],
                    soru_sayisi=blok[idx],
                    optik_blok=blok[4],
                    katsayi=blok[5],
                    lgs_ders=blok[6],
                )


class Migration(migrations.Migration):
    dependencies = [("okuma", "0003_deneme_turleri")]
    operations = [migrations.RunPython(turleri_ekle, migrations.RunPython.noop)]
