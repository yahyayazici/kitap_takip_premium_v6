/* E-Kitap — tam ekran soru görünümü.
 *
 * Kitaptaki büyüteç rozetine dokunulunca soru kitabın üstünde açılır ve en-boy
 * oranı korunarak ekrana sığdırılır. Sorular arasında sayfa sınırına takılmadan
 * (bölümler dahil) kitap sırasıyla gezilir. Kitap arkada olduğu gibi kalır;
 * kapatınca aynı sayfa ve konuma dönülür.
 *
 * Görseller: sunucunun ürettiği yüksek çözünürlüklü soru kırpıntısı; yoksa
 * sayfa görselinden CSS ile kırpılır.
 *
 * Yakınlaştırma Pointer Events ile yapılır: iki parmak (çimdik) yakınlaştırır,
 * tek parmak/fare yakınlaştırılmışken kaydırır; yakınlaştırılmamışken yatay
 * kaydırma önceki/sonraki soruya geçer. Kalem araçları (2. aşama) bu katmana
 * bağlanır: içerik koordinatları kâğıt birimindedir, yakınlaştırmadan bağımsızdır.
 */
(function () {
    'use strict';

    var veri = JSON.parse(document.getElementById('ekitapVeri').textContent);
    var kok = document.getElementById('soruGorunum');
    if (!kok) return;
    var sahne = document.getElementById('soruSahne');
    var katman = document.getElementById('soruKatman');
    var kagit = document.getElementById('soruKagit');
    var baslik = document.getElementById('soruBaslik');
    var altBaslik = document.getElementById('soruAlt');
    var oncekiBtn = document.getElementById('soruOnceki');
    var sonrakiBtn = document.getElementById('soruSonraki');
    var kapatBtn = document.getElementById('soruKapat');
    var zoomOran = document.getElementById('soruZoomSifirla');
    var cizimSvg = document.getElementById('soruCizim');

    var MIN_ZOOM = 1;
    var MAX_ZOOM = 6;
    var ADIM = 1.35;
    var PARCA_ARASI = 0.012; // devam eden alanlar arası boşluk (kâğıt genişliği oranı)

    // Kitaptaki tüm sorular, kitap sırasıyla (bölüm → okuma sırası).
    var sorular = [];
    veri.forEach(function (bolum, b) {
        var testler = {};
        (bolum.sorular || []).forEach(function (s) { testler[s.t] = true; });
        var cokTestli = Object.keys(testler).length > 1;
        (bolum.sorular || []).forEach(function (s) {
            sorular.push({ b: b, soru: s, cokTestli: cokTestli });
        });
    });

    var aktif = -1;
    var acik = false;
    var liste = null; // ders akışı: gezilecek soru indeksleri (sırasıyla)
    var listeAdi = '';
    var donusOdagi = null;
    var olcu = { w: 1, h: 1, olcek: 1, soruW: 1, soruH: 1 }; // kâğıt birimi ve ekrana sığdırma ölçeği
    var ekAlan = { alt: 0, sag: 0 }; // çözüm alanı (sorunun boyutuna oran)
    var yerlesim = []; // parçaların kâğıttaki yeri (kâğıt biriminde)
    var cizim = null; // çizim köprüsü: { basla(e), surdur(e), bitir(e), iptal(), avucMu(e), ciziyorMu() }
    var z = { s: 1, x: 0, y: 0 };

    function sinirla(d, a, b) { return Math.max(a, Math.min(b, d)); }

    // —— Görsel kaynakları —————————————————————————————————————————————————
    function sayfaBilgisi(b, s) {
        return veri[b].sayfalar[s] || { w: 1000, h: 1414, src: '' };
    }

    function parcalar(kayit) {
        return kayit.soru.alanlar.map(function (a) {
            var sayfa = sayfaBilgisi(kayit.b, a.s);
            var k = a.k;
            return {
                src: a.src,
                sayfa: sayfa,
                k: k,
                w: (k[2] - k[0]) * sayfa.w,
                h: (k[3] - k[1]) * sayfa.h
            };
        });
    }

    function onYukle(indeks) {
        var kayit = sorular[indeks];
        if (!kayit) return;
        parcalar(kayit).forEach(function (p) {
            var img = new Image();
            img.decoding = 'async';
            img.src = p.src || p.sayfa.src;
        });
    }

    // —— Çizim ————————————————————————————————————————————————————————————
    function kagidiKur(kayit) {
        var ps = parcalar(kayit);
        var genislik = 1;
        ps.forEach(function (p) { genislik = Math.max(genislik, p.w); });
        var bosluk = genislik * PARCA_ARASI;
        var yukseklik = 0;
        ps.forEach(function (p, i) { yukseklik += p.h + (i ? bosluk : 0); });
        olcu.soruW = genislik;
        olcu.soruH = Math.max(yukseklik, 1);
        // Çözüm alanı soru içeriğinin sağına/altına eklenir; içerik sol üstte kalır,
        // böylece çizimlerin kâğıt koordinatları değişmez.
        olcu.w = genislik * (1 + ekAlan.sag);
        olcu.h = olcu.soruH * (1 + ekAlan.alt);
        yerlesim = [];

        kagit.innerHTML = '';
        var y = 0;
        ps.forEach(function (p, i) {
            if (i) y += bosluk;
            var parca = document.createElement('div');
            parca.className = 'ek-soru-parca' + (i ? ' ek-soru-devam' : '');
            parca.style.left = '0';
            parca.style.top = (y / olcu.h * 100) + '%';
            parca.style.width = (p.w / olcu.w * 100) + '%';
            parca.style.height = (p.h / olcu.h * 100) + '%';
            var img = document.createElement('img');
            img.alt = i ? 'Sorunun devamı' : 'Soru ' + kayit.soru.no;
            img.draggable = false;
            img.decoding = 'async';
            if (p.src) {
                img.src = p.src;
                img.className = 'ek-soru-kirpinti';
            } else {
                // Sunucu kırpıntısı yoksa sayfa görselinden kırp.
                img.src = p.sayfa.src;
                img.className = 'ek-soru-sayfadan';
                img.style.width = (p.sayfa.w / p.w * 100) + '%';
                img.style.left = (-p.k[0] * p.sayfa.w / p.w * 100) + '%';
                img.style.top = (-p.k[1] * p.sayfa.h / p.h * 100) + '%';
            }
            parca.appendChild(img);
            kagit.appendChild(parca);
            yerlesim.push({ y: y, w: p.w, h: p.h, k: p.k, sayfa: p.sayfa });
            y += p.h;
        });
        if (ekAlan.alt) {
            var alt = document.createElement('div');
            alt.className = 'ek-cozum-alani';
            alt.style.left = '0';
            alt.style.right = '0';
            alt.style.top = (olcu.soruH / olcu.h * 100) + '%';
            alt.style.bottom = '0';
            kagit.appendChild(alt);
        }
        if (ekAlan.sag) {
            var sag = document.createElement('div');
            sag.className = 'ek-cozum-alani';
            sag.style.left = (olcu.soruW / olcu.w * 100) + '%';
            sag.style.right = '0';
            sag.style.top = '0';
            sag.style.bottom = ekAlan.alt ? ((1 - olcu.soruH / olcu.h) * 100) + '%' : '0';
            kagit.appendChild(sag);
        }
        if (cizimSvg) {
            cizimSvg.setAttribute('viewBox', '0 0 ' + olcu.w + ' ' + olcu.h);
            kagit.appendChild(cizimSvg);
        }
        sigdir();
    }

    function sigdir() {
        if (!acik) return;
        var stil = getComputedStyle(sahne);
        var W = sahne.clientWidth - parseFloat(stil.paddingLeft) - parseFloat(stil.paddingRight);
        var H = sahne.clientHeight - parseFloat(stil.paddingTop) - parseFloat(stil.paddingBottom);
        olcu.olcek = Math.max(0.05, Math.min(W / olcu.w, H / olcu.h));
        kagit.style.width = Math.floor(olcu.w * olcu.olcek) + 'px';
        kagit.style.height = Math.floor(olcu.h * olcu.olcek) + 'px';
        zoomSifirla();
        kok.dispatchEvent(new CustomEvent('ek-soru-olcu'));
    }

    function etiketleriGuncelle(kayit) {
        var bolum = veri[kayit.b];
        baslik.textContent = kayit.soru.no + '. soru';
        var parcalarMetin = [];
        if (veri.length > 1) parcalarMetin.push(bolum.ad);
        if (kayit.cokTestli) parcalarMetin.push(kayit.soru.t + '. test');
        if (liste) {
            var konum = liste.indexOf(aktif);
            parcalarMetin.unshift(listeAdi);
            parcalarMetin.push((konum + 1) + ' / ' + liste.length);
            oncekiBtn.disabled = konum <= 0;
            sonrakiBtn.disabled = konum >= liste.length - 1;
        } else {
            parcalarMetin.push((aktif + 1) + ' / ' + sorular.length);
            oncekiBtn.disabled = aktif <= 0;
            sonrakiBtn.disabled = aktif >= sorular.length - 1;
        }
        altBaslik.textContent = parcalarMetin.join(' · ');
    }

    function goster(indeks) {
        if (indeks < 0 || indeks >= sorular.length) return;
        var onceki = aktif;
        aktif = indeks;
        var kayit = sorular[indeks];
        kok.dispatchEvent(new CustomEvent('ek-soru-degisecek', { detail: { onceki: onceki, simdi: indeks } }));
        kagidiKur(kayit);
        etiketleriGuncelle(kayit);
        onYukle(komsu(indeks, 1));
        onYukle(komsu(indeks, -1));
        onYukle(komsu(indeks, 2));
        kok.dispatchEvent(new CustomEvent('ek-soru-degisti', { detail: { onceki: onceki, simdi: indeks } }));
    }

    // —— Dış arayüz ———————————————————————————————————————————————————————
    function ac(indeks, odak) {
        if (!sorular[indeks]) return;
        if (!acik) { liste = null; listeAdi = ''; }
        donusOdagi = odak || document.activeElement;
        if (!acik) {
            acik = true;
            kok.hidden = false;
            document.body.classList.add('ek-soru-acik');
            kok.dispatchEvent(new CustomEvent('ek-soru-acildi'));
        }
        goster(indeks);
        kapatBtn.focus({ preventScroll: true });
    }

    // Çizim varsa onay ister: false dönerse kapatma bekletilir, onaylanınca devam() çağrılır.
    var kapatmaOnayi = null;

    function kapat(zorla) {
        if (!acik) return;
        if (zorla !== true && kapatmaOnayi && kapatmaOnayi(function () { kapat(true); }) === false) return;
        acik = false;
        kok.hidden = true;
        document.body.classList.remove('ek-soru-acik');
        kok.dispatchEvent(new CustomEvent('ek-soru-kapandi'));
        kagit.innerHTML = '';
        ekAlan = { alt: 0, sag: 0 };
        aktif = -1;
        liste = null;
        listeAdi = '';
        if (donusOdagi && document.contains(donusOdagi)) {
            try { donusOdagi.focus({ preventScroll: true }); } catch (e) { /* yok say */ }
        }
    }

    /* Sıradaki soru: ders akışında listedeki sıra, değilse kitap sırası. */
    function komsu(indeks, adim) {
        if (!liste) return indeks + adim;
        var k = liste.indexOf(indeks) + adim;
        return k >= 0 && k < liste.length ? liste[k] : -1;
    }

    function sonraki() { var i = komsu(aktif, 1); if (sorular[i]) goster(i); }
    function onceki() { var i = komsu(aktif, -1); if (i >= 0 && sorular[i]) goster(i); }

    /* Ders akışını baştan aç: yalnızca seçilen sorular, seçilen sırayla. */
    function listeAc(indeksler, ad, odak) {
        indeksler = indeksler.filter(function (i) { return !!sorular[i]; });
        if (!indeksler.length) return;
        if (acik) kapat(true);
        ac(indeksler[0], odak);
        liste = indeksler;
        listeAdi = ad || 'Ders akışı';
        etiketleriGuncelle(sorular[aktif]);
        onYukle(komsu(aktif, 1));
    }

    function indeksBul(bolumIndeksi, soruId) {
        for (var i = 0; i < sorular.length; i++) {
            if (sorular[i].b === bolumIndeksi && sorular[i].soru.id === soruId) return i;
        }
        return -1;
    }

    // —— Yakınlaştırma ————————————————————————————————————————————————————
    function sinirlariUygula() {
        var W = sahne.clientWidth;
        var H = sahne.clientHeight;
        z.x = sinirla(z.x, W - W * z.s, 0);
        z.y = sinirla(z.y, H - H * z.s, 0);
    }

    function zoomCiz() {
        katman.style.transform = 'translate(' + z.x + 'px,' + z.y + 'px) scale(' + z.s + ')';
        kok.classList.toggle('ek-yakin', z.s > 1.001);
        zoomOran.textContent = '%' + Math.round(z.s * 100);
    }

    function zoomAyarla(yeniS, px, py) {
        yeniS = sinirla(yeniS, MIN_ZOOM, MAX_ZOOM);
        if (px === undefined) {
            px = sahne.clientWidth / 2;
            py = sahne.clientHeight / 2;
        }
        z.x = px - (px - z.x) * (yeniS / z.s);
        z.y = py - (py - z.y) * (yeniS / z.s);
        z.s = yeniS;
        if (z.s <= 1.001) { z.s = 1; z.x = 0; z.y = 0; }
        sinirlariUygula();
        zoomCiz();
    }

    function zoomSifirla() {
        z.s = 1; z.x = 0; z.y = 0;
        zoomCiz();
    }

    function yerel(e) {
        var r = sahne.getBoundingClientRect();
        return { x: e.clientX - r.left, y: e.clientY - r.top };
    }

    /* Ekran noktasını kâğıt birimine çevirir (çizim katmanı için). */
    function kagitNoktasi(clientX, clientY) {
        var r = kagit.getBoundingClientRect();
        return {
            x: (clientX - r.left) / r.width * olcu.w,
            y: (clientY - r.top) / r.height * olcu.h
        };
    }

    // İşaretçi takibi. Çizim aracı seçiliyse tek işaretçi çizime gider; ikinci
    // parmak gelince yeni başlamış çizgi iptal edilir ve çimdik başlar. Kalem
    // ucu yazarken gelen dokunmalar (avuç içi) yok sayılır.
    var isaretciler = {};
    var jest = null;
    var sonDokunus = { t: 0, x: 0, y: 0 };

    function aktifIsaretciler() {
        return Object.keys(isaretciler).map(function (k) { return isaretciler[k]; });
    }

    function cimdikBaslat() {
        var p = aktifIsaretciler();
        p.forEach(function (k) { k.cizim = false; });
        var a = p[0], b = p[1];
        var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        jest = {
            tur: 'cimdik',
            mesafe: Math.hypot(a.x - b.x, a.y - b.y) || 1,
            s: z.s,
            icerik: { x: (mx - z.x) / z.s, y: (my - z.y) / z.s }
        };
    }

    sahne.addEventListener('pointerdown', function (e) {
        if (!acik) return;
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        if (cizim && cizim.avucMu(e)) { e.preventDefault(); return; }
        var p = yerel(e);
        isaretciler[e.pointerId] = { x: p.x, y: p.y, bx: p.x, by: p.y, t: Date.now(), tur: e.pointerType, cizim: false };
        try { sahne.setPointerCapture(e.pointerId); } catch (h) { /* yok say */ }
        e.preventDefault();
        if (aktifIsaretciler().length >= 2) {
            if (cizim) cizim.iptal();
            cimdikBaslat();
            return;
        }
        if (cizim && cizim.basla(e)) {
            isaretciler[e.pointerId].cizim = true;
            jest = null;
            return;
        }
        jest = { tur: 'kaydir', bx: p.x, by: p.y, x: z.x, y: z.y, t: Date.now() };
        if (e.pointerType !== 'mouse') {
            var simdi = Date.now();
            var cift = simdi - sonDokunus.t < 320 && Math.hypot(p.x - sonDokunus.x, p.y - sonDokunus.y) < 40;
            sonDokunus = { t: cift ? 0 : simdi, x: p.x, y: p.y };
            if (cift) {
                if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
                jest = null;
            }
        }
    });

    sahne.addEventListener('pointermove', function (e) {
        var kayit = isaretciler[e.pointerId];
        if (!kayit) return;
        var p = yerel(e);
        kayit.x = p.x;
        kayit.y = p.y;
        if (kayit.cizim) {
            cizim.surdur(e);
            return;
        }
        if (!jest) return;
        if (jest.tur === 'cimdik') {
            var ps = aktifIsaretciler();
            if (ps.length < 2) return;
            var a = ps[0], b = ps[1];
            var yeniS = sinirla(jest.s * (Math.hypot(a.x - b.x, a.y - b.y) || 1) / jest.mesafe, MIN_ZOOM, MAX_ZOOM);
            var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
            z.s = yeniS;
            z.x = mx - jest.icerik.x * yeniS;
            z.y = my - jest.icerik.y * yeniS;
            if (z.s <= 1.001) z.s = 1;
            sinirlariUygula();
            zoomCiz();
        } else if (jest.tur === 'kaydir' && z.s > 1.001) {
            z.x = jest.x + (p.x - jest.bx);
            z.y = jest.y + (p.y - jest.by);
            sinirlariUygula();
            zoomCiz();
        }
    });

    function isaretciBitti(e) {
        var kayit = isaretciler[e.pointerId];
        if (!kayit) return;
        delete isaretciler[e.pointerId];
        if (kayit.cizim) {
            cizim.bitir(e);
            jest = null;
            return;
        }
        var kalan = aktifIsaretciler();
        if (jest && jest.tur === 'kaydir' && z.s <= 1.001 && e.type === 'pointerup' && kalan.length === 0) {
            // Yakınlaştırılmamışken hızlı yatay kaydırma → sorular arasında geçiş
            var dx = kayit.x - kayit.bx;
            var dy = kayit.y - kayit.by;
            var sure = Date.now() - kayit.t;
            if (Math.abs(dx) > 90 && Math.abs(dx) > Math.abs(dy) * 1.6 && sure < 700) {
                if (dx < 0) sonraki(); else onceki();
            }
        }
        if (kalan.length === 1) {
            kalan[0].bx = kalan[0].x; kalan[0].by = kalan[0].y; kalan[0].t = Date.now();
            kalan[0].cizim = false;
            jest = { tur: 'kaydir', bx: kalan[0].x, by: kalan[0].y, x: z.x, y: z.y, t: Date.now() };
        } else if (kalan.length === 0) {
            jest = null;
            if (z.s <= 1.001) zoomSifirla();
        }
    }
    sahne.addEventListener('pointerup', isaretciBitti);
    sahne.addEventListener('pointercancel', isaretciBitti);

    sahne.addEventListener('dblclick', function (e) {
        if (cizim && cizim.ciziyorMu()) return;
        var p = yerel(e);
        if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
    });
    sahne.addEventListener('wheel', function (e) {
        var p = yerel(e);
        zoomAyarla(z.s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), p.x, p.y);
        if (e.cancelable) e.preventDefault();
    }, { passive: false });

    // —— Olaylar ——————————————————————————————————————————————————————————
    oncekiBtn.addEventListener('click', onceki);
    sonrakiBtn.addEventListener('click', sonraki);
    kapatBtn.addEventListener('click', kapat);
    document.getElementById('soruZoomCok').addEventListener('click', function () { zoomAyarla(z.s * ADIM); });
    document.getElementById('soruZoomAz').addEventListener('click', function () { zoomAyarla(z.s / ADIM); });
    zoomOran.addEventListener('click', zoomSifirla);

    document.addEventListener('keydown', function (e) {
        if (!acik) return;
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        var tus = e.key;
        var islendi = true;
        if (tus === 'Escape') kapat();
        else if (tus === 'ArrowRight' || tus === 'PageDown' || (tus === ' ' && e.target === document.body)) sonraki();
        else if (tus === 'ArrowLeft' || tus === 'PageUp') onceki();
        else if (tus === '+' || tus === '=') zoomAyarla(z.s * ADIM);
        else if (tus === '-') zoomAyarla(z.s / ADIM);
        else if (tus === '0') zoomSifirla();
        else islendi = false;
        if (islendi) {
            e.preventDefault();
            e.stopImmediatePropagation();
        }
    }, true);

    var zamanlayici = null;
    window.addEventListener('resize', function () {
        clearTimeout(zamanlayici);
        zamanlayici = setTimeout(sigdir, 120);
    });

    window.EKitapSoru = {
        ac: ac,
        listeAc: listeAc,
        kapat: kapat,
        acikMi: function () { return acik; },
        indeksBul: indeksBul,
        sorular: sorular,
        aktif: function () { return aktif; },
        kok: kok,
        sahne: sahne,
        kagit: kagit,
        olcu: olcu,
        kagitNoktasi: kagitNoktasi,
        zoom: z,
        cizimBagla: function (kopru) { cizim = kopru; },
        ekAlan: function () { return { alt: ekAlan.alt, sag: ekAlan.sag }; },
        /* sessiz: yalnızca değeri ayarla (soru değişirken, kâğıt zaten yeniden kurulacak). */
        ekAlanAyarla: function (yeni, sessiz) {
            ekAlan = { alt: yeni.alt || 0, sag: yeni.sag || 0 };
            if (!sessiz && acik && sorular[aktif]) kagidiKur(sorular[aktif]);
        },
        /* Şıkların kâğıttaki dikdörtgeni (kâğıt biriminde); bilinmiyorsa null. */
        sikKutusu: function () {
            var kayit = sorular[aktif];
            if (!kayit || !kayit.soru.siklar) return null;
            var parca = yerlesim[kayit.soru.siklar[0]];
            if (!parca) return null;
            var ust = parca.y + (kayit.soru.siklar[1] - parca.k[1]) * parca.sayfa.h;
            return { x: 0, y: ust, w: parca.w, h: parca.y + parca.h - ust };
        },
        kapatmaOnayiAyarla: function (fn) { kapatmaOnayi = fn; },
        sonraki: sonraki,
        onceki: onceki
    };
})();
