/* E-Kitap okuyucu — akıllı tahta için flipbook + yakınlaştırma.
 *
 * Sayfa çevirme StPageFlip (MIT) ile yapılır. Yakınlaştırma kitabın üstündeki
 * katmana CSS transform uygular; yakınlaştırılmışken dokunma/fare olayları
 * yakalama (capture) aşamasında burada tüketilir, böylece kaydırma yaparken
 * sayfa yanlışlıkla çevrilmez.
 */
(function () {
    'use strict';

    var veri = JSON.parse(document.getElementById('ekitapVeri').textContent);
    var okuyucu = document.getElementById('okuyucu');
    var tuval = document.getElementById('tuval');
    var katman = document.getElementById('zoomKatman');
    var kitapKap = document.getElementById('kitap');
    var sayfaNo = document.getElementById('sayfaNo');
    var sayfaToplam = document.getElementById('sayfaToplam');
    var zoomOran = document.getElementById('zoomSifirla');
    var tamEkranBtn = document.getElementById('tamEkran');
    var ilerleme = document.getElementById('ilerleme');
    var sekmeler = Array.prototype.slice.call(document.querySelectorAll('.ek-sekme'));

    var MIN_ZOOM = 1;
    var MAX_ZOOM = 5;
    var ADIM = 1.35;
    var ONYUKLEME_GERI = 2;
    var ONYUKLEME_ILERI = 6;

    var pageFlip = null;
    var aktif = 0;
    var yatay = false;
    var z = { s: 1, x: 0, y: 0 };

    // —— Yardımcılar ——————————————————————————————————————————————————————
    function sinirla(deger, min, max) {
        return Math.max(min, Math.min(max, deger));
    }

    function hafizaAnahtari(i) {
        return 'ekitap:' + location.pathname + ':' + veri[i].id;
    }

    function sonSayfaOku(i) {
        try {
            return parseInt(sessionStorage.getItem(hafizaAnahtari(i)), 10) || 0;
        } catch (e) {
            return 0;
        }
    }

    function sonSayfaYaz(i, sayfa) {
        try {
            sessionStorage.setItem(hafizaAnahtari(i), String(sayfa));
        } catch (e) { /* özel pencere: yok say */ }
    }

    function sayfaSayisi() {
        return veri[aktif].sayfalar.length;
    }

    // —— Kitap kurulumu ————————————————————————————————————————————————————
    function sayfaElemanlari(bolum) {
        return bolum.sayfalar.map(function (s, i) {
            var div = document.createElement('div');
            div.className = 'ek-sayfa';
            div.setAttribute('data-i', String(i));
            var img = document.createElement('img');
            img.alt = 'Sayfa ' + (i + 1);
            img.draggable = false;
            img.decoding = 'async';
            img.setAttribute('data-src', s.src);
            div.appendChild(img);
            rozetleriEkle(div, bolum, i, s);
            return div;
        });
    }

    // —— Büyüteç rozetleri ————————————————————————————————————————————————
    var ROZET_GENISLIK = 0.075; // sayfa genişliğine oran (dokunma alanı)

    function rozetleriEkle(div, bolum, sayfaIndeksi, sayfa) {
        (bolum.sorular || []).forEach(function (soru) {
            var ilk = soru.alanlar[0];
            if (!ilk || ilk.s !== sayfaIndeksi) return;
            var oran = sayfa.h ? sayfa.w / sayfa.h : 0.707;
            // Rozet numaranın soluna, numara satırının ortasına oturur; metni kapatmaz.
            var sol = Math.max(ilk.k[0] + 0.004, ROZET_GENISLIK + 0.002);
            var ust = ilk.k[1] + 0.017;
            ust = Math.max(ust, ROZET_GENISLIK * oran / 2);
            var btn = document.createElement('button');
            btn.type = 'button';
            btn.className = 'ek-buyutec';
            btn.setAttribute('data-bolum', String(veri.indexOf(bolum)));
            btn.setAttribute('data-soru', String(soru.id));
            btn.setAttribute('aria-label', soru.no + '. soruyu büyüt');
            btn.title = soru.no + '. soruyu büyüt';
            btn.style.left = (sol * 100) + '%';
            btn.style.top = (ust * 100) + '%';
            btn.style.width = (ROZET_GENISLIK * 100) + '%';
            btn.innerHTML = '<span class="ek-buyutec-ic" aria-hidden="true"><svg viewBox="0 0 24 24">' +
                '<circle cx="10.5" cy="10.5" r="6"/><path d="M15 15l5 5"/></svg></span>';
            div.appendChild(btn);
        });
    }

    function kitapCiziliyor() {
        return !!(window.EKitapCizim && window.EKitapCizim.kitapModu());
    }

    function kitapKalemi() {
        // Kitap çizim modunda bir çizim aracı seçili: tek dokunuş çizime aittir.
        return kitapCiziliyor() && window.EKitapCizim.ciziyorMu();
    }

    function rozetMi(e) {
        return !!(e.target && e.target.closest && e.target.closest('.ek-buyutec'));
    }

    // Rozete basış sayfa çevirmeyi başlatmasın (StPageFlip kök öğede dinler).
    ['mousedown', 'touchstart', 'pointerdown'].forEach(function (tur) {
        kitapKap.addEventListener(tur, function (e) {
            if (rozetMi(e)) e.stopPropagation();
        }, { capture: true, passive: true });
    });
    kitapKap.addEventListener('click', function (e) {
        var btn = e.target && e.target.closest ? e.target.closest('.ek-buyutec') : null;
        if (!btn || !window.EKitapSoru) return;
        e.stopPropagation();
        e.preventDefault();
        var indeks = window.EKitapSoru.indeksBul(
            parseInt(btn.getAttribute('data-bolum'), 10),
            parseInt(btn.getAttribute('data-soru'), 10)
        );
        if (indeks >= 0) window.EKitapSoru.ac(indeks, btn);
    }, true);

    function gorselleriYukle(merkez) {
        // usePortrait kipinde StPageFlip sayfaları kopyalar; tüm kopyalar yüklenir.
        for (var k = merkez - ONYUKLEME_GERI; k <= merkez + ONYUKLEME_ILERI; k++) {
            if (k < 0 || k >= sayfaSayisi()) continue;
            var resimler = kitapKap.querySelectorAll('.ek-sayfa[data-i="' + k + '"] img[data-src]');
            for (var j = 0; j < resimler.length; j++) {
                resimler[j].src = resimler[j].getAttribute('data-src');
                resimler[j].removeAttribute('data-src');
            }
        }
    }

    function olcuHesapla(bolum) {
        var ilk = bolum.sayfalar[0];
        var oran = ilk && ilk.h ? ilk.w / ilk.h : 0.707;
        var stil = getComputedStyle(tuval);
        var gW = tuval.clientWidth - parseFloat(stil.paddingLeft) - parseFloat(stil.paddingRight);
        var gH = tuval.clientHeight - parseFloat(stil.paddingTop) - parseFloat(stil.paddingBottom);
        // İki sayfa yan yana makul büyüklükte sığıyorsa açık kitap, yoksa tek sayfa.
        var ikiliH = Math.min(gH, gW / (2 * oran));
        var tekliH = Math.min(gH, gW / oran);
        yatay = ikiliH >= tekliH * 0.72 && bolum.sayfalar.length > 1;
        var h = Math.floor(yatay ? ikiliH : tekliH);
        var w = Math.floor(h * oran);
        return { w: Math.max(w, 50), h: Math.max(h, 70) };
    }

    function kur(bolumIndeksi, baslangic) {
        aktif = bolumIndeksi;
        zoomSifirla();
        var bolum = veri[aktif];
        if (pageFlip) {
            try { pageFlip.destroy(); } catch (e) { /* zaten kaldırılmış */ }
            pageFlip = null;
        }
        kitapKap.innerHTML = '';
        var kok = document.createElement('div');
        kitapKap.appendChild(kok);

        var olcu = olcuHesapla(bolum);
        // StPageFlip (autoSize) kökü kabın %100 genişliğine yayar ve yönü
        // (tek sayfa / açık kitap) bu genişliğe göre seçer; kabı açıkça boyutlandır.
        kitapKap.style.width = (yatay ? olcu.w * 2 : olcu.w) + 'px';
        kitapKap.style.height = olcu.h + 'px';
        var bas = sinirla(baslangic || 0, 0, Math.max(bolum.sayfalar.length - 1, 0));

        pageFlip = new St.PageFlip(kok, {
            width: olcu.w,
            height: olcu.h,
            size: 'fixed',
            maxWidth: olcu.w,
            maxHeight: olcu.h,
            showCover: true,
            usePortrait: true,
            autoSize: true,
            startPage: bas,
            drawShadow: true,
            maxShadowOpacity: 0.45,
            flippingTime: 650,
            mobileScrollSupport: false,
            swipeDistance: 25,
            disableFlipByClick: true,
            showPageCorners: true
        });
        pageFlip.on('flip', function (e) {
            gorselleriYukle(e.data);
            sonSayfaYaz(aktif, e.data);
            gostergeyiGuncelle();
        });
        pageFlip.on('changeOrientation', gostergeyiGuncelle);
        pageFlip.loadFromHTML(sayfaElemanlari(bolum));
        gorselleriYukle(bas);
        sayfaNo.max = String(bolum.sayfalar.length);
        sayfaToplam.textContent = '/ ' + bolum.sayfalar.length;
        sekmeler.forEach(function (btn, i) {
            btn.setAttribute('aria-selected', i === aktif ? 'true' : 'false');
        });
        gostergeyiGuncelle();
        document.dispatchEvent(new CustomEvent('ek-kitap-kuruldu'));
    }

    function mevcutSayfa() {
        return pageFlip ? pageFlip.getCurrentPageIndex() : 0;
    }

    function gostergeyiGuncelle() {
        var no = mevcutSayfa() + 1;
        if (document.activeElement !== sayfaNo) {
            sayfaNo.value = String(no);
        }
        if (ilerleme) {
            var toplam = Math.max(sayfaSayisi(), 1);
            // Açık kitapta görünen sağ sayfa da okunmuş sayılır.
            var gorunen = yatay && no > 1 ? Math.min(no + 1, toplam) : no;
            ilerleme.style.width = (toplam > 1 ? (gorunen / toplam) * 100 : 100) + '%';
        }
    }

    function sayfayaGit(no) {
        if (!pageFlip || kitapCiziliyor()) return;
        var hedef = sinirla(no - 1, 0, sayfaSayisi() - 1);
        zoomSifirla();
        if (Math.abs(hedef - mevcutSayfa()) <= 3) {
            pageFlip.flip(hedef, 'bottom');
        } else {
            pageFlip.turnToPage(hedef);
            gorselleriYukle(hedef);
            sonSayfaYaz(aktif, hedef);
        }
        gostergeyiGuncelle();
    }

    function sonraki() {
        if (kitapCiziliyor()) return;
        zoomSifirla();
        if (pageFlip) pageFlip.flipNext('bottom');
    }

    function onceki() {
        if (kitapCiziliyor()) return;
        zoomSifirla();
        if (pageFlip) pageFlip.flipPrev('bottom');
    }

    // —— Yakınlaştırma ————————————————————————————————————————————————————
    function sinirlariUygula() {
        var W = tuval.clientWidth;
        var H = tuval.clientHeight;
        z.x = sinirla(z.x, W - W * z.s, 0);
        z.y = sinirla(z.y, H - H * z.s, 0);
    }

    function zoomCiz() {
        katman.style.transform = 'translate(' + z.x + 'px,' + z.y + 'px) scale(' + z.s + ')';
        var yakin = z.s > 1.001;
        okuyucu.classList.toggle('ek-yakin', yakin);
        zoomOran.textContent = '%' + Math.round(z.s * 100);
    }

    function zoomAyarla(yeniS, px, py) {
        yeniS = sinirla(yeniS, MIN_ZOOM, MAX_ZOOM);
        if (px === undefined) {
            px = tuval.clientWidth / 2;
            py = tuval.clientHeight / 2;
        }
        // (px, py) altındaki içerik noktası yerinde kalsın.
        z.x = px - (px - z.x) * (yeniS / z.s);
        z.y = py - (py - z.y) * (yeniS / z.s);
        z.s = yeniS;
        if (z.s <= 1.001) {
            z.s = 1;
            z.x = 0;
            z.y = 0;
        }
        sinirlariUygula();
        zoomCiz();
    }

    function zoomSifirla() {
        z.s = 1;
        z.x = 0;
        z.y = 0;
        zoomCiz();
    }

    function yerelNokta(clientX, clientY) {
        var r = tuval.getBoundingClientRect();
        return { x: clientX - r.left, y: clientY - r.top };
    }

    function dokunusMerkezi(t1, t2) {
        return yerelNokta((t1.clientX + t2.clientX) / 2, (t1.clientY + t2.clientY) / 2);
    }

    function mesafe(t1, t2) {
        return Math.hypot(t1.clientX - t2.clientX, t1.clientY - t2.clientY) || 1;
    }

    function tuket(e) {
        if (e.cancelable) e.preventDefault();
        e.stopPropagation();
    }

    var jest = null;
    var sonDokunus = { t: 0, x: 0, y: 0 };

    function cimdikBaslat(e) {
        var t1 = e.touches[0];
        var t2 = e.touches[1];
        var merkez = dokunusMerkezi(t1, t2);
        jest = {
            tur: 'cimdik',
            mesafe: mesafe(t1, t2),
            s: z.s,
            icerik: { x: (merkez.x - z.x) / z.s, y: (merkez.y - z.y) / z.s }
        };
    }

    function kaydirBaslat(clientX, clientY) {
        jest = { tur: 'kaydir', bx: clientX, by: clientY, x: z.x, y: z.y };
    }

    tuval.addEventListener('touchstart', function (e) {
        if (e.touches.length === 1 && (rozetMi(e) || kitapKalemi())) return;
        if (e.touches.length >= 2) {
            if (kitapCiziliyor()) window.EKitapCizim.kitapIptal();
            cimdikBaslat(e);
            tuket(e);
            return;
        }
        var t = e.touches[0];
        var simdi = Date.now();
        var ciftDokunus = simdi - sonDokunus.t < 320 &&
            Math.hypot(t.clientX - sonDokunus.x, t.clientY - sonDokunus.y) < 40;
        sonDokunus = { t: ciftDokunus ? 0 : simdi, x: t.clientX, y: t.clientY };
        if (ciftDokunus) {
            var p = yerelNokta(t.clientX, t.clientY);
            if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
            tuket(e);
            return;
        }
        if (z.s > 1.001) {
            kaydirBaslat(t.clientX, t.clientY);
            tuket(e);
        }
    }, { capture: true, passive: false });

    tuval.addEventListener('touchmove', function (e) {
        if (!jest) {
            if (z.s > 1.001) tuket(e);
            return;
        }
        if (jest.tur === 'cimdik' && e.touches.length >= 2) {
            var t1 = e.touches[0];
            var t2 = e.touches[1];
            var yeniS = sinirla(jest.s * mesafe(t1, t2) / jest.mesafe, MIN_ZOOM, MAX_ZOOM);
            var merkez = dokunusMerkezi(t1, t2);
            z.s = yeniS;
            z.x = merkez.x - jest.icerik.x * yeniS;
            z.y = merkez.y - jest.icerik.y * yeniS;
            if (z.s <= 1.001) {
                z.s = 1;
            }
            sinirlariUygula();
            zoomCiz();
        } else if (jest.tur === 'kaydir' && e.touches.length === 1) {
            z.x = jest.x + (e.touches[0].clientX - jest.bx);
            z.y = jest.y + (e.touches[0].clientY - jest.by);
            sinirlariUygula();
            zoomCiz();
        }
        tuket(e);
    }, { capture: true, passive: false });

    function dokunusBitti(e) {
        if (!jest) return;
        if (e.touches.length === 1 && z.s > 1.001) {
            kaydirBaslat(e.touches[0].clientX, e.touches[0].clientY);
        } else if (e.touches.length === 0) {
            jest = null;
            if (z.s <= 1.001) zoomSifirla();
        }
        tuket(e);
    }
    tuval.addEventListener('touchend', dokunusBitti, { capture: true, passive: false });
    tuval.addEventListener('touchcancel', dokunusBitti, { capture: true, passive: false });

    // Fare / kalem: yakınlaştırılmışken sürükleyerek kaydırma
    tuval.addEventListener('mousedown', function (e) {
        if (rozetMi(e) || kitapKalemi()) return;
        if (z.s > 1.001 && e.button === 0) {
            kaydirBaslat(e.clientX, e.clientY);
            tuket(e);
        }
    }, true);
    window.addEventListener('mousemove', function (e) {
        if (jest && jest.tur === 'kaydir') {
            z.x = jest.x + (e.clientX - jest.bx);
            z.y = jest.y + (e.clientY - jest.by);
            sinirlariUygula();
            zoomCiz();
            tuket(e);
        }
    }, true);
    window.addEventListener('mouseup', function (e) {
        if (jest && jest.tur === 'kaydir') {
            jest = null;
            tuket(e);
        }
    }, true);
    tuval.addEventListener('dblclick', function (e) {
        if (rozetMi(e) || kitapKalemi()) return;
        var p = yerelNokta(e.clientX, e.clientY);
        if (z.s > 1.001) zoomSifirla(); else zoomAyarla(2.5, p.x, p.y);
        tuket(e);
    }, true);
    tuval.addEventListener('wheel', function (e) {
        if (window.EKitapSoru && window.EKitapSoru.acikMi()) return;
        var p = yerelNokta(e.clientX, e.clientY);
        zoomAyarla(z.s * (e.deltaY < 0 ? 1.15 : 1 / 1.15), p.x, p.y);
        if (e.cancelable) e.preventDefault();
    }, { passive: false });

    // —— Tam ekran ————————————————————————————————————————————————————————
    function tamEkrandaMi() {
        return !!(document.fullscreenElement || document.webkitFullscreenElement);
    }

    function tamEkranDegistir() {
        var kok = document.documentElement;
        if (tamEkrandaMi()) {
            (document.exitFullscreen || document.webkitExitFullscreen).call(document);
        } else if (kok.requestFullscreen) {
            kok.requestFullscreen().catch(function () { /* izin verilmedi */ });
        } else if (kok.webkitRequestFullscreen) {
            kok.webkitRequestFullscreen();
        }
    }

    function tamEkranDugmesi() {
        var tam = tamEkrandaMi();
        okuyucu.classList.toggle('ek-tam-ekran', tam);
        tamEkranBtn.setAttribute('aria-label', tam ? 'Tam ekrandan çık' : 'Tam ekran');
        tamEkranBtn.title = tam ? 'Tam ekrandan çık (F)' : 'Tam ekran (F)';
    }

    if (!(document.documentElement.requestFullscreen || document.documentElement.webkitRequestFullscreen)) {
        tamEkranBtn.hidden = true;
    }

    // —— Olaylar ——————————————————————————————————————————————————————————
    document.getElementById('sonrakiSayfa').addEventListener('click', sonraki);
    document.getElementById('oncekiSayfa').addEventListener('click', onceki);
    document.getElementById('zoomCok').addEventListener('click', function () { zoomAyarla(z.s * ADIM); });
    document.getElementById('zoomAz').addEventListener('click', function () { zoomAyarla(z.s / ADIM); });
    zoomOran.addEventListener('click', zoomSifirla);
    tamEkranBtn.addEventListener('click', tamEkranDegistir);
    document.getElementById('sayfaGit').addEventListener('submit', function (e) {
        e.preventDefault();
        sayfayaGit(parseInt(sayfaNo.value, 10) || 1);
        sayfaNo.blur();
    });
    sekmeler.forEach(function (btn, i) {
        btn.addEventListener('click', function () {
            if (kitapCiziliyor()) return;
            if (i !== aktif) kur(i, sonSayfaOku(i));
        });
    });

    document.addEventListener('keydown', function (e) {
        if (e.target && (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA')) return;
        var tus = e.key;
        if (window.EKitapSoru && window.EKitapSoru.acikMi()) {
            if (tus === 'f' || tus === 'F') tamEkranDegistir();
            return;
        }
        if (tus === 'ArrowRight' || tus === 'PageDown' || tus === ' ') { sonraki(); e.preventDefault(); }
        else if (tus === 'ArrowLeft' || tus === 'PageUp') { onceki(); e.preventDefault(); }
        else if (tus === '+' || tus === '=') { zoomAyarla(z.s * ADIM); }
        else if (tus === '-') { zoomAyarla(z.s / ADIM); }
        else if (tus === '0') { zoomSifirla(); }
        else if (tus === 'f' || tus === 'F') { tamEkranDegistir(); }
        else if (tus === 'Home') { sayfayaGit(1); }
        else if (tus === 'End') { sayfayaGit(sayfaSayisi()); }
    });

    var yenidenKurZamanlayici = null;
    function boyutDegisti() {
        clearTimeout(yenidenKurZamanlayici);
        yenidenKurZamanlayici = setTimeout(function () {
            kur(aktif, mevcutSayfa());
        }, 180);
    }
    window.addEventListener('resize', boyutDegisti);
    document.addEventListener('fullscreenchange', function () { tamEkranDugmesi(); boyutDegisti(); });
    document.addEventListener('webkitfullscreenchange', function () { tamEkranDugmesi(); boyutDegisti(); });

    var ipucu = document.getElementById('ipucu');
    setTimeout(function () { if (ipucu) ipucu.classList.add('ek-gizle'); }, 6000);

    kur(0, sonSayfaOku(0));
})();
