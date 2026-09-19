(function () {
    "use strict";

    if ("scrollRestoration" in history) {
        try { history.scrollRestoration = "manual"; } catch (e) {}
    }

    function heroKapaliMi() {
        var hero = document.querySelector(".dash-hero");
        if (!hero) return false;
        // Sayfa en üstte değil ama hero da (kaynatan sticky menü altında) hâlâ
        // görünüm alanının başındaysa: PWA arka plandan dönerken veya
        // bfcache'ten geri gelirken tarayıcının eski scroll konumunu
        // sayfaya uygulaması, hero'nun üst kısmını (logo/başlık) sabit
        // menünün arkasında bırakıyor. Derin scroll yapılmış başka
        // sayfalara dokunmamak için sadece küçük ofsetlerde düzeltiyoruz.
        return window.scrollY > 0 && window.scrollY < hero.offsetHeight + 160;
    }

    function enUsteAl() {
        if (heroKapaliMi()) {
            window.scrollTo(0, 0);
        }
    }

    window.addEventListener("pageshow", enUsteAl);
    document.addEventListener("visibilitychange", function () {
        if (document.visibilityState === "visible") enUsteAl();
    });
})();
