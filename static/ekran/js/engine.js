/* ============================================================
   Çinili Saray — Ekran Render Motoru
   ------------------------------------------------------------
   Sunucudan gelen sahne JSON'unu DOM'a çizer. Stüdyo önizlemesi
   ve televizyon görüntüleyicisi AYNI motoru kullanır; stüdyoda
   görülen ile ekrana çıkan bu sayede birebir aynıdır.

   Neden canvas kütüphanesi (Fabric/Konva) değil:
   sahnede gerçek <video>, canlı saat ve akan yazı var. Bunlar
   DOM öğeleridir; canvas'a çizilemez ya da çizilirse tarayıcı
   donanım hızlandırmasını kaybeder. DOM + CSS transform hem
   daha hafif hem de sıfır bağımlılık.

   Ölçekleme: sahne 1920×1080 (ya da projenin tuvali) tasarım
   uzayında çizilir, kapsayıcıya transform: scale() ile
   oturtulur. Böylece 1366×768, 1080p ve 4K tek veriyle çalışır.
   ============================================================ */
(function (global) {
    'use strict';

    var TR_GUNLER = ['Pazar', 'Pazartesi', 'Salı', 'Çarşamba', 'Perşembe', 'Cuma', 'Cumartesi'];
    var TR_AYLAR = ['Ocak', 'Şubat', 'Mart', 'Nisan', 'Mayıs', 'Haziran',
        'Temmuz', 'Ağustos', 'Eylül', 'Ekim', 'Kasım', 'Aralık'];

    function el(etiket, sinif) {
        var dugum = document.createElement(etiket);
        if (sinif) { dugum.className = sinif; }
        return dugum;
    }

    function ikiHane(sayi) { return (sayi < 10 ? '0' : '') + sayi; }

    /* Metin her zaman textContent ile yazılır — innerHTML asla
       kullanılmaz. Duyuru metni yönetici tarafından girilir ve
       ekranda script çalıştırmamalıdır (XSS). */
    function metinYaz(dugum, metin) {
        dugum.textContent = metin == null ? '' : String(metin);
    }

    function sayi(deger, varsayilan) {
        var n = parseFloat(deger);
        return isFinite(n) ? n : (varsayilan || 0);
    }

    // ——— Ortak stil uygulaması ———————————————————————————————

    function kutuStili(dugum, oge) {
        var s = oge.stil || {};
        var k = dugum.style;

        k.left = oge.x + 'px';
        k.top = oge.y + 'px';
        k.width = oge.g + 'px';
        k.height = oge.h + 'px';
        k.opacity = oge.opaklik == null ? 1 : oge.opaklik;
        k.zIndex = oge.katman || 0;
        if (oge.donus) {
            k.transform = 'rotate(' + oge.donus + 'deg)';
        }
        if (s.arka_plan && s.arka_plan !== 'transparent') {
            k.background = s.arka_plan;
        }
        if (s.kose) { k.borderRadius = s.kose + 'px'; }
        if (s.kenarlik_kalinlik) {
            k.border = s.kenarlik_kalinlik + 'px solid ' + (s.kenarlik_renk || '#ffffff');
        }
        if (s.ic_bosluk) { k.padding = s.ic_bosluk + 'px'; }
        if (s.golge === 'yumusak') {
            k.boxShadow = '0 18px 48px rgba(0,0,0,0.28)';
        } else if (s.golge === 'guclu') {
            k.boxShadow = '0 28px 80px rgba(0,0,0,0.45)';
        }
        if (oge.gorunur === false) { k.display = 'none'; }
    }

    function yaziStili(dugum, s) {
        var k = dugum.style;
        if (s.yazi_tipi) { k.fontFamily = '"' + s.yazi_tipi + '", Poppins, system-ui, sans-serif'; }
        if (s.punto) { k.fontSize = s.punto + 'px'; }
        if (s.kalinlik) { k.fontWeight = s.kalinlik; }
        if (s.renk) { k.color = s.renk; }
        if (s.hizalama) { k.textAlign = s.hizalama; }
        if (s.satir_araligi) { k.lineHeight = s.satir_araligi; }
        if (s.harf_araligi) { k.letterSpacing = s.harf_araligi + 'px'; }
        if (s.golge_metin) { k.textShadow = '0 4px 24px rgba(0,0,0,0.45)'; }
    }

    function nesneUydur(dugum, sigdir) {
        // "icine" = alana sığdır (kırpmaz), "doldur" = alanı doldur (kırpar)
        dugum.style.objectFit = sigdir === 'doldur' ? 'cover' : 'contain';
    }

    /**
     * Dosyası henüz seçilmemiş medya öğesi için yer tutucu.
     * YALNIZ stüdyoda çizilir (ortam.duzenleme): televizyonda boş bir kutu
     * görünmemeli — zaten eksik dosyalı yayın hiç çıkmıyor. Stüdyoda ise
     * görünmezse kullanıcı taslağı uygulayınca boş tahta sanıyor.
     */
    function yerTutucu(oge, etiket) {
        var kutu = el('div', 'ek-oge ek-yer-tutucu');
        kutuStili(kutu, oge);
        var ic = el('div', 'ek-yer-tutucu-ic');
        var baslik = el('div', 'ek-yer-tutucu-ad');
        metinYaz(baslik, oge.ad || etiket);
        var ipucu = el('div', 'ek-yer-tutucu-ipucu');
        metinYaz(ipucu, 'Dosya seçilmedi — sağdaki panelden seç ya da buraya sürükle');
        ic.appendChild(baslik);
        ic.appendChild(ipucu);
        kutu.appendChild(ic);
        return { dugum: kutu };
    }

    function kaynakVarMi(oge) {
        if (oge.kaynak && (oge.kaynak.url || (oge.kaynak.sayfalar || []).length)) { return true; }
        return !!(oge.kaynaklar && oge.kaynaklar.length);
    }

    // ——— Öğe çiziciler ————————————————————————————————————————
    // Her çizici bir DOM düğümü döndürür ve isteğe bağlı olarak
    // { baslat, durdur } yaşam döngüsü kancaları bırakır.
    // durdur(), sahne değişince ÇAĞRILIR — zamanlayıcı ve video
    // nesneleri burada temizlenir; günlerce açık kalan sayfada
    // bellek şişmesini önleyen ana mekanizma budur.

    var ciziciler = {};

    ciziciler.metin = function (oge) {
        var kutu = el('div', 'ek-oge ek-metin');
        var ic = el('div', 'ek-metin-ic');
        kutu.appendChild(ic);
        kutuStili(kutu, oge);
        yaziStili(ic, oge.stil || {});

        var s = oge.stil || {};
        ic.style.justifyContent = s.dikey_hizalama === 'flex-start' ? 'flex-start'
            : (s.dikey_hizalama === 'flex-end' ? 'flex-end' : 'center');

        var icerik = oge.icerik || {};
        var sozler = (icerik.sozler || []).filter(function (x) { return x && x.metin; });
        if (!sozler.length) { sozler = [{ metin: '', sure: 0 }]; }

        var indeks = 0;
        var zaman = null;

        function goster() {
            var soz = sozler[indeks % sozler.length];
            metinYaz(ic, soz.metin);
            if (s.tasma === 'kucult') { otomatikKucult(kutu, ic, s.punto || 48); }
        }

        return {
            dugum: kutu,
            baslat: function () {
                goster();
                if (sozler.length > 1) {
                    var sure = sayi(sozler[0].sure, 0) || sayi(icerik.ortak_sure, 8);
                    zaman = setInterval(function () {
                        indeks += 1;
                        goster();
                    }, Math.max(1, sure) * 1000);
                }
            },
            durdur: function () { if (zaman) { clearInterval(zaman); zaman = null; } }
        };
    };

    function otomatikKucult(kutu, ic, baslangicPunto) {
        // Metin kutuya sığmıyorsa punto kademeli küçültülür.
        var punto = baslangicPunto;
        ic.style.fontSize = punto + 'px';
        var guvenlik = 0;
        while (ic.scrollHeight > kutu.clientHeight && punto > 12 && guvenlik < 60) {
            punto -= Math.max(1, Math.round(punto * 0.06));
            ic.style.fontSize = punto + 'px';
            guvenlik += 1;
        }
    }

    ciziciler.gorsel = function (oge, ortam) {
        if (!kaynakVarMi(oge)) {
            return (ortam && ortam.duzenleme) ? yerTutucu(oge, 'Görsel / afiş') : { dugum: el('div') };
        }
        var kutu = el('div', 'ek-oge ek-gorsel');
        kutuStili(kutu, oge);

        var icerik = oge.icerik || {};
        var kareler = [];

        if (oge.kaynaklar && oge.kaynaklar.length) {
            oge.kaynaklar.forEach(function (k) {
                if (k.medya && k.medya.url) {
                    kareler.push({ url: k.medya.url, sure: sayi(k.sure, 8) });
                }
            });
        } else if (oge.kaynak && oge.kaynak.url) {
            kareler.push({ url: oge.kaynak.url, sure: 0 });
        }

        var gorseller = kareler.map(function (kare, i) {
            var img = el('img', 'ek-gorsel-kare');
            img.src = kare.url;
            img.alt = '';
            img.loading = 'eager';
            nesneUydur(img, icerik.sigdir);
            if (icerik.odak) { img.style.objectPosition = icerik.odak; }
            img.style.opacity = i === 0 ? '1' : '0';
            kutu.appendChild(img);
            return img;
        });

        var indeks = 0;
        var zaman = null;

        return {
            dugum: kutu,
            baslat: function () {
                if (kareler.length < 2) { return; }
                function ilerle() {
                    var onceki = gorseller[indeks % gorseller.length];
                    indeks += 1;
                    var sonraki = gorseller[indeks % gorseller.length];
                    onceki.style.opacity = '0';
                    sonraki.style.opacity = '1';
                    zaman = setTimeout(ilerle, Math.max(1, kareler[indeks % kareler.length].sure ||
                        sayi(icerik.ortak_sure, 8)) * 1000);
                }
                zaman = setTimeout(ilerle, Math.max(1, kareler[0].sure ||
                    sayi(icerik.ortak_sure, 8)) * 1000);
            },
            durdur: function () { if (zaman) { clearTimeout(zaman); zaman = null; } }
        };
    };

    ciziciler.pdf = function (oge, ortam) {
        /* PDF sayfaları sunucuda PNG'ye çevrilmiştir; burada sadece
           görsel döndürürüz. Televizyonda PDF motoru çalışmaz. */
        if (!kaynakVarMi(oge)) {
            return (ortam && ortam.duzenleme) ? yerTutucu(oge, 'Sunum (PDF)') : { dugum: el('div') };
        }
        var kutu = el('div', 'ek-oge ek-pdf');
        kutuStili(kutu, oge);

        var icerik = oge.icerik || {};
        var kaynak = oge.kaynak || {};
        var tumSayfalar = kaynak.sayfalar || [];

        // Sayfa ayarları: gizlenen sayfalar çıkarılır, sıra ve süre uygulanır.
        var ayarlar = icerik.sayfalar || [];
        var ayarHaritasi = {};
        ayarlar.forEach(function (a) { ayarHaritasi[a.no] = a; });

        var sayfalar = [];
        if (icerik.tek_sayfa != null) {
            var tek = tumSayfalar[icerik.tek_sayfa];
            if (tek) { sayfalar.push({ url: tek.url, sure: 0 }); }
        } else {
            var sira = ayarlar.length
                ? ayarlar.map(function (a) { return a.no; })
                : tumSayfalar.map(function (s, i) { return i; });
            sira.forEach(function (no) {
                var ayar = ayarHaritasi[no];
                if (ayar && ayar.gorunur === false) { return; }
                var sayfa = tumSayfalar[no];
                if (!sayfa) { return; }
                sayfalar.push({
                    url: sayfa.url,
                    sure: sayi(ayar && ayar.sure, 0) || sayi(icerik.ortak_sure, 10)
                });
            });
        }

        var gorseller = sayfalar.map(function (s, i) {
            var img = el('img', 'ek-pdf-sayfa');
            img.src = s.url;
            img.alt = '';
            nesneUydur(img, icerik.sigdir);
            img.style.opacity = i === 0 ? '1' : '0';
            kutu.appendChild(img);
            return img;
        });

        var indeks = 0;
        var zaman = null;

        return {
            dugum: kutu,
            sayfaSayisi: sayfalar.length,
            toplamSure: sayfalar.reduce(function (t, s) { return t + (s.sure || 10); }, 0),
            baslat: function () {
                if (sayfalar.length < 2) { return; }
                function ilerle() {
                    var onceki = gorseller[indeks];
                    indeks += 1;
                    if (indeks >= gorseller.length) {
                        if (icerik.dongu === false) { return; }
                        indeks = 0;
                    }
                    onceki.style.opacity = '0';
                    gorseller[indeks].style.opacity = '1';
                    zaman = setTimeout(ilerle, Math.max(1, sayfalar[indeks].sure) * 1000);
                }
                zaman = setTimeout(ilerle, Math.max(1, sayfalar[0].sure) * 1000);
            },
            durdur: function () { if (zaman) { clearTimeout(zaman); zaman = null; } }
        };
    };

    ciziciler.video = function (oge, ortam) {
        if (!kaynakVarMi(oge)) {
            return (ortam && ortam.duzenleme) ? yerTutucu(oge, 'Video') : { dugum: el('div') };
        }
        var kutu = el('div', 'ek-oge ek-video');
        kutuStili(kutu, oge);

        var icerik = oge.icerik || {};
        var kaynak = oge.kaynak || {};
        var video = document.createElement('video');
        video.playsInline = true;
        video.muted = icerik.sessiz !== false;   // otomatik oynatma için şart
        video.loop = icerik.dongu !== false;
        video.preload = 'auto';
        video.controls = false;
        nesneUydur(video, icerik.sigdir);
        if (kaynak.url) { video.src = kaynak.url; }
        kutu.appendChild(video);

        var bitisZamani = null;

        function baslangicaAl() {
            var bas = sayi(icerik.baslangic_sn, 0);
            if (bas > 0) { try { video.currentTime = bas; } catch (e) { /* metadata henüz yok */ } }
        }

        function zamanDinle() {
            var bit = sayi(icerik.bitis_sn, 0);
            if (bit > 0 && video.currentTime >= bit) {
                if (video.loop) { baslangicaAl(); } else { video.pause(); }
            }
        }

        return {
            dugum: kutu,
            video: video,
            baslat: function () {
                baslangicaAl();
                video.addEventListener('loadedmetadata', baslangicaAl);
                video.addEventListener('timeupdate', zamanDinle);
                if (icerik.otomatik_baslat !== false) {
                    var sozu = video.play();
                    if (sozu && sozu.catch) {
                        sozu.catch(function () {
                            /* Tarayıcı otomatik oynatmayı engelledi.
                               Sesi kapatıp bir kez daha denenir; yine
                               olmazsa sahne ilk karede kalır — ekranda
                               teknik hata metni ASLA gösterilmez. */
                            video.muted = true;
                            video.play().catch(function () { });
                        });
                    }
                }
                if (ortam && ortam.videoBitince) {
                    video.addEventListener('ended', ortam.videoBitince);
                }
            },
            durdur: function () {
                video.removeEventListener('loadedmetadata', baslangicaAl);
                video.removeEventListener('timeupdate', zamanDinle);
                if (bitisZamani) { clearTimeout(bitisZamani); }
                try {
                    video.pause();
                    video.removeAttribute('src');
                    video.load();   // tampon belleği bırakır
                } catch (e) { /* yoksay */ }
            }
        };
    };

    ciziciler.geri_sayim = function (oge, ortam) {
        var kutu = el('div', 'ek-oge ek-geri-sayim');
        kutuStili(kutu, oge);
        var s = oge.stil || {};
        var icerik = oge.icerik || {};

        var baslik = el('div', 'ek-gs-baslik');
        metinYaz(baslik, icerik.baslik || '');
        if (s.etiket_renk) { baslik.style.color = s.etiket_renk; }
        kutu.appendChild(baslik);

        var govde = el('div', 'ek-gs-govde');
        yaziStili(govde, s);
        kutu.appendChild(govde);

        var hedef = icerik.hedef ? new Date(icerik.hedef) : null;
        var zaman = null;

        function yaz() {
            if (!hedef || isNaN(hedef.getTime())) {
                metinYaz(govde, '—');
                return;
            }
            /* Televizyonun saati yanlış olabilir. Sunucu zamanı ile
               tarayıcı zamanı arasındaki fark ortam.saatFarki olarak
               tutulur ve burada telafi edilir. */
            var simdi = Date.now() + ((ortam && ortam.saatFarki) || 0);
            var kalan = hedef.getTime() - simdi;

            if (kalan <= 0) {
                if (icerik.bitince_gizle) { kutu.style.display = 'none'; }
                metinYaz(govde, icerik.bitince_metin || 'Süre doldu');
                if (zaman) { clearInterval(zaman); zaman = null; }
                return;
            }

            var saniye = Math.floor(kalan / 1000);
            var gun = Math.floor(saniye / 86400);
            var saat = Math.floor((saniye % 86400) / 3600);
            var dakika = Math.floor((saniye % 3600) / 60);
            var sn = saniye % 60;

            govde.textContent = '';
            [
                { goster: icerik.gun !== false, deger: gun, etiket: 'gün' },
                { goster: icerik.saat !== false, deger: ikiHane(saat), etiket: 'saat' },
                { goster: icerik.dakika !== false, deger: ikiHane(dakika), etiket: 'dakika' },
                { goster: icerik.saniye === true, deger: ikiHane(sn), etiket: 'saniye' }
            ].forEach(function (birim) {
                if (!birim.goster) { return; }
                var kart = el('div', 'ek-gs-birim');
                var deger = el('div', 'ek-gs-deger');
                metinYaz(deger, birim.deger);
                var etiket = el('div', 'ek-gs-etiket');
                metinYaz(etiket, birim.etiket);
                if (s.etiket_renk) { etiket.style.color = s.etiket_renk; }
                kart.appendChild(deger);
                kart.appendChild(etiket);
                govde.appendChild(kart);
            });
        }

        return {
            dugum: kutu,
            baslat: function () { yaz(); zaman = setInterval(yaz, 1000); },
            durdur: function () { if (zaman) { clearInterval(zaman); zaman = null; } }
        };
    };

    ciziciler.saat = function (oge, ortam) {
        var kutu = el('div', 'ek-oge ek-saat');
        kutuStili(kutu, oge);
        var s = oge.stil || {};
        var icerik = oge.icerik || {};

        var saatDugum = el('div', 'ek-saat-deger');
        yaziStili(saatDugum, s);
        kutu.appendChild(saatDugum);

        var tarihDugum = el('div', 'ek-saat-tarih');
        if (s.tarih_renk) { tarihDugum.style.color = s.tarih_renk; }
        kutu.appendChild(tarihDugum);

        var zaman = null;

        function yaz() {
            var simdi = new Date(Date.now() + ((ortam && ortam.saatFarki) || 0));
            var parcalar = [ikiHane(simdi.getHours()), ikiHane(simdi.getMinutes())];
            if (icerik.saniye) { parcalar.push(ikiHane(simdi.getSeconds())); }
            metinYaz(saatDugum, parcalar.join(':'));

            if (icerik.tarih === false) {
                tarihDugum.style.display = 'none';
                return;
            }
            var tarih = simdi.getDate() + ' ' + TR_AYLAR[simdi.getMonth()] + ' ' + simdi.getFullYear();
            if (icerik.gun_adi !== false) {
                tarih += ' · ' + TR_GUNLER[simdi.getDay()];
            }
            metinYaz(tarihDugum, tarih);
        }

        return {
            dugum: kutu,
            baslat: function () { yaz(); zaman = setInterval(yaz, 1000); },
            durdur: function () { if (zaman) { clearInterval(zaman); zaman = null; } }
        };
    };

    ciziciler.kayan_bant = function (oge) {
        var kutu = el('div', 'ek-oge ek-bant');
        kutuStili(kutu, oge);
        var s = oge.stil || {};
        var icerik = oge.icerik || {};

        if (icerik.acil) { kutu.classList.add('ek-bant-acil'); }

        var ray = el('div', 'ek-bant-ray');
        var metin = el('div', 'ek-bant-metin');
        yaziStili(metin, s);

        var duyurular = (icerik.duyurular || []).filter(Boolean);
        var ayirici = '   ' + (s.ayirici || '•') + '   ';
        metinYaz(metin, duyurular.join(ayirici) || '');

        // Kesintisiz akış için metin iki kez basılır.
        var kopya = metin.cloneNode(true);
        ray.appendChild(metin);
        ray.appendChild(kopya);
        kutu.appendChild(ray);

        return {
            dugum: kutu,
            baslat: function () {
                // Hız px/sn; süre = yol / hız.
                var genislik = metin.scrollWidth || oge.g;
                var hiz = Math.max(10, sayi(icerik.hiz, 60));
                ray.style.animationDuration = (genislik / hiz) + 's';
                ray.style.animationDirection = icerik.yon === 'saga' ? 'reverse' : 'normal';
                ray.classList.add('ek-bant-akiyor');
            },
            durdur: function () { ray.classList.remove('ek-bant-akiyor'); }
        };
    };

    ciziciler.logo = function (oge) {
        var kutu = el('div', 'ek-oge ek-logo');
        kutuStili(kutu, oge);
        var img = el('img');
        img.src = (global.EKRAN_LOGO_URL || '');
        img.alt = 'Çinili Saray Proje';
        img.style.objectFit = 'contain';
        kutu.appendChild(img);
        return { dugum: kutu };
    };

    ciziciler.qr = function (oge) {
        var kutu = el('div', 'ek-oge ek-qr');
        kutuStili(kutu, oge);
        var icerik = oge.icerik || {};
        var img = el('img');
        // QR sunucuda üretilir (segno) — dış servise bağımlılık yok.
        img.src = (global.EKRAN_QR_URL || '/ekran/qr/') + '?veri=' + encodeURIComponent(icerik.adres || '');
        img.alt = '';
        img.style.objectFit = 'contain';
        kutu.appendChild(img);
        return { dugum: kutu };
    };

    ciziciler.sekil = function (oge) {
        var kutu = el('div', 'ek-oge ek-sekil');
        kutuStili(kutu, oge);
        var icerik = oge.icerik || {};
        if (icerik.sekil === 'daire') { kutu.style.borderRadius = '50%'; }
        return { dugum: kutu };
    };

    ciziciler.cizgi = function (oge) {
        var kutu = el('div', 'ek-oge ek-cizgi');
        kutuStili(kutu, oge);
        var s = oge.stil || {};
        var kalinlik = sayi(s.kalinlik_px, 3);
        var stil = s.stil_tipi === 'kesikli' ? 'dashed' : (s.stil_tipi === 'noktali' ? 'dotted' : 'solid');
        if ((oge.icerik || {}).yon === 'dikey') {
            kutu.style.borderLeft = kalinlik + 'px ' + stil + ' ' + (s.renk || '#ffffff');
        } else {
            kutu.style.borderTop = kalinlik + 'px ' + stil + ' ' + (s.renk || '#ffffff');
        }
        return { dugum: kutu };
    };

    function listeCizici(sinif) {
        return function (oge) {
            var kutu = el('div', 'ek-oge ek-liste ' + sinif);
            kutuStili(kutu, oge);
            var s = oge.stil || {};
            var icerik = oge.icerik || {};

            var baslik = el('div', 'ek-liste-baslik');
            metinYaz(baslik, icerik.baslik || '');
            if (s.baslik_renk) { baslik.style.color = s.baslik_renk; }
            kutu.appendChild(baslik);

            var govde = el('div', 'ek-liste-govde');
            yaziStili(govde, s);
            (icerik.satirlar || []).forEach(function (satir) {
                var satirDugum = el('div', 'ek-liste-satir');
                if (satir && typeof satir === 'object') {
                    var sol = el('span', 'ek-liste-sol');
                    metinYaz(sol, satir.sol || satir.saat || '');
                    var sag = el('span', 'ek-liste-sag');
                    metinYaz(sag, satir.sag || satir.metin || '');
                    satirDugum.appendChild(sol);
                    satirDugum.appendChild(sag);
                } else {
                    metinYaz(satirDugum, satir);
                }
                govde.appendChild(satirDugum);
            });
            kutu.appendChild(govde);
            return { dugum: kutu };
        };
    }

    ciziciler.bilgi_kutusu = listeCizici('ek-bilgi');
    ciziciler.gunluk_program = listeCizici('ek-program');
    ciziciler.yemek_listesi = listeCizici('ek-yemek');
    ciziciler.sinav_duyurusu = listeCizici('ek-sinav');
    ciziciler.namaz_vakitleri = listeCizici('ek-namaz');

    // ——— Sahne ————————————————————————————————————————————————

    /**
     * Bir sahneyi verilen kapsayıcıya çizer.
     * Döndürülen nesnenin durdur()'u çağrılana kadar zamanlayıcılar
     * çalışır; sahne değişiminde MUTLAKA çağrılmalıdır.
     */
    function sahneCiz(kapsayici, sahne, ortam) {
        ortam = ortam || {};
        var tuval = sahne.tuval || { g: 1920, y: 1080 };

        var sahneDugum = el('div', 'ek-sahne');
        sahneDugum.style.width = tuval.g + 'px';
        sahneDugum.style.height = tuval.y + 'px';
        sahneDugum.style.background = (sahne.arka_plan && sahne.arka_plan.renk) || '#0f203c';
        if (sahne.arka_plan && sahne.arka_plan.gorsel) {
            sahneDugum.style.backgroundImage = 'url("' + sahne.arka_plan.gorsel.replace(/"/g, '%22') + '")';
            sahneDugum.style.backgroundSize = 'cover';
            sahneDugum.style.backgroundPosition = 'center';
        }

        var gruplar = {};
        (sahne.gruplar || []).forEach(function (g) { gruplar[g.id] = g; });

        var ornekler = [];
        var pdfOrnekleri = [];
        var videoOrnekleri = [];
        // Stüdyo, seçim çerçevesini doğru öğenin üstüne koyabilmek için
        // id → DOM düğümü eşlemesine ihtiyaç duyar.
        var dugumler = {};

        (sahne.ogeler || []).slice()
            .sort(function (a, b) { return (a.katman || 0) - (b.katman || 0); })
            .forEach(function (oge) {
                var grup = oge.grup != null ? gruplar[oge.grup] : null;
                if (grup && grup.gorunur === false) { return; }

                var cizici = ciziciler[oge.tur];
                if (!cizici) { return; }

                var ornek;
                try {
                    ornek = cizici(oge, ortam);
                } catch (hata) {
                    // Tek bir öğe çizilemezse sahnenin tamamı düşmez.
                    if (global.console && console.warn) {
                        console.warn('Öğe çizilemedi:', oge.tur, hata);
                    }
                    return;
                }
                if (!ornek || !ornek.dugum) { return; }

                if (oge.id != null) {
                    ornek.dugum.setAttribute('data-oge-id', oge.id);
                    dugumler[oge.id] = ornek.dugum;
                }
                sahneDugum.appendChild(ornek.dugum);
                ornekler.push(ornek);
                if (oge.tur === 'pdf') { pdfOrnekleri.push(ornek); }
                if (oge.tur === 'video') { videoOrnekleri.push(ornek); }
            });

        kapsayici.appendChild(sahneDugum);
        ornekler.forEach(function (o) { if (o.baslat) { o.baslat(); } });

        return {
            dugum: sahneDugum,
            dugumler: dugumler,
            pdfOrnekleri: pdfOrnekleri,
            videoOrnekleri: videoOrnekleri,
            /** Sahnenin gerçek süresi (saniye) — oynatıcı bunu kullanır. */
            sure: function () {
                if (sahne.sure_tipi === 'suresiz') { return 0; }
                if (sahne.sure_tipi === 'video_bitene') { return 0; }
                if (sahne.sure_tipi === 'pdf_bitene') {
                    var toplam = pdfOrnekleri.reduce(function (t, p) {
                        return Math.max(t, p.toplamSure || 0);
                    }, 0);
                    return toplam || sahne.sure_sn || 20;
                }
                return sahne.sure_sn || 20;
            },
            durdur: function () {
                ornekler.forEach(function (o) {
                    if (o.durdur) {
                        try { o.durdur(); } catch (e) { /* yoksay */ }
                    }
                });
                ornekler.length = 0;
                if (sahneDugum.parentNode) {
                    sahneDugum.parentNode.removeChild(sahneDugum);
                }
            }
        };
    }

    /**
     * Tasarım uzayını kapsayıcıya oturtur.
     * 1920×1080 tasarım; 1366×768, 1080p ve 4K'da bozulmadan çalışır.
     */
    function olcekle(kapsayici, sahneDugum, tuval) {
        var kutu = kapsayici.getBoundingClientRect();
        if (!kutu.width || !kutu.height) { return 1; }
        var olcek = Math.min(kutu.width / tuval.g, kutu.height / tuval.y);
        sahneDugum.style.transformOrigin = 'top left';
        sahneDugum.style.transform = 'scale(' + olcek + ')';
        sahneDugum.style.left = ((kutu.width - tuval.g * olcek) / 2) + 'px';
        sahneDugum.style.top = ((kutu.height - tuval.y * olcek) / 2) + 'px';
        return olcek;
    }

    global.EkranMotoru = {
        sahneCiz: sahneCiz,
        olcekle: olcekle,
        ciziciler: ciziciler,
        TR_GUNLER: TR_GUNLER,
        TR_AYLAR: TR_AYLAR
    };
}(window));
