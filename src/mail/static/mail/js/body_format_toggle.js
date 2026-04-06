(function () {
    "use strict";

    function init() {
        var bodyEl = document.getElementById("id_body");
        if (!bodyEl) return;

        // body_format radios rendered by Django RadioSelect
        var radios = document.querySelectorAll('input[name="body_format"]');
        if (!radios.length) return;

        function applyStyle() {
            var selected = document.querySelector('input[name="body_format"]:checked');
            if (!selected) return;
            if (selected.value === "html") {
                bodyEl.style.fontFamily = "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace";
                bodyEl.style.fontSize = "13px";
                bodyEl.style.whiteSpace = "pre";
                bodyEl.style.overflowWrap = "normal";
                bodyEl.style.lineHeight = "1.5";
                bodyEl.rows = 20;
            } else {
                bodyEl.style.fontFamily = "";
                bodyEl.style.fontSize = "";
                bodyEl.style.whiteSpace = "";
                bodyEl.style.overflowWrap = "";
                bodyEl.style.lineHeight = "";
                bodyEl.rows = 10;
            }
        }

        radios.forEach(function (radio) {
            radio.addEventListener("change", applyStyle);
        });
        applyStyle();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
