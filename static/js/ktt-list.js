(function () {
    "use strict";

    var modal = document.getElementById("ktt-form-modal");
    if (!modal) return;

    var openBtn = document.getElementById("ktt-open-form");
    var body = document.body;

    function openModal() {
        modal.hidden = false;
        body.classList.add("ktt-modal-open");
        if (openBtn) openBtn.setAttribute("aria-expanded", "true");
        var first = modal.querySelector("input, select, textarea");
        if (first) {
            setTimeout(function () {
                first.focus();
            }, 80);
        }
    }

    function closeModal() {
        modal.hidden = true;
        body.classList.remove("ktt-modal-open");
        if (openBtn) {
            openBtn.setAttribute("aria-expanded", "false");
            openBtn.focus();
        }
    }

    if (openBtn) {
        openBtn.addEventListener("click", openModal);
    }

    document.querySelectorAll("[data-ktt-open-form]").forEach(function (el) {
        el.addEventListener("click", openModal);
    });

    modal.querySelectorAll("[data-ktt-close]").forEach(function (el) {
        el.addEventListener("click", closeModal);
    });

    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape" && !modal.hidden) {
            closeModal();
        }
    });

    if (document.documentElement.dataset.kttFormOpen === "1") {
        openModal();
    }
})();
