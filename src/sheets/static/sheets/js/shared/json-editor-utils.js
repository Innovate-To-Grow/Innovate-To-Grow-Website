(function () {
    "use strict";

    function hideFieldAndLabel(textarea) {
        textarea.style.display = "none";
        var label = document.querySelector('label[for="' + textarea.id + '"]');
        if (label) label.style.display = "none";
    }

    function showTextarea(textarea) {
        textarea.style.display = "";
        textarea.style.width = "100%";
        textarea.style.minHeight = "120px";
        textarea.style.fontFamily = "monospace";
        textarea.style.fontSize = "0.8125rem";
        textarea.rows = 8;
    }

    function createEditorContainer(textarea, className) {
        var container = document.createElement("div");
        container.className = className;
        textarea.parentElement.insertBefore(container, textarea.nextSibling);
        return container;
    }

    function escapeAttr(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    window.SheetsJsonEditorUtils = {
        hideFieldAndLabel: hideFieldAndLabel,
        showTextarea: showTextarea,
        createEditorContainer: createEditorContainer,
        escapeAttr: escapeAttr,
    };
})();
