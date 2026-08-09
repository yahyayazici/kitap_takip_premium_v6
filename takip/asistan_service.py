"""Panel yapay zeka asistanı — analiz sonucundan yanıt ve eylem üretimi."""

from __future__ import annotations

from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.urls import reverse

from takip.asistan_analyzer import (
    AnalizSonuc,
    analiz_et,
    genel_sohbet_mi,
    net_panel_komutu_mu,
)
from takip.asistan_llm import llm_sohbet_cevabi, openai_yapilandirildi_mi
from takip.asistan_types import AsistanAction, AsistanYanit
from takip.models import (
    ImamMuezzinListesi,
    ProgramPlan,
    Sinav,
    Talebe,
    TemizlikListesi,
    YemekciListesi,
    Zimmet,
)
from takip.permissions.scope import tum_talebe_kapsami_var, yetkili_talebeler
from takip.permissions.service import can
from takip.talebe_liste_raporu_service import erisilebilir_siniflar, sinif_etiketi_goster
from takip.talebe_panel_service import kullanici_talebe_mi
from takip.veli_service import kullanici_veli_mi
from takip.ogretmen_service import ogretmen_paneli_kullanicisi_mi


YARDIM_METNI = """Doğal Türkçe ile sorabilirsiniz; kelime komutu şart değil.

**Okuma / rapor**
• “5-A sınıfının okuma raporunu gönderir misin?”
• “Sadece 5. sınıfların okuma raporu”
• “Bu hafta okuma özeti”

**Talebe**
• “Ahmet Yılmaz hakkında bilgi ver”
• “Mehmet’in profil karnesi PDF”

**Kurum**
• “Kaç aktif talebe var?”
• “Program PDF”, “İmam müezzin listesi PDF”

Takip mesajlarında önceki isteği hatırlarım — örneğin önce okuma raporu deyip sonra “5. sınıfların sadece” yazabilirsiniz."""


def asistan_kullanilabilir(user: User) -> bool:
    if not getattr(settings, "AI_ASSISTANT_ENABLED", True):
        return False
    if not user.is_authenticated:
        return False
    # Yönetim + öğretmen + veli panelleri
    if kullanici_veli_mi(user) or ogretmen_paneli_kullanicisi_mi(user):
        return True
    if kullanici_talebe_mi(user):
        return getattr(settings, "AI_ASSISTANT_ENABLED", True)
    return can(user, "asistan", "view") or user.is_superuser


def _ozel_panel_asistan_yanit(user: User, message: str) -> AsistanYanit | None:
    """Öğretmen / veli panelleri için sade, panele özel yardım."""
    if ogretmen_paneli_kullanicisi_mi(user):
        return AsistanYanit(
            reply=(
                "Merhaba! Öğretmen panelinde size yardımcı olabilirim.\n\n"
                "• **Not Girişi** — haftalık katılım / takip / disiplin notları\n"
                "• **Değerlendirmeler** — girdiğiniz kayıtları görüntüleyin\n"
                "• **Ders Programı** — haftalık planınızı ve PDF’i açın\n\n"
                "Hangi adımda takıldınız?"
            ),
            suggestions=[
                "Not girişini nasıl yaparım?",
                "Değerlendirmeler nerede?",
                "Ders programı PDF",
            ],
        )
    if kullanici_veli_mi(user):
        return AsistanYanit(
            reply=(
                "Merhaba! Veli panelinde size yardımcı olabilirim.\n\n"
                "• **Ana Sayfa** — deneme, KTT, ders ve soru özetleri\n"
                "• **Ders Notları / Soru / Yoklama / Namaz** — detaylı takip\n"
                "• **Dini Ders** ve **Sohbet Mevzuu** — haftalık içerikler\n\n"
                "Hangi bilgiyi merak ediyorsunuz?"
            ),
            suggestions=[
                "Haftalık notlar nerede?",
                "Yoklama bilgisi",
                "Sohbet mevzuu nedir?",
            ],
        )
    return None


