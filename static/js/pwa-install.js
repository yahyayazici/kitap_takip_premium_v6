(function () {
    "use strict";

    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/sw.js?v=13", { scope: "/" }).catch(function () {
            /* Sessiz — PWA olmadan da ana ekrana eklenebilir (iOS) */
        });
    });
})();
