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
    let mappings = [];          // [{header: "", field: ""}]
    let modelFields = [];       // [{value, label, group}]
    let fieldsUrl = "";
    let hiddenTextarea = null;
    let editorContainer = null;

    // ---------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------

    function init() {
        hiddenTextarea = document.getElementById("id_column_mapping");
        if (!hiddenTextarea) return;

        fieldsUrl = window.MODEL_FIELDS_URL || "";

        // Parse existing mapping
        const initial = window.COLUMN_MAPPING_INITIAL || {};
        mappings = Object.entries(initial).map(function (entry) {
            return { header: entry[0], field: entry[1] };
        });

        // Hide the original textarea and its parent wrapper
        const fieldRow = hiddenTextarea.closest(".flex-col");
        if (fieldRow) fieldRow.style.display = "none";

        // Build editor container and insert after the hidden field's fieldset row
        editorContainer = document.createElement("div");
        editorContainer.className = "column-mapping-editor";

        // Find the Column Mapping fieldset to insert into
        const fieldset = findColumnMappingFieldset();
        if (fieldset) {
            // Insert editor inside the fieldset content area
            const contentArea = fieldset.querySelector(".flex-col") || fieldset;
            contentArea.appendChild(editorContainer);
        } else {
            // Fallback: insert after the hidden textarea's container
            hiddenTextarea.parentElement.appendChild(editorContainer);
        }

        renderEditor();

        // Listen for content_type changes
        const ctSelect = document.getElementById("id_content_type");
        if (ctSelect) {
            ctSelect.addEventListener("change", function () {
                fetchModelFields(ctSelect.value);
            });
            // Initial fetch if a value is already selected
            if (ctSelect.value) {
                fetchModelFields(ctSelect.value);
            }
        }
    }

    function findColumnMappingFieldset() {
        // Look for the fieldset whose heading contains "Column Mapping"
        const headings = document.querySelectorAll("h2, h3, .module caption, legend, [class*='title']");
        for (let i = 0; i < headings.length; i++) {
            if (headings[i].textContent.trim().indexOf("Column Mapping") !== -1) {
                // Walk up to find the fieldset/module container
                let el = headings[i].parentElement;
                while (el && !el.matches("fieldset, .module, section, [class*='border']")) {
                    el = el.parentElement;
                }
                return el;
            }
        }
        return null;
    }

    // ---------------------------------------------------------------
    // Render
    // ---------------------------------------------------------------

    function renderEditor() {
        let html = '<div class="mapping-rows">';

        if (mappings.length === 0) {
            html += '<div class="mapping-empty">No column mappings yet. Click "Add Mapping" to start.</div>';
        } else {
            for (let i = 0; i < mappings.length; i++) {
                html += renderRow(i, mappings[i]);
            }
        }

        html += "</div>";
        html += '<button type="button" class="mapping-add-btn" onclick="window._colMapEditor.addRow()">+ Add Mapping</button>';
        html += '<p class="mapping-hint">Use Django __ syntax for FK fields (e.g. semester__year). Select "__skip__" to ignore a column.</p>';

        // Datalist for autocomplete
        html += '<datalist id="model-fields-list">';
        html += '<option value="__skip__">';
        for (let j = 0; j < modelFields.length; j++) {
            html += '<option value="' + escapeAttr(modelFields[j].value) + '" label="' + escapeAttr(modelFields[j].label) + '">';
        }
        html += "</datalist>";

        editorContainer.innerHTML = html;
    }

    function renderRow(index, mapping) {
        return (
            '<div class="mapping-row">' +
            '<span class="mapping-row-number">' + (index + 1) + "</span>" +
            '<input type="text" class="mapping-input" placeholder="Sheet Header (e.g. Year)" ' +
            'value="' + escapeAttr(mapping.header) + '" ' +
            'onchange="window._colMapEditor.updateHeader(' + index + ', this.value)" ' +
            'oninput="window._colMapEditor.updateHeader(' + index + ', this.value)">' +
            '<span class="mapping-arrow">\u2192</span>' +
            '<input type="text" class="mapping-input" list="model-fields-list" placeholder="Model Field (e.g. class_code)" ' +
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
        // Focus the new header input
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
    };

    // Init on DOMContentLoaded
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
