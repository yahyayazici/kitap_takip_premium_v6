"""Django messages — çoklu hataları tek özet mesaja indirger."""



from __future__ import annotations



from django.contrib import messages





def hatalari_ozetle(

    request,

    hatalar: list[str],

    *,

    tek_baslik: str | None = None,

    ornek_limit: int = 2,

) -> None:

    """Birden fazla satır hatasını tek toast'ta gösterir."""

    if not hatalar:

        return

    if len(hatalar) == 1:

        messages.error(request, hatalar[0])

        return



    ortak = None

    isimler: list[str] = []

    for h in hatalar:

        if ": " not in h:

            ortak = None

            break

        ad, mesaj = h.split(": ", 1)

        if ortak is None:

            ortak = mesaj

        if mesaj != ortak:

            ortak = None

            break

        isimler.append(ad)



    if ortak and len(isimler) == len(hatalar):

        ornek = ", ".join(isimler[:ornek_limit])

        kalan = len(isimler) - ornek_limit

        baslik = tek_baslik or ortak

        metin = f"{len(hatalar)} satır — {baslik}"

        if ornek:

            metin += f" · örn. {ornek}"

            if kalan > 0:

                metin += f" +{kalan}"

        messages.error(request, metin)

        return



    ornekler = "; ".join(hatalar[:ornek_limit])

    kalan = len(hatalar) - ornek_limit

    if tek_baslik:

        metin = f"{tek_baslik} ({len(hatalar)} satır). Örnek: {ornekler}"

    else:

        metin = f"{len(hatalar)} satırda hata. Örnek: {ornekler}"

    if kalan > 0:

        metin += f" … +{kalan} uyarı daha"

    messages.error(request, metin)


