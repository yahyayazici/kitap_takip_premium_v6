/* ============================================================
   Çinili Saray — Televizyon Görüntüleyicisi
   ------------------------------------------------------------
   Görevleri:
     1) Cihazı sunucuya tanıtmak, eşleştirme kodunu göstermek
     2) ~10 sn'de bir damga sorup değiştiyse yayını çekmek
     3) Sahneleri sırayla oynatmak
     4) Acil duyuruyu mevcut yayının üzerine bindirmek
     5) Bağlantı kesilince son yayına devam etmek

   Uzun ömür: sayfa günlerce açık kalır. Bu yüzden her sahne
   değişiminde önceki sahnenin durdur()'u çağrılır (zamanlayıcı
   ve video nesneleri serbest bırakılır) ve DOM'da aynı anda en
   fazla iki sahne bulunur.
   ============================================================ */
(function () {
    'use strict';

    var SURUM = '1.0.0';

    /* Görüntüleyici iki yerde birden yayınlanıyor:
         ekran.<domain>/        → TEMEL = "/"
         <domain>/tv/           → TEMEL = "/tv/"
       Adresler bu köke göre kurulur; sabit "/api/..." yazılırsa ikinci
       durumda ana sitenin köküne istek gider ve cihaz hiç bağlanamaz. */
    var TEMEL = (window.EKRAN_TEMEL || '/');
    if (TEMEL.charAt(TEMEL.length - 1) !== '/') { TEMEL += '/'; }

    function yol(parca) { return TEMEL + parca; }
    var ANAHTAR_DEPO = 'ekran.cihaz.anahtari';
    var YAYIN_DEPO = 'ekran.son.yayin';
    var VARSAYILAN_YOKLAMA = 10;

    var sahneKatmani = document.getElementById('ek-sahne-katmani');
    var durumKatmani = document.getElementById('ek-durum-katmani');
    var acilKatmani = document.getElementById('ek-acil-katmani');
    var rozet = document.getElementById('ek-rozet');

    var durum = {
        anahtar: null,
        damga: null,
        paket: null,
        saatFarki: 0,
        yoklamaSn: VARSAYILAN_YOKLAMA,
        aktifSahne: null,
        sahneIndeksi: 0,
        sahneZamani: null,
        yoklamaZamani: null,
        cevrimici: true,
        ardArdaHata: 0,
        acilId: null
    };

    // ——— Depolama ———————————————————————————————————————————

    function depoOku(anahtar) {
        try { return localStorage.getItem(anahtar); } catch (e) { return null; }
    }
    function depoYaz(anahtar, deger) {
        try { localStorage.setItem(anahtar, deger); } catch (e) { /* özel mod */ }
    }

    function sonYayiniKaydet(paket) {
        try {
            depoYaz(YAYIN_DEPO, JSON.stringify(paket));
        } catch (e) { /* kota dolu olabilir — yayın yine de oynar */ }
    }

    function sonYayiniOku() {
        var ham = depoOku(YAYIN_DEPO);
        if (!ham) { return null; }
        try { return JSON.parse(ham); } catch (e) { return null; }
    }

    // ——— Eski televizyon tarayıcıları için yedekler ————————————
    // Akıllı TV tarayıcılarının bir kısmı 2015 öncesi WebKit/Opera
    // sürümleri; fetch() ve Promise bulunmayabiliyor. Bunlar yoksa sayfa
    // sessizce boş kalırdı. Aşağıdaki iki yedek, XMLHttpRequest üzerinden
    // aynı işi görür.

    function BasitSoz(calistir) {
        var durum = 'bekliyor', deger, basarili = [], basarisiz = [];
        function coz(d) {
            if (durum !== 'bekliyor') { return; }
            durum = 'oldu'; deger = d;
            for (var i = 0; i < basarili.length; i++) { basarili[i](deger); }
        }
        function reddet(h) {
            if (durum !== 'bekliyor') { return; }
            durum = 'olmadi'; deger = h;
            for (var i = 0; i < basarisiz.length; i++) { basarisiz[i](deger); }
        }
        this.then = function (tamam, hata) {
            var sonraki = new BasitSoz(function () {});
            function sar(islev, iletici) {
                return function (d) {
                    if (typeof islev !== 'function') { iletici(d); return; }
                    var sonuc;
                    try { sonuc = islev(d); } catch (e) { sonraki.__reddet(e); return; }
                    if (sonuc && typeof sonuc.then === 'function') {
                        sonuc.then(sonraki.__coz, sonraki.__reddet);
                    } else {
                        sonraki.__coz(sonuc);
                    }
                };
            }
            var t = sar(tamam, function (d) { sonraki.__coz(d); });
            var h = sar(hata, function (d) { sonraki.__reddet(d); });
            if (durum === 'oldu') { setTimeout(function () { t(deger); }, 0); }
            else if (durum === 'olmadi') { setTimeout(function () { h(deger); }, 0); }
            else { basarili.push(t); basarisiz.push(h); }
            return sonraki;
        };
        this['catch'] = function (hata) { return this.then(null, hata); };
        this.__coz = coz;
        this.__reddet = reddet;
        calistir(coz, reddet);
    }

    var Soz = (typeof window.Promise === 'function') ? window.Promise : BasitSoz;

    /** fetch() yoksa XMLHttpRequest ile aynı sözleşmeyi taklit eder. */
    function agIstegi(yol, secenekler) {
        if (typeof window.fetch === 'function') {
            return window.fetch(yol, secenekler);
        }
        return new Soz(function (coz, reddet) {
            var xhr = new XMLHttpRequest();
            xhr.open(secenekler.method || 'GET', yol, true);
            var basliklar = secenekler.headers || {};
            for (var ad in basliklar) {
                if (Object.prototype.hasOwnProperty.call(basliklar, ad)) {
                    try { xhr.setRequestHeader(ad, basliklar[ad]); } catch (e) { /* yoksay */ }
                }
            }
            xhr.onload = function () {
                coz({
                    status: xhr.status,
                    json: function () {
                        var govde = xhr.responseText;
                        return new Soz(function (c, r) {
                            try { c(JSON.parse(govde)); } catch (e) { r(e); }
                        });
                    }
                });
            };
            xhr.onerror = function () { reddet(new Error('ag hatasi')); };
            xhr.ontimeout = function () { reddet(new Error('zaman asimi')); };
            try { xhr.send(secenekler.body || null); } catch (e) { reddet(e); }
        });
    }

    // ——— Ağ ——————————————————————————————————————————————————

    function istek(yol, secenekler) {
        secenekler = secenekler || {};
        var basliklar = secenekler.headers || {};
        if (durum.anahtar) { basliklar['X-Ekran-Anahtar'] = durum.anahtar; }
        if (secenekler.body) { basliklar['Content-Type'] = 'application/json'; }

        return agIstegi(yol, {
            method: secenekler.method || 'GET',
            headers: basliklar,
            body: secenekler.body ? JSON.stringify(secenekler.body) : undefined,
            cache: 'no-store',
            credentials: 'omit'
        }).then(function (yanit) {
            return yanit.json().then(function (veri) {
                return { durum: yanit.status, veri: veri };
            });
        });
    }

    function cihazBilgisi() {
        return {
            surum: SURUM,
            genislik: window.screen ? window.screen.width : window.innerWidth,
            yukseklik: window.screen ? window.screen.height : window.innerHeight
        };
    }

    // ——— Durum ekranları ——————————————————————————————————————

    function durumGoster(baslik, aciklama, kod) {
        durumKatmani.innerHTML = '';
        durumKatmani.hidden = false;

        var kart = document.createElement('div');
        kart.className = 'ek-durum-kart';

        var logo = document.createElement('img');
        logo.className = 'ek-durum-logo';
        logo.src = window.EKRAN_LOGO_URL || '';
        logo.alt = '';
        kart.appendChild(logo);

        var h = document.createElement('h1');
        h.textContent = baslik;
        kart.appendChild(h);

        if (aciklama) {
            var p = document.createElement('p');
            p.textContent = aciklama;
            kart.appendChild(p);
        }

        if (kod) {
            var kodKutu = document.createElement('div');
            kodKutu.className = 'ek-durum-kod';
            kodKutu.textContent = kod;
            kart.appendChild(kodKutu);

            var ipucu = document.createElement('p');
            ipucu.className = 'ek-durum-ipucu';
            ipucu.textContent = 'Bu kodu yönetim panelindeki “Ekran eşleştir” alanına girin.';
            kart.appendChild(ipucu);
        }

        durumKatmani.appendChild(kart);
    }

    function durumGizle() {
        durumKatmani.hidden = true;
        durumKatmani.innerHTML = '';
    }

    function rozetGuncelle() {
        if (!rozet) { return; }
        rozet.classList.toggle('ek-rozet-cevrimdisi', !durum.cevrimici);
        rozet.title = durum.cevrimici ? 'Bağlantı var' : 'Bağlantı yok — son yayın oynatılıyor';
    }

    // ——— Oynatma ——————————————————————————————————————————————

    function sahneleriTemizle() {
        if (durum.aktifSahne) {
            durum.aktifSahne.durdur();
            durum.aktifSahne = null;
        }
        if (durum.sahneZamani) {
            clearTimeout(durum.sahneZamani);
            durum.sahneZamani = null;
        }
        sahneKatmani.innerHTML = '';
    }

    function sahneOynat(indeks) {
        var paket = durum.paket;
        if (!paket || !paket.sahneler || !paket.sahneler.length) {
            beklemeEkrani();
            return;
        }

        if (indeks >= paket.sahneler.length) {
            if (paket.dongu === false) {
                indeks = paket.sahneler.length - 1;   // son sahnede kal
            } else {
                indeks = 0;
            }
        }
        durum.sahneIndeksi = indeks;

        var sahne = paket.sahneler[indeks];
        var oncekiSahne = durum.aktifSahne;

        var ortam = {
            saatFarki: durum.saatFarki,
            videoBitince: function () {
                if (sahne.sure_tipi === 'video_bitene') { sonrakiSahne(); }
            }
        };

        var ornek;
        try {
            ornek = window.EkranMotoru.sahneCiz(sahneKatmani, sahne, ortam);
        } catch (hata) {
            // Bir sahne çizilemezse sonrakine geç; ekran asla boş kalmaz.
            hataBildir('Sahne çizilemedi: ' + (hata && hata.message));
            if (paket.sahneler.length > 1) {
                durum.sahneZamani = setTimeout(sonrakiSahne, 2000);
            } else {
                beklemeEkrani();
            }
            return;
        }

        window.EkranMotoru.olcekle(sahneKatmani, ornek.dugum, sahne.tuval || { g: 1920, y: 1080 });
        ornek.dugum.classList.add('ek-gecis-' + (sahne.gecis || 'soldur'));

        // Önceki sahne yeni sahne göründükten SONRA yıkılır → geçiş akıcı olur.
        requestAnimationFrame(function () {
            ornek.dugum.classList.add('ek-gorunur');
            if (oncekiSahne) {
                setTimeout(function () { oncekiSahne.durdur(); }, 600);
            }
        });

        durum.aktifSahne = ornek;
        durumGizle();

        var sure = ornek.sure();
        if (sure > 0 && paket.sahneler.length > 0) {
            durum.sahneZamani = setTimeout(sonrakiSahne, sure * 1000);
        }

        sonrakiSahneyiOnYukle(indeks + 1);
    }

    function sonrakiSahne() {
        sahneOynat(durum.sahneIndeksi + 1);
    }

    /** Sonraki sahnenin görselleri arka planda indirilir — geçişte takılma olmaz. */
    function sonrakiSahneyiOnYukle(indeks) {
        var paket = durum.paket;
        if (!paket || !paket.sahneler || !paket.sahneler.length) { return; }
        var sahne = paket.sahneler[indeks % paket.sahneler.length];
        if (!sahne) { return; }

        (sahne.ogeler || []).forEach(function (oge) {
            var kaynak = oge.kaynak;
            if (!kaynak) { return; }
            if (kaynak.tur === 'pdf') {
                (kaynak.sayfalar || []).slice(0, 3).forEach(function (s) {
                    if (s.url) { new Image().src = s.url; }
                });
            } else if (kaynak.tur === 'gorsel' && kaynak.url) {
                new Image().src = kaynak.url;
            }
        });
    }

    function beklemeEkrani() {
        sahneleriTemizle();
        durumGoster(
            'Çinili Saray Proje',
            durum.cevrimici
                ? 'Bu ekran için planlanmış bir yayın yok.'
                : 'Bağlantı bekleniyor…'
        );
    }

    // ——— Acil duyuru ——————————————————————————————————————————

    function acilGoster(acil) {
        if (!acil) {
            if (durum.acilId !== null) {
                durum.acilId = null;
                acilKatmani.hidden = true;
                acilKatmani.innerHTML = '';
            }
            return;
        }
        if (durum.acilId === acil.id) { return; }
        durum.acilId = acil.id;

        acilKatmani.innerHTML = '';
        acilKatmani.hidden = false;
        acilKatmani.className = 'ek-acil ek-acil-' + (acil.ton || 'kirmizi');
        if (acil.arka_plan_rengi) { acilKatmani.style.background = acil.arka_plan_rengi; }

        var kart = document.createElement('div');
        kart.className = 'ek-acil-kart';

        if (acil.video) {
            var video = document.createElement('video');
            video.src = acil.video;
            video.autoplay = true;
            video.muted = !acil.sesli_uyari;
            video.loop = true;
            video.playsInline = true;
            video.className = 'ek-acil-video';
            kart.appendChild(video);
            video.play().catch(function () { });
        } else if (acil.gorsel) {
            var img = document.createElement('img');
            img.src = acil.gorsel;
            img.alt = '';
            img.className = 'ek-acil-gorsel';
            kart.appendChild(img);
        }

        var baslik = document.createElement('h1');
        baslik.textContent = acil.baslik || '';
        kart.appendChild(baslik);

        if (acil.mesaj) {
            var mesaj = document.createElement('p');
            mesaj.textContent = acil.mesaj;
            kart.appendChild(mesaj);
        }

        acilKatmani.appendChild(kart);
    }

    // ——— Yayın alma ————————————————————————————————————————————

    function yayiniCek() {
        return istek(yol('api/cihaz/yayin/')).then(function (sonuc) {
            if (sonuc.durum !== 200 || !sonuc.veri) { return false; }
            var paket = sonuc.veri;

            durum.paket = paket;
            durum.damga = paket.damga;
            sonYayiniKaydet(paket);
            varliklariOnbellege(paket.varliklar || []);

            sahneleriTemizle();
            durum.sahneIndeksi = 0;
            if (paket.bos) {
                beklemeEkrani();
            } else {
                sahneOynat(0);
            }

            istek(yol('api/cihaz/rapor/'), {
                method: 'POST',
                body: {
                    damga: paket.damga,
                    paket_damgasi: paket.paket_damgasi || '',
                    sonuc: 'alindi'
                }
            }).catch(function () { });

            return true;
        });
    }

    function hataBildir(mesaj) {
        istek(yol('api/cihaz/rapor/'), {
            method: 'POST',
            body: { damga: durum.damga || '', sonuc: 'hata', mesaj: String(mesaj).slice(0, 380) }
        }).catch(function () { });
    }

    /** Service worker'a "şu dosyaları önbelleğe al" der. */
    function varliklariOnbellege(adresler) {
        if (!adresler.length) { return; }
        if (navigator.serviceWorker && navigator.serviceWorker.controller) {
            navigator.serviceWorker.controller.postMessage({
                tur: 'varliklari-onbellege',
                adresler: adresler
            });
        }
    }

    // ——— Yoklama döngüsü ————————————————————————————————————————

    function yoklamaPlanla(saniye) {
        if (durum.yoklamaZamani) { clearTimeout(durum.yoklamaZamani); }
        durum.yoklamaZamani = setTimeout(yokla, Math.max(3, saniye) * 1000);
    }

    function yokla() {
        istek(yol('api/cihaz/yoklama/'), { method: 'POST', body: cihazBilgisi() })
            .then(function (sonuc) {
                var veri = sonuc.veri || {};

                if (sonuc.durum === 404 && veri.yeniden_kaydol) {
                    // Cihaz kaydı silinmiş — baştan kaydol.
                    depoYaz(ANAHTAR_DEPO, '');
                    durum.anahtar = null;
                    return kaydol();
                }

                durum.cevrimici = true;
                durum.ardArdaHata = 0;
                rozetGuncelle();

                if (veri.sunucu_zamani) {
                    durum.saatFarki = new Date(veri.sunucu_zamani).getTime() - Date.now();
                }
                if (veri.yoklama_sn) { durum.yoklamaSn = veri.yoklama_sn; }

                if (veri.eslestirildi === false) {
                    sahneleriTemizle();
                    durum.paket = null;
                    durumGoster(
                        'Ekran eşleştirmesi bekleniyor',
                        'Bu ekranı yayına almak için aşağıdaki kodu yönetim paneline girin.',
                        veri.eslestirme_kodu
                    );
                    yoklamaPlanla(durum.yoklamaSn);
                    return null;
                }

                if (veri.pasif) {
                    sahneleriTemizle();
                    durum.paket = null;
                    durumGoster('Çinili Saray Proje', veri.mesaj || 'Bu ekran pasif durumda.');
                    yoklamaPlanla(durum.yoklamaSn);
                    return null;
                }

                if (veri.yeniden_yukle) {
                    window.location.reload();
                    return null;
                }

                acilGoster(veri.acil);

                if (veri.damga && veri.damga !== durum.damga) {
                    return yayiniCek();
                }
                return null;
            })
            .catch(function () {
                // Ağ yok. Son yayın oynamaya devam eder; ekran boş kalmaz.
                durum.cevrimici = false;
                durum.ardArdaHata += 1;
                rozetGuncelle();

                if (!durum.paket) {
                    var kayitli = sonYayiniOku();
                    if (kayitli) {
                        durum.paket = kayitli;
                        durum.damga = kayitli.damga;
                        sahneleriTemizle();
                        sahneOynat(0);
                    } else {
                        beklemeEkrani();
                    }
                }
            })
            .then(function () {
                /* Üstel geri çekilme: bağlantı yokken sunucuyu
                   saniyede bir dövmeyiz, ama 2 dakikayı da aşmayız
                   ki bağlantı gelince ekran hızla güncellensin. */
                var bekleme = durum.cevrimici
                    ? durum.yoklamaSn
                    : Math.min(120, durum.yoklamaSn * Math.pow(2, Math.min(4, durum.ardArdaHata)));
                yoklamaPlanla(bekleme);
            });
    }

    // ——— Kayıt ————————————————————————————————————————————————

    function kaydol() {
        return istek(yol('api/cihaz/kayit/'), { method: 'POST', body: cihazBilgisi() })
            .then(function (sonuc) {
                var veri = sonuc.veri || {};
                if (sonuc.durum === 429) {
                    durumGoster('Çinili Saray Proje', veri.mesaj || 'Lütfen biraz sonra tekrar deneyin.');
                    yoklamaPlanla(60);
                    return;
                }
                if (!veri.anahtar) {
                    durumGoster('Çinili Saray Proje', 'Sunucuya bağlanılamadı. Yeniden denenecek…');
                    yoklamaPlanla(15);
                    return;
                }
                durum.anahtar = veri.anahtar;
                depoYaz(ANAHTAR_DEPO, veri.anahtar);
                durumGoster(
                    'Ekran eşleştirmesi bekleniyor',
                    'Bu ekranı yayına almak için aşağıdaki kodu yönetim paneline girin.',
                    veri.eslestirme_kodu
                );
                yoklamaPlanla(veri.yoklama_sn || VARSAYILAN_YOKLAMA);
            })
            .catch(function () {
                durumGoster('Çinili Saray Proje', 'Bağlantı bekleniyor…');
                yoklamaPlanla(15);
            });
    }

    // ——— Başlangıç ————————————————————————————————————————————

    function yenidenOlcekle() {
        if (durum.aktifSahne && durum.aktifSahne.dugum) {
            var sahne = (durum.paket && durum.paket.sahneler || [])[durum.sahneIndeksi];
            window.EkranMotoru.olcekle(
                sahneKatmani,
                durum.aktifSahne.dugum,
                (sahne && sahne.tuval) || { g: 1920, y: 1080 }
            );
        }
    }

    function baslat() {
        durum.anahtar = depoOku(ANAHTAR_DEPO) || null;

        // Bağlantı gelmeden önce bile son yayın hemen oynasın.
        var kayitli = sonYayiniOku();
        if (kayitli && kayitli.sahneler && kayitli.sahneler.length) {
            durum.paket = kayitli;
            durum.damga = kayitli.damga;
            sahneOynat(0);
        } else {
            durumGoster('Çinili Saray Proje', 'Yayın hazırlanıyor…');
        }

        if (durum.anahtar) { yokla(); } else { kaydol(); }

        window.addEventListener('resize', yenidenOlcekle);
        window.addEventListener('online', function () {
            durum.ardArdaHata = 0;
            yoklamaPlanla(1);
        });
        window.addEventListener('offline', function () {
            durum.cevrimici = false;
            rozetGuncelle();
        });

        // Sekme uzun süre gizli kalıp geri gelince hemen tazele.
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) { yoklamaPlanla(1); }
        });

        if ('serviceWorker' in navigator) {
            navigator.serviceWorker.register(yol('sw.js'), { scope: TEMEL }).catch(function () { });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', baslat);
    } else {
        baslat();
    }
}());
