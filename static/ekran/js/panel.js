/* Ekran yönetim paneli — küçük ortak davranışlar. */
(function () {
    'use strict';

    // Bildirimler: elle kapatılabilir, başarı mesajları kendiliğinden solar.
    document.querySelectorAll('[data-ekp-bildirim] .ekp-bildirim').forEach(function (kutu) {
        var kapat = kutu.querySelector('.ekp-bildirim-kapat');
        if (kapat) {
            kapat.addEventListener('click', function () { kutu.remove(); });
        }
        if (kutu.classList.contains('ekp-bildirim-success')) {
            setTimeout(function () {
                kutu.style.opacity = '0';
                setTimeout(function () { kutu.remove(); }, 300);
            }, 6000);
        }
    });

    // Geri alınamayan işlemler için onay. data-onay="metin"
    document.querySelectorAll('[data-onay]').forEach(function (dugum) {
        dugum.addEventListener('click', function (olay) {
            if (!window.confirm(dugum.getAttribute('data-onay'))) {
                olay.preventDefault();
                olay.stopPropagation();
            }
        });
    });

    // Açılır bölümler (gelişmiş ayarlar ilk ekranda yığılmasın)
    document.querySelectorAll('[data-ekp-katla]').forEach(function (baslik) {
        var hedef = document.getElementById(baslik.getAttribute('data-ekp-katla'));
        if (!hedef) { return; }
        baslik.addEventListener('click', function () {
            var acik = hedef.hasAttribute('hidden');
            if (acik) { hedef.removeAttribute('hidden'); } else { hedef.setAttribute('hidden', ''); }
            baslik.setAttribute('aria-expanded', acik ? 'true' : 'false');
        });
    });

    // Cihaz listesi canlı durum yenilemesi
    var durumKutusu = document.querySelector('[data-ekp-cihaz-durum]');
    if (durumKutusu) {
        var adres = durumKutusu.getAttribute('data-ekp-cihaz-durum');
        setInterval(function () {
            fetch(adres, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (y) { return y.json(); })
                .then(function (veri) {
                    (veri.cihazlar || []).forEach(function (c) {
                        var satir = document.querySelector('[data-cihaz-id="' + c.id + '"]');
                        if (!satir) { return; }
                        var rozet = satir.querySelector('[data-cihaz-rozet]');
                        if (rozet) {
                            rozet.classList.toggle('ekp-rozet-cevrimici', c.cevrimici);
                            rozet.classList.toggle('ekp-rozet-cevrimdisi', !c.cevrimici);
                            rozet.textContent = c.cevrimici ? 'Çevrim içi' : 'Çevrim dışı';
                        }
                        var zaman = satir.querySelector('[data-cihaz-zaman]');
                        if (zaman) { zaman.textContent = c.son_baglanti || '—'; }
                    });
                })
                .catch(function () { /* geçici ağ hatası — bir sonraki turda düzelir */ });
        }, 15000);
    }
}());
