(function () {
    "use strict";

    var isStandalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    /* iOS PWA: önbellekten POST sayfası geri gelince CSRF 403 olmasın */
    if (isStandalone) {
        window.addEventListener("pageshow", function (event) {
            if (event.persisted) {
                window.location.replace("/giris/?source=pwa");
            }
        });
    }

    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
            /* Sessiz — PWA olmadan da ana ekrana eklenebilir (iOS) */
        });
    });
})();
