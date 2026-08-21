(function () {
    const form = document.getElementById("va-anket-form");
    if (!form) return;

    const ratingRow = document.getElementById("vaRatingRow");
    const ratingHidden = document.querySelector('input[name="genel_degerlendirme"]');
    const ratingError = document.getElementById("vaRatingError");
    const benefitRow = document.getElementById("vaBenefitRow");
    const benefitHidden = document.querySelector('input[name="istifade_duzeyi"]');

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

    wirePills(ratingRow, ratingHidden, function () {
        if (ratingError) ratingError.hidden = true;
    });
    wirePills(benefitRow, benefitHidden);

    form.addEventListener("submit", function (e) {
        if (!ratingHidden.value) {
            e.preventDefault();
            if (ratingError) ratingError.hidden = false;
            ratingRow.scrollIntoView({ behavior: "smooth", block: "center" });
        }
    });
})();
