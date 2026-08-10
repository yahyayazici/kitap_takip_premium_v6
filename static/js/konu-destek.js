(function () {
    "use strict";

    var cfg = window.KD_VIDEO;
    if (!cfg || !cfg.heartbeatUrl) return;

    var sureSn = 0;
    var timer = null;

    function gonder(tamamlandi) {
        fetch(cfg.heartbeatUrl, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": cfg.csrfToken
            },
            body: JSON.stringify({
                izleme_id: cfg.izlemeId,
                sure_sn: sureSn,
                tamamlandi: !!tamamlandi
            }),
            credentials: "same-origin"
        }).catch(function () {});
    }

    timer = setInterval(function () {
        sureSn += 15;
        gonder(false);
    }, 15000);

    var doneBtn = document.getElementById("kd-video-done");
    if (doneBtn) {
        doneBtn.addEventListener("click", function () {
            clearInterval(timer);
            gonder(true);
            window.location.href = cfg.detayUrl;
        });
    }

    window.addEventListener("beforeunload", function () {
        gonder(false);
    });
})();
