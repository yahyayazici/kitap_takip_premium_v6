"""Konu destek — yapay zeka ile mini test sorusu üretimi."""

from __future__ import annotations

from takip.ai_gateway import ai_json_uret, ai_llm_aktif_mi, onbellekten_al, onbellege_yaz
from takip.konu_destek_models import KonuKatalogu, KonuSorusu


def _ai_anahtar(konu: KonuKatalogu) -> str:
    return f"konu-{konu.pk}-v1"


def _kural_tabanli_sorular(konu: KonuKatalogu, adet: int = 5) -> list[dict]:
    """OpenAI yoksa basit pedagojik soru şablonları."""
    konu_ad = konu.konu_ad
    brans = konu.brans_etiket
    sinif = konu.sinif_seviyesi
    sablon = [
        {
            "soru_metni": f"{sinif}. sınıf {brans} dersinde «{konu_ad}» konusunun temel kavramı aşağıdakilerden hangisidir?",
            "secenek_a": f"{konu_ad} konusunun tanım ve kuralları",
            "secenek_b": "Konu ile ilgisi olmayan bir kavram",
            "secenek_c": "Yalnızca ezber gerektiren bir bilgi",
            "secenek_d": "Sınavda hiç sorulmayan bir detay",
            "dogru_secenek": "A",
            "aciklama": f"«{konu_ad}» konusunun temel tanım ve kurallarını bilmek gerekir.",
        },
        {
            "soru_metni": f"«{konu_ad}» konusunda en sık yapılan hata hangisidir?",
            "secenek_a": "Formülü yanlış uygulamak",
            "secenek_b": "Konuyu hiç çalışmamak",
            "secenek_c": "Soruyu dikkatlice okumak",
            "secenek_d": "Konu tekrarı yapmak",
            "dogru_secenek": "A",
            "aciklama": "Kural ve formüllerin doğru uygulanması kritiktir.",
        },
        {
            "soru_metni": f"{konu_ad} konusunu pekiştirmek için en etkili yöntem hangisidir?",
            "secenek_a": "Konu anlatımı izleyip ardından soru çözmek",
            "secenek_b": "Yalnızca videoyu izleyip bırakmak",
            "secenek_c": "Konuyu atlayıp sonraki üniteye geçmek",
            "secenek_d": "Sadece cevap anahtarına bakmak",
            "dogru_secenek": "A",
            "aciklama": "İzleme + uygulama birlikte öğrenmeyi kalıcı kılar.",
        },
        {
            "soru_metni": f"LGS {brans} sınavında «{konu_ad}» konusundan soru gelme olasılığı için ne söylenir?",
            "secenek_a": "Müfredatta yer aldığı için soru gelebilir",
            "secenek_b": "Hiçbir zaman sorulmaz",
            "secenek_c": "Yalnızca yazılıda sorulur",
            "secenek_d": "Sadece sözlü sınavda çıkar",
            "dogru_secenek": "A",
            "aciklama": "Müfredat konuları sınavda değerlendirilir.",
        },
        {
            "soru_metni": f"«{konu_ad}» konusunda zayıfsan ilk adım ne olmalıdır?",
            "secenek_a": "Temel kavramları tekrar etmek",
            "secenek_b": "Zor sorularla başlamak",
            "secenek_c": "Konuyu tamamen atlamak",
            "secenek_d": "Sadece deneme çözmek",
            "dogru_secenek": "A",
            "aciklama": "Önce temel, sonra ileri seviye soru çözümü.",
        },
    ]
    return sablon[:adet]