def _talebe_bul(user: User, ad_parcasi: str) -> Talebe | None:
    qs = yetkili_talebeler(user).select_related("sinif_sube", "etut_hocasi")
    adaylar = list(qs.filter(ad_soyad__icontains=ad_parcasi)[:6])
    if not adaylar:
        kelimeler = ad_parcasi.split()
        if kelimeler:
            kosul = Q()
            for kelime in kelimeler:
                kosul &= Q(ad_soyad__icontains=kelime)
            adaylar = list(qs.filter(kosul)[:6])
    if len(adaylar) == 1:
        return adaylar[0]
    return None


def _talebe_adaylari(user: User, ad_parcasi: str) -> list[Talebe]:
    return list(yetkili_talebeler(user).filter(ad_soyad__icontains=ad_parcasi)[:5])


def _son_kayit(user: User, lookup: str):
    if lookup == "program" and can(user, "program", "view"):
        return ProgramPlan.objects.filter(aktif=True).order_by("-baslangic_tarihi").first()
    if lookup == "imam" and can(user, "imam_muezzin", "view"):
        return ImamMuezzinListesi.objects.filter(aktif=True).order_by("-baslangic_tarihi").first()
    if lookup == "temizlik" and can(user, "temizlik", "view"):
        return TemizlikListesi.objects.filter(aktif=True).order_by("-baslangic_tarihi").first()
    if lookup == "yemek" and can(user, "yemekcilik", "view"):
        return YemekciListesi.objects.filter(aktif=True).order_by("-baslangic_tarihi").first()
    return None


def _okuma_pdf_actions(user: User, siniflar: list) -> list[AsistanAction]:
    if not can(user, "raporlar", "export_pdf"):
        return []
    if not siniflar:
        return [
            AsistanAction(
                type="pdf",
                label="Okuma Raporu — Tümü",
                url=reverse("okuma_raporu_pdf"),
            )
        ]
    actions = []
    for sinif in siniflar:
        qs = urlencode({"sinif": sinif.pk})
        etiket = sinif_etiketi_goster(sinif)
        actions.append(
            AsistanAction(
                type="pdf",
                label=f"Okuma Raporu — {etiket}",
                url=f"{reverse('okuma_raporu_pdf')}?{qs}",
            )
        )
        actions.append(
            AsistanAction(
                type="link",
                label=f"Raporlar — {etiket}",
                url=f"{reverse('raporlar')}?{qs}",
            )
        )
    return actions


def _talebe_ozet(user: User, talebe: Talebe) -> AsistanYanit:
    sinif = str(talebe.sinif_sube) if talebe.sinif_sube else talebe.sinif or "—"
    etut = talebe.etut_hocasi.ad_soyad if talebe.etut_hocasi else "—"
    aktif_zimmet = (
        Zimmet.objects.filter(talebe=talebe, durum="okunuyor")
        .select_related("kitap")
        .first()
    )
    kitap = aktif_zimmet.kitap.ad if aktif_zimmet else "Aktif zimmet yok"
    son_sinav = (
        Sinav.objects.filter(sonuclar__talebe=talebe)
        .order_by("-sinav_tarihi")
        .distinct()
        .first()
    )
    sinav_metni = son_sinav.ad if son_sinav else "Kayıtlı sınav yok"

    reply = (
        f"**{talebe.ad_soyad}** ({talebe.talebe_no or 'no yok'})\n"
        f"• Sınıf: {sinif}\n"
        f"• Etüt hocası: {etut}\n"
        f"• Okunan kitap: {kitap}\n"
        f"• Son sınav: {sinav_metni}"
    )
    actions = [
        AsistanAction(
            type="link",
            label="Profil sayfası",
            url=reverse("talebe_detay", kwargs={"talebe_id": talebe.pk}),
        )
    ]
    if can(user, "egitim_kitap", "export_pdf"):
        actions.append(
            AsistanAction(
                type="pdf",
                label="Kitap Karnesi PDF",
                url=reverse("talebe_profil_karne_pdf", kwargs={"talebe_id": talebe.pk}),
            )
        )
    return AsistanYanit(
        reply=reply,
        actions=actions,
        suggestions=[f"{talebe.ad_soyad.split()[0]} için okuma raporu", "Kaç aktif talebe var?"],
    )


