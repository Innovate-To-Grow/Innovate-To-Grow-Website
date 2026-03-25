/**
 * Lookup Fields Visual Editor for SheetLink admin.
 *
 * Replaces the raw JSON textarea (#id_lookup_fields) with a simple
 * row-based list editor.  Each row is a field name with autocomplete
 * from the model fields AJAX endpoint.
 */
(function () {
    "use strict";

    // State
    var lookupFields = [];      // array of strings
    var modelFields = [];       // [{value, label, group}]
    var fieldsUrl = "";
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    // ---------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------

    function init() {
        hiddenTextarea = document.getElementById("id_lookup_fields");
        if (!hiddenTextarea) return;

        fieldsUrl = window.MODEL_FIELDS_URL || "";

        // Parse existing value
        var initial = window.LOOKUP_FIELDS_INITIAL || [];
        lookupFields = Array.isArray(initial) ? initial.slice() : [];

        // Hide the textarea and its label/wrapper robustly
        hideFieldAndLabel(hiddenTextarea);

        // Build editor container and insert right after the hidden textarea
        editorContainer = document.createElement("div");
        editorContainer.className = "lookup-fields-editor";
        hiddenTextarea.parentElement.insertBefore(editorContainer, hiddenTextarea.nextSibling);

        renderEditor();

        // Listen for content_type changes to update model fields
        var ctSelect = document.getElementById("id_content_type");
        if (ctSelect) {
            ctSelect.addEventListener("change", function () {
                fetchModelFields(ctSelect.value);
            });
            if (ctSelect.value) {
                fetchModelFields(ctSelect.value);
            }
        }

        // Safety net: sync before form submission
        var form = hiddenTextarea.closest("form");
        if (form) {
            form.addEventListener("submit", function () {
                syncToHidden();
            });
        }
    }

    // ---------------------------------------------------------------
    // Hide field + label robustly
    // ---------------------------------------------------------------

    function hideFieldAndLabel(textarea) {
        textarea.style.display = "none";
        var label = document.querySelector('label[for="' + textarea.id + '"]');
        if (label) {
            var wrapper = label.closest(".flex-col");
            if (wrapper && wrapper.contains(textarea)) {
                wrapper.style.display = "none";
            } else {
                label.style.display = "none";
            }
        }
    }

    function showTextarea(textarea) {
        textarea.style.display = "";
        textarea.style.width = "100%";
        textarea.style.minHeight = "120px";
        textarea.style.fontFamily = "monospace";
        textarea.style.fontSize = "0.8125rem";
        textarea.rows = 8;
    }

    // ---------------------------------------------------------------
    // Render
    // ---------------------------------------------------------------

    function renderEditor() {
        var html = '';

        // Toggle button
        html += '<div class="json-editor-toggle">';
        html += '<button type="button" class="json-toggle-btn" onclick="window._lookupFieldsEditor.toggleRaw()">';
        html += rawMode ? "Show visual editor" : "Show raw JSON";
        html += '</button></div>';

        if (rawMode) {
            editorContainer.innerHTML = html;
            return;
        }

        html += '<div class="lookup-rows">';
        if (lookupFields.length === 0) {
            html += '<div class="lookup-empty">No lookup fields yet. Click "Add Field" to start.</div>';
        } else {
            for (var i = 0; i < lookupFields.length; i++) {
                html += renderRow(i, lookupFields[i]);
            }
        }
        html += "</div>";
        html += '<button type="button" class="lookup-add-btn" onclick="window._lookupFieldsEditor.addField()">+ Add Field</button>';
        html += '<p class="lookup-hint">Fields forming the unique key for upserts (used with update_or_create). ' +
            'Use direct field names or FK field names (e.g. "semester", not "semester__year").</p>';

        // Datalist for autocomplete
        html += '<datalist id="lookup-fields-list">';
        for (var j = 0; j < modelFields.length; j++) {
            html += '<option value="' + escapeAttr(modelFields[j].value) + '" label="' + escapeAttr(modelFields[j].label) + '">';
        }
        html += "</datalist>";

        editorContainer.innerHTML = html;
    }

    function renderRow(index, fieldName) {
        return (
            '<div class="lookup-row">' +
            '<span class="lookup-row-number">' + (index + 1) + "</span>" +
            '<input type="text" class="lookup-input" list="lookup-fields-list" ' +
            'placeholder="Field name (e.g. semester)" ' +
            'value="' + escapeAttr(fieldName) + '" ' +
            'onchange="window._lookupFieldsEditor.updateField(' + index + ', this.value)" ' +
            'oninput="window._lookupFieldsEditor.updateField(' + index + ', this.value)">' +
            '<button type="button" class="lookup-remove-btn" title="Remove" ' +
            'onclick="window._lookupFieldsEditor.removeField(' + index + ')">\u00d7</button>' +
            "</div>"
        );
    }

    // ---------------------------------------------------------------
    // Actions
    // ---------------------------------------------------------------

    function addField() {
        lookupFields.push("");
        renderEditor();
        syncToHidden();
        var rows = editorContainer.querySelectorAll(".lookup-row");
        if (rows.length > 0) {
            var lastRow = rows[rows.length - 1];
            var input = lastRow.querySelector(".lookup-input");
            if (input) input.focus();
        }
    }

    function removeField(index) {
        lookupFields.splice(index, 1);
        renderEditor();
        syncToHidden();
    }

    function updateField(index, value) {
        lookupFields[index] = value;
        syncToHidden();
    }

    // ---------------------------------------------------------------
    // Toggle raw JSON
    // ---------------------------------------------------------------

    function toggleRaw() {
        if (rawMode) {
            if (!reparseFromTextarea()) return;
            rawMode = false;
            hiddenTextarea.style.display = "none";
            renderEditor();
        } else {
            syncToHidden();
            rawMode = true;
            showTextarea(hiddenTextarea);
            try {
                var arr = JSON.parse(hiddenTextarea.value);
                hiddenTextarea.value = JSON.stringify(arr, null, 2);
            } catch (e) { /* leave as-is */ }
            renderEditor();
        }
    }

    function reparseFromTextarea() {
        try {
            var arr = JSON.parse(hiddenTextarea.value || "[]");
            if (!Array.isArray(arr)) {
                alert("Expected a JSON array. Please fix the JSON.");
                return false;
            }
            lookupFields = arr.map(function (v) { return String(v); });
            return true;
        } catch (e) {
            alert("Invalid JSON. Please fix the JSON before switching to visual mode.");
            return false;
        }
    }

    // ---------------------------------------------------------------
    // Sync to hidden field
    // ---------------------------------------------------------------

    function syncToHidden() {
        var arr = [];
        for (var i = 0; i < lookupFields.length; i++) {
            var v = lookupFields[i].trim();
            if (v) arr.push(v);
        }
        hiddenTextarea.value = JSON.stringify(arr);
    }

    // ---------------------------------------------------------------
    // AJAX: fetch model fields
    // ---------------------------------------------------------------

    function fetchModelFields(contentTypeId) {
        if (!fieldsUrl || !contentTypeId) {
            modelFields = [];
            renderEditor();
            return;
        }

        var url = fieldsUrl.replace("__CT_ID__", contentTypeId);
        fetch(url, {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                var rawFields = data.fields || [];
                var result = [];
                var seenFk = {};
                for (var i = 0; i < rawFields.length; i++) {
                    var f = rawFields[i];
                    if (f.group && f.group.indexOf("FK:") === 0) {
                        var prefix = f.group.replace("FK: ", "").replace("FK:", "").trim();
                        if (!seenFk[prefix]) {
                            seenFk[prefix] = true;
                            result.push({
                                value: prefix,
                                label: prefix + " (FK field)",
                                group: "FK fields",
                            });
                        }
                    } else {
                        result.push(f);
                    }
                }
                modelFields = result;
                renderEditor();
            })
            .catch(function () {
                modelFields = [];
                renderEditor();
            });
    }

    // ---------------------------------------------------------------
    // Helpers
    // ---------------------------------------------------------------

    function escapeAttr(str) {
        if (!str) return "";
        return str.replace(/&/g, "&amp;").replace(/"/g, "&quot;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
    }

    // ---------------------------------------------------------------
    // Public API
    // ---------------------------------------------------------------

    window._lookupFieldsEditor = {
        addField: addField,
        removeField: removeField,
        updateField: updateField,
        toggleRaw: toggleRaw,
    };

    // Init on DOMContentLoaded
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
