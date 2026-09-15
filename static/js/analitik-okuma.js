(function () {
    "use strict";

    function paintStars(root, value) {
        var n = parseInt(value, 10);
        if (isNaN(n) || n < 1) n = 0;
        if (n > 10) n = 10;
        root.querySelectorAll("[data-star]").forEach(function (btn) {
            var v = parseInt(btn.getAttribute("data-star"), 10);
            btn.classList.toggle("is-on", v <= n && n > 0);
        });
        var score = root.querySelector("[data-ao-score]");
        if (score) score.textContent = n ? n + "/10" : "—/10";
        var row = root.closest("[data-ao-row]") || root;
        var hidden = row.querySelector("[data-ao-kavram]");
        if (hidden) hidden.value = n ? String(n) : "";
    }

    function setAbsent(row, absent) {
        row.classList.toggle("is-absent", absent);
        var puan = row.querySelector("[data-ao-puan]");
        var note = row.querySelector("[data-ao-note]");
        var stars = row.querySelector("[data-ao-stars]");
        if (puan) {
            puan.disabled = absent;
            if (absent) puan.value = "";
        }
        if (note) {
            note.disabled = absent;
            if (absent) note.value = "Derse katılmadı.";
        }
        if (stars) {
            stars.setAttribute("aria-disabled", absent ? "true" : "false");
            if (absent) paintStars(stars, 0);
        }
    }

    function initForm(form) {
        form.querySelectorAll("[data-ao-row]").forEach(function (row) {
            var stars = row.querySelector("[data-ao-stars]");
            var hidden = row.querySelector("[data-ao-kavram]");
            if (stars) paintStars(stars, hidden ? hidden.value : "");
            var absent = row.querySelector("[data-ao-absent]");
            if (absent) setAbsent(row, absent.checked);
        });

        form.addEventListener("click", function (ev) {
            var star = ev.target.closest("[data-star]");
            if (!star) return;
            var wrap = star.closest("[data-ao-stars]");
            var row = star.closest("[data-ao-row]");
            if (!wrap || !row) return;
            if (row.classList.contains("is-absent")) return;
            ev.preventDefault();
            paintStars(wrap, star.getAttribute("data-star"));
        });

        form.addEventListener("change", function (ev) {
            var box = ev.target.closest("[data-ao-absent]");
            if (!box) return;
            var row = box.closest("[data-ao-row]");
            if (!row) return;
            setAbsent(row, box.checked);
        });

        form.addEventListener("keydown", function (ev) {
            if (ev.key !== "Enter") return;
            var input = ev.target.closest("input");
            if (!input) return;
            ev.preventDefault();
            var inputs = Array.prototype.slice.call(
                form.querySelectorAll("input:not([type=hidden]):not([type=radio]):not([disabled])")
            );
            var i = inputs.indexOf(input);
            if (i >= 0 && i < inputs.length - 1) inputs[i + 1].focus();
        });

        var dirty = false;
        form.addEventListener("input", function () { dirty = true; });
        form.addEventListener("change", function () { dirty = true; });
        form.addEventListener("submit", function () { dirty = false; });
        window.addEventListener("beforeunload", function (ev) {
            if (!dirty) return;
            ev.preventDefault();
            ev.returnValue = "";
        });
    }

    document.querySelectorAll("[data-ao-form]").forEach(initForm);
})();
