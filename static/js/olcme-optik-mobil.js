(function () {
    "use strict";

    var form = document.getElementById("olcme-mobil-form");
    if (!form) return;

    var sections = Array.prototype.slice.call(form.querySelectorAll(".olcme-mobil-soru"));
    var dots = Array.prototype.slice.call(document.querySelectorAll(".olcme-mobil-dot"));
    var counter = document.getElementById("olcme-mobil-counter");
    var answeredEl = document.getElementById("olcme-mobil-answered");
    var prevBtn = document.getElementById("olcme-mobil-prev");
    var nextBtn = document.getElementById("olcme-mobil-next");
    var current = 0;

    function updateAnswered() {
        var count = 0;
        sections.forEach(function (sec) {
            var hidden = sec.querySelector('input[type="hidden"]');
            if (hidden && hidden.value && hidden.value !== "BOS") count += 1;
        });
        if (answeredEl) answeredEl.textContent = count + " cevaplı";
    }

    function show(index) {
        if (index < 0 || index >= sections.length) return;
        current = index;
        sections.forEach(function (sec, i) {
            var active = i === index;
            sec.classList.toggle("is-active", active);
            sec.hidden = !active;
        });
        dots.forEach(function (dot, i) {
            dot.classList.toggle("is-current", i === index);
            var hidden = sections[i].querySelector('input[type="hidden"]');
            dot.classList.toggle("is-filled", hidden && hidden.value && hidden.value !== "BOS");
        });
        if (counter) counter.textContent = "Soru " + (index + 1) + " / " + sections.length;
        if (prevBtn) prevBtn.disabled = index === 0;
        if (nextBtn) nextBtn.disabled = index >= sections.length - 1;
    }

    sections.forEach(function (sec) {
        sec.querySelectorAll(".olcme-cevap-btn").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var secim = btn.getAttribute("data-secim");
                var hidden = sec.querySelector('input[type="hidden"]');
                if (hidden) hidden.value = secim;
                sec.querySelectorAll(".olcme-cevap-btn").forEach(function (b) {
                    b.classList.toggle("is-selected", b === btn);
                });
                updateAnswered();
                var idx = parseInt(sec.getAttribute("data-index"), 10);
                if (idx < sections.length - 1) show(idx + 1);
            });
        });
    });

    dots.forEach(function (dot) {
        dot.addEventListener("click", function () {
            show(parseInt(dot.getAttribute("data-index"), 10));
        });
    });

    if (prevBtn) prevBtn.addEventListener("click", function () { show(current - 1); });
    if (nextBtn) nextBtn.addEventListener("click", function () { show(current + 1); });

    show(0);
    updateAnswered();
})();