def _yanit_uret(user: User, analiz: AnalizSonuc) -> AsistanYanit | None:
    niyet = analiz.niyet
    dogal = (analiz.aciklama or "").strip()

    if niyet == "yardim":
        return AsistanYanit(reply=YARDIM_METNI, suggestions=["5-A okuma raporu gönder", "Kaç talebe var?"])

    if niyet == "pdf_okuma":
        actions = _okuma_pdf_actions(user, analiz.siniflar)
        if not actions:
            return AsistanYanit(reply="Okuma raporu PDF için yetkiniz bulunmuyor.")
        if analiz.siniflar:
            etiketler = ", ".join(sinif_etiketi_goster(s) for s in analiz.siniflar)
            reply = (
                dogal
                if dogal and not dogal.startswith("{")
                else f"**{etiketler}** için okuma raporu hazır. PDF’e tıklayarak indirebilirsiniz."
            )
        else:
            reply = (
                dogal
                if dogal
                else "Kurum geneli okuma raporu hazır. Sınıf belirtirseniz filtreleyebilirim."
            )
        return AsistanYanit(
            reply=reply,
            actions=actions[:6],
            suggestions=["5. sınıfların okuma raporu", "Raporlar sayfasını aç"],
        )

    if niyet == "pdf_talebe_liste":
        if not can(user, "egitim_kitap", "view"):
            return AsistanYanit(reply="Talebe listesi PDF için yetkiniz yok.")
        talebe_qs = yetkili_talebeler(user)
        if not talebe_qs.exists():
            return AsistanYanit(reply="Yetkiniz dahilinde talebe bulunamadı.")
        siniflar = analiz.siniflar or list(erisilebilir_siniflar(talebe_qs))
        actions = []
        if analiz.siniflar:
            for sinif in analiz.siniflar:
                qs = urlencode({"tur": "sinif", "sinif_sube": sinif.pk})
                actions.append(
                    AsistanAction(
                        type="pdf",
                        label=f"Talebe Listesi — {sinif_etiketi_goster(sinif)}",
                        url=f"{reverse('talebe_liste_raporu_pdf')}?{qs}",
                    )
                )
        else:
            etiket = (
                "Kurum Geneli Talebe Listesi"
                if user.is_superuser or tum_talebe_kapsami_var(user)
                else "Etüt Grubum — Öğrenci Listesi"
            )
            actions.append(
                AsistanAction(
                    type="pdf",
                    label=etiket,
                    url=f"{reverse('talebe_liste_raporu_pdf')}?tur=kurum",
                )
            )
            for sinif in siniflar[:8]:
                qs = urlencode({"tur": "sinif", "sinif_sube": sinif.pk})
                actions.append(
                    AsistanAction(
                        type="pdf",
                        label=f"Sınıf Listesi — {sinif_etiketi_goster(sinif)}",
                        url=f"{reverse('talebe_liste_raporu_pdf')}?{qs}",
                    )
                )
        if analiz.siniflar:
            etiket = ", ".join(sinif_etiketi_goster(s) for s in analiz.siniflar)
        elif user.is_superuser or tum_talebe_kapsami_var(user):
            etiket = "kurum geneli"
        else:
            etiket = "etüt grubunuz"
        return AsistanYanit(
            reply=dogal or f"**{etiket}** için talebe listesi PDF hazır.",
            actions=actions[:6],
        )

    if niyet == "pdf_profil" and analiz.talebe_adi:
        talebe = _talebe_bul(user, analiz.talebe_adi)
        if talebe and can(user, "egitim_kitap", "export_pdf"):
            yanit = AsistanYanit(
                reply=dogal or f"{talebe.ad_soyad} için profil karnesi hazır.",
                actions=[
                    AsistanAction(
                        type="pdf",
                        label=f"{talebe.ad_soyad} — Kitap Karnesi",
                        url=reverse("talebe_profil_karne_pdf", kwargs={"talebe_id": talebe.pk}),
                    )
                ],
            )
            return yanit
        adaylar = _talebe_adaylari(user, analiz.talebe_adi)
        if adaylar:
            return AsistanYanit(
                reply="Birden fazla talebe bulundu: " + ", ".join(t.ad_soyad for t in adaylar),
            )

    if niyet == "pdf_sinav" and can(user, "deneme", "export_pdf"):
        sinav = Sinav.objects.order_by("-sinav_tarihi").first()
        if sinav:
            actions = [
                AsistanAction(
                    type="pdf",
                    label=f"{sinav.ad} — Sıralı Sonuç",
                    url=reverse("sinav_sirali_sonuc_pdf", kwargs={"sinav_id": sinav.pk}),
                )
            ]
            if analiz.talebe_adi:
                talebe = _talebe_bul(user, analiz.talebe_adi)
                if talebe:
                    actions.insert(
                        0,
                        AsistanAction(
                            type="pdf",
                            label=f"{talebe.ad_soyad} — Sınav Karnesi",
                            url=reverse(
                                "sinav_karne_pdf",
                                kwargs={"sinav_id": sinav.pk, "talebe_id": talebe.pk},
                            ),
                        ),
                    )
            return AsistanYanit(
                reply=dogal or f"Son sınav **{sinav.ad}** için PDF linkleri hazır.",
                actions=actions,
            )

    pdf_map = {
        "pdf_program": ("program", "program_pdf", "Kurum Programı PDF"),
        "pdf_imam": ("imam_muezzin", "imam_muezzin_pdf", "İmam & Müezzin PDF"),
        "pdf_temizlik": ("temizlik", "temizlik_pdf", "Temizlik PDF"),
        "pdf_yemek": ("yemekcilik", "yemekcilik_pdf", "Yemekçilik PDF"),
    }
    if niyet in pdf_map:
        modul, url_name, label = pdf_map[niyet]
        if not can(user, modul, "export_pdf"):
            return AsistanYanit(reply=f"{label} için yetkiniz yok.")
        lookup = niyet.replace("pdf_", "")
        kayit = _son_kayit(user, lookup)
        if kayit:
            return AsistanYanit(
                reply=dogal or f"{label} hazır.",
                actions=[
                    AsistanAction(
                        type="pdf",
                        label=f"{label} — {kayit.ad}",
                        url=reverse(url_name, kwargs={"pk": kayit.pk}),
                    )
                ],
            )
        return AsistanYanit(
            reply="Aktif kayıt bulunamadı. İlgili modülden önce liste oluşturun.",
            actions=[AsistanAction(type="link", label="Programlar", url=reverse("program_panel"))],
        )

    if niyet == "veri_talebe_say":
        qs = yetkili_talebeler(user)
        toplam = qs.count()
        siniflar = (
            qs.values("sinif_sube__sinif", "sinif_sube__sube")
            .annotate(adet=Count("id"))
            .order_by("-adet")[:6]
        )
        satirlar = [
            f"• {row['sinif_sube__sinif']}/{row['sinif_sube__sube']}: {row['adet']}"
            for row in siniflar
            if row["sinif_sube__sinif"]
        ]
        reply = dogal or f"Yetkiniz dahilinde **{toplam}** aktif talebe var."
        if satirlar:
            reply += "\n\n" + "\n".join(satirlar)
        actions = _okuma_pdf_actions(user, [])[:1] if can(user, "raporlar", "export_pdf") else []
        return AsistanYanit(reply=reply, actions=actions, suggestions=["5. sınıfların okuma raporu"])

    if niyet == "veri_okuma":
        zimmet_say = Zimmet.objects.filter(
            talebe__in=yetkili_talebeler(user),
            durum="okunuyor",
        ).count()
        reply = dogal or f"Şu an **{zimmet_say}** aktif kitap zimmeti var."
        actions = _okuma_pdf_actions(user, analiz.siniflar)[:2]
        return AsistanYanit(reply=reply, actions=actions)

    if niyet == "talebe_bilgi" and analiz.talebe_adi:
        talebe = _talebe_bul(user, analiz.talebe_adi)
        if talebe:
            ozet = _talebe_ozet(user, talebe)
            if dogal:
                ozet.reply = f"{dogal}\n\n{ozet.reply}"
            return ozet

    return None


