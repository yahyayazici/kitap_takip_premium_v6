(function () {
    "use strict";

    var panel = document.querySelector("[data-pid-panel]");
    if (!panel) return;

    var beklenenTarih = document.getElementById("pid-beklenen-tarih");
    var beklenenSaat = document.getElementById("pid-beklenen-saat");

    function pad(n) {
        return String(n).padStart(2, "0");
    }

    function simdiSaat() {
        var d = new Date();
        return pad(d.getHours()) + ":" + pad(d.getMinutes());
    }

    function parseDateTime(tarihStr, saatStr) {
        if (!tarihStr || !saatStr) return null;
        var p = tarihStr.split("-").map(Number);
        var s = saatStr.split(":").map(Number);
        return new Date(p[0], p[1] - 1, p[2], s[0], s[1] || 0, 0);
    }

    function gecikmeHesapla(girisSaat) {
        if (!beklenenTarih || !beklenenSaat || !girisSaat) return 0;
        var beklenen = parseDateTime(beklenenTarih.value, beklenenSaat.value);
        var gercek = parseDateTime(beklenenTarih.value, girisSaat);
        if (!beklenen || !gercek) return 0;
        var dk = Math.floor((gercek - beklenen) / 60000);
        return Math.max(dk, 0);
    }

    function satirGuncelle(row) {
        var durum = row.querySelector("[data-pid-durum]");
        var saatInput = row.querySelector("[data-pid-giris-saat]");
        var placeholder = row.querySelector("[data-pid-giris-placeholder]");
        var gecikmeEl = row.querySelector("[data-pid-gecikme]");

        if (!durum) return;

        var gecGeldi = durum.value === "gec_geldi";

        if (saatInput) {
            saatInput.hidden = !gecGeldi;
            saatInput.disabled = !gecGeldi;
        }
        if (placeholder) placeholder.hidden = gecGeldi;

        if (gecGeldi && saatInput && saatInput.value) {
            if (gecikmeEl) gecikmeEl.textContent = String(gecikmeHesapla(saatInput.value));
        } else {
            if (gecikmeEl) gecikmeEl.textContent = "—";
        }
    }

    function gecGeldiIsaretle(row) {
        var saatInput = row.querySelector("[data-pid-giris-saat]");
        if (saatInput) {
            saatInput.value = simdiSaat();
            saatInput.hidden = false;
            saatInput.disabled = false;
        }
        satirGuncelle(row);
    }

    panel.querySelectorAll("[data-pid-row]").forEach(function (row) {
        var durum = row.querySelector("[data-pid-durum]");
        var saatInput = row.querySelector("[data-pid-giris-saat]");

        if (durum) {
            durum.addEventListener("change", function () {
                if (durum.value === "gec_geldi") {
                    gecGeldiIsaretle(row);
                } else {
                    if (saatInput) {
                        saatInput.value = "";
                        saatInput.hidden = true;
                        saatInput.disabled = true;
                    }
                    satirGuncelle(row);
                }
            });
        }

        if (saatInput) {
            saatInput.addEventListener("change", function () { satirGuncelle(row); });
            saatInput.addEventListener("input", function () { satirGuncelle(row); });
        }

        satirGuncelle(row);
    });

    [beklenenTarih, beklenenSaat].forEach(function (inp) {
        if (inp) {
            inp.addEventListener("change", function () {
                panel.querySelectorAll("[data-pid-row]").forEach(satirGuncelle);
            });
        }
    });
})();
