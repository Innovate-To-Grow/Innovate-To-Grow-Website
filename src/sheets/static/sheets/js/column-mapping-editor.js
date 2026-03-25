/**
 * Column Mapping Visual Editor for SheetLink admin.
 *
 * Replaces the raw JSON textarea (#id_column_mapping) with a visual
 * key-value pair editor. Fetches available model fields via AJAX
 * when the content_type dropdown changes.
 */
(function () {
    "use strict";

    // State
    var mappings = [];          // [{header: "", field: ""}]
    var modelFields = [];       // [{value, label, group}]
    var fieldsUrl = "";
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    // ---------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------

    function init() {
        hiddenTextarea = document.getElementById("id_column_mapping");
        if (!hiddenTextarea) return;

        fieldsUrl = window.MODEL_FIELDS_URL || "";

        // Parse existing mapping
        var initial = window.COLUMN_MAPPING_INITIAL || {};
        mappings = Object.entries(initial).map(function (entry) {
            return { header: entry[0], field: entry[1] };
        });

        // Hide the textarea and its label/wrapper robustly
        hideFieldAndLabel(hiddenTextarea);

        // Build editor container and insert right after the hidden textarea
        editorContainer = document.createElement("div");
        editorContainer.className = "column-mapping-editor";
        hiddenTextarea.parentElement.insertBefore(editorContainer, hiddenTextarea.nextSibling);

        renderEditor();

        // Listen for content_type changes
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
            label.style.display = "none";
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
        html += '<button type="button" class="json-toggle-btn" onclick="window._colMapEditor.toggleRaw()">';
        html += rawMode ? "Show visual editor" : "Show raw JSON";
        html += '</button></div>';

        if (rawMode) {
            editorContainer.innerHTML = html;
            return;
        }

        html += '<div class="mapping-rows">';
        if (mappings.length === 0) {
            html += '<div class="mapping-empty">No column mappings yet. Click "Add Mapping" to start.</div>';
        } else {
            for (var i = 0; i < mappings.length; i++) {
                html += renderRow(i, mappings[i]);
            }
        }
        html += "</div>";
        html += '<button type="button" class="mapping-add-btn" onclick="window._colMapEditor.addRow()">+ Add Mapping</button>';
        html += '<p class="mapping-hint">Use Django __ syntax for FK fields (e.g. semester__year). Select "__skip__" to ignore a column.</p>';

        // Datalist for autocomplete
        html += '<datalist id="model-fields-list">';
        html += '<option value="__skip__">';
        for (var j = 0; j < modelFields.length; j++) {
            html += '<option value="' + escapeAttr(modelFields[j].value) + '" label="' + escapeAttr(modelFields[j].label) + '">';
        }
        html += "</datalist>";

        editorContainer.innerHTML = html;
    }

    function renderRow(index, mapping) {
        return (
            '<div class="mapping-row">' +
            '<span class="mapping-row-number">' + (index + 1) + "</span>" +
            '<input type="text" class="mapping-input mapping-header-input" placeholder="Sheet Header (e.g. Year)" ' +
            'value="' + escapeAttr(mapping.header) + '" ' +
            'onchange="window._colMapEditor.updateHeader(' + index + ', this.value)" ' +
            'oninput="window._colMapEditor.updateHeader(' + index + ', this.value)">' +
            '<span class="mapping-arrow">\u2192</span>' +
            '<input type="text" class="mapping-input mapping-field-input" list="model-fields-list" placeholder="Model Field (e.g. class_code)" ' +
            'value="' + escapeAttr(mapping.field) + '" ' +
            'onchange="window._colMapEditor.updateField(' + index + ', this.value)" ' +
            'oninput="window._colMapEditor.updateField(' + index + ', this.value)">' +
            '<button type="button" class="mapping-remove-btn" title="Remove" onclick="window._colMapEditor.removeRow(' + index + ')">\u00d7</button>' +
            "</div>"
        );
    }

    // ---------------------------------------------------------------
    // Actions
    // ---------------------------------------------------------------

    function addRow() {
        mappings.push({ header: "", field: "" });
        renderEditor();
        syncToHidden();
        var rows = editorContainer.querySelectorAll(".mapping-row");
        if (rows.length > 0) {
            var lastRow = rows[rows.length - 1];
            var headerInput = lastRow.querySelector(".mapping-input");
            if (headerInput) headerInput.focus();
        }
    }

    function removeRow(index) {
        mappings.splice(index, 1);
        renderEditor();
        syncToHidden();
    }

    function updateHeader(index, value) {
        mappings[index].header = value;
        syncToHidden();
    }

    function updateField(index, value) {
        mappings[index].field = value;
        syncToHidden();
    }

    // ---------------------------------------------------------------
    // Toggle raw JSON
    // ---------------------------------------------------------------

    function toggleRaw() {
        if (rawMode) {
            // Switching back to visual — re-parse textarea
            if (!reparseFromTextarea()) return;
            rawMode = false;
            hiddenTextarea.style.display = "none";
            renderEditor();
        } else {
            // Switch to raw JSON
            syncToHidden();
            rawMode = true;
            showTextarea(hiddenTextarea);
            // Pretty-print the JSON
            try {
                var obj = JSON.parse(hiddenTextarea.value);
                hiddenTextarea.value = JSON.stringify(obj, null, 2);
            } catch (e) { /* leave as-is */ }
            renderEditor();
        }
    }

    function reparseFromTextarea() {
        try {
            var obj = JSON.parse(hiddenTextarea.value || "{}");
            mappings = Object.entries(obj).map(function (entry) {
                return { header: entry[0], field: String(entry[1]) };
            });
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
        var obj = {};
        for (var i = 0; i < mappings.length; i++) {
            var h = mappings[i].header.trim();
            var f = mappings[i].field.trim();
            if (h) {
                obj[h] = f || "";
            }
        }
        hiddenTextarea.value = JSON.stringify(obj);
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
                modelFields = data.fields || [];
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
    // Public API (for inline event handlers)
    // ---------------------------------------------------------------

    window._colMapEditor = {
        addRow: addRow,
        removeRow: removeRow,
        updateHeader: updateHeader,
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