def _kullanici_hitap(user: User) -> str:
    profil = getattr(user, "personel_profili", None)
    if profil and profil.ad_soyad:
        return profil.ad_soyad.split()[0]
    ad = (user.first_name or "").strip()
    if ad:
        return ad
    return ""


def _gunsel_selam() -> str:
    from datetime import datetime

    saat = datetime.now().hour
    if saat < 12:
        return "Günaydın"
    if saat < 18:
        return "İyi günler"
    return "İyi akşamlar"


def genel_sohbet_yanit(user: User, message: str) -> AsistanYanit:
    """Selamlaşma ve günlük sohbete sıcak, doğal yanıt (OpenAI olmadan)."""
    norm = (message or "").lower()
    hitap = _kullanici_hitap(user)
    selam = f"{hitap}, " if hitap else ""

    if any(k in norm for k in ("teşekkür", "tesekkur", "sağol", "sagol", "eyvallah", "eyv")):
        reply = (
            f"{selam}Rica ederim, ne demek! "
            "Başka bir konuda yardımcı olmamı istersen buradayım."
        )
    elif any(k in norm for k in ("hoşça kal", "hosca kal", "görüşürüz", "gorusuruz", "bye", "bb")):
        reply = (
            f"{selam}Görüşmek üzere! "
            "Panelde ihtiyaç olursa yine yazabilirsiniz."
        )
    elif any(k in norm for k in ("naber", "naberr", "nbr", "ne haber", "ne var ne yok")):
        reply = (
            f"İyiyim, teşekkürler{(' ' + hitap) if hitap else ''}! "
            "Siz nasılsınız? "
            "İsterseniz okuma raporu, talebe bilgisi veya başarı takibi "
            "konusunda da yardımcı olabilirim."
        )
    elif any(k in norm for k in ("nasılsın", "nasilsin", "nasılsınız", "nasilsiniz", "nası gidiyor", "nasil gidiyor")):
        reply = (
            f"Teşekkürler, iyiyim{(' ' + hitap) if hitap else ''}! "
            "Umarım siz de iyisinizdir. "
            "Panel işlerinizde bir şeye ihtiyaç olursa sorabilirsiniz."
        )
    elif any(k in norm for k in ("tamam", "peki", "anladım", "anladim", "süper", "super", "harika", "güzel", "guzel")):
        reply = (
            f"{selam}Harika! "
            "Devam etmek isterseniz rapor, talebe veya sınav konularında "
            "yardımcı olabilirim."
        )
    elif any(k in norm for k in ("kolay gelsin", "hayırlı işler", "hayirli isler")):
        reply = f"{selam}Size de kolay gelsin! İyi çalışmalar."
    else:
        zaman_selam = _gunsel_selam()
        reply = (
            f"{zaman_selam}{(' ' + hitap) if hitap else ''}! "
            "Ben panel asistanınızım — sohbet edebilir, okuma raporu alabilir, "
            "talebe bilgisi sorabilir veya başarı takibi hakkında konuşabiliriz. "
            "Bugün ne yapmak istersiniz?"
        )

    return AsistanYanit(
        reply=reply,
        suggestions=[
            "Naber",
            "5-A okuma raporu gönder",
            "Kaç aktif talebe var?",
            "Başarı analizi için ne önerirsin?",
        ],
    )


