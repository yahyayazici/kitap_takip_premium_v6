document.addEventListener("DOMContentLoaded", function () {
    const sinifInputs = document.querySelectorAll(
        'input[name="sinif_sube"]'
    );
    const hocaSelect = document.querySelector(
        'select[name="etut_hocasi"]'
    );

    if (!sinifInputs.length || !hocaSelect) {
        return;
    }

    const tumSecenekler = Array.from(hocaSelect.options);

    function hocalariFiltrele() {
        const seciliSinif = document.querySelector(
            'input[name="sinif_sube"]:checked'
        );

        if (!seciliSinif) {
            tumSecenekler.forEach(function (option) {
                option.hidden = false;
                option.disabled = false;
            });
            return;
        }

        const sinifId = seciliSinif.value;

        tumSecenekler.forEach(function (option) {
            if (!option.value) {
                option.hidden = false;
                option.disabled = false;
                return;
            }

            const url = (
                "/yonetim/api/hoca-siniflari/"
                + option.value
                + "/"
            );

            option.hidden = false;
            option.disabled = false;
        });
    }

    sinifInputs.forEach(function (input) {
        input.addEventListener("change", hocalariFiltrele);
    });

    hocalariFiltrele();
});
