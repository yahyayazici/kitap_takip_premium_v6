/* Sınav başvuru formu — zorunlu "Hatırlatmaları açın" adımı.
 * Bildirimi destekleyen tarayıcıda (Android, bilgisayar) bildirim izni alınır;
 * desteklemeyen yerde (iPhone Safari, uygulama içi tarayıcılar) sınav takvime eklenir. */
(function () {
    "use strict";

    var kutu = document.getElementById("sb-hatirlatma");
    var form = document.getElementById("sb-basvuru-form");
    if (!kutu || !form) {
        return;
    }

    var vapidKey = kutu.getAttribute("data-vapid-key") || "";
    var pushBtn = kutu.querySelector("[data-hat-push]");
    var takvimBtn = kutu.querySelector("[data-hat-takvim]");
    var notEl = kutu.querySelector("[data-hat-not]");
    var okEl = kutu.querySelector("[data-hat-ok]");
    var hataEl = kutu.querySelector("[data-hat-hata]");
    var turu = document.getElementById("sb-hatirlatma-turu");
    var abonelikEl = document.getElementById("sb-bildirim-abonelik");

    var ua = navigator.userAgent || "";
    var iosCihaz = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var uygulamaIci = /Instagram|FBAN|FBAV|FB_IAB|Line\//.test(ua);
    var pushDestek = !!vapidKey && window.isSecureContext &&
        "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

    function goster(el, metin) {
        if (!el) return;
        el.textContent = metin;
        el.hidden = !metin;
    }

    function tamam(metin) {
        if (pushBtn) pushBtn.hidden = true;
        if (takvimBtn) takvimBtn.hidden = true;
        goster(notEl, "");
        goster(okEl, metin);
        kutu.classList.add("sb-hatirlatma--tamam");
        kutu.classList.remove("sb-hatirlatma--hata");
        if (hataEl) hataEl.hidden = true;
    }

    function takvimGoster(not) {
        if (pushBtn) pushBtn.hidden = true;
        if (takvimBtn) {
            takvimBtn.hidden = false;
        }
        goster(notEl, not || "");
    }

    function base64ToUint8(b64) {
        var pad = "=".repeat((4 - (b64.length % 4)) % 4);
        var raw = window.atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
        var out = new Uint8Array(raw.length);
        for (var i = 0; i < raw.length; i++) {
            out[i] = raw.charCodeAt(i);
        }
        return out;
    }

    function abonelikAl() {
        return navigator.serviceWorker.register("/sw.js?v=14", { scope: "/" })
            .then(function () { return navigator.serviceWorker.ready; })
            .then(function (kayit) {
                return kayit.pushManager.getSubscription().then(function (mevcut) {
                    return mevcut || kayit.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: base64ToUint8(vapidKey),
                    });
                });
            });
    }

    function pushTamamla(abonelik) {
        abonelikEl.value = JSON.stringify(abonelik.toJSON());
        turu.value = "push";
        tamam("Bildirimler açık. Hatırlatmalar bu cihaza gelecek.");
    }

    // Sayfa hata ile geri döndüyse önceki seçim korunur.
    if (turu.value === "push" && abonelikEl.value) {
        tamam("Bildirimler açık. Hatırlatmalar bu cihaza gelecek.");
    } else if (turu.value === "takvim") {
        tamam("Sınav takviminize eklendi.");
    } else if (pushDestek && Notification.permission !== "denied") {
        pushBtn.hidden = false;
        if (Notification.permission === "granted") {
            abonelikAl().then(pushTamamla).catch(function () {});
        }
    } else if (pushDestek) {
        takvimGoster("Bu tarayıcıda bildirim izni kapalı. Hatırlatmalar için sınavı takviminize ekleyin.");
    } else if (uygulamaIci) {
        takvimGoster("Bildirim için sayfayı Chrome'da açabilir ya da sınavı takviminize ekleyebilirsiniz.");
    } else if (iosCihaz) {
        takvimGoster("iPhone'da hatırlatmalar telefonunuzun takvimine eklenir. Açılan ekranda “Ekle”ye dokunun.");
    } else {
        takvimGoster("Hatırlatmalar için sınavı takviminize ekleyin.");
    }

    if (pushBtn) {
        pushBtn.addEventListener("click", function () {
            pushBtn.disabled = true;
            Notification.requestPermission()
                .then(function (izin) {
                    if (izin !== "granted") {
                        takvimGoster("Bildirim izni verilmedi. Hatırlatmalar için sınavı takviminize ekleyin.");
                        return;
                    }
                    return abonelikAl().then(pushTamamla);
                })
                .catch(function () {
                    takvimGoster("Bildirim açılamadı. Hatırlatmalar için sınavı takviminize ekleyin.");
                })
                .then(function () {
                    pushBtn.disabled = false;
                });
        });
    }

    if (takvimBtn) {
        takvimBtn.addEventListener("click", function () {
            turu.value = "takvim";
            abonelikEl.value = "";
            // Dosya açıldıktan sonra kullanıcı forma geri döner.
            window.setTimeout(function () {
                tamam("Sınav takviminize eklendi. Açılan ekranda “Ekle”ye dokunmayı unutmayın.");
            }, 300);
        });
    }

    form.addEventListener("submit", function (event) {
        if (turu.value) {
            return;
        }
        event.preventDefault();
        event.stopImmediatePropagation();
        kutu.classList.add("sb-hatirlatma--hata");
        if (hataEl) hataEl.hidden = false;
        kutu.scrollIntoView({ behavior: "smooth", block: "center" });
    }, true);
})();
