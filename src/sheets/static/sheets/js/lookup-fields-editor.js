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

        // Hide the original textarea and its parent wrapper
        var fieldRow = hiddenTextarea.closest(".flex-col");
        if (fieldRow) fieldRow.style.display = "none";

        // Build editor container
        editorContainer = document.createElement("div");
        editorContainer.className = "lookup-fields-editor";

        // Find the Upsert Configuration fieldset
        var fieldset = findFieldsetByTitle("Upsert Configuration");
        if (fieldset) {
            var contentArea = fieldset.querySelector(".flex-col") || fieldset;
            contentArea.appendChild(editorContainer);
        } else {
            hiddenTextarea.parentElement.appendChild(editorContainer);
        }

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
    }

    function findFieldsetByTitle(title) {
        var headings = document.querySelectorAll("h2, h3, .module caption, legend, [class*='title']");
        for (var i = 0; i < headings.length; i++) {
            if (headings[i].textContent.trim().indexOf(title) !== -1) {
                var el = headings[i].parentElement;
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
        var html = '<div class="lookup-rows">';

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

        // Datalist for autocomplete — include direct fields and FK-level names
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
        // Focus the new input
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
                // Build a deduplicated list: direct fields + FK-level names
                var result = [];
                var seenFk = {};
                for (var i = 0; i < rawFields.length; i++) {
                    var f = rawFields[i];
                    if (f.group && f.group.indexOf("FK:") === 0) {
                        // Extract FK prefix name
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
    };

    // Init on DOMContentLoaded
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
