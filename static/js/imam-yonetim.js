(function () {
    var root = document.querySelector("[data-im-panel]");
    if (!root) return;

    var ay = document.getElementById("id_ay");
    var yil = document.getElementById("id_yil");
    var hidAy = document.getElementById("im-ay");
    var hidYil = document.getElementById("im-yil");

    function goFilter() {
        if (!ay || !yil) return;
        if (hidAy) hidAy.value = ay.value;
        if (hidYil) hidYil.value = yil.value;
        window.location =
            "?yil=" + encodeURIComponent(yil.value) + "&ay=" + encodeURIComponent(ay.value);
    }
    if (ay) ay.addEventListener("change", goFilter);
    if (yil) yil.addEventListener("change", goFilter);

    function openModal(name) {
        var el = root.querySelector('[data-im-modal="' + name + '"]');
        if (el) el.hidden = false;
    }
    function closeModal(el) {
        var modal = el.closest("[data-im-modal]");
        if (modal) modal.hidden = true;
    }

    root.addEventListener("click", function (e) {
        var openBtn = e.target.closest("[data-im-open]");
        if (openBtn) {
            openModal(openBtn.getAttribute("data-im-open"));
            return;
        }
        if (e.target.closest("[data-im-close]")) {
            closeModal(e.target);
            return;
        }
        if (e.target.classList.contains("im-modal")) {
            e.target.hidden = true;
        }
    });

    root.querySelectorAll("[data-im-bulk-remove]").forEach(function (btn) {
        btn.addEventListener("click", function (e) {
            var form = document.getElementById(btn.getAttribute("form"));
            if (!form) return;
            var checked = form.querySelectorAll('input[name="kayit_ids"]:checked');
            if (!checked.length) {
                e.preventDefault();
                alert("Çıkarmak için en az bir öğrenci seçin.");
            }
        });
    });

    root.querySelectorAll(".im-bulk-form").forEach(function (form) {
        var search = form.querySelector("[data-im-bulk-search]");
        var rows = form.querySelectorAll("[data-im-bulk-row]");
        var allBtn = form.querySelector("[data-im-bulk-all]");
        var noneBtn = form.querySelector("[data-im-bulk-none]");

        if (search) {
            search.addEventListener("input", function () {
                var q = (search.value || "").trim().toLocaleLowerCase("tr");
                rows.forEach(function (row) {
                    var name = row.getAttribute("data-name") || "";
                    row.hidden = q && name.indexOf(q) === -1;
                });
            });
        }
        if (allBtn) {
            allBtn.addEventListener("click", function () {
                rows.forEach(function (row) {
                    if (row.hidden) return;
                    var cb = row.querySelector('input[type="checkbox"]');
                    if (cb) cb.checked = true;
                });
            });
        }
        if (noneBtn) {
            noneBtn.addEventListener("click", function () {
                rows.forEach(function (row) {
                    var cb = row.querySelector('input[type="checkbox"]');
                    if (cb) cb.checked = false;
                });
            });
        }
        form.addEventListener("submit", function (e) {
            var checked = form.querySelectorAll('input[name="talebe_ids"]:checked');
            if (!checked.length) {
                e.preventDefault();
                alert("Eklemek için en az bir öğrenci seçin.");
            }
        });
    });
})();
