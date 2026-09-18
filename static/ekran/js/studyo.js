/* ============================================================
   Çinili Saray — Ekran Tasarım Stüdyosu
   ------------------------------------------------------------
   Tuval, gerçek render motorunun (engine.js) çıktısını gösterir;
   üstüne yalnız seçim çerçevesi ve tutamaklar bindirilir. Bu
   yüzden stüdyoda görülen, televizyonda çıkacak olanın birebir
   kendisidir.

   Performans: sürükleme/boyutlandırma sırasında sahne yeniden
   çizilmez — yalnız ilgili DOM düğümünün style'ı güncellenir.
   Tam yeniden çizim, öğe eklenince/silinince ya da özellik
   değişince yapılır.
   ============================================================ */
(function () {
    'use strict';

    var kok = document.getElementById('ek-studyo');
    if (!kok) { return; }

    var BAS = JSON.parse(document.getElementById('ek-baslangic').textContent);
    var TUVAL = BAS.proje.tuval;
    var SALT_OKUNUR = BAS.salt_okunur;
    var YAPISMA_ESIGI = 6;          // tasarım pikseli
    var GECMIS_SINIRI = 60;

    // ——— Durum ———————————————————————————————————————————————

    var D = {
        sahne: BAS.sahne,
        secili: [],                 // öğe id dizisi
        zoom: 1,
        zoomModu: 'sigdir',
        gecmis: [],
        gecmisIndeksi: -1,
        pano: null,
        kirli: false,
        kaydediliyor: false,
        sonKayit: null,
        ornek: null,                // engine sahne örneği
        gecicilId: -1               // yeni öğeler için negatif geçici id
    };

    // ——— DOM ————————————————————————————————————————————————

    var tuvalAlan = document.getElementById('ek-tuval-alan');
    var tuvalSahne = document.getElementById('ek-tuval-sahne');
    var kaplama = document.getElementById('ek-kaplama');
    var kilavuzKat = document.getElementById('ek-kilavuzlar');
    var katmanListe = document.getElementById('ek-katman-liste');
    var ozellikPanel = document.getElementById('ek-ozellik-panel');
    var ogeKatalog = document.getElementById('ek-oge-katalog');
    var durumMetni = document.getElementById('ek-durum-metni');
    var zoomEtiket = document.getElementById('ek-zoom-etiket');

    function $(secici, kapsam) { return (kapsam || document).querySelector(secici); }
    function olustur(etiket, sinif, metin) {
        var d = document.createElement(etiket);
        if (sinif) { d.className = sinif; }
        if (metin != null) { d.textContent = metin; }
        return d;
    }

    // ——— Yardımcılar ——————————————————————————————————————————

    function ogeBul(id) {
        for (var i = 0; i < D.sahne.ogeler.length; i += 1) {
            if (String(D.sahne.ogeler[i].id) === String(id)) { return D.sahne.ogeler[i]; }
        }
        return null;
    }

    function seciliOgeler() {
        return D.secili.map(ogeBul).filter(Boolean);
    }

    function kilitliMi(oge) { return !!(oge && oge.kilitli); }

    function yeniId() {
        D.gecicilId -= 1;
        return D.gecicilId;
    }

    function kopyala(nesne) { return JSON.parse(JSON.stringify(nesne)); }

    function sayi(deger, varsayilan) {
        var n = parseFloat(deger);
        return isFinite(n) ? n : (varsayilan || 0);
    }

    // ——— Geçmiş (geri al / ileri al) ————————————————————————————

    function gecmiseYaz() {
        D.gecmis = D.gecmis.slice(0, D.gecmisIndeksi + 1);
        D.gecmis.push(kopyala(D.sahne));
        if (D.gecmis.length > GECMIS_SINIRI) { D.gecmis.shift(); }
        D.gecmisIndeksi = D.gecmis.length - 1;
        D.kirli = true;
        durumGuncelle();
    }

    function geriAl() {
        if (D.gecmisIndeksi <= 0) { return; }
        D.gecmisIndeksi -= 1;
        D.sahne = kopyala(D.gecmis[D.gecmisIndeksi]);
        D.secili = D.secili.filter(function (id) { return ogeBul(id); });
        D.kirli = true;
        cizTam();
    }

    function ileriAl() {
        if (D.gecmisIndeksi >= D.gecmis.length - 1) { return; }
        D.gecmisIndeksi += 1;
        D.sahne = kopyala(D.gecmis[D.gecmisIndeksi]);
        D.secili = D.secili.filter(function (id) { return ogeBul(id); });
        D.kirli = true;
        cizTam();
    }

    // ——— Çizim ————————————————————————————————————————————————

    function zoomHesapla() {
        if (D.zoomModu !== 'sigdir') { return D.zoom; }
        var kutu = tuvalAlan.getBoundingClientRect();
        var pay = 56;
        return Math.min(
            (kutu.width - pay) / TUVAL.g,
            (kutu.height - pay) / TUVAL.y
        );
    }

    function cizTam() {
        if (D.ornek) { D.ornek.durdur(); }
        tuvalSahne.innerHTML = '';

        D.zoom = zoomHesapla();
        var genislik = TUVAL.g * D.zoom;
        var yukseklik = TUVAL.y * D.zoom;

        tuvalSahne.style.width = genislik + 'px';
        tuvalSahne.style.height = yukseklik + 'px';
        kaplama.style.width = genislik + 'px';
        kaplama.style.height = yukseklik + 'px';

        var sahneKopya = kopyala(D.sahne);
        sahneKopya.tuval = TUVAL;

        try {
            // duzenleme: dosyası seçilmemiş öğeler yer tutucu olarak görünsün.
            D.ornek = window.EkranMotoru.sahneCiz(tuvalSahne, sahneKopya, { saatFarki: 0, duzenleme: true });
        } catch (hata) {
            D.ornek = null;
            if (window.console) { console.warn('Sahne çizilemedi', hata); }
        }

        if (D.ornek) {
            var dugum = D.ornek.dugum;
            dugum.style.transformOrigin = 'top left';
            dugum.style.transform = 'scale(' + D.zoom + ')';
            dugum.style.left = '0';
            dugum.style.top = '0';
            dugum.classList.add('ek-gorunur');
        }

        kaplamaCiz();
        katmanlariCiz();
        ozellikleriCiz();
        zoomEtiket.textContent = Math.round(D.zoom * 100) + '%';
    }

    /** Seçim çerçeveleri ve tutamaklar — ekran uzayında çizilir ki
        tutamaklar yakınlaştırmayla büyüyüp küçülmesin. */
    function kaplamaCiz() {
        kaplama.innerHTML = '';
        if (SALT_OKUNUR) { return; }

        seciliOgeler().forEach(function (oge, indeks) {
            var cerceve = olustur('div', 'ek-secim' + (kilitliMi(oge) ? ' ek-secim-kilitli' : ''));
            cerceve.style.left = (oge.x * D.zoom) + 'px';
            cerceve.style.top = (oge.y * D.zoom) + 'px';
            cerceve.style.width = (oge.g * D.zoom) + 'px';
            cerceve.style.height = (oge.h * D.zoom) + 'px';
            if (oge.donus) { cerceve.style.transform = 'rotate(' + oge.donus + 'deg)'; }
            cerceve.setAttribute('data-secim-id', oge.id);

            if (!kilitliMi(oge) && D.secili.length === 1) {
                ['kb', 'ku', 'sb', 'su', 'u', 'a', 'sol', 'sag'].forEach(function (yon) {
                    var tutamak = olustur('span', 'ek-tutamak ek-tutamak-' + yon);
                    tutamak.setAttribute('data-tutamak', yon);
                    cerceve.appendChild(tutamak);
                });
                var donduruci = olustur('span', 'ek-dondur');
                donduruci.setAttribute('data-tutamak', 'dondur');
                donduruci.title = 'Döndür';
                cerceve.appendChild(donduruci);
            }

            if (indeks === 0) {
                var etiketMetni = oge.ad || oge.tur;
                if (oge.tur === 'metin') { etiketMetni += ' · yazmak için çift tıkla'; }
                var etiket = olustur('span', 'ek-secim-etiket', etiketMetni);
                cerceve.appendChild(etiket);
            }

            kaplama.appendChild(cerceve);
        });
    }

    function kilavuzTemizle() { kilavuzKat.innerHTML = ''; }

    function kilavuzCiz(yon, konum) {
        var cizgi = olustur('div', 'ek-kilavuz ek-kilavuz-' + yon);
        if (yon === 'dikey') {
            cizgi.style.left = (konum * D.zoom) + 'px';
        } else {
            cizgi.style.top = (konum * D.zoom) + 'px';
        }
        kilavuzKat.appendChild(cizgi);
    }

    // ——— Katman paneli ————————————————————————————————————————

    function katmanlariCiz() {
        katmanListe.innerHTML = '';
        var sirali = D.sahne.ogeler.slice().sort(function (a, b) {
            return (b.katman || 0) - (a.katman || 0);   // üstteki en başta
        });

        if (!sirali.length) {
            katmanListe.appendChild(olustur('p', 'ek-yan-bos', 'Henüz öğe yok. Soldan bir öğe ekleyin.'));
            return;
        }

        sirali.forEach(function (oge) {
            var satir = olustur('div', 'ek-katman' +
                (D.secili.indexOf(oge.id) >= 0 ? ' ek-katman-secili' : ''));
            satir.setAttribute('data-katman-id', oge.id);
            satir.draggable = !SALT_OKUNUR;

            var ad = olustur('button', 'ek-katman-ad');
            ad.type = 'button';
            ad.textContent = oge.ad || oge.tur;
            ad.title = 'Adı değiştirmek için çift tıklayın';
            ad.addEventListener('click', function (olay) {
                sec(oge.id, olay.shiftKey || olay.metaKey || olay.ctrlKey);
            });
            ad.addEventListener('dblclick', function () { katmanAdiDuzenle(oge, ad); });
            satir.appendChild(ad);

            var eylemler = olustur('span', 'ek-katman-eylem');

            var gorunurDugme = olustur('button', 'ek-ikon-dugme', oge.gorunur === false ? '🚫' : '👁');
            gorunurDugme.type = 'button';
            gorunurDugme.title = oge.gorunur === false ? 'Göster' : 'Gizle';
            gorunurDugme.addEventListener('click', function () {
                oge.gorunur = oge.gorunur === false;
                gecmiseYaz();
                cizTam();
            });
            eylemler.appendChild(gorunurDugme);

            var kilitDugme = olustur('button', 'ek-ikon-dugme', oge.kilitli ? '🔒' : '🔓');
            kilitDugme.type = 'button';
            kilitDugme.title = oge.kilitli ? 'Kilidi aç' : 'Kilitle';
            kilitDugme.addEventListener('click', function () {
                oge.kilitli = !oge.kilitli;
                gecmiseYaz();
                cizTam();
            });
            eylemler.appendChild(kilitDugme);

            satir.appendChild(eylemler);

            if (!SALT_OKUNUR) {
                satir.addEventListener('dragstart', function (olay) {
                    olay.dataTransfer.setData('text/plain', String(oge.id));
                    satir.classList.add('ek-katman-tasiniyor');
                });
                satir.addEventListener('dragend', function () {
                    satir.classList.remove('ek-katman-tasiniyor');
                });
                satir.addEventListener('dragover', function (olay) { olay.preventDefault(); });
                satir.addEventListener('drop', function (olay) {
                    olay.preventDefault();
                    var tasinanId = olay.dataTransfer.getData('text/plain');
                    katmanTasi(tasinanId, oge.id);
                });
            }

            katmanListe.appendChild(satir);
        });
    }

    function katmanAdiDuzenle(oge, dugum) {
        var girdi = olustur('input', 'ek-katman-girdi');
        girdi.value = oge.ad || '';
        dugum.replaceWith(girdi);
        girdi.focus();
        girdi.select();

        function bitir() {
            oge.ad = girdi.value.trim().slice(0, 120);
            gecmiseYaz();
            katmanlariCiz();
        }
        girdi.addEventListener('blur', bitir);
        girdi.addEventListener('keydown', function (olay) {
            if (olay.key === 'Enter') { girdi.blur(); }
            if (olay.key === 'Escape') { girdi.value = oge.ad || ''; girdi.blur(); }
        });
    }

    function katmanTasi(tasinanId, hedefId) {
        var tasinan = ogeBul(tasinanId);
        var hedef = ogeBul(hedefId);
        if (!tasinan || !hedef || tasinan === hedef) { return; }
        var yeni = hedef.katman;
        tasinan.katman = yeni;
        // Aradaki öğeleri kaydır ki sıra benzersiz kalsın.
        D.sahne.ogeler.forEach(function (o) {
            if (o !== tasinan && o.katman >= yeni) { o.katman += 1; }
        });
        katmanlariNormalize();
        gecmiseYaz();
        cizTam();
    }

    function katmanlariNormalize() {
        D.sahne.ogeler
            .slice()
            .sort(function (a, b) { return (a.katman || 0) - (b.katman || 0); })
            .forEach(function (o, i) { o.katman = i; });
    }

    // ——— Seçim ————————————————————————————————————————————————

    function sec(id, ekle) {
        if (SALT_OKUNUR) { return; }
        var mevcut = D.secili.indexOf(id);
        if (ekle) {
            if (mevcut >= 0) { D.secili.splice(mevcut, 1); } else { D.secili.push(id); }
        } else {
            D.secili = id == null ? [] : [id];
        }
        kaplamaCiz();
        katmanlariCiz();
        ozellikleriCiz();
    }

    function secimiTemizle() { sec(null, false); }

    // ——— Öğe ekleme / silme ————————————————————————————————————

    function katalogCiz() {
        var gruplar = {};
        BAS.katalog.forEach(function (tanim) {
            (gruplar[tanim.grup] = gruplar[tanim.grup] || []).push(tanim);
        });

        Object.keys(gruplar).forEach(function (grupAdi) {
            var baslik = olustur('h4', 'ek-yan-baslik', grupAdi);
            ogeKatalog.appendChild(baslik);

            var kutu = olustur('div', 'ek-katalog-izgara');
            gruplar[grupAdi].forEach(function (tanim) {
                var dugme = olustur('button', 'ek-katalog-dugme');
                dugme.type = 'button';
                dugme.title = tanim.aciklama;
                dugme.disabled = SALT_OKUNUR;
                dugme.appendChild(olustur('span', 'ek-katalog-ad', tanim.ad));
                dugme.addEventListener('click', function () { ogeEkle(tanim); });
                kutu.appendChild(dugme);
            });
            ogeKatalog.appendChild(kutu);
        });
    }

    function ogeEkle(tanim, medya) {
        var v = tanim.varsayilan;
        var g = Math.min(v.g, TUVAL.g);
        var h = Math.min(v.y, TUVAL.y);

        var oge = {
            id: yeniId(),
            tur: tanim.tur,
            ad: tanim.ad,
            x: Math.round((TUVAL.g - g) / 2),
            y: Math.round((TUVAL.y - h) / 2),
            g: g,
            h: h,
            donus: 0,
            katman: D.sahne.ogeler.length,
            opaklik: 1,
            kilitli: false,
            gorunur: true,
            stil: kopyala(v.stil || {}),
            icerik: kopyala(v.icerik || {}),
            zamanlama: {},
            animasyon: {}
        };

        if (medya) { ogeyeMedyaBagla(oge, medya, true); }

        D.sahne.ogeler.push(oge);
        D.secili = [oge.id];
        gecmiseYaz();
        cizTam();
        tuvaliGorunurYap();

        if (tanim.medya_gerekir && !medya) {
            medyaSeciciAc(tanim.medya_turu, function (secilen) {
                ogeyeMedyaBagla(oge, secilen, true);
                gecmiseYaz();
                cizTam();
            });
        }
    }

    /**
     * Öğeye medya bağlar.
     * @param {boolean} oranaUydur Yalnız yeni eklenen öğede true. Var olan
     *   bir kutuya dosya seçilirken kutu ölçüsüne DOKUNULMAZ; kullanıcının
     *   (ya da şablonun) kurduğu yerleşim bozulmamalıdır. Görselin çarpık
     *   görünmemesi zaten "alana sığdır" ayarıyla sağlanır.
     */
    /**
     * Dar pencerede içerik listesi tuvalin üstünde kalabiliyor; öğe eklenince
     * kullanıcı "hiçbir şey olmadı" sanmasın diye tuvali görüş alanına getir.
     */
    function tuvaliGorunurYap() {
        var kutu = tuvalAlan.getBoundingClientRect();
        var gorunuyor = kutu.top < window.innerHeight * 0.75 && kutu.bottom > 80;
        if (!gorunuyor && tuvalAlan.scrollIntoView) {
            tuvalAlan.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
    }

    function ogeyeMedyaBagla(oge, medya, oranaUydur) {
        oge.medya_id = medya.id;
        oge.kaynak = {
            id: medya.id,
            tur: medya.tur,
            ad: medya.ad,
            url: medya.url,
            g: medya.g,
            y: medya.y,
            sayfalar: medya.sayfalar || [],
            sayfa_sayisi: medya.sayfa_sayisi,
            sure: medya.sure
        };
        if (!oge.ad || oge.ad === 'PDF' || oge.ad === 'Görsel / afiş' || oge.ad === 'Video') {
            oge.ad = medya.ad;
        }
        if (oranaUydur && medya.g && medya.y && medya.tur === 'gorsel') {
            var oran = medya.g / medya.y;
            oge.h = Math.round(oge.g / oran);
            if (oge.h > TUVAL.y) {
                oge.h = TUVAL.y;
                oge.g = Math.round(oge.h * oran);
            }
        }
    }

    function seciliSil() {
        if (SALT_OKUNUR || !D.secili.length) { return; }
        var silinecek = seciliOgeler().filter(function (o) { return !kilitliMi(o); });
        if (!silinecek.length) { return; }
        D.sahne.ogeler = D.sahne.ogeler.filter(function (o) {
            return silinecek.indexOf(o) < 0;
        });
        D.secili = [];
        katmanlariNormalize();
        gecmiseYaz();
        cizTam();
    }

    function seciliCogalt() {
        if (SALT_OKUNUR) { return; }
        var yeniler = seciliOgeler().map(function (oge) {
            var kopya2 = kopyala(oge);
            kopya2.id = yeniId();
            kopya2.x += 24;
            kopya2.y += 24;
            kopya2.katman = D.sahne.ogeler.length;
            kopya2.ad = (oge.ad || oge.tur) + ' kopya';
            D.sahne.ogeler.push(kopya2);
            return kopya2.id;
        });
        if (!yeniler.length) { return; }
        D.secili = yeniler;
        katmanlariNormalize();
        gecmiseYaz();
        cizTam();
    }

    // ——— Sürükleme / boyutlandırma / döndürme ————————————————————

    var surukleme = null;

    // tür → katalog tanımı (çift tıklamada dosya seçici için)
    var OGE_TANIMLARI_JS = {};
    BAS.katalog.forEach(function (t) { OGE_TANIMLARI_JS[t.tur] = t; });

    function tuvalKonumu(olay) {
        var kutu = tuvalSahne.getBoundingClientRect();
        return {
            x: (olay.clientX - kutu.left) / D.zoom,
            y: (olay.clientY - kutu.top) / D.zoom
        };
    }

    /** Diğer öğelerin ve tuvalin hizalama çizgileri. */
    function yapismaNoktalari(haricId) {
        var dikey = [0, TUVAL.g / 2, TUVAL.g];
        var yatay = [0, TUVAL.y / 2, TUVAL.y];

        D.sahne.ogeler.forEach(function (o) {
            if (String(o.id) === String(haricId) || o.gorunur === false) { return; }
            dikey.push(o.x, o.x + o.g / 2, o.x + o.g);
            yatay.push(o.y, o.y + o.h / 2, o.y + o.h);
        });
        return { dikey: dikey, yatay: yatay };
    }

    function yapistir(deger, adaylar) {
        var enIyi = null;
        var enKucukFark = YAPISMA_ESIGI / D.zoom;
        adaylar.forEach(function (aday) {
            var fark = Math.abs(deger - aday);
            if (fark <= enKucukFark) {
                enKucukFark = fark;
                enIyi = aday;
            }
        });
        return enIyi;
    }

    function dugumGuncelle(oge) {
        if (!D.ornek || !D.ornek.dugumler) { return; }
        var dugum = D.ornek.dugumler[oge.id];
        if (!dugum) { return; }
        dugum.style.left = oge.x + 'px';
        dugum.style.top = oge.y + 'px';
        dugum.style.width = oge.g + 'px';
        dugum.style.height = oge.h + 'px';
        dugum.style.transform = oge.donus ? 'rotate(' + oge.donus + 'deg)' : '';
    }

    function tuvalBasla(olay) {
        if (SALT_OKUNUR || olay.button !== 0) { return; }
        // Yazı düzenlenirken imleçle seçim yapılabilsin.
        if (duzenlenen && duzenlenen.dugum.contains(olay.target)) { return; }

        var tutamakDugum = olay.target.closest('[data-tutamak]');
        var ogeDugum = olay.target.closest('[data-oge-id]');

        if (tutamakDugum) {
            var hedefOge = ogeBul(tutamakDugum.parentNode.getAttribute('data-secim-id'));
            if (!hedefOge || kilitliMi(hedefOge)) { return; }
            olay.preventDefault();
            var yon = tutamakDugum.getAttribute('data-tutamak');
            surukleme = {
                tur: yon === 'dondur' ? 'dondur' : 'boyut',
                yon: yon,
                baslangic: tuvalKonumu(olay),
                ogeler: [{ oge: hedefOge, ilk: kopyala(hedefOge) }],
                oranKilit: olay.shiftKey
            };
            tuvalAlan.setPointerCapture(olay.pointerId);
            return;
        }

        if (ogeDugum) {
            var id = ogeDugum.getAttribute('data-oge-id');
            var oge = ogeBul(id);
            if (!oge) { return; }

            var coklu = olay.shiftKey || olay.metaKey || olay.ctrlKey;
            if (D.secili.indexOf(oge.id) < 0) { sec(oge.id, coklu); }
            else if (coklu) { sec(oge.id, true); return; }

            var tasinacak = seciliOgeler().filter(function (o) { return !kilitliMi(o); });
            if (!tasinacak.length) { return; }

            olay.preventDefault();
            surukleme = {
                tur: 'tasi',
                baslangic: tuvalKonumu(olay),
                ogeler: tasinacak.map(function (o) { return { oge: o, ilk: kopyala(o) }; })
            };
            tuvalAlan.setPointerCapture(olay.pointerId);
            return;
        }

        // Boş alana basıldı → çerçeveyle çoklu seçim
        olay.preventDefault();
        secimiTemizle();
        surukleme = {
            tur: 'cerceve',
            baslangic: tuvalKonumu(olay),
            kutu: olustur('div', 'ek-secim-cercevesi')
        };
        kaplama.appendChild(surukleme.kutu);
        tuvalAlan.setPointerCapture(olay.pointerId);
    }

    function tuvalHareket(olay) {
        if (!surukleme) { return; }
        var simdi = tuvalKonumu(olay);
        var dx = simdi.x - surukleme.baslangic.x;
        var dy = simdi.y - surukleme.baslangic.y;

        if (surukleme.tur === 'tasi') {
            kilavuzTemizle();
            var ana = surukleme.ogeler[0];
            var yeniX = ana.ilk.x + dx;
            var yeniY = ana.ilk.y + dy;

            if (!olay.altKey) {
                var noktalar = yapismaNoktalari(ana.oge.id);
                var solY = yapistir(yeniX, noktalar.dikey);
                var ortaY = yapistir(yeniX + ana.ilk.g / 2, noktalar.dikey);
                var sagY = yapistir(yeniX + ana.ilk.g, noktalar.dikey);

                if (solY !== null) { yeniX = solY; kilavuzCiz('dikey', solY); }
                else if (ortaY !== null) { yeniX = ortaY - ana.ilk.g / 2; kilavuzCiz('dikey', ortaY); }
                else if (sagY !== null) { yeniX = sagY - ana.ilk.g; kilavuzCiz('dikey', sagY); }

                var ustY = yapistir(yeniY, noktalar.yatay);
                var ortaX = yapistir(yeniY + ana.ilk.h / 2, noktalar.yatay);
                var altY = yapistir(yeniY + ana.ilk.h, noktalar.yatay);

                if (ustY !== null) { yeniY = ustY; kilavuzCiz('yatay', ustY); }
                else if (ortaX !== null) { yeniY = ortaX - ana.ilk.h / 2; kilavuzCiz('yatay', ortaX); }
                else if (altY !== null) { yeniY = altY - ana.ilk.h; kilavuzCiz('yatay', altY); }
            }

            var gercekDx = yeniX - ana.ilk.x;
            var gercekDy = yeniY - ana.ilk.y;

            surukleme.ogeler.forEach(function (kayit) {
                kayit.oge.x = Math.round(kayit.ilk.x + gercekDx);
                kayit.oge.y = Math.round(kayit.ilk.y + gercekDy);
                dugumGuncelle(kayit.oge);
            });
            kaplamaCiz();
            ozellikDegerleriYenile();
            return;
        }

        if (surukleme.tur === 'boyut') {
            var kayit2 = surukleme.ogeler[0];
            var ilk = kayit2.ilk;
            var oge = kayit2.oge;
            var yon = surukleme.yon;

            var x = ilk.x, y = ilk.y, g = ilk.g, h = ilk.h;

            if (yon.indexOf('sol') >= 0 || yon === 'ku' || yon === 'kb') { x = ilk.x + dx; g = ilk.g - dx; }
            if (yon.indexOf('sag') >= 0 || yon === 'su' || yon === 'sb') { g = ilk.g + dx; }
            if (yon === 'u' || yon === 'ku' || yon === 'su') { y = ilk.y + dy; h = ilk.h - dy; }
            if (yon === 'a' || yon === 'kb' || yon === 'sb') { h = ilk.h + dy; }

            // Shift ile en-boy oranını koru
            if (surukleme.oranKilit || olay.shiftKey) {
                var oran = ilk.g / (ilk.h || 1);
                if (Math.abs(dx) > Math.abs(dy)) { h = g / oran; } else { g = h * oran; }
                if (yon === 'ku' || yon === 'kb') { x = ilk.x + (ilk.g - g); }
                if (yon === 'ku' || yon === 'su') { y = ilk.y + (ilk.h - h); }
            }

            oge.x = Math.round(x);
            oge.y = Math.round(y);
            oge.g = Math.max(8, Math.round(g));
            oge.h = Math.max(8, Math.round(h));
            dugumGuncelle(oge);
            kaplamaCiz();
            ozellikDegerleriYenile();
            return;
        }

        if (surukleme.tur === 'dondur') {
            var kayit3 = surukleme.ogeler[0];
            var merkezX = kayit3.ilk.x + kayit3.ilk.g / 2;
            var merkezY = kayit3.ilk.y + kayit3.ilk.h / 2;
            var aci = Math.atan2(simdi.y - merkezY, simdi.x - merkezX) * 180 / Math.PI + 90;
            if (!olay.altKey) { aci = Math.round(aci / 15) * 15; }   // 15°'lik kademeler
            kayit3.oge.donus = ((Math.round(aci) % 360) + 360) % 360;
            dugumGuncelle(kayit3.oge);
            kaplamaCiz();
            ozellikDegerleriYenile();
            return;
        }

        if (surukleme.tur === 'cerceve') {
            var solUst = {
                x: Math.min(surukleme.baslangic.x, simdi.x),
                y: Math.min(surukleme.baslangic.y, simdi.y)
            };
            var genislik = Math.abs(simdi.x - surukleme.baslangic.x);
            var yukseklik = Math.abs(simdi.y - surukleme.baslangic.y);

            surukleme.kutu.style.left = (solUst.x * D.zoom) + 'px';
            surukleme.kutu.style.top = (solUst.y * D.zoom) + 'px';
            surukleme.kutu.style.width = (genislik * D.zoom) + 'px';
            surukleme.kutu.style.height = (yukseklik * D.zoom) + 'px';
            surukleme.alan = { x: solUst.x, y: solUst.y, g: genislik, h: yukseklik };
        }
    }

    function tuvalBitir() {
        if (!surukleme) { return; }
        kilavuzTemizle();

        if (surukleme.tur === 'cerceve') {
            if (surukleme.kutu.parentNode) { surukleme.kutu.remove(); }
            var alan = surukleme.alan;
            if (alan && alan.g > 4 && alan.h > 4) {
                D.secili = D.sahne.ogeler.filter(function (o) {
                    return o.x < alan.x + alan.g && o.x + o.g > alan.x &&
                        o.y < alan.y + alan.h && o.y + o.h > alan.y;
                }).map(function (o) { return o.id; });
                kaplamaCiz();
                katmanlariCiz();
                ozellikleriCiz();
            }
            surukleme = null;
            return;
        }

        var degisti = surukleme.ogeler.some(function (kayit) {
            return kayit.oge.x !== kayit.ilk.x || kayit.oge.y !== kayit.ilk.y ||
                kayit.oge.g !== kayit.ilk.g || kayit.oge.h !== kayit.ilk.h ||
                kayit.oge.donus !== kayit.ilk.donus;
        });
        surukleme = null;
        if (degisti) { gecmiseYaz(); }
    }

    // ——— Tahtada yazıyı doğrudan düzenleme ————————————————————
    // Yazıyı değiştirmek için sağdaki paneli aramak gerekmesin: metne çift
    // tıkla, yaz, başka yere tıkla. Esc değişikliği iptal eder.

    var duzenlenen = null;   // { oge, dugum, eskiMetin }

    function metinDuzenlemeBaslat(oge) {
        if (SALT_OKUNUR || kilitliMi(oge) || duzenlenen) { return; }
        if (oge.tur !== 'metin') { return; }

        var sozler = (oge.icerik && oge.icerik.sozler) || [];
        if (sozler.length > 1) {
            // Sırayla dönen birden çok söz var; hangisinin düzenlendiği
            // karışmasın diye bunu sağdaki panele bırakıyoruz.
            uyar('Bu metinde birden fazla söz var. Sağdaki “Metin” kutusundan düzenleyebilirsin.');
            return;
        }

        var kap = D.ornek && D.ornek.dugumler && D.ornek.dugumler[oge.id];
        var dugum = kap && kap.querySelector('.ek-metin-ic');
        if (!dugum) { return; }

        duzenlenen = { oge: oge, dugum: dugum, eskiMetin: (sozler[0] || {}).metin || '' };

        dugum.setAttribute('contenteditable', 'plaintext-only');
        dugum.classList.add('ek-metin-duzenleniyor');
        dugum.focus();

        // İmleç metnin tamamını seçsin ki hemen üzerine yazılabilsin.
        var aralik = document.createRange();
        aralik.selectNodeContents(dugum);
        var secim = window.getSelection();
        secim.removeAllRanges();
        secim.addRange(aralik);

        dugum.addEventListener('blur', metinDuzenlemeBitir);
        dugum.addEventListener('keydown', metinDuzenlemeTus);
    }

    function metinDuzenlemeTus(olay) {
        // Tahtanın kısayolları (Delete, ok tuşları) yazarken devreye girmesin.
        olay.stopPropagation();
        if (olay.key === 'Escape') {
            olay.preventDefault();
            if (duzenlenen) { duzenlenen.dugum.textContent = duzenlenen.eskiMetin; }
            metinDuzenlemeBitir(null, true);
        }
    }

    function metinDuzenlemeBitir(olay, iptal) {
        if (!duzenlenen) { return; }
        var kayit = duzenlenen;
        duzenlenen = null;

        kayit.dugum.removeEventListener('blur', metinDuzenlemeBitir);
        kayit.dugum.removeEventListener('keydown', metinDuzenlemeTus);
        kayit.dugum.removeAttribute('contenteditable');
        kayit.dugum.classList.remove('ek-metin-duzenleniyor');

        var yeniMetin = (kayit.dugum.textContent || '').replace(/\u00a0/g, ' ');
        if (iptal || yeniMetin === kayit.eskiMetin) {
            cizTam();
            return;
        }

        kayit.oge.icerik = kayit.oge.icerik || {};
        kayit.oge.icerik.sozler = [{ metin: yeniMetin, sure: 0 }];
        gecmiseYaz();
        cizTam();
    }

    tuvalAlan.addEventListener('dblclick', function (olay) {
        var ogeDugum = olay.target.closest('[data-oge-id]');
        if (!ogeDugum) { return; }
        var oge = ogeBul(ogeDugum.getAttribute('data-oge-id'));
        if (!oge) { return; }
        olay.preventDefault();

        if (oge.tur === 'metin') {
            sec(oge.id, false);
            metinDuzenlemeBaslat(oge);
            return;
        }
        // Dosya isteyen öğede çift tıklama dosya seçiciyi açsın.
        var tanim = OGE_TANIMLARI_JS[oge.tur];
        if (tanim && tanim.medya_gerekir) {
            sec(oge.id, false);
            medyaSeciciAc(tanim.medya_turu, function (secilen) {
                ogeyeMedyaBagla(oge, secilen, false);
                gecmiseYaz();
                cizTam();
            });
        }
    });

    tuvalAlan.addEventListener('pointerdown', tuvalBasla);
    tuvalAlan.addEventListener('pointermove', tuvalHareket);
    tuvalAlan.addEventListener('pointerup', tuvalBitir);
    tuvalAlan.addEventListener('pointercancel', tuvalBitir);

    // ——— Hizalama ve katman sırası ————————————————————————————

    function hizala(tur) {
        var ogeler = seciliOgeler().filter(function (o) { return !kilitliMi(o); });
        if (!ogeler.length) { return; }

        // Tek öğe seçiliyse tuvale, birden çok seçiliyse birbirine göre hizala.
        var referans;
        if (ogeler.length === 1) {
            referans = { x: 0, y: 0, g: TUVAL.g, h: TUVAL.y };
        } else {
            var solEn = Math.min.apply(null, ogeler.map(function (o) { return o.x; }));
            var ustEn = Math.min.apply(null, ogeler.map(function (o) { return o.y; }));
            var sagEn = Math.max.apply(null, ogeler.map(function (o) { return o.x + o.g; }));
            var altEn = Math.max.apply(null, ogeler.map(function (o) { return o.y + o.h; }));
            referans = { x: solEn, y: ustEn, g: sagEn - solEn, h: altEn - ustEn };
        }

        ogeler.forEach(function (o) {
            if (tur === 'sol') { o.x = referans.x; }
            if (tur === 'yatay-orta') { o.x = Math.round(referans.x + (referans.g - o.g) / 2); }
            if (tur === 'sag') { o.x = referans.x + referans.g - o.g; }
            if (tur === 'ust') { o.y = referans.y; }
            if (tur === 'dikey-orta') { o.y = Math.round(referans.y + (referans.h - o.h) / 2); }
            if (tur === 'alt') { o.y = referans.y + referans.h - o.h; }
        });
        gecmiseYaz();
        cizTam();
    }

    function katmanDegistir(islem) {
        var ogeler = seciliOgeler();
        if (!ogeler.length) { return; }
        katmanlariNormalize();
        var enUst = D.sahne.ogeler.length - 1;

        ogeler.forEach(function (o) {
            if (islem === 'one') { o.katman = enUst + 1; }
            if (islem === 'arkaya') { o.katman = -1; }
            if (islem === 'bir-one') { o.katman += 1.5; }
            if (islem === 'bir-arkaya') { o.katman -= 1.5; }
        });
        katmanlariNormalize();
        gecmiseYaz();
        cizTam();
    }

    // ——— Klavye ————————————————————————————————————————————————

    function girdideMi(hedef) {
        var etiket = (hedef && hedef.tagName) || '';
        return etiket === 'INPUT' || etiket === 'TEXTAREA' || etiket === 'SELECT' ||
            (hedef && hedef.isContentEditable);
    }

    document.addEventListener('keydown', function (olay) {
        if (SALT_OKUNUR || girdideMi(olay.target) || duzenlenen) { return; }
        var komut = olay.metaKey || olay.ctrlKey;

        if (komut && olay.key.toLowerCase() === 'z') {
            olay.preventDefault();
            if (olay.shiftKey) { ileriAl(); } else { geriAl(); }
            return;
        }
        if (komut && olay.key.toLowerCase() === 'y') { olay.preventDefault(); ileriAl(); return; }
        if (komut && olay.key.toLowerCase() === 's') { olay.preventDefault(); kaydet(); return; }
        if (komut && olay.key.toLowerCase() === 'd') { olay.preventDefault(); seciliCogalt(); return; }
        if (komut && olay.key.toLowerCase() === 'a') {
            olay.preventDefault();
            D.secili = D.sahne.ogeler.map(function (o) { return o.id; });
            kaplamaCiz(); katmanlariCiz(); ozellikleriCiz();
            return;
        }
        if (komut && olay.key.toLowerCase() === 'c') { D.pano = kopyala(seciliOgeler()); return; }
        if (komut && olay.key.toLowerCase() === 'v') {
            if (!D.pano || !D.pano.length) { return; }
            olay.preventDefault();
            var yeniler = D.pano.map(function (ham) {
                var kopya2 = kopyala(ham);
                kopya2.id = yeniId();
                kopya2.x += 32;
                kopya2.y += 32;
                kopya2.katman = D.sahne.ogeler.length;
                D.sahne.ogeler.push(kopya2);
                return kopya2.id;
            });
            D.secili = yeniler;
            katmanlariNormalize();
            gecmiseYaz();
            cizTam();
            return;
        }

        if (olay.key === 'Delete' || olay.key === 'Backspace') {
            olay.preventDefault();
            seciliSil();
            return;
        }
        if (olay.key === 'Escape') { secimiTemizle(); return; }

        var yonler = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] };
        if (yonler[olay.key]) {
            var ogeler = seciliOgeler().filter(function (o) { return !kilitliMi(o); });
            if (!ogeler.length) { return; }
            olay.preventDefault();
            var adim = olay.shiftKey ? 10 : 1;
            ogeler.forEach(function (o) {
                o.x += yonler[olay.key][0] * adim;
                o.y += yonler[olay.key][1] * adim;
                dugumGuncelle(o);
            });
            kaplamaCiz();
            ozellikDegerleriYenile();
            klavyeGecmisiErtele();
        }
    });

    // Ok tuşuyla art arda kaydırma tek bir geri alma adımı olsun.
    var klavyeZaman = null;
    function klavyeGecmisiErtele() {
        if (klavyeZaman) { clearTimeout(klavyeZaman); }
        klavyeZaman = setTimeout(function () { gecmiseYaz(); }, 500);
    }

    // ——— Özellik paneli ————————————————————————————————————————
    // Alanlar küçük bir tanım listesinden üretilir; yeni öğe türü
    // eklemek için buraya bir dizi eklemek yeterlidir.

    function alanKutusu(etiket, girdi, yardim) {
        var kutu = olustur('div', 'ek-ozellik-alan');
        var lbl = olustur('label', null, etiket);
        kutu.appendChild(lbl);
        kutu.appendChild(girdi);
        if (yardim) { kutu.appendChild(olustur('small', 'ek-ozellik-yardim', yardim)); }
        return kutu;
    }

    function sayiGirdi(deger, degisti, ayar) {
        ayar = ayar || {};
        var girdi = olustur('input', 'ek-ozellik-girdi');
        girdi.type = 'number';
        girdi.value = Math.round((deger || 0) * 100) / 100;
        if (ayar.min != null) { girdi.min = ayar.min; }
        if (ayar.max != null) { girdi.max = ayar.max; }
        if (ayar.step != null) { girdi.step = ayar.step; }
        girdi.addEventListener('change', function () { degisti(sayi(girdi.value, 0)); });
        return girdi;
    }

    function metinGirdi(deger, degisti) {
        var girdi = olustur('input', 'ek-ozellik-girdi');
        girdi.type = 'text';
        girdi.value = deger || '';
        girdi.addEventListener('change', function () { degisti(girdi.value); });
        return girdi;
    }

    function alanGirdi(deger, degisti) {
        var girdi = olustur('textarea', 'ek-ozellik-girdi');
        girdi.rows = 4;
        girdi.value = deger || '';
        girdi.addEventListener('change', function () { degisti(girdi.value); });
        return girdi;
    }

    function renkGirdi(deger, degisti) {
        var sarmal = olustur('div', 'ek-renk-sarmal');
        var girdi = olustur('input');
        girdi.type = 'color';
        girdi.value = /^#[0-9a-f]{6}$/i.test(deger || '') ? deger : '#ffffff';
        var metin = olustur('input', 'ek-ozellik-girdi');
        metin.type = 'text';
        metin.value = deger || '';
        girdi.addEventListener('input', function () { metin.value = girdi.value; degisti(girdi.value); });
        metin.addEventListener('change', function () { degisti(metin.value); });
        sarmal.appendChild(girdi);
        sarmal.appendChild(metin);
        return sarmal;
    }

    function secimGirdi(deger, secenekler, degisti) {
        var girdi = olustur('select', 'ek-ozellik-girdi');
        secenekler.forEach(function (secenek) {
            var opt = olustur('option', null, secenek[1]);
            opt.value = secenek[0];
            if (String(secenek[0]) === String(deger)) { opt.selected = true; }
            girdi.appendChild(opt);
        });
        girdi.addEventListener('change', function () { degisti(girdi.value); });
        return girdi;
    }

    function onayGirdi(deger, etiket, degisti) {
        var sarmal = olustur('label', 'ek-ozellik-onay');
        var girdi = olustur('input');
        girdi.type = 'checkbox';
        girdi.checked = deger !== false && deger !== undefined ? !!deger : false;
        girdi.addEventListener('change', function () { degisti(girdi.checked); });
        sarmal.appendChild(girdi);
        sarmal.appendChild(olustur('span', null, etiket));
        return sarmal;
    }

    function bolum(baslik, acik) {
        var kutu = olustur('section', 'ek-ozellik-bolum');
        var dugme = olustur('button', 'ek-ozellik-bolum-basi');
        dugme.type = 'button';
        dugme.appendChild(olustur('span', null, baslik));
        dugme.appendChild(olustur('span', 'ek-ozellik-ok', acik ? '▾' : '▸'));
        var govde = olustur('div', 'ek-ozellik-govde');
        if (!acik) { govde.hidden = true; }
        dugme.addEventListener('click', function () {
            govde.hidden = !govde.hidden;
            dugme.lastChild.textContent = govde.hidden ? '▸' : '▾';
        });
        kutu.appendChild(dugme);
        kutu.appendChild(govde);
        kutu.govde = govde;
        return kutu;
    }

    function guncelle(oge, yol, deger, yenidenCiz) {
        var parcalar = yol.split('.');
        var hedef = oge;
        for (var i = 0; i < parcalar.length - 1; i += 1) {
            hedef[parcalar[i]] = hedef[parcalar[i]] || {};
            hedef = hedef[parcalar[i]];
        }
        hedef[parcalar[parcalar.length - 1]] = deger;
        gecmiseYaz();
        if (yenidenCiz === false) { dugumGuncelle(oge); kaplamaCiz(); } else { cizTam(); }
    }

    function ozellikDegerleriYenile() {
        // Sürükleme sırasında yalnız konum/ölçü kutularını tazele.
        var oge = seciliOgeler()[0];
        if (!oge) { return; }
        [['x', oge.x], ['y', oge.y], ['g', oge.g], ['h', oge.h], ['donus', oge.donus]]
            .forEach(function (cift) {
                var girdi = ozellikPanel.querySelector('[data-canli="' + cift[0] + '"]');
                if (girdi && document.activeElement !== girdi) {
                    girdi.value = Math.round(cift[1]);
                }
            });
    }

    function ozellikleriCiz() {
        ozellikPanel.innerHTML = '';

        var ogeler = seciliOgeler();
        if (!ogeler.length) {
            ozellikPanel.appendChild(sahneOzellikleri());
            return;
        }
        if (ogeler.length > 1) {
            var coklu = olustur('div', 'ek-ozellik-coklu');
            coklu.appendChild(olustur('h3', null, ogeler.length + ' öğe seçili'));
            coklu.appendChild(olustur('p', 'ek-ozellik-yardim',
                'Birlikte taşıyabilir, hizalayabilir ve silebilirsiniz. Ayrıntılı ayar için tek öğe seçin.'));
            ozellikPanel.appendChild(coklu);
            return;
        }

        var oge = ogeler[0];
        var baslik = olustur('div', 'ek-ozellik-basi');
        baslik.appendChild(olustur('h3', null, oge.ad || oge.tur));
        baslik.appendChild(olustur('span', 'ek-ozellik-tur', turAdi(oge.tur)));
        ozellikPanel.appendChild(baslik);

        ozellikPanel.appendChild(yerlesimBolumu(oge));

        var turBolumu = turOzellikleri(oge);
        if (turBolumu) { ozellikPanel.appendChild(turBolumu); }

        ozellikPanel.appendChild(gorunumBolumu(oge));
        ozellikPanel.appendChild(zamanlamaBolumu(oge));
    }

    function turAdi(tur) {
        for (var i = 0; i < BAS.katalog.length; i += 1) {
            if (BAS.katalog[i].tur === tur) { return BAS.katalog[i].ad; }
        }
        return tur;
    }

    function yerlesimBolumu(oge) {
        var b = bolum('Konum ve boyut', true);
        var izgara = olustur('div', 'ek-ozellik-izgara');

        [['X', 'x'], ['Y', 'y'], ['Genişlik', 'g'], ['Yükseklik', 'h']].forEach(function (cift) {
            var girdi = sayiGirdi(oge[cift[1]], function (deger) {
                guncelle(oge, cift[1], Math.round(deger), false);
            });
            girdi.setAttribute('data-canli', cift[1]);
            izgara.appendChild(alanKutusu(cift[0], girdi));
        });
        b.govde.appendChild(izgara);

        var donus = sayiGirdi(oge.donus, function (deger) {
            guncelle(oge, 'donus', ((deger % 360) + 360) % 360, false);
        }, { min: 0, max: 359, step: 1 });
        donus.setAttribute('data-canli', 'donus');
        b.govde.appendChild(alanKutusu('Döndürme (derece)', donus));

        var oranDugme = olustur('button', 'ek-ozellik-dugme', 'Kaynağın oranına döndür');
        oranDugme.type = 'button';
        oranDugme.disabled = !(oge.kaynak && oge.kaynak.g && oge.kaynak.y);
        oranDugme.addEventListener('click', function () {
            var oran = oge.kaynak.g / oge.kaynak.y;
            oge.h = Math.round(oge.g / oran);
            gecmiseYaz();
            cizTam();
        });
        b.govde.appendChild(oranDugme);

        var hizaKutu = olustur('div', 'ek-hiza-izgara');
        [
            ['sol', 'Sola yasla'], ['yatay-orta', 'Yatay ortala'], ['sag', 'Sağa yasla'],
            ['ust', 'Üste yasla'], ['dikey-orta', 'Dikey ortala'], ['alt', 'Alta yasla']
        ].forEach(function (cift) {
            var dugme = olustur('button', 'ek-hiza-dugme', cift[1]);
            dugme.type = 'button';
            dugme.addEventListener('click', function () { hizala(cift[0]); });
            hizaKutu.appendChild(dugme);
        });
        b.govde.appendChild(alanKutusu('Hizalama', hizaKutu,
            'Tek öğe seçiliyken ekrana, birden çok öğe seçiliyken birbirine göre hizalar.'));

        return b;
    }

    function gorunumBolumu(oge) {
        var b = bolum('Görünüm', false);
        var s = oge.stil || {};

        b.govde.appendChild(alanKutusu('Opaklık',
            sayiGirdi(oge.opaklik == null ? 1 : oge.opaklik, function (deger) {
                guncelle(oge, 'opaklik', Math.min(1, Math.max(0, deger)));
            }, { min: 0, max: 1, step: 0.05 })));

        b.govde.appendChild(alanKutusu('Arka plan',
            renkGirdi(s.arka_plan, function (deger) { guncelle(oge, 'stil.arka_plan', deger); })));

        b.govde.appendChild(alanKutusu('Köşe yuvarlaklığı',
            sayiGirdi(s.kose, function (deger) { guncelle(oge, 'stil.kose', deger); }, { min: 0, max: 400 })));

        b.govde.appendChild(alanKutusu('İç boşluk',
            sayiGirdi(s.ic_bosluk, function (deger) { guncelle(oge, 'stil.ic_bosluk', deger); }, { min: 0, max: 200 })));

        var kenarIzgara = olustur('div', 'ek-ozellik-izgara');
        kenarIzgara.appendChild(alanKutusu('Kenarlık',
            sayiGirdi(s.kenarlik_kalinlik, function (deger) { guncelle(oge, 'stil.kenarlik_kalinlik', deger); }, { min: 0, max: 40 })));
        kenarIzgara.appendChild(alanKutusu('Kenar rengi',
            renkGirdi(s.kenarlik_renk, function (deger) { guncelle(oge, 'stil.kenarlik_renk', deger); })));
        b.govde.appendChild(kenarIzgara);

        b.govde.appendChild(alanKutusu('Gölge', secimGirdi(s.golge || 'yok', [
            ['yok', 'Gölge yok'], ['yumusak', 'Yumuşak'], ['guclu', 'Güçlü']
        ], function (deger) { guncelle(oge, 'stil.golge', deger); })));

        b.govde.appendChild(onayGirdi(oge.kilitli, 'Kilitle (taşınmasın)', function (deger) {
            guncelle(oge, 'kilitli', deger);
        }));
        b.govde.appendChild(onayGirdi(oge.gorunur !== false, 'Ekranda göster', function (deger) {
            guncelle(oge, 'gorunur', deger);
        }));

        var katmanKutu = olustur('div', 'ek-hiza-izgara');
        [['one', 'Öne getir'], ['bir-one', 'Bir öne'], ['arkaya', 'Arkaya gönder'], ['bir-arkaya', 'Bir arkaya']]
            .forEach(function (cift) {
                var dugme = olustur('button', 'ek-hiza-dugme', cift[1]);
                dugme.type = 'button';
                dugme.addEventListener('click', function () { katmanDegistir(cift[0]); });
                katmanKutu.appendChild(dugme);
            });
        b.govde.appendChild(alanKutusu('Katman sırası', katmanKutu));

        return b;
    }

    function zamanlamaBolumu(oge) {
        var b = bolum('Zamanlama ve animasyon', false);
        var z = oge.zamanlama || {};
        var a = oge.animasyon || {};

        var izgara = olustur('div', 'ek-ozellik-izgara');
        izgara.appendChild(alanKutusu('Görünme (sn)',
            sayiGirdi(z.baslangic_sn, function (deger) { guncelle(oge, 'zamanlama.baslangic_sn', deger); }, { min: 0 })));
        izgara.appendChild(alanKutusu('Gizlenme (sn)',
            sayiGirdi(z.bitis_sn, function (deger) { guncelle(oge, 'zamanlama.bitis_sn', deger); }, { min: 0 })));
        b.govde.appendChild(izgara);
        b.govde.appendChild(olustur('small', 'ek-ozellik-yardim',
            'Sahne başladıktan kaç saniye sonra görünsün / gizlensin. 0 = sahne boyunca.'));

        b.govde.appendChild(alanKutusu('Giriş animasyonu', secimGirdi(a.giris || 'yok', [
            ['yok', 'Yok'], ['soldur', 'Yumuşak beliriş'], ['yukari', 'Aşağıdan yukarı'], ['yakinlastir', 'Yakınlaştır']
        ], function (deger) { guncelle(oge, 'animasyon.giris', deger); })));

        return b;
    }

    function sahneOzellikleri() {
        var kutu = olustur('div');
        var baslik = olustur('div', 'ek-ozellik-basi');
        baslik.appendChild(olustur('h3', null, 'Sahne ayarları'));
        kutu.appendChild(baslik);

        var b = bolum('Sahne', true);
        b.govde.appendChild(alanKutusu('Sahne adı', metinGirdi(D.sahne.ad, function (deger) {
            D.sahne.ad = deger;
            gecmiseYaz();
            var sekme = document.querySelector('[data-sahne-sekme="' + D.sahne.id + '"]');
            if (sekme) { sekme.textContent = deger; }
        })));

        b.govde.appendChild(alanKutusu('Arka plan rengi',
            renkGirdi((D.sahne.arka_plan || {}).renk, function (deger) {
                D.sahne.arka_plan = D.sahne.arka_plan || {};
                D.sahne.arka_plan.renk = deger;
                gecmiseYaz();
                cizTam();
            })));

        b.govde.appendChild(alanKutusu('Gösterim süresi', secimGirdi(D.sahne.sure_tipi, [
            ['saniye', 'Belirli süre'],
            ['video_bitene', 'Video bitene kadar'],
            ['pdf_bitene', 'PDF sayfaları bitene kadar'],
            ['suresiz', 'Süresiz (tek sahne)']
        ], function (deger) { D.sahne.sure_tipi = deger; gecmiseYaz(); ozellikleriCiz(); })));

        if (D.sahne.sure_tipi === 'saniye') {
            b.govde.appendChild(alanKutusu('Süre (saniye)',
                sayiGirdi(D.sahne.sure_sn, function (deger) {
                    D.sahne.sure_sn = Math.max(1, Math.round(deger));
                    gecmiseYaz();
                }, { min: 1, max: 86400 })));
        }

        b.govde.appendChild(alanKutusu('Geçiş efekti', secimGirdi(D.sahne.gecis, [
            ['soldur', 'Yumuşak geçiş'], ['yok', 'Geçiş yok'],
            ['kaydir', 'Kaydır'], ['yakinlastir', 'Yakınlaştır']
        ], function (deger) { D.sahne.gecis = deger; gecmiseYaz(); })));

        kutu.appendChild(b);

        var ipucu = olustur('p', 'ek-ozellik-yardim',
            'Bir öğe seçtiğinizde burada o öğenin ayarları görünür.');
        kutu.appendChild(ipucu);
        return kutu;
    }

    // ——— Türe özgü ayarlar ————————————————————————————————————

    function turOzellikleri(oge) {
        var s = oge.stil || {};
        var i = oge.icerik || {};

        if (oge.tur === 'metin') {
            var b = bolum('Metin ve tipografi', true);
            b.govde.appendChild(olustur('p', 'ek-ozellik-vurgu',
                'Yazıyı değiştirmek için tahtadaki metne çift tıklayabilirsin.'));

            var sozler = (i.sozler || []).map(function (x) { return x.metin; }).join('\n---\n');
            b.govde.appendChild(alanKutusu('Metin',
                alanGirdi(sozler, function (deger) {
                    var parcalar = deger.split(/\n-{3,}\n/).map(function (p) { return p.trim(); });
                    guncelle(oge, 'icerik.sozler', parcalar.map(function (p) { return { metin: p, sure: 0 }; }));
                }),
                'Birden fazla söz göstermek için aralarına tek satırda --- yazın.'));

            if ((i.sozler || []).length > 1) {
                b.govde.appendChild(alanKutusu('Her sözün süresi (sn)',
                    sayiGirdi(i.ortak_sure || 8, function (deger) {
                        guncelle(oge, 'icerik.ortak_sure', Math.max(1, deger));
                    }, { min: 1 })));
            }

            var yaziIzgara = olustur('div', 'ek-ozellik-izgara');
            yaziIzgara.appendChild(alanKutusu('Punto',
                sayiGirdi(s.punto, function (d) { guncelle(oge, 'stil.punto', d); }, { min: 8, max: 400 })));
            yaziIzgara.appendChild(alanKutusu('Kalınlık', secimGirdi(s.kalinlik || 600, [
                [300, 'İnce'], [400, 'Normal'], [500, 'Orta'], [600, 'Kalın'], [700, 'Çok kalın']
            ], function (d) { guncelle(oge, 'stil.kalinlik', parseInt(d, 10)); })));
            b.govde.appendChild(yaziIzgara);

            b.govde.appendChild(alanKutusu('Yazı rengi',
                renkGirdi(s.renk, function (d) { guncelle(oge, 'stil.renk', d); })));

            var hizaIzgara = olustur('div', 'ek-ozellik-izgara');
            hizaIzgara.appendChild(alanKutusu('Yatay hizalama', secimGirdi(s.hizalama || 'center', [
                ['left', 'Sola'], ['center', 'Ortaya'], ['right', 'Sağa']
            ], function (d) { guncelle(oge, 'stil.hizalama', d); })));
            hizaIzgara.appendChild(alanKutusu('Dikey hizalama', secimGirdi(s.dikey_hizalama || 'center', [
                ['flex-start', 'Üste'], ['center', 'Ortaya'], ['flex-end', 'Alta']
            ], function (d) { guncelle(oge, 'stil.dikey_hizalama', d); })));
            b.govde.appendChild(hizaIzgara);

            var araIzgara = olustur('div', 'ek-ozellik-izgara');
            araIzgara.appendChild(alanKutusu('Satır aralığı',
                sayiGirdi(s.satir_araligi || 1.25, function (d) { guncelle(oge, 'stil.satir_araligi', d); }, { step: 0.05 })));
            araIzgara.appendChild(alanKutusu('Harf aralığı',
                sayiGirdi(s.harf_araligi, function (d) { guncelle(oge, 'stil.harf_araligi', d); }, { step: 0.5 })));
            b.govde.appendChild(araIzgara);

            b.govde.appendChild(alanKutusu('Metin taşarsa', secimGirdi(s.tasma || 'kucult', [
                ['kucult', 'Yazıyı otomatik küçült'], ['kirp', 'Taşan kısmı gizle']
            ], function (d) { guncelle(oge, 'stil.tasma', d); })));

            return b;
        }

        if (oge.tur === 'pdf') {
            var bp = bolum('PDF ayarları', true);
            bp.govde.appendChild(medyaSecDugmesi(oge, 'pdf'));

            if (oge.kaynak && oge.kaynak.sayfalar) {
                bp.govde.appendChild(olustur('p', 'ek-ozellik-yardim',
                    oge.kaynak.sayfalar.length + ' sayfa hazır.'));
            }

            bp.govde.appendChild(alanKutusu('Alana yerleşim', secimGirdi(i.sigdir || 'icine', [
                ['icine', 'Alana sığdır (kırpmaz)'], ['doldur', 'Alanı doldur (kırpar)']
            ], function (d) { guncelle(oge, 'icerik.sigdir', d); })));

            bp.govde.appendChild(alanKutusu('Her sayfanın süresi (sn)',
                sayiGirdi(i.ortak_sure || 10, function (d) {
                    guncelle(oge, 'icerik.ortak_sure', Math.max(1, d));
                }, { min: 1 })));

            bp.govde.appendChild(onayGirdi(i.dongu !== false, 'Sayfalar bitince başa dön', function (d) {
                guncelle(oge, 'icerik.dongu', d);
            }));

            if (oge.kaynak && (oge.kaynak.sayfalar || []).length > 1) {
                bp.govde.appendChild(sayfaYoneticisi(oge));
            }
            return bp;
        }

        if (oge.tur === 'gorsel') {
            var bg = bolum('Görsel ayarları', true);
            bg.govde.appendChild(medyaSecDugmesi(oge, 'gorsel'));
            bg.govde.appendChild(coklinMedyaYoneticisi(oge, 'gorsel'));

            bg.govde.appendChild(alanKutusu('Alana yerleşim', secimGirdi(i.sigdir || 'icine', [
                ['icine', 'Alana sığdır (kırpmaz)'], ['doldur', 'Alanı doldur (kırpar)']
            ], function (d) { guncelle(oge, 'icerik.sigdir', d); })));

            bg.govde.appendChild(alanKutusu('Odak noktası', secimGirdi(i.odak || 'center', [
                ['center', 'Orta'], ['top', 'Üst'], ['bottom', 'Alt'], ['left', 'Sol'], ['right', 'Sağ']
            ], function (d) { guncelle(oge, 'icerik.odak', d); }),
                'Görsel kırpılırken hangi bölümün korunacağını belirler.'));

            if ((oge.kaynaklar || []).length > 1) {
                bg.govde.appendChild(alanKutusu('Slayt süresi (sn)',
                    sayiGirdi(i.ortak_sure || 8, function (d) {
                        guncelle(oge, 'icerik.ortak_sure', Math.max(1, d));
                    }, { min: 1 })));
            }
            return bg;
        }

        if (oge.tur === 'video') {
            var bv = bolum('Video ayarları', true);
            bv.govde.appendChild(medyaSecDugmesi(oge, 'video'));

            bv.govde.appendChild(alanKutusu('Alana yerleşim', secimGirdi(i.sigdir || 'icine', [
                ['icine', 'Alana sığdır'], ['doldur', 'Alanı doldur (kırpar)']
            ], function (d) { guncelle(oge, 'icerik.sigdir', d); })));

            bv.govde.appendChild(onayGirdi(i.sessiz !== false, 'Sessiz oynat', function (d) {
                guncelle(oge, 'icerik.sessiz', d);
            }));
            bv.govde.appendChild(olustur('small', 'ek-ozellik-yardim',
                'Tarayıcılar sesli videoyu kendiliğinden başlatmaz. Sesli yayın için bu kutuyu kapatın, ancak bazı ekranlarda video duraklayabilir.'));

            bv.govde.appendChild(onayGirdi(i.dongu !== false, 'Bitince baştan oynat', function (d) {
                guncelle(oge, 'icerik.dongu', d);
            }));

            var kesme = olustur('div', 'ek-ozellik-izgara');
            kesme.appendChild(alanKutusu('Başlangıç (sn)',
                sayiGirdi(i.baslangic_sn, function (d) { guncelle(oge, 'icerik.baslangic_sn', Math.max(0, d)); }, { min: 0 })));
            kesme.appendChild(alanKutusu('Bitiş (sn)',
                sayiGirdi(i.bitis_sn, function (d) { guncelle(oge, 'icerik.bitis_sn', Math.max(0, d)); }, { min: 0 })));
            bv.govde.appendChild(kesme);
            bv.govde.appendChild(olustur('small', 'ek-ozellik-yardim', 'Bitiş 0 ise video sonuna kadar oynar.'));

            return bv;
        }

        if (oge.tur === 'geri_sayim') {
            var bs = bolum('Geri sayım', true);
            bs.govde.appendChild(alanKutusu('Başlık', metinGirdi(i.baslik, function (d) {
                guncelle(oge, 'icerik.baslik', d);
            })));

            var hedefGirdi = olustur('input', 'ek-ozellik-girdi');
            hedefGirdi.type = 'datetime-local';
            hedefGirdi.value = (i.hedef || '').slice(0, 16);
            hedefGirdi.addEventListener('change', function () {
                guncelle(oge, 'icerik.hedef', hedefGirdi.value ? new Date(hedefGirdi.value).toISOString() : '');
            });
            bs.govde.appendChild(alanKutusu('Hedef tarih ve saat', hedefGirdi));

            var birimler = olustur('div');
            [['gun', 'Gün'], ['saat', 'Saat'], ['dakika', 'Dakika'], ['saniye', 'Saniye']]
                .forEach(function (cift) {
                    var varsayilan = cift[0] === 'saniye' ? false : true;
                    var deger = i[cift[0]] === undefined ? varsayilan : i[cift[0]];
                    birimler.appendChild(onayGirdi(deger, cift[1], function (d) {
                        guncelle(oge, 'icerik.' + cift[0], d);
                    }));
                });
            bs.govde.appendChild(alanKutusu('Gösterilecek birimler', birimler));

            bs.govde.appendChild(alanKutusu('Süre dolunca yazılacak',
                metinGirdi(i.bitince_metin, function (d) { guncelle(oge, 'icerik.bitince_metin', d); })));
            bs.govde.appendChild(onayGirdi(i.bitince_gizle, 'Süre dolunca öğeyi gizle', function (d) {
                guncelle(oge, 'icerik.bitince_gizle', d);
            }));

            var gsIzgara = olustur('div', 'ek-ozellik-izgara');
            gsIzgara.appendChild(alanKutusu('Punto',
                sayiGirdi(s.punto, function (d) { guncelle(oge, 'stil.punto', d); }, { min: 12, max: 400 })));
            gsIzgara.appendChild(alanKutusu('Renk',
                renkGirdi(s.renk, function (d) { guncelle(oge, 'stil.renk', d); })));
            bs.govde.appendChild(gsIzgara);

            bs.govde.appendChild(olustur('small', 'ek-ozellik-yardim',
                'Geri sayım sunucu saatiyle eşitlenir; televizyonun saati yanlış olsa bile doğru sayar.'));
            return bs;
        }

        if (oge.tur === 'saat') {
            var bsa = bolum('Saat ve tarih', true);
            bsa.govde.appendChild(onayGirdi(i.saniye, 'Saniyeyi göster', function (d) {
                guncelle(oge, 'icerik.saniye', d);
            }));
            bsa.govde.appendChild(onayGirdi(i.tarih !== false, 'Tarihi göster', function (d) {
                guncelle(oge, 'icerik.tarih', d);
            }));
            bsa.govde.appendChild(onayGirdi(i.gun_adi !== false, 'Gün adını göster', function (d) {
                guncelle(oge, 'icerik.gun_adi', d);
            }));
            var saIzgara = olustur('div', 'ek-ozellik-izgara');
            saIzgara.appendChild(alanKutusu('Punto',
                sayiGirdi(s.punto, function (d) { guncelle(oge, 'stil.punto', d); }, { min: 12, max: 400 })));
            saIzgara.appendChild(alanKutusu('Renk',
                renkGirdi(s.renk, function (d) { guncelle(oge, 'stil.renk', d); })));
            bsa.govde.appendChild(saIzgara);
            return bsa;
        }

        if (oge.tur === 'kayan_bant') {
            var bb = bolum('Kayan duyuru', true);
            bb.govde.appendChild(alanKutusu('Duyurular',
                alanGirdi((i.duyurular || []).join('\n'), function (d) {
                    guncelle(oge, 'icerik.duyurular',
                        d.split('\n').map(function (x) { return x.trim(); }).filter(Boolean));
                }),
                'Her satır ayrı bir duyurudur; arka arkaya akar.'));

            bb.govde.appendChild(alanKutusu('Akış yönü', secimGirdi(i.yon || 'sola', [
                ['sola', 'Sağdan sola'], ['saga', 'Soldan sağa']
            ], function (d) { guncelle(oge, 'icerik.yon', d); })));

            bb.govde.appendChild(alanKutusu('Akış hızı',
                sayiGirdi(i.hiz || 60, function (d) { guncelle(oge, 'icerik.hiz', Math.max(10, d)); }, { min: 10, max: 400 }),
                'Saniyede kaç piksel ilerlesin. Büyük değer = hızlı akış.'));

            bb.govde.appendChild(onayGirdi(i.acil, 'Acil duyuru görünümü (kırmızı)', function (d) {
                guncelle(oge, 'icerik.acil', d);
            }));

            var bbIzgara = olustur('div', 'ek-ozellik-izgara');
            bbIzgara.appendChild(alanKutusu('Punto',
                sayiGirdi(s.punto, function (d) { guncelle(oge, 'stil.punto', d); }, { min: 10, max: 200 })));
            bbIzgara.appendChild(alanKutusu('Ayırıcı',
                metinGirdi(s.ayirici || '•', function (d) { guncelle(oge, 'stil.ayirici', d); })));
            bb.govde.appendChild(bbIzgara);
            return bb;
        }

        if (oge.tur === 'qr') {
            var bq = bolum('QR kod', true);
            bq.govde.appendChild(alanKutusu('Adres veya metin',
                metinGirdi(i.adres, function (d) { guncelle(oge, 'icerik.adres', d); })));
            return bq;
        }

        if (oge.tur === 'sekil') {
            var bsk = bolum('Şekil', true);
            bsk.govde.appendChild(alanKutusu('Biçim', secimGirdi(i.sekil || 'dikdortgen', [
                ['dikdortgen', 'Dikdörtgen'], ['daire', 'Daire / elips']
            ], function (d) { guncelle(oge, 'icerik.sekil', d); })));
            return bsk;
        }

        if (oge.tur === 'cizgi') {
            var bc = bolum('Çizgi', true);
            bc.govde.appendChild(alanKutusu('Yön', secimGirdi(i.yon || 'yatay', [
                ['yatay', 'Yatay'], ['dikey', 'Dikey']
            ], function (d) { guncelle(oge, 'icerik.yon', d); })));
            bc.govde.appendChild(alanKutusu('Kalınlık',
                sayiGirdi(s.kalinlik_px || 3, function (d) { guncelle(oge, 'stil.kalinlik_px', d); }, { min: 1, max: 60 })));
            bc.govde.appendChild(alanKutusu('Biçim', secimGirdi(s.stil_tipi || 'duz', [
                ['duz', 'Düz'], ['kesikli', 'Kesikli'], ['noktali', 'Noktalı']
            ], function (d) { guncelle(oge, 'stil.stil_tipi', d); })));
            bc.govde.appendChild(alanKutusu('Renk',
                renkGirdi(s.renk, function (d) { guncelle(oge, 'stil.renk', d); })));
            return bc;
        }

        var listeTurleri = ['bilgi_kutusu', 'gunluk_program', 'yemek_listesi', 'sinav_duyurusu', 'namaz_vakitleri'];
        if (listeTurleri.indexOf(oge.tur) >= 0) {
            var bl = bolum('İçerik', true);
            bl.govde.appendChild(alanKutusu('Başlık',
                metinGirdi(i.baslik, function (d) { guncelle(oge, 'icerik.baslik', d); })));

            var satirlar = (i.satirlar || []).map(function (satir) {
                if (satir && typeof satir === 'object') {
                    return (satir.sol || satir.saat || '') + ' | ' + (satir.sag || satir.metin || '');
                }
                return satir;
            }).join('\n');

            bl.govde.appendChild(alanKutusu('Satırlar', alanGirdi(satirlar, function (d) {
                var yeni = d.split('\n').map(function (x) { return x.trim(); }).filter(Boolean)
                    .map(function (x) {
                        var parcalar = x.split('|');
                        if (parcalar.length > 1) {
                            return { sol: parcalar[0].trim(), sag: parcalar.slice(1).join('|').trim() };
                        }
                        return x;
                    });
                guncelle(oge, 'icerik.satirlar', yeni);
            }), 'Her satır bir kayıt. İki sütun için araya | koyun (örn. 08:30 | Sabah etüdü).'));

            var blIzgara = olustur('div', 'ek-ozellik-izgara');
            blIzgara.appendChild(alanKutusu('Punto',
                sayiGirdi(s.punto || 30, function (d) { guncelle(oge, 'stil.punto', d); }, { min: 10, max: 160 })));
            blIzgara.appendChild(alanKutusu('Renk',
                renkGirdi(s.renk, function (d) { guncelle(oge, 'stil.renk', d); })));
            bl.govde.appendChild(blIzgara);
            return bl;
        }

        return null;
    }

    function medyaSecDugmesi(oge, tur) {
        var dugme = olustur('button', 'ek-ozellik-dugme ek-ozellik-dugme-ana',
            oge.kaynak ? 'Dosyayı değiştir' : 'Dosya seç');
        dugme.type = 'button';
        dugme.addEventListener('click', function () {
            medyaSeciciAc(tur, function (medya) {
                ogeyeMedyaBagla(oge, medya);
                gecmiseYaz();
                cizTam();
            });
        });

        var sarmal = olustur('div');
        if (oge.kaynak) {
            sarmal.appendChild(olustur('p', 'ek-ozellik-kaynak', oge.kaynak.ad || ''));
        } else {
            sarmal.appendChild(olustur('p', 'ek-ozellik-uyari', 'Henüz dosya seçilmedi.'));
        }
        sarmal.appendChild(dugme);
        return sarmal;
    }

    function sayfaYoneticisi(oge) {
        var kutu = olustur('div', 'ek-sayfa-yonetici');
        kutu.appendChild(olustur('div', 'ek-ozellik-yardim', 'Gösterilmeyecek sayfaların işaretini kaldırın.'));

        var tumSayfalar = oge.kaynak.sayfalar || [];
        var ayarlar = (oge.icerik.sayfalar || []).slice();
        if (!ayarlar.length) {
            ayarlar = tumSayfalar.map(function (_, indeks) {
                return { no: indeks, sure: oge.icerik.ortak_sure || 10, gorunur: true };
            });
        }

        var izgara = olustur('div', 'ek-sayfa-izgara');
        ayarlar.forEach(function (ayar) {
            var sayfa = tumSayfalar[ayar.no];
            if (!sayfa) { return; }
            var kart = olustur('label', 'ek-sayfa-kart');
            var onay = olustur('input');
            onay.type = 'checkbox';
            onay.checked = ayar.gorunur !== false;
            onay.addEventListener('change', function () {
                ayar.gorunur = onay.checked;
                guncelle(oge, 'icerik.sayfalar', ayarlar);
            });
            var kucuk = olustur('img');
            kucuk.src = sayfa.url;
            kucuk.alt = '';
            kart.appendChild(onay);
            kart.appendChild(kucuk);
            kart.appendChild(olustur('span', null, String(ayar.no + 1)));
            izgara.appendChild(kart);
        });
        kutu.appendChild(izgara);

        var tekSayfa = secimGirdi(
            oge.icerik.tek_sayfa == null ? '' : String(oge.icerik.tek_sayfa),
            [['', 'Tüm sayfalar sırayla']].concat(tumSayfalar.map(function (_, indeks) {
                return [String(indeks), 'Yalnız sayfa ' + (indeks + 1)];
            })),
            function (deger) {
                guncelle(oge, 'icerik.tek_sayfa', deger === '' ? null : parseInt(deger, 10));
            }
        );
        kutu.appendChild(alanKutusu('Sabit sayfa', tekSayfa));
        return kutu;
    }

    function coklinMedyaYoneticisi(oge, tur) {
        var kutu = olustur('div', 'ek-coklu-medya');
        var kaynaklar = oge.kaynaklar || [];

        if (kaynaklar.length) {
            var liste = olustur('div', 'ek-coklu-liste');
            kaynaklar.forEach(function (kayit, indeks) {
                var satir = olustur('div', 'ek-coklu-satir');
                var kucuk = olustur('img');
                kucuk.src = (kayit.medya && kayit.medya.url) || '';
                kucuk.alt = '';
                satir.appendChild(kucuk);
                satir.appendChild(olustur('span', 'ek-coklu-ad', (kayit.medya && kayit.medya.ad) || ''));

                var yukari = olustur('button', 'ek-ikon-dugme', '↑');
                yukari.type = 'button';
                yukari.disabled = indeks === 0;
                yukari.addEventListener('click', function () {
                    kaynaklar.splice(indeks - 1, 0, kaynaklar.splice(indeks, 1)[0]);
                    guncelle(oge, 'kaynaklar', kaynaklar);
                });
                satir.appendChild(yukari);

                var sil = olustur('button', 'ek-ikon-dugme', '×');
                sil.type = 'button';
                sil.addEventListener('click', function () {
                    kaynaklar.splice(indeks, 1);
                    guncelle(oge, 'kaynaklar', kaynaklar);
                });
                satir.appendChild(sil);
                liste.appendChild(satir);
            });
            kutu.appendChild(liste);
        }

        var ekle = olustur('button', 'ek-ozellik-dugme', 'Slayta görsel ekle');
        ekle.type = 'button';
        ekle.addEventListener('click', function () {
            medyaSeciciAc(tur, function (medya) {
                oge.kaynaklar = oge.kaynaklar || [];
                if (!oge.kaynaklar.length && oge.kaynak) {
                    oge.kaynaklar.push({ medya: oge.kaynak, sira: 0, sure: 8, gorunur: true });
                }
                oge.kaynaklar.push({
                    medya: { id: medya.id, tur: medya.tur, ad: medya.ad, url: medya.url, g: medya.g, y: medya.y },
                    sira: oge.kaynaklar.length,
                    sure: oge.icerik.ortak_sure || 8,
                    gorunur: true
                });
                gecmiseYaz();
                cizTam();
            });
        });
        kutu.appendChild(ekle);
        return kutu;
    }

    // ——— Medya seçici ————————————————————————————————————————

    var medyaKatman = document.getElementById('ek-medya-katman');
    var medyaIzgara = document.getElementById('ek-medya-izgara');
    var medyaArama = document.getElementById('ek-medya-arama');
    var medyaYukleGirdi = document.getElementById('ek-medya-dosya');
    var medyaDurum = document.getElementById('ek-medya-durum');
    var medyaGeriCagri = null;
    var medyaTuru = '';

    function medyaSeciciAc(tur, geriCagri) {
        if (!medyaKatman) {
            // Seçici penceresi olmayan bir sayfadayız: doğrudan dosya diyaloğu aç.
            dosyaDiyaloguAc(tur, geriCagri);
            return;
        }
        medyaTuru = tur || '';
        medyaGeriCagri = geriCagri;
        medyaKatman.hidden = false;
        medyaArama.value = '';
        medyaListele();
        medyaArama.focus();
    }

    function medyaSeciciKapat() {
        medyaKatman.hidden = true;
        medyaGeriCagri = null;
        medyaDurum.textContent = '';
    }

    function medyaListele() {
        medyaIzgara.innerHTML = '';
        medyaDurum.textContent = 'Yükleniyor…';

        var adres = BAS.adresler.medya_liste + '?tur=' + encodeURIComponent(medyaTuru) +
            '&q=' + encodeURIComponent(medyaArama.value || '');

        fetch(adres, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
            .then(function (y) { return y.json(); })
            .then(function (veri) {
                medyaDurum.textContent = '';
                var medyalar = veri.medyalar || [];
                if (!medyalar.length) {
                    medyaIzgara.appendChild(olustur('p', 'ek-medya-bos',
                        'Bu türde dosya yok. Aşağıdaki “Bilgisayardan yükle” ile ekleyebilir '
                        + 'ya da dosyayı doğrudan tahtaya sürükleyip bırakabilirsin.'));
                    return;
                }
                medyalar.forEach(function (medya) {
                    var kart = olustur('button', 'ek-medya-kart');
                    kart.type = 'button';

                    var gorsel = olustur('div', 'ek-medya-onizleme');
                    if (medya.onizleme) {
                        var img = olustur('img');
                        img.src = medya.onizleme;
                        img.alt = '';
                        img.loading = 'lazy';
                        gorsel.appendChild(img);
                    } else {
                        gorsel.appendChild(olustur('span', 'ek-medya-simge',
                            medya.tur === 'video' ? '▶' : '◻'));
                    }
                    kart.appendChild(gorsel);

                    kart.appendChild(olustur('span', 'ek-medya-ad', medya.ad));
                    var altBilgi = medya.boyut + (medya.sayfa_sayisi ? ' · ' + medya.sayfa_sayisi + ' sayfa' : '');
                    kart.appendChild(olustur('span', 'ek-medya-bilgi', altBilgi));

                    if (medya.durum === 'hata') {
                        kart.classList.add('ek-medya-hatali');
                        kart.title = medya.not || 'Bu dosya işlenemedi.';
                    }

                    kart.addEventListener('click', function () {
                        if (medyaGeriCagri) { medyaGeriCagri(medya); }
                        medyaSeciciKapat();
                    });
                    medyaIzgara.appendChild(kart);
                });
            })
            .catch(function () {
                medyaDurum.textContent = 'Dosyalar getirilemedi. Bağlantınızı kontrol edip tekrar deneyin.';
            });
    }

    if (medyaArama) {
        var aramaZaman = null;
        medyaArama.addEventListener('input', function () {
            if (aramaZaman) { clearTimeout(aramaZaman); }
            aramaZaman = setTimeout(medyaListele, 250);
        });
    }

    document.querySelectorAll('[data-medya-kapat]').forEach(function (dugme) {
        dugme.addEventListener('click', medyaSeciciKapat);
    });

    if (medyaYukleGirdi) {
        medyaYukleGirdi.addEventListener('change', function () {
            var dosya = medyaYukleGirdi.files && medyaYukleGirdi.files[0];
            if (!dosya) { return; }
            medyaYukle(dosya);
            medyaYukleGirdi.value = '';
        });
    }

    function medyaDurumYaz(metin) {
        if (medyaDurum) { medyaDurum.textContent = metin; }
    }

    /**
     * @param {File} dosya
     * @param {Function} [geriCagri] Yükleme bitince medya nesnesiyle çağrılır.
     *   Tahtaya sürükle-bırakta öğeyi yerleştirmek için kullanılır.
     */
    function medyaYukle(dosya, geriCagri) {
        medyaDurumYaz('“' + dosya.name + '” yükleniyor…');
        yuklemeGostergesi(dosya.name, true);

        function gonder(sure) {
            var govde = new FormData();
            govde.append('dosya', dosya);
            govde.append('sure', sure || 0);

            fetch(BAS.adresler.medya_yukle, {
                method: 'POST',
                body: govde,
                headers: { 'X-CSRFToken': csrfAl(), 'X-Requested-With': 'XMLHttpRequest' },
                credentials: 'same-origin'
            })
                .then(function (y) { return y.json(); })
                .then(function (veri) {
                    yuklemeGostergesi(dosya.name, false);
                    if (!veri.tamam) {
                        medyaDurumYaz(veri.mesaj || 'Dosya yüklenemedi.');
                        uyar(veri.mesaj || 'Dosya yüklenemedi.');
                        return;
                    }
                    medyaDurumYaz(veri.mesaj || 'Yüklendi.');
                    if (medyaIzgara) { medyaListele(); }
                    if (geriCagri) { geriCagri(veri.medya); }
                })
                .catch(function () {
                    yuklemeGostergesi(dosya.name, false);
                    medyaDurumYaz('Dosya yüklenemedi. Bağlantınızı kontrol edin.');
                    uyar('Dosya yüklenemedi. Bağlantınızı kontrol edin.');
                });
        }

        // Videonun süresini tarayıcı okur; sunucuda ffmpeg gerekmez.
        if (dosya.type.indexOf('video') === 0) {
            var video = document.createElement('video');
            video.preload = 'metadata';
            video.onloadedmetadata = function () {
                URL.revokeObjectURL(video.src);
                gonder(video.duration || 0);
            };
            video.onerror = function () { gonder(0); };
            video.src = URL.createObjectURL(dosya);
        } else {
            gonder(0);
        }
    }

    function csrfAl() {
        var girdi = document.querySelector('input[name="csrfmiddlewaretoken"]');
        return girdi ? girdi.value : '';
    }

    // ——— Tahtaya dosya bırakma ————————————————————————————————
    // Kullanıcı videoyu/afişi doğrudan tahtaya sürükleyebilmeli: dosya
    // yüklenir, türüne uygun öğe oluşturulur ve bırakıldığı noktaya konur.

    var birakKatmani = document.getElementById('ek-birak-katmani');
    var birakSayaci = 0;   // dragenter/dragleave iç içe öğelerde sekiyor

    function dosyaTasiniyorMu(olay) {
        var t = olay.dataTransfer;
        return !!t && Array.prototype.indexOf.call(t.types || [], 'Files') >= 0;
    }

    function birakGoster(goster) {
        if (birakKatmani) { birakKatmani.hidden = !goster; }
    }

    function turdenTanim(medya) {
        for (var i = 0; i < BAS.katalog.length; i += 1) {
            if (BAS.katalog[i].tur === medya.tur) { return BAS.katalog[i]; }
        }
        return null;
    }

    function birakilanMedyayiYerlestir(medya, nokta) {
        var tanim = turdenTanim(medya);
        if (!tanim) { return; }

        var v = tanim.varsayilan;
        var g = Math.min(v.g, TUVAL.g);
        var h = Math.min(v.y, TUVAL.y);

        // Görselin/videonun kendi oranını koru.
        if (medya.g && medya.y) {
            var oran = medya.g / medya.y;
            h = Math.round(g / oran);
            if (h > TUVAL.y) { h = TUVAL.y; g = Math.round(h * oran); }
        }

        var oge = {
            id: yeniId(),
            tur: medya.tur,
            ad: medya.ad,
            x: Math.round(Math.min(Math.max(0, nokta.x - g / 2), TUVAL.g - g)),
            y: Math.round(Math.min(Math.max(0, nokta.y - h / 2), TUVAL.y - h)),
            g: g,
            h: h,
            donus: 0,
            katman: D.sahne.ogeler.length,
            opaklik: 1,
            kilitli: false,
            gorunur: true,
            stil: kopyala(v.stil || {}),
            icerik: kopyala(v.icerik || {}),
            zamanlama: {},
            animasyon: {}
        };
        ogeyeMedyaBagla(oge, medya, false);

        D.sahne.ogeler.push(oge);
        D.secili = [oge.id];
        gecmiseYaz();
        cizTam();
    }

    if (!SALT_OKUNUR) {
        tuvalAlan.addEventListener('dragenter', function (olay) {
            if (!dosyaTasiniyorMu(olay)) { return; }
            olay.preventDefault();
            birakSayaci += 1;
            birakGoster(true);
        });
        tuvalAlan.addEventListener('dragover', function (olay) {
            if (!dosyaTasiniyorMu(olay)) { return; }
            olay.preventDefault();
            olay.dataTransfer.dropEffect = 'copy';
        });
        tuvalAlan.addEventListener('dragleave', function (olay) {
            if (!dosyaTasiniyorMu(olay)) { return; }
            birakSayaci = Math.max(0, birakSayaci - 1);
            if (!birakSayaci) { birakGoster(false); }
        });
        tuvalAlan.addEventListener('drop', function (olay) {
            if (!dosyaTasiniyorMu(olay)) { return; }
            olay.preventDefault();
            birakSayaci = 0;
            birakGoster(false);

            var nokta = tuvalKonumu(olay);
            var dosyalar = Array.prototype.slice.call(olay.dataTransfer.files || []);
            // Birden çok dosya bırakılırsa sırayla yerleştirilir.
            dosyalar.forEach(function (dosya, indeks) {
                medyaYukle(dosya, function (medya) {
                    birakilanMedyayiYerlestir(medya, {
                        x: nokta.x + indeks * 40,
                        y: nokta.y + indeks * 40
                    });
                });
            });
        });

        // Tarayıcı sayfanın geri kalanına bırakılan dosyayı AÇMASIN.
        window.addEventListener('dragover', function (olay) {
            if (dosyaTasiniyorMu(olay)) { olay.preventDefault(); }
        });
        window.addEventListener('drop', function (olay) {
            if (dosyaTasiniyorMu(olay)) { olay.preventDefault(); }
        });
    }

    /** Seçici yokken kullanılan yedek: tarayıcının dosya diyaloğu. */
    function dosyaDiyaloguAc(tur, geriCagri) {
        var girdi = document.createElement('input');
        girdi.type = 'file';
        girdi.accept = tur === 'video' ? '.mp4,.mov,.webm,.m4v'
            : (tur === 'pdf' ? '.pdf' : '.png,.jpg,.jpeg,.webp');
        girdi.addEventListener('change', function () {
            var dosya = girdi.files && girdi.files[0];
            if (dosya) { medyaYukle(dosya, geriCagri); }
        });
        girdi.click();
    }

    /** Tahtanın üstünde küçük bir "yükleniyor" şeridi. */
    var yuklemeler = {};
    function yuklemeGostergesi(ad, acik) {
        var kutu = document.getElementById('ek-yukleme-serit');
        if (!kutu) { return; }
        if (acik) { yuklemeler[ad] = true; } else { delete yuklemeler[ad]; }
        var adlar = Object.keys(yuklemeler);
        kutu.hidden = !adlar.length;
        if (adlar.length) {
            kutu.textContent = adlar.length === 1
                ? '“' + adlar[0] + '” yükleniyor…'
                : adlar.length + ' dosya yükleniyor…';
        }
    }

    function uyar(mesaj) {
        var kutu = document.getElementById('ek-uyari-serit');
        if (!kutu) { window.alert(mesaj); return; }
        kutu.textContent = mesaj;
        kutu.hidden = false;
        setTimeout(function () { kutu.hidden = true; }, 6000);
    }

    // ——— Kaydetme ————————————————————————————————————————————

    function durumGuncelle() {
        if (D.kaydediliyor) { durumMetni.textContent = 'Kaydediliyor…'; return; }
        if (D.kirli) { durumMetni.textContent = 'Kaydedilmemiş değişiklik var'; return; }
        durumMetni.textContent = D.sonKayit ? ('Kaydedildi · ' + D.sonKayit) : 'Kaydedildi';
    }

    function kaydet(sessiz) {
        if (SALT_OKUNUR || D.kaydediliyor) { return Promise.resolve(false); }
        D.kaydediliyor = true;
        durumGuncelle();

        var govde = kopyala(D.sahne);
        govde.tuval = TUVAL;
        // Geçici (negatif) id'ler sunucuya gönderilmez; sunucu yenilerini üretir.
        govde.ogeler.forEach(function (o) { if (o.id < 0) { delete o.id; } });

        return fetch(BAS.adresler.kaydet, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfAl(),
                'X-Requested-With': 'XMLHttpRequest'
            },
            credentials: 'same-origin',
            body: JSON.stringify(govde)
        })
            .then(function (y) { return y.json(); })
            .then(function (veri) {
                D.kaydediliyor = false;
                if (!veri.tamam) {
                    durumMetni.textContent = veri.mesaj || 'Kaydedilemedi';
                    return false;
                }
                D.kirli = false;
                D.sonKayit = veri.kaydedilme;
                // Sunucudan dönen gerçek id'lerle çalışmaya devam et.
                if (veri.sahne) {
                    var seciliIndeksler = D.secili.map(function (id) {
                        for (var i = 0; i < D.sahne.ogeler.length; i += 1) {
                            if (String(D.sahne.ogeler[i].id) === String(id)) { return i; }
                        }
                        return -1;
                    }).filter(function (i) { return i >= 0; });

                    D.sahne = veri.sahne;
                    D.secili = seciliIndeksler
                        .map(function (i) { return D.sahne.ogeler[i] && D.sahne.ogeler[i].id; })
                        .filter(function (id) { return id != null; });
                    D.gecmis = [kopyala(D.sahne)];
                    D.gecmisIndeksi = 0;
                    cizTam();
                }
                durumGuncelle();
                return true;
            })
            .catch(function () {
                D.kaydediliyor = false;
                durumMetni.textContent = 'Kaydedilemedi — bağlantınızı kontrol edin';
                return false;
            });
    }

    // Otomatik kaydetme: değişiklikten 25 sn sonra, sessizce.
    // Sürükleme ya da yazı düzenleme sırasında ÇALIŞMAZ: kayıt başarılı
    // olunca tuval yeniden çizilir ve düzenlenen kutu yok olur; kullanıcı
    // cümlenin ortasında odağını kaybederdi.
    setInterval(function () {
        if (D.kirli && !D.kaydediliyor && !surukleme && !duzenlenen) { kaydet(true); }
    }, 25000);

    window.addEventListener('beforeunload', function (olay) {
        if (D.kirli) {
            olay.preventDefault();
            olay.returnValue = '';
        }
    });

    // ——— Araç çubuğu ————————————————————————————————————————

    function baglaTiklama(id, islev) {
        var dugme = document.getElementById(id);
        if (dugme) { dugme.addEventListener('click', islev); }
    }

    baglaTiklama('ek-kaydet', function () { kaydet(); });
    baglaTiklama('ek-geri-al', geriAl);
    baglaTiklama('ek-ileri-al', ileriAl);
    baglaTiklama('ek-cogalt', seciliCogalt);
    baglaTiklama('ek-sil', seciliSil);

    baglaTiklama('ek-onizle', function () {
        var ac = function () { window.open(BAS.adresler.onizleme, '_blank', 'noopener'); };
        if (D.kirli) { kaydet().then(ac); } else { ac(); }
    });

    var zoomSecim = document.getElementById('ek-zoom-secim');
    if (zoomSecim) {
        zoomSecim.addEventListener('change', function () {
            if (zoomSecim.value === 'sigdir') {
                D.zoomModu = 'sigdir';
            } else {
                D.zoomModu = 'sabit';
                D.zoom = parseFloat(zoomSecim.value);
            }
            cizTam();
        });
    }

    window.addEventListener('resize', function () {
        if (D.zoomModu === 'sigdir') { cizTam(); }
    });

    // Ctrl/Cmd + tekerlek ile yakınlaştırma
    tuvalAlan.addEventListener('wheel', function (olay) {
        if (!(olay.ctrlKey || olay.metaKey)) { return; }
        olay.preventDefault();
        D.zoomModu = 'sabit';
        D.zoom = Math.min(3, Math.max(0.1, D.zoom * (olay.deltaY < 0 ? 1.1 : 0.9)));
        if (zoomSecim) { zoomSecim.value = 'sabit'; }
        cizTam();
    }, { passive: false });

    // ——— Başlat ————————————————————————————————————————————————

    katalogCiz();
    D.gecmis = [kopyala(D.sahne)];
    D.gecmisIndeksi = 0;
    cizTam();
    durumGuncelle();
}());
