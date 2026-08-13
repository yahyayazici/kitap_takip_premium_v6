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

    var adInput = document.getElementById("id_ad");
    var dersSelect = document.getElementById("id_ders");
    var oneriBox = document.createElement("div");
    oneriBox.className = "ktt-konu-oneri";
    oneriBox.hidden = true;

    if (adInput && adInput.closest(".ktt-field")) {
        var konuField = adInput.closest(".ktt-field");
        konuField.classList.add("ktt-field-konu");
        konuField.appendChild(oneriBox);
    }

    var debounceTimer;
    function konuOneriYukle() {
        if (!adInput || adInput.value.trim().length < 2) {
            oneriBox.hidden = true;
            return;
        }
        var params = new URLSearchParams({
            q: adInput.value.trim(),
            sinif: "7",
        });
        if (dersSelect && dersSelect.value) {
            params.set("ders", dersSelect.value);
        }
        fetch("/ktt/konu-oneri/?" + params.toString(), {
            headers: { Accept: "application/json" },
        })
            .then(function (r) {
                return r.json();
            })
            .then(function (data) {
                oneriBox.innerHTML = "";
                var list = data.oneriler || [];
                if (!list.length) {
                    oneriBox.hidden = true;
                    return;
                }
                list.forEach(function (item) {
                    var btn = document.createElement("button");
                    btn.type = "button";
                    btn.textContent = item.ad;
                    btn.addEventListener("click", function () {
                        adInput.value = item.ad;
                        oneriBox.hidden = true;
                    });
                    oneriBox.appendChild(btn);
                });
                oneriBox.hidden = false;
            })
            .catch(function () {
                oneriBox.hidden = true;
            });
    }

    if (adInput) {
        adInput.addEventListener("input", function () {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(konuOneriYukle, 220);
        });
        adInput.addEventListener("blur", function () {
            setTimeout(function () {
                oneriBox.hidden = true;
            }, 180);
        });
    }
})();