def _llm_sorulari_uret(konu: KonuKatalogu, adet: int = 5) -> list[dict] | None:
    if not ai_llm_aktif_mi():
        return None

    anahtar = _ai_anahtar(konu)
    onbellek = onbellekten_al("konu_destek_test", anahtar)
    if onbellek and isinstance(onbellek.get("sorular"), list):
        return onbellek["sorular"][:adet]

    system = (
        "Sen Türkiye LGS müfredatına hakim bir öğretmensin. "
        "Yalnızca geçerli JSON döndür. Sorular sınıf seviyesine uygun, net ve tek doğru cevaplı olsun."
    )
    prompt = f"""
{konu.sinif_seviyesi}. sınıf {konu.brans_etiket} — «{konu.konu_ad}» konusu için {adet} adet çoktan seçmeli soru üret.

JSON formatı:
{{
  "sorular": [
    {{
      "soru_metni": "...",
      "secenek_a": "...",
      "secenek_b": "...",
      "secenek_c": "...",
      "secenek_d": "...",
      "dogru_secenek": "A",
      "aciklama": "Kısa açıklama"
    }}
  ]
}}
"""
    llm = ai_json_uret(system=system, user_prompt=prompt, temperature=0.5, max_tokens=2200)
    if not llm or not isinstance(llm.get("sorular"), list):
        return None

    sorular = []
    for satir in llm["sorular"][:adet]:
        if not isinstance(satir, dict):
            continue
        dogru = str(satir.get("dogru_secenek", "A")).strip().upper()[:1]
        if dogru not in {"A", "B", "C", "D"}:
            dogru = "A"
        metin = (satir.get("soru_metni") or "").strip()
        if not metin:
            continue
        sorular.append(
            {
                "soru_metni": metin,
                "secenek_a": (satir.get("secenek_a") or "A şıkkı").strip(),
                "secenek_b": (satir.get("secenek_b") or "B şıkkı").strip(),
                "secenek_c": (satir.get("secenek_c") or "C şıkkı").strip(),
                "secenek_d": (satir.get("secenek_d") or "D şıkkı").strip(),
                "dogru_secenek": dogru,
                "aciklama": (satir.get("aciklama") or "").strip(),
            }
        )

    if sorular:
        onbellege_yaz("konu_destek_test", anahtar, {"sorular": sorular})
    return sorular or None


def _sorulari_kaydet(konu: KonuKatalogu, ham_sorular: list[dict]) -> list[KonuSorusu]:
    kayitlar: list[KonuSorusu] = []
    mevcut_sira = int(
        konu.sorular.order_by("-sira").values_list("sira", flat=True).first() or 0
    )
    for satir in ham_sorular:
        mevcut_sira += 1
        soru, _ = KonuSorusu.objects.update_or_create(
            konu=konu,
            soru_metni=satir["soru_metni"],
            defaults={
                "secenek_a": satir["secenek_a"],
                "secenek_b": satir["secenek_b"],
                "secenek_c": satir["secenek_c"],
                "secenek_d": satir["secenek_d"],
                "dogru_secenek": satir["dogru_secenek"],
                "aciklama": f"AI: {satir.get('aciklama', '')}".strip(),
                "sira": mevcut_sira,
                "aktif": True,
            },
        )
        kayitlar.append(soru)
    return kayitlar


def konu_ai_sorulari_hazirla(konu: KonuKatalogu, hedef: int = 5) -> tuple[list[KonuSorusu], str]:
    """
    Konu için mini test sorularını hazırla.
    Dönüş: (sorular, kaynak_etiket) — kaynak: 'ai', 'kural', 'havuz'
    """
    mevcut = list(konu.sorular.filter(aktif=True).order_by("sira", "id")[:hedef])
    if len(mevcut) >= hedef:
        return mevcut[:hedef], "havuz"

    eksik = hedef - len(mevcut)
    llm = _llm_sorulari_uret(konu, adet=eksik)
    kaynak = "ai"
    if not llm:
        llm = _kural_tabanli_sorular(konu, adet=eksik)
        kaynak = "kural"

    if llm:
        yeni = _sorulari_kaydet(konu, llm)
        mevcut.extend(yeni)

    return mevcut[:hedef], kaynak
