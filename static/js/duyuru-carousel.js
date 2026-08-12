(function () {
    const shell = document.querySelector("[data-duyuru-carousel]");
    if (!shell) return;

    const mediaSlides = [...shell.querySelectorAll("[data-duyuru-media-slide]")];
    const copySlides = [...shell.querySelectorAll("[data-duyuru-copy-slide]")];
    const dots = [...shell.querySelectorAll("[data-duyuru-dot]")];
    const prevBtn = shell.querySelector("[data-duyuru-prev]");
    const nextBtn = shell.querySelector("[data-duyuru-next]");

    const count = mediaSlides.length;
    if (count === 0) return;

    let index = 0;
    let timer = null;

    function pauseMedia(slide) {
        slide?.querySelector("video")?.pause();
    }

    function setActive(nextIndex) {
        index = (nextIndex + count) % count;

        mediaSlides.forEach((slide, i) => {
            if (slide.classList.contains("is-active")) pauseMedia(slide);
            slide.classList.toggle("is-active", i === index);
        });
        copySlides.forEach((slide, i) => slide.classList.toggle("is-active", i === index));
        dots.forEach((dot, i) => dot.classList.toggle("is-active", i === index));
    }

    function next() {
        setActive(index + 1);
    }

    function prev() {
        setActive(index - 1);
    }

    function restartAuto() {
        if (timer) window.clearInterval(timer);
        if (count < 2) return;
        timer = window.setInterval(next, 6000);
    }

    prevBtn?.addEventListener("click", () => {
        prev();
        restartAuto();
    });

    nextBtn?.addEventListener("click", () => {
        next();
        restartAuto();
    });

    dots.forEach((dot, dotIndex) => {
        dot.addEventListener("click", () => {
            setActive(dotIndex);
            restartAuto();
        });
    });

    restartAuto();

    shell.querySelectorAll("[data-duyuru-photo]").forEach((img) => {
        const showFallback = () => {
            const inner = img.closest("[data-duyuru-media-inner]");
            if (!inner || inner.classList.contains("is-photo-missing")) return;
            inner.classList.add("is-photo-missing");
            img.remove();
            const fallback = inner.querySelector("[data-duyuru-photo-fallback]");
            if (fallback) fallback.hidden = false;
        };
        img.addEventListener("error", showFallback);
        if (img.complete && img.naturalWidth === 0) showFallback();
    });
})();
