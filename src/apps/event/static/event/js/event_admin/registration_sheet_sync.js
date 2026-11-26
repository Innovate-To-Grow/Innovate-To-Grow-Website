(function () {
    "use strict";
    function updateTiming() {
        var selected = document.querySelector('input[name="sync_mode"]:checked');
        var mode = selected ? selected.value : "automatic";
        document.querySelectorAll("[data-interval-settings]").forEach(function (element) {
            element.hidden = mode !== "interval";
        });
        document.querySelectorAll("[data-timing-hint]").forEach(function (element) {
            element.hidden = element.dataset.timingHint !== mode;
        });
    }
    document.querySelectorAll('input[name="sync_mode"]').forEach(function (input) {
        input.addEventListener("change", updateTiming);
    });
    updateTiming();
}());
