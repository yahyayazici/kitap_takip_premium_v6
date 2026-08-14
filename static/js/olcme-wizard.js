(function () {
    "use strict";

    var root = document.querySelector(".olcme-wizard-step3");
    if (!root) return;

    var list = root.querySelector("#olcme-ders-bloklari");
    var tpl = root.querySelector("#olcme-ders-blok-tpl");
    var toplamEl = root.querySelector("[data-olcme-toplam]");
    var hedef = parseInt(root.dataset.hedefSoru || "0", 10);
    var tur = root.dataset.sinavTuru || "";

    function satirEkle(data) {
        if (!tpl || !list) return;
        var node = tpl.content.cloneNode(true);
        var row = node.querySelector(".olcme-ders-blok-row");
        if (data) {
            if (data.ders_id) row.querySelector('[name="ders_id"]').value = data.ders_id;
            if (data.bolum) row.querySelector('[name="bolum"]').value = data.bolum;
            if (data.soru_sayisi) row.querySelector('[name="soru_sayisi_blok"]').value = data.soru_sayisi;
            if (data.katsayi) row.querySelector('[name="katsayi"]').value = data.katsayi;
        }
        list.appendChild(node);
        guncelleToplam();
    }

    function guncelleToplam() {
        if (!toplamEl) return;
        var toplam = 0;
        list.querySelectorAll('[name="soru_sayisi_blok"]').forEach(function (inp) {
            toplam += parseInt(inp.value || "0", 10) || 0;
        });
        toplamEl.textContent = String(toplam);
        toplamEl.classList.toggle("olcme-error", hedef > 0 && toplam !== hedef);
    }

    root.querySelector("[data-olcme-add-blok]")?.addEventListener("click", function () {
        satirEkle({});
    });

    root.addEventListener("click", function (e) {
        if (e.target.matches("[data-olcme-del-blok]")) {
            var row = e.target.closest(".olcme-ders-blok-row");
            if (row && list.children.length > 1) {
                row.remove();
                guncelleToplam();
            }
        }
    });

    root.addEventListener("input", function (e) {
        if (e.target.matches('[name="soru_sayisi_blok"]')) guncelleToplam();
    });

    function preset(tip) {
        while (list.firstChild) list.removeChild(list.firstChild);
        if (tip === "lgs90") {
            [
                { bolum: "sozel", soru_sayisi: 20 },
                { bolum: "sozel", soru_sayisi: 10 },
                { bolum: "sayisal", soru_sayisi: 40 },
                { bolum: "sayisal", soru_sayisi: 20 },
            ].forEach(satirEkle);
        } else if (tip === "brans40") {
            satirEkle({ bolum: "genel", soru_sayisi: 40 });
        } else if (tip === "tek") {
            satirEkle({ bolum: "genel", soru_sayisi: hedef || 20 });
        }
    }

    root.querySelectorAll("[data-olcme-preset]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            preset(btn.getAttribute("data-olcme-preset"));
        });
    });

    if (!list.children.length) {
        satirEkle({ bolum: tur === "sozel_sayisal" ? "sozel" : "genel", soru_sayisi: hedef });
    } else {
        guncelleToplam();
    }
})();

(function () {
    "use strict";
    var step2 = document.querySelector(".olcme-wizard-step2");
    if (!step2) return;
    var soruInput = step2.querySelector('[name="soru_sayisi"]');
    step2.querySelectorAll("[data-olcme-soru-preset]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            if (soruInput) soruInput.value = btn.getAttribute("data-olcme-soru-preset");
        });
    });
})();
