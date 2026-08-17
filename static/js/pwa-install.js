(function () {
    "use strict";

    var isStandalone =
        window.matchMedia("(display-mode: standalone)").matches ||
        window.navigator.standalone === true;

    /* iOS PWA: bfcache'ten dönünce oturum varsa panele, yoksa girişe */
    if (isStandalone) {
        window.addEventListener("pageshow", function (event) {
            if (event.persisted) {
                window.location.replace("/pwa/baslat/");
            }
        });
    }

    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/sw.js?v=11", { scope: "/" }).catch(function () {
            /* Sessiz — PWA olmadan da ana ekrana eklenebilir (iOS) */
        });
    });
})();
