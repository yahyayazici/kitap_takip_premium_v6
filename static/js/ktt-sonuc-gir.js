(function () {
    const page = document.getElementById("kttSonucGirPage");
    if (!page) return;

    const cikarUrl = page.dataset.cikarUrl;
    const bar = document.getElementById("kttKatilmayanBar");
    const countEl = document.getElementById("kttKatilmayanCount");
    const cikarBtn = document.getElementById("kttSecilenleriCikar");
    const selectAll = document.getElementById("kttSelectAllKatilmayan");
    const feedbackEl = document.getElementById("kttKatilmayanFeedback");
    const table = document.getElementById("kttSonucTable");
    const csrfToken = document.querySelector("#kttSonucForm [name=csrfmiddlewaretoken]")?.value || "";

    function katilmayanChecks() {
        return Array.from(document.querySelectorAll(".ktt-katilmayan-check"));
    }

    function seciliChecks() {
        return katilmayanChecks().filter((cb) => cb.checked);
    }

    function guncelleSecim() {
        const secili = seciliChecks();
        const adet = secili.length;
        const sayac = document.getElementById("kttSecimSayisi");
        if (sayac) sayac.textContent = String(adet);
        if (cikarBtn && cikarBtn.dataset.busy !== "1") {
            cikarBtn.disabled = adet === 0;
        }

        if (selectAll) {
            const tumu = katilmayanChecks();
            selectAll.indeterminate = adet > 0 && adet < tumu.length;
            selectAll.checked = tumu.length > 0 && adet === tumu.length;
        }
    }

    function guncelleKatilmayanSayisi() {
        const kalan = katilmayanChecks().length;
        if (countEl) countEl.textContent = String(kalan);
        if (kalan === 0 && bar) {
            bar.hidden = true;
        }
        if (selectAll) {
            selectAll.disabled = kalan === 0;
            if (kalan === 0) {
                selectAll.checked = false;
                selectAll.indeterminate = false;
            }
        }
    }

    function mesajGoster(metin, tur) {
        if (!feedbackEl) return;
        feedbackEl.textContent = metin;
        feedbackEl.hidden = false;
        feedbackEl.classList.toggle("is-error", tur === "error");
        feedbackEl.classList.toggle("is-success", tur === "success");
        window.clearTimeout(mesajGoster._timer);
        mesajGoster._timer = window.setTimeout(() => {
            feedbackEl.hidden = true;
        }, 4000);
    }

    function satirlariKaldir(talebeIds) {
        const idSet = new Set(talebeIds.map(String));
        table?.querySelectorAll("tbody tr[data-talebe-id]").forEach((row) => {
            if (!idSet.has(row.dataset.talebeId)) return;
            row.classList.add("ktt-row-removing");
            window.setTimeout(() => row.remove(), 180);
        });
        window.setTimeout(() => {
            guncelleKatilmayanSayisi();
            guncelleSecim();
        }, 200);
    }

    async function secilenleriCikar() {
        const secili = seciliChecks();
        if (!secili.length || !cikarUrl || cikarBtn?.dataset.busy === "1") return;

        const adet = secili.length;
        const onay = window.confirm(
            adet === 1
                ? "Seçili öğrenci sonuç listesinden çıkarılsın mı?"
                : `${adet} öğrenci sonuç listesinden çıkarılsın mı?`
        );
        if (!onay) return;

        const formData = new FormData();
        secili.forEach((cb) => formData.append("talebe_ids", cb.value));

        const oncekiLabel = cikarBtn?.innerHTML || "";
        if (cikarBtn) {
            cikarBtn.dataset.busy = "1";
            cikarBtn.disabled = true;
            cikarBtn.textContent = "Çıkarılıyor…";
        }

        try {
            const response = await fetch(cikarUrl, {
                method: "POST",
                headers: {
                    "X-CSRFToken": csrfToken,
                    "X-Requested-With": "XMLHttpRequest",
                },
                body: formData,
            });

            let data = {};
            try {
                data = await response.json();
            } catch (_) {
                data = { ok: false, hata: "Sunucu yanıtı okunamadı." };
            }

            if (!response.ok || !data.ok) {
                mesajGoster(data.hata || "İşlem başarısız.", "error");
                return;
            }

            satirlariKaldir(data.talebe_ids || secili.map((cb) => cb.value));
            mesajGoster(data.mesaj || "Seçilen öğrenciler listeden çıkarıldı.", "success");
        } catch (_) {
            mesajGoster("Bağlantı hatası. Tekrar deneyin.", "error");
        } finally {
            if (cikarBtn) {
                delete cikarBtn.dataset.busy;
                cikarBtn.innerHTML = oncekiLabel;
            }
            guncelleSecim();
        }
    }

    katilmayanChecks().forEach((cb) => {
        cb.addEventListener("change", guncelleSecim);
    });

    selectAll?.addEventListener("change", () => {
        const checked = selectAll.checked;
        katilmayanChecks().forEach((cb) => {
            cb.checked = checked;
        });
        guncelleSecim();
    });

    cikarBtn?.addEventListener("click", secilenleriCikar);

    guncelleSecim();
})();