def konusma_yanit(user: User, message: str, analiz: AnalizSonuc) -> AsistanYanit:
    """Açık uçlu sohbet — eğitim takibi, panel, pedagoji (varsayılan yanıt katmanı)."""
    if genel_sohbet_mi(message):
        return genel_sohbet_yanit(user, message)

    norm = _normalize_asistan(message)
    hitap = _kullanici_hitap(user)
    selam = f"{hitap}, " if hitap else ""
    talebe_say = yetkili_talebeler(user).count()
    aktif_zimmet = Zimmet.objects.filter(
        talebe__in=yetkili_talebeler(user),
        durum="okunuyor",
    ).count()

    if any(k in norm for k in ("egitim takip", "takip", "egitim")) and any(
        k in norm for k in ("konusalim", "konuşalım", "sohbet", "alakali", "alakalı", "hakkinda", "hakkında", "biraz")
    ):
        reply = (
            f"Tabii{(', ' + hitap) if hitap else ''}, memnuniyetle konuşuruz!\n\n"
            "Eğitim takibinde panelin gücü, dağınık bilgiyi **tek yerde** toplaması. "
            f"Şu an yetkiniz dahilinde **{talebe_say}** aktif talebe ve **{aktif_zimmet}** "
            "devam eden kitap zimmeti var — bunlar günlük disiplinin en somut göstergeleri.\n\n"
            "**Okuma kültürü** haftalık raporlarla, **sınav performansı** deneme trendleriyle, "
            "**bireysel gelişim** ise talebe profili ve rehberlik kayıtlarıyla izlenir. "
            "Üçünü birlikte okuduğunuzda öğrencinin gerçek tablosu netleşir.\n\n"
            "Hangi başlığa odaklanmak istersiniz? Okuma mı, sınav mı, rehberlik mi — "
            "oradan devam edelim."
        )
        return AsistanYanit(
            reply=reply,
            suggestions=[
                "Okuma takibinde nelere bakmalıyım?",
                "Başarı analizi için ne önerirsin?",
                "5-A okuma raporu gönder",
                "Kaç aktif talebe var?",
            ],
        )

    if any(k in norm for k in ("okuma", "kitap", "zimmet")):
        reply = (
            "Okuma takibi kurum kültürünün omurgası. Panelde her öğrencinin zimmetli kitabı, "
            "okunan sayfa ve haftalık tempo görünür. Düşen okuma hacmi çoğu zaman sınav "
            "düşüşünden **önce** sinyal verir.\n\n"
            "Pratik öneri: Önce sınıf ortalamasına bakın, sonra alt grubu (5–10 öğrenci) "
            "seçin — tüm sınıfa aynı müdahale genelde işe yaramaz. "
            "İsterseniz belirli bir sınıfın okuma raporunu da hazırlayabilirim."
        )
        siniflar = analiz.siniflar or list(erisilebilir_siniflar(yetkili_talebeler(user))[:2])
        actions = _okuma_pdf_actions(user, siniflar[:1]) if siniflar else []
        return AsistanYanit(
            reply=reply,
            actions=actions[:1],
            suggestions=["5-A okuma raporu gönder", "Okuma takibinde nelere bakmalıyım?"],
        )

    if any(k in norm for k in ("basari", "başarı", "analiz", "performans", "sinav", "deneme")):
        reply = (
            f"Öğrenci başarısını katmanlı okumak en sağlıklısı "
            f"(yetkiniz dahilinde **{talebe_say}** aktif talebe):\n\n"
            "**1. Okuma & disiplin** — haftalık okuma raporu ve günlük takip\n"
            "**2. Sınav trendi** — tek sınav değil, 2–3 denemelik gelişim\n"
            "**3. Etüt & rehberlik** — yoklama + görüşme notları birlikte\n"
            "**4. Sınıf kırılımı** — önce ortalama, sonra hedef alt grup\n\n"
            "Hangi katmanda takılı kaldınız, birlikte derinleştirebiliriz."
        )
        return AsistanYanit(
            reply=reply,
            suggestions=[
                "5-A okuma raporu gönder",
                "Kaç aktif talebe var?",
                "Rehberlik sürecinde nelere dikkat etmeliyim?",
            ],
        )

    if any(k in norm for k in ("rehberlik", "gorusme", "görüşme", "veli", "disiplin")):
        return AsistanYanit(
            reply=(
                "Rehberlikte düzenli kayıt tutmak altın kural. Panelden görüşme türü, "
                "genel durum ve alınan kararları yazın; veli görüşmelerini aynı dosyada "
                "biriktirmek kurul süreçlerinde de güçlü dayanak olur.\n\n"
                "Öğrenci hakkında konuşurken tek seferlik izlenim yerine **zaman içindeki "
                "değişimi** göstermek veli iletişimini çok güçlendirir."
            ),
            suggestions=["Başarı analizi için ne önerirsin?", "Eğitim takip ile konuşalım"],
        )

    if any(k in norm for k in ("panel", "modul", "modül", "nasil kullan", "nasıl kullan")):
        return AsistanYanit(
            reply=(
                f"{selam}Paneli günlük iş akışında şöyle düşünebilirsiniz:\n\n"
                "• **Raporlar** — okuma ve disiplin özeti\n"
                "• **Talebe profili** — kitap, sınav, gelişim dosyası\n"
                "• **Sınavlar** — sonuç ve karne PDF\n"
                "• **Rehberlik** — görüşme kayıtları\n\n"
                "Doğal Türkçe yazmanız yeterli; rapor istediğinizde PDF butonu çıkar, "
                "sohbet etmek istediğinizde birlikte konuşuruz."
            ),
            suggestions=["5-A okuma raporu gönder", "Kaç aktif talebe var?", "Naber"],
        )

    return AsistanYanit(
        reply=(
            f"{selam}Elbette, konuşabiliriz! "
            "Ben hem sohbet edebilen hem de panel işlerinizi yapan asistanınızım — "
            "rapor istemek zorunda değilsiniz.\n\n"
            "Eğitim takibi, okuma kültürü, sınav trendleri, rehberlik veya "
            "panel kullanımı… Hangi konuyu merak ediyorsunuz, oradan devam edelim."
        ),
        suggestions=[
            "Eğitim takip ile konuşalım",
            "Okuma takibinde nelere bakmalıyım?",
            "Başarı analizi için ne önerirsin?",
            "Naber",
        ],
    )


