(function () {
    "use strict";

    function token() {
        var input = document.querySelector(".nh-metin input[name=csrfmiddlewaretoken]");
        if (input && input.value) {
            return input.value;
        }
        var match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
        return match ? decodeURIComponent(match[1]) : "";
    }

    function sayaclariGuncelle() {
        var kutular = document.querySelectorAll("[data-nehari-odev]");
        var yapildi = 0;
        kutular.forEach(function (kutu) {
            if (kutu.checked) {
                yapildi += 1;
            }
        });
        var toplam = kutular.length;
        var yapildiEl = document.querySelector("[data-nh-yapildi]");
        var toplamEl = document.querySelector("[data-nh-toplam]");
        var bekleyenEl = document.querySelector("[data-nh-bekleyen]");
        var bar = document.querySelector(".nh-bar");
        if (yapildiEl) {
            yapildiEl.textContent = String(yapildi);
        }
        if (toplamEl) {
            toplamEl.textContent = String(toplam);
        }
        if (bekleyenEl) {
            bekleyenEl.textContent = (toplam - yapildi) + " bekliyor";
        }
        if (bar) {
            var oran = toplam ? Math.round(yapildi * 100 / toplam) : 0;
            var dolu = bar.querySelector("span");
            if (dolu) {
                dolu.style.width = oran + "%";
            }
            bar.setAttribute("aria-valuenow", String(oran));
        }
    }

    document.addEventListener("change", function (event) {
        var kutu = event.target;
        if (!kutu || !kutu.matches || !kutu.matches("[data-nehari-odev]")) {
            return;
        }
        var satir = kutu.closest("[data-nehari-satir]");
        var etiket = satir ? satir.querySelector("[data-nehari-etiket]") : null;
        var onceki = !kutu.checked;
        var veri = new FormData();
        veri.append("talebe_id", kutu.value);
        veri.append("tarih", kutu.getAttribute("data-tarih") || "");
        veri.append("yapildi", kutu.checked ? "1" : "0");
        veri.append("csrfmiddlewaretoken", token());
        kutu.disabled = true;
        fetch(kutu.getAttribute("data-url"), {
            method: "POST",
            body: veri,
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
                "X-CSRFToken": token(),
            },
        }).then(function (yanit) {
            return yanit.json().then(function (govde) {
                if (!yanit.ok || !govde.ok) {
                    throw new Error(govde.mesaj || "Kaydedilemedi");
                }
                return govde;
            });
        }).then(function (govde) {
            kutu.checked = !!govde.yapildi;
            if (satir) {
                satir.classList.toggle("is-done", kutu.checked);
            }
            if (etiket) {
                etiket.textContent = govde.etiket;
            }
            sayaclariGuncelle();
        }).catch(function () {
            kutu.checked = onceki;
            if (satir) {
                satir.classList.toggle("is-done", onceki);
            }
            if (etiket) {
                etiket.textContent = onceki ? "Yapıldı" : "Yapılmadı";
            }
        }).finally(function () {
            kutu.disabled = false;
        });
    });
})();
