(function () {
    const form = document.getElementById("va-anket-form");
    if (!form) return;

    const sinifRow = document.getElementById("vaSinifRow");
    const sinifHidden = document.querySelector('input[name="sinif"]');
    const sinifError = document.getElementById("vaSinifError");

    const ihtiyacRow = document.getElementById("vaIhtiyacRow");
    const ihtiyacHidden = document.querySelector('input[name="konu_ihtiyaci_cevap"]');

    const ratingRow = document.getElementById("vaRatingRow");
    const ratingHidden = document.querySelector('input[name="istifade_puani"]');
    const ratingError = document.getElementById("vaRatingError");

    function wirePills(row, hiddenInput, onSelect) {
        if (!row || !hiddenInput) return;
        const initial = hiddenInput.value;
        Array.prototype.forEach.call(row.children, function (btn) {
            if (btn.getAttribute("data-value") === initial) {
                btn.classList.add("is-selected");
            }
        });
        row.addEventListener("click", function (e) {
            const btn = e.target.closest("button");
            if (!btn) return;
            hiddenInput.value = btn.getAttribute("data-value");
            Array.prototype.forEach.call(row.children, function (c) {
                c.classList.toggle("is-selected", c === btn);
            });
            if (onSelect) onSelect();
        });
    }

    wirePills(sinifRow, sinifHidden, function () {
        if (sinifError) sinifError.hidden = true;
    });
    wirePills(ihtiyacRow, ihtiyacHidden);
    wirePills(ratingRow, ratingHidden, function () {
        if (ratingError) ratingError.hidden = true;
    });

    form.addEventListener("submit", function (e) {
        let blocked = false;
        if (!sinifHidden.value) {
            blocked = true;
            if (sinifError) sinifError.hidden = false;
        }
        if (!ratingHidden.value) {
            blocked = true;
            if (ratingError) ratingError.hidden = false;
        }
        if (blocked) {
            e.preventDefault();
            const target = !sinifHidden.value ? sinifRow : ratingRow;
            target.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    });
})();
