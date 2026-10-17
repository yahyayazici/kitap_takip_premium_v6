/* Sınav başvurusu teşekkür sayfası — uygulama bildirimi izni ve aboneliği */
(function () {
    "use strict";

    var root = document.querySelector("[data-sbb]");
    if (!root) {
        return;
    }

    var vapidKey = root.getAttribute("data-vapid-key") || "";
    var aboneUrl = root.getAttribute("data-abone-url") || "";
    var csrf = root.getAttribute("data-csrf") || "";
    var btn = root.querySelector("[data-sbb-ac]");
    var durum = root.querySelector("[data-sbb-durum]");
    var ios = root.querySelector("[data-sbb-ios]");

    var ua = navigator.userAgent || "";
    var iosCihaz = /iPad|iPhone|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var anaEkranda = window.navigator.standalone === true ||
        (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
    var destek = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

    function goster(metin, basarili) {
        durum.textContent = metin;
        durum.hidden = false;
        durum.classList.toggle("sb-bildirim-durum--ok", !!basarili);
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

    function kaydiGonder(abonelik) {
        return fetch(aboneUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
            body: JSON.stringify(abonelik.toJSON()),
        }).then(function (yanit) {
            if (!yanit.ok) {
                throw new Error("kayit");
            }
        });
    }

    function abone() {
        return navigator.serviceWorker.register("/sw.js?v=14", { scope: "/" })
            .then(function () { return navigator.serviceWorker.ready; })
            .then(function (kayit) {
                return kayit.pushManager.getSubscription().then(function (mevcut) {
                    return mevcut || kayit.pushManager.subscribe({
                        userVisibleOnly: true,
                        applicationServerKey: base64ToUint8(vapidKey),
                    });
                });
            })
            .then(kaydiGonder);
    }

    function acik() {
        btn.hidden = true;
        goster("Bildirimler açık. Hatırlatmalar bu cihaza gelecek.", true);
    }

    if (!destek) {
        btn.hidden = true;
        if (iosCihaz && !anaEkranda) {
            ios.hidden = false;
        } else {
            goster("Bu tarayıcı bildirimleri desteklemiyor. Telefonunuzda Chrome ya da Safari ile açmayı deneyin.");
        }
        return;
    }

    if (Notification.permission === "granted") {
        abone().then(acik).catch(function () {});
    } else if (Notification.permission === "denied") {
        btn.hidden = true;
        goster("Bildirim izni kapalı. Tarayıcı ayarlarından bu site için bildirimlere izin verebilirsiniz.");
    }

    btn.addEventListener("click", function () {
        btn.disabled = true;
        Notification.requestPermission()
            .then(function (izin) {
                if (izin !== "granted") {
                    btn.hidden = true;
                    goster("Bildirim izni verilmedi. İsterseniz tarayıcı ayarlarından açabilirsiniz.");
                    return;
                }
                return abone().then(acik);
            })
            .catch(function () {
                goster("Bildirimler açılamadı. Sayfayı yenileyip tekrar deneyin.");
            })
            .then(function () {
                btn.disabled = false;
            });
    });
})();