def _normalize_asistan(text: str) -> str:
    text = (text or "").lower().strip()
    for src, dst in {"ı": "i", "ğ": "g", "ü": "u", "ş": "s", "ö": "o", "ç": "c"}.items():
        text = text.replace(src, dst)
    return text

def mesaj_isle(user: User, message: str, history: list[dict] | None = None) -> dict[str, Any]:
    history = history or []
    message = (message or "").strip()

    ozel = kullanici_veli_mi(user) or ogretmen_paneli_kullanicisi_mi(user) or kullanici_talebe_mi(user)
    if ozel:
        if not message:
            yanit = _ozel_panel_asistan_yanit(user, "")
            if yanit:
                return yanit.as_dict()
            if kullanici_talebe_mi(user):
                return AsistanYanit(
                    reply=(
                        "Merhaba! Talebe panelinde sana yardımcı olabilirim.\n\n"
                        "• **Haftalık soru** ve okuma durumun\n"
                        "• **Gelişim özeti** ve çalışma önerileri\n"
                        "• **Program** ve görevler\n\n"
                        "Ne merak ediyorsun?"
                    ),
                    suggestions=["Bu hafta kaç soru çözdüm?", "Gelişim özetim", "Bugün ne yapmalıyım?"],
                ).as_dict()
            return AsistanYanit(reply="Merhaba! Size nasıl yardımcı olabilirim?").as_dict()
        if kullanici_talebe_mi(user):
            from takip.talebe_panel_service import talebe_hesabi_for_user
            from takip.ai_service import gelisim_zekasi_analizi

            hesap = talebe_hesabi_for_user(user)
            talebe = hesap.talebe if hesap else None
            norm = _normalize_asistan(message)
            if talebe and any(k in norm for k in ("gelisim", "gelişim", "ozet", "özet", "analiz", "durumum")):
                analiz = gelisim_zekasi_analizi(user, talebe)
                ozet_bolum = analiz.bolumler[0].icerik if analiz.bolumler else analiz.tam_metin
                return AsistanYanit(
                    reply=f"**Gelişim özeti**\n\n{ozet_bolum}",
                    suggestions=["Bu hafta kaç soru çözdüm?", "Ne yapmalıyım?"],
                ).as_dict()
            if talebe and any(k in norm for k in ("soru", "kac", "kaç", "hafta")):
                from takip.soru_takip_service import haftalik_ozet

                hafta = haftalik_ozet(talebe)
                return AsistanYanit(
                    reply=(
                        f"Bu hafta **{hafta.get('toplam_soru', 0)}** soru çözdün, "
                        f"net **{hafta.get('toplam_net', 0)}**, başarı **%{hafta.get('basari_orani', 0)}**."
                    ),
                    suggestions=["Gelişim özetim", "Ne yapmalıyım?"],
                ).as_dict()
        yanit = _ozel_panel_asistan_yanit(user, message)
        if kullanici_talebe_mi(user) and not yanit:
            return AsistanYanit(
                reply=(
                    "Sana yardımcı olabilirim! **Gelişim özetim**, **bu hafta kaç soru çözdüm** "
                    "veya **bugün ne yapmalıyım** diye sorabilirsin."
                ),
                suggestions=["Gelişim özetim", "Bu hafta kaç soru çözdüm?"],
            ).as_dict()
        if yanit:
            # Kısa yönlendirme; mesaja göre ufak uyarlama
            norm = _normalize_asistan(message)
            if ogretmen_paneli_kullanicisi_mi(user):
                if any(k in norm for k in ("not", "degerlendirme", "puan")):
                    yanit = AsistanYanit(
                        reply=(
                            "Haftalık notlar için üst menüden **Not Girişi**’ne gidin; "
                            "sınıfı seçip katılım / takip / disiplin alanlarını doldurun. "
                            "Kayıtlarınız **Değerlendirmeler** sayfasında listelenir."
                        ),
                        suggestions=["Değerlendirmeler nerede?", "Ders programı PDF"],
                    )
                elif any(k in norm for k in ("program", "ders", "pdf")):
                    yanit = AsistanYanit(
                        reply=(
                            "**Ders Programı** menüsünden haftalık planınızı görebilir, "
                            "PDF indir butonuyla çıktı alabilirsiniz."
                        ),
                        suggestions=["Not girişini nasıl yaparım?"],
                    )
            else:
                if any(k in norm for k in ("not", "ders", "hafta")):
                    yanit = AsistanYanit(
                        reply=(
                            "Aktif hafta notları ana sayfada ve **Ders Notları** menüsünde. "
                            "Geçmiş haftalar için sayfadaki **Haftalar** düğmesini kullanın."
                        ),
                        suggestions=["Yoklama bilgisi", "Sohbet mevzuu nedir?"],
                    )
                elif any(k in norm for k in ("yoklama", "devamsizlik", "devamsızlık", "namaz")):
                    yanit = AsistanYanit(
                        reply=(
                            "**Yoklama** son 30 gün katılımını, **Namaz** ise namaz "
                            "yoklaması kayıtlarını gösterir."
                        ),
                        suggestions=["Haftalık notlar nerede?"],
                    )
                elif any(k in norm for k in ("sohbet", "mevzu")):
                    yanit = AsistanYanit(
                        reply=(
                            "**Sohbet Mevzuu** sayfasında yönetimin girdiği haftalık "
                            "sohbet başlığı ve içeriğini okuyabilirsiniz."
                        ),
                        suggestions=["Haftalık notlar nerede?"],
                    )
            return yanit.as_dict()

    if not message:
        return AsistanYanit(
            reply=(
                "Merhaba! Öğrenci takibi, raporlar veya panel kullanımı hakkında "
                "sohbet edebiliriz. Ne konuşmak istersiniz?"
            ),
            suggestions=[
                "Başarı analizi için ne önerirsin?",
                "5-A okuma raporu gönder",
            ],
        ).as_dict()

    analiz = analiz_et(user, message, history)
    panel_yanit = _yanit_uret(user, analiz)
    panel_komutu = net_panel_komutu_mu(message)

    # Net panel komutu + yüksek güven → doğrudan eylem (LLM yokken)
    if (
        panel_komutu
        and panel_yanit
        and analiz.guven >= 0.78
        and analiz.niyet.startswith(("pdf_", "veri_", "talebe_bilgi", "yardim"))
        and not openai_yapilandirildi_mi()
    ):
        return panel_yanit.as_dict()

    # OpenAI varsa doğal sohbet + varsa panel eylemleri
    if openai_yapilandirildi_mi():
        sohbet = llm_sohbet_cevabi(user, message, history, analiz, panel_yanit)
        if sohbet:
            return sohbet.as_dict()

    # Net panel komutu → panel yanıtı
    if panel_komutu and panel_yanit:
        return panel_yanit.as_dict()

    if panel_yanit and analiz.guven >= 0.78 and analiz.niyet.startswith(("pdf_", "veri_", "talebe_bilgi", "yardim")):
        return panel_yanit.as_dict()

    # Geri kalan her şey sohbet — varsayılan açık
    return konusma_yanit(user, message, analiz).as_dict()
