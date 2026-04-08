(function () {
    "use strict";

    var cm = null;
    var cmTextArea = null;
    var formatToolbar = null;
    var resizeHandle = null;

    var HEIGHT_STORAGE_KEY = "itg-mail-cm-body-height";
    var DEFAULT_CM_HEIGHT = 600;
    var MIN_CM_HEIGHT = 240;
    var MAX_CM_HEIGHT = 1200;

    function clampHeight(h) {
        var max = Math.min(MAX_CM_HEIGHT, window.innerHeight - 100);
        max = Math.max(MIN_CM_HEIGHT, max);
        h = Math.max(MIN_CM_HEIGHT, Math.min(max, h));
        return Math.round(h);
    }

    function readSavedHeight() {
        try {
            var raw = window.localStorage.getItem(HEIGHT_STORAGE_KEY);
            if (raw !== null) {
                var n = parseInt(raw, 10);
                if (!isNaN(n)) {
                    return clampHeight(n);
                }
            }
        } catch (e) {}
        return DEFAULT_CM_HEIGHT;
    }

    function saveHeight(px) {
        try {
            window.localStorage.setItem(HEIGHT_STORAGE_KEY, String(px));
        } catch (e) {}
    }

    function applyCmHeight(px) {
        if (!cm) return;
        cm.setSize("100%", clampHeight(px));
        cm.refresh();
    }

    function removeResizeHandle() {
        if (resizeHandle && resizeHandle.parentNode) {
            resizeHandle.parentNode.removeChild(resizeHandle);
        }
        resizeHandle = null;
    }

    function attachResizeHandle() {
        if (!cm) return;
        removeResizeHandle();
        var wrap = cm.getWrapperElement();
        if (!wrap || !wrap.parentNode) return;

        var handle = document.createElement("div");
        handle.className = "itg-cm-resize-handle";
        handle.setAttribute("role", "separator");
        handle.setAttribute("aria-orientation", "horizontal");
        handle.setAttribute("aria-label", "Drag to resize editor height");
        handle.title = "Drag to resize height";

        wrap.parentNode.insertBefore(handle, wrap.nextSibling);
        resizeHandle = handle;

        var startY;
        var startH;

        function finishResize() {
            document.body.style.cursor = "";
            document.body.style.userSelect = "";
            if (cm) {
                var w = cm.getWrapperElement();
                if (w && w.offsetHeight) {
                    saveHeight(w.offsetHeight);
                }
            }
        }

        if (window.PointerEvent) {
            handle.addEventListener("pointerdown", function (e) {
                if (e.pointerType === "mouse" && e.button !== 0) return;
                e.preventDefault();
                startY = e.clientY;
                startH = wrap.offsetHeight;
                try {
                    handle.setPointerCapture(e.pointerId);
                } catch (err) {}

                function onPointerMove(pe) {
                    applyCmHeight(startH + (pe.clientY - startY));
                }

                function onPointerUp(pe) {
                    handle.removeEventListener("pointermove", onPointerMove);
                    handle.removeEventListener("pointerup", onPointerUp);
                    handle.removeEventListener("pointercancel", onPointerUp);
                    try {
                        handle.releasePointerCapture(pe.pointerId);
                    } catch (err2) {}
                    finishResize();
                }

                handle.addEventListener("pointermove", onPointerMove);
                handle.addEventListener("pointerup", onPointerUp);
                handle.addEventListener("pointercancel", onPointerUp);
                document.body.style.cursor = "ns-resize";
                document.body.style.userSelect = "none";
            });
        } else {
            function onMove(e) {
                applyCmHeight(startH + (e.clientY - startY));
            }

            function onUp() {
                document.removeEventListener("mousemove", onMove);
                document.removeEventListener("mouseup", onUp);
                finishResize();
            }

            handle.addEventListener("mousedown", function (e) {
                e.preventDefault();
                startY = e.clientY;
                startH = wrap.offsetHeight;
                document.addEventListener("mousemove", onMove);
                document.addEventListener("mouseup", onUp);
                document.body.style.cursor = "ns-resize";
                document.body.style.userSelect = "none";
            });
        }
    }

    function removeFormatToolbar() {
        if (formatToolbar && formatToolbar.parentNode) {
            formatToolbar.parentNode.removeChild(formatToolbar);
        }
        formatToolbar = null;
    }

    function formatEditorHtml() {
        if (!cm || typeof window.html_beautify !== "function") return;
        var raw = cm.getValue();
        var formatted = window.html_beautify(raw, {
            indent_size: 2,
            indent_char: " ",
            wrap_line_length: 120,
            preserve_newlines: true,
            max_preserve_newlines: 2,
            indent_inner_html: true,
        });
        cm.setValue(formatted);
        cm.refresh();
        try {
            cm.focus();
        } catch (e) {}
    }

    function attachFormatToolbar() {
        if (!cm) return;
        removeFormatToolbar();
        var wrap = cm.getWrapperElement();
        if (!wrap || !wrap.parentNode) return;

        var bar = document.createElement("div");
        bar.className = "itg-cm-toolbar";
        bar.setAttribute("role", "toolbar");

        var btn = document.createElement("button");
        btn.type = "button";
        btn.className = "itg-cm-toolbar__format";
        btn.textContent = "Format code";
        btn.setAttribute("aria-label", "Format HTML code");
        btn.title = "Indent and wrap HTML (js-beautify)";
        btn.addEventListener("click", function () {
            formatEditorHtml();
        });

        bar.appendChild(btn);
        wrap.parentNode.insertBefore(bar, wrap);
        formatToolbar = bar;
    }

    function getSelectedFormat() {
        var selected = document.querySelector('input[name="body_format"]:checked');
        return selected ? selected.value : null;
    }

    function ensureCodeMirrorLoaded() {
        return !!(window.CodeMirror && typeof window.CodeMirror.fromTextArea === "function");
    }

    function destroyEditor() {
        removeFormatToolbar();
        removeResizeHandle();
        if (cm) {
            try {
                cm.save();
            } catch (e) {}
            try {
                cm.toTextArea();
            } catch (e2) {}
        }
        cm = null;
        cmTextArea = null;
    }

    function createEditor(textarea) {
        if (!ensureCodeMirrorLoaded()) return;
        if (cm) return;
        cmTextArea = textarea;
        cm = window.CodeMirror.fromTextArea(textarea, {
            mode: "htmlmixed",
            lineNumbers: true,
            lineWrapping: true,
            tabSize: 2,
            indentUnit: 2,
            viewportMargin: Infinity,
        });
        applyCmHeight(readSavedHeight());

        attachFormatToolbar();
        attachResizeHandle();

        // Keep textarea in sync for Django form submit.
        var form = textarea.form;
        if (form && !form.__itgCmHooked) {
            form.__itgCmHooked = true;
            form.addEventListener("submit", function () {
                try {
                    if (cm) cm.save();
                } catch (e) {}
            });
        }
    }

    function applyMode() {
        var textarea = document.getElementById("id_body");
        if (!textarea) return;

        var format = getSelectedFormat();
        if (format === "html") {
            createEditor(textarea);
        } else {
            destroyEditor();
        }
    }

    function init() {
        var textarea = document.getElementById("id_body");
        if (!textarea) return;
        var radios = document.querySelectorAll('input[name="body_format"]');
        if (!radios.length) return;

        radios.forEach(function (radio) {
            radio.addEventListener("change", applyMode);
        });

        applyMode();
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();

