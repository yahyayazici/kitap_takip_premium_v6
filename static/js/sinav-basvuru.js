(function () {
    const hidden = document.getElementById("id_dogum_tarihi");
    const gun = document.getElementById("sb-gun");
    const ay = document.getElementById("sb-ay");
    const yil = document.getElementById("sb-yil");
    const form = document.querySelector(".sb-form");
    if (!hidden || !gun || !ay || !yil || !form) return;

    const aylar = [
        ["01", "Ocak"],
        ["02", "Şubat"],
        ["03", "Mart"],
        ["04", "Nisan"],
        ["05", "Mayıs"],
        ["06", "Haziran"],
        ["07", "Temmuz"],
        ["08", "Ağustos"],
        ["09", "Eylül"],
        ["10", "Ekim"],
        ["11", "Kasım"],
        ["12", "Aralık"],
    ];

    const now = new Date().getFullYear();
    const yilBas = now - 5;
    const yilSon = now - 25;

    function option(value, label, selected) {
        const el = document.createElement("option");
        el.value = value;
        el.textContent = label;
        if (selected) el.selected = true;
        return el;
    }

    function fillSelects(initial) {
        let initGun = "";
        let initAy = "";
        let initYil = "";
        if (initial && /^\d{4}-\d{2}-\d{2}$/.test(initial)) {
            const parts = initial.split("-");
            initYil = parts[0];
            initAy = parts[1];
            initGun = parts[2];
        }

        gun.innerHTML = "";
        gun.appendChild(option("", "Gün", !initGun));
        for (let d = 1; d <= 31; d += 1) {
            const v = String(d).padStart(2, "0");
            gun.appendChild(option(v, String(d), v === initGun));
        }

        ay.innerHTML = "";
        ay.appendChild(option("", "Ay", !initAy));
        aylar.forEach(([v, label]) => {
            ay.appendChild(option(v, label, v === initAy));
        });

        yil.innerHTML = "";
        yil.appendChild(option("", "Yıl", !initYil));
        for (let y = yilBas; y >= yilSon; y -= 1) {
            const v = String(y);
            yil.appendChild(option(v, v, v === initYil));
        }
    }

    function syncHidden() {
        if (gun.value && ay.value && yil.value) {
            hidden.value = `${yil.value}-${ay.value}-${gun.value}`;
        } else {
            hidden.value = "";
        }
    }

    fillSelects(hidden.dataset.initial || hidden.value || "");
    syncHidden();

    [gun, ay, yil].forEach((el) => {
        el.addEventListener("change", syncHidden);
    });

    const onay = document.getElementById("id_bilgilendirme_onay");
    const submitBtn = document.getElementById("sb-submit");
    const notices = document.querySelectorAll(".sb-notice");

    function syncSubmit() {
        if (!submitBtn || !onay) return;
        submitBtn.disabled = !onay.checked;
    }

    function pulseNotices() {
        notices.forEach((el) => {
            el.classList.remove("is-attention");
            void el.offsetWidth;
            el.classList.add("is-attention");
        });
        const first = document.getElementById("sb-bilgilendirme");
        if (first) first.scrollIntoView({ behavior: "smooth", block: "center" });
    }

    if (onay) {
        syncSubmit();
        onay.addEventListener("change", syncSubmit);
    }

    form.addEventListener("submit", (event) => {
        syncHidden();
        if (!hidden.value) {
            event.preventDefault();
            const err = document.getElementById("sb-dogum-error");
            if (err) {
                err.hidden = false;
                err.textContent = "Doğum tarihini seçin.";
            }
            gun.focus();
            return;
        }
        if (onay && !onay.checked) {
            event.preventDefault();
            pulseNotices();
            onay.focus();
        }
    });
})();
