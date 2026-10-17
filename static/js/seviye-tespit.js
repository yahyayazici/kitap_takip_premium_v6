/* Salonlar — satır ekle/çıkar, toplam yer anında hesaplanır. */
(function () {
    "use strict";
    var form = document.getElementById("st-salon-form");
    if (!form) {
        return;
    }
    var liste = document.getElementById("st-salon-satirlar");
    var bilgi = document.getElementById("st-salon-kapasite");

    function hesapla() {
        var kisiEl = form.querySelector("input[name=masa_kisi]:checked");
        var kisi = kisiEl ? parseInt(kisiEl.value, 10) : 1;
        var masa = 0;
        var satirlar = liste.querySelectorAll(".st-salon-satir");
        satirlar.forEach(function (li) {
            masa += parseInt(li.querySelector("input[name=salon_masa]").value, 10) || 0;
        });
        bilgi.textContent = satirlar.length + " salon · " + masa + " masa · " + (masa * kisi) + " kişilik yer";
        liste.querySelectorAll("[data-salon-sil]").forEach(function (b) {
            b.hidden = satirlar.length < 2;
        });
    }

    document.getElementById("st-salon-ekle").addEventListener("click", function () {
        var satirlar = liste.querySelectorAll(".st-salon-satir");
        var son = satirlar[satirlar.length - 1];
        var yeni = son.cloneNode(true);
        var ad = yeni.querySelector("input[name=salon_ad]");
        ad.value = "Salon " + (satirlar.length + 1);
        yeni.querySelector("input[name=salon_masa]").value = son.querySelector("input[name=salon_masa]").value;
        liste.appendChild(yeni);
        ad.focus();
        ad.select();
        hesapla();
    });

    liste.addEventListener("click", function (e) {
        var sil = e.target.closest("[data-salon-sil]");
        if (sil && liste.children.length > 1) {
            sil.closest(".st-salon-satir").remove();
            hesapla();
        }
    });
    form.addEventListener("input", hesapla);
    form.addEventListener("change", hesapla);
    hesapla();
})();

/* Sonuçlar — dosya seçilince yüklenir, karar değişince kaydedilir, seçimle toplu işlem. */
(function () {
    "use strict";

    document.querySelectorAll("[data-otomatik-gonder]").forEach(function (girdi) {
        girdi.addEventListener("change", function () {
            if (!girdi.files.length) {
                return;
            }
            var form = girdi.closest("form");
            form.classList.add("st-yukleniyor");
            form.submit();
        });
    });

    var karneForm = document.getElementById("st-karne-form");
    if (karneForm) {
        var karneDosya = document.getElementById("st-karne-dosya");
        document.querySelectorAll("[data-karne-yukle]").forEach(function (dugme) {
            dugme.addEventListener("click", function () {
                document.getElementById("st-karne-basvuru").value = dugme.getAttribute("data-karne-yukle");
                karneDosya.value = "";
                karneDosya.click();
            });
        });
        karneDosya.addEventListener("change", function () {
            if (karneDosya.files.length) {
                karneForm.submit();
            }
        });
    }

    var form = document.getElementById("st-sonuc-form");
    if (!form) {
        return;
    }
    var eylem = document.getElementById("st-sonuc-eylem");
    var hepsi = document.getElementById("st-sonuc-hepsi");
    var satirlar = Array.prototype.slice.call(form.querySelectorAll(".st-sonuc-sec"));
    var toplu = document.getElementById("st-sonuc-toplu");
    var sayac = document.getElementById("st-sonuc-secili");

    function guncelle() {
        var secili = satirlar.filter(function (el) { return el.checked; }).length;
        toplu.hidden = secili === 0;
        sayac.textContent = String(secili);
        if (hepsi) {
            hepsi.checked = secili > 0 && secili === satirlar.length;
            hepsi.indeterminate = secili > 0 && secili < satirlar.length;
        }
    }
    if (hepsi) {
        hepsi.addEventListener("change", function () {
            satirlar.forEach(function (el) { el.checked = hepsi.checked; });
            guncelle();
        });
    }
    satirlar.forEach(function (el) { el.addEventListener("change", guncelle); });

    document.getElementById("st-sonuc-vazgec").addEventListener("click", function () {
        satirlar.forEach(function (el) { el.checked = false; });
        guncelle();
    });
    form.querySelectorAll("[data-toplu-karar]").forEach(function (dugme) {
        dugme.addEventListener("click", function () {
            eylem.value = "karar_toplu";
            document.getElementById("st-toplu-karar").value = dugme.getAttribute("data-toplu-karar");
            form.submit();
        });
    });
    document.getElementById("st-sonuc-gonder").addEventListener("click", function () {
        if (!window.confirm(sayac.textContent + " öğrencinin sonucu veliye gönderilsin mi? Karnesi olmayanlar atlanır.")) {
            return;
        }
        eylem.value = "sonuc_gonder";
        form.submit();
    });
    form.querySelectorAll("[data-karar]").forEach(function (el) {
        el.addEventListener("change", function () {
            satirlar.forEach(function (s) { s.checked = false; });
            eylem.value = "karar_satir";
            form.submit();
        });
    });
    guncelle();
})();

/* Seviye Tespit — filtreler kendiliğinden uygulanır, seçim yapılınca toplu işlem çubuğu çıkar,
 * satırdaki durum değişince kaydedilir. */
(function () {
    "use strict";

    var filtre = document.getElementById("st-filtre");
    if (filtre) {
        filtre.querySelectorAll("[data-otomatik]").forEach(function (el) {
            el.addEventListener("change", function () {
                filtre.submit();
            });
        });
    }

    var form = document.getElementById("st-liste-form");
    if (!form) {
        return;
    }

    var eylem = document.getElementById("st-eylem");
    var hepsi = document.getElementById("st-hepsi");
    var satirlar = Array.prototype.slice.call(form.querySelectorAll(".st-satir-sec"));
    var toplu = document.getElementById("st-toplu");
    var seciliSayi = document.getElementById("st-secili");
    var topluDurum = document.getElementById("st-toplu-durum");

    function guncelle() {
        var secili = satirlar.filter(function (el) { return el.checked; }).length;
        toplu.hidden = secili === 0;
        seciliSayi.textContent = String(secili);
        if (hepsi) {
            hepsi.checked = secili > 0 && secili === satirlar.length;
            hepsi.indeterminate = secili > 0 && secili < satirlar.length;
        }
    }

    if (hepsi) {
        hepsi.addEventListener("change", function () {
            satirlar.forEach(function (el) { el.checked = hepsi.checked; });
            guncelle();
        });
    }
    satirlar.forEach(function (el) { el.addEventListener("change", guncelle); });

    document.getElementById("st-toplu-vazgec").addEventListener("click", function () {
        satirlar.forEach(function (el) { el.checked = false; });
        guncelle();
    });

    document.getElementById("st-toplu-uygula").addEventListener("click", function () {
        if (!topluDurum.value) {
            topluDurum.focus();
            return;
        }
        var ad = topluDurum.options[topluDurum.selectedIndex].text;
        var secili = seciliSayi.textContent;
        if (!window.confirm(secili + " başvurunun durumu “" + ad + "” olarak değiştirilsin mi?")) {
            return;
        }
        eylem.value = "toplu_durum";
        form.submit();
    });

    form.querySelectorAll("[data-satir-durum]").forEach(function (el) {
        el.addEventListener("change", function () {
            eylem.value = "satir_durumlar";
            form.submit();
        });
    });

    guncelle();
})();
