(function () {
    if (!("serviceWorker" in navigator)) {
        return;
    }

    window.addEventListener("load", function () {
        navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(function () {
            /* Sessiz — PWA olmadan da ana ekrana eklenebilir (iOS) */
        });
    });
})();
