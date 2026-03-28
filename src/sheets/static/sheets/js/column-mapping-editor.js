(function () {
    "use strict";

    var utils = window.SheetsJsonEditorUtils;
    var mappings = [];
    var modelFields = [];
    var fieldsUrl = "";
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    function init() {
        hiddenTextarea = document.getElementById("id_column_mapping");
        if (!hiddenTextarea) return;
        fieldsUrl = window.MODEL_FIELDS_URL || "";
        mappings = Object.entries(window.COLUMN_MAPPING_INITIAL || {}).map(function (entry) { return { header: entry[0], field: entry[1] }; });
        utils.hideFieldAndLabel(hiddenTextarea);
        editorContainer = utils.createEditorContainer(hiddenTextarea, "column-mapping-editor");
        renderEditor();

        var ctSelect = document.getElementById("id_content_type");
        if (ctSelect) {
            ctSelect.addEventListener("change", function () { fetchModelFields(ctSelect.value); });
            if (ctSelect.value) fetchModelFields(ctSelect.value);
        }
        var form = hiddenTextarea.closest("form");
        if (form) form.addEventListener("submit", syncToHidden);
    }

    function renderEditor() {
        var html = '<div class="json-editor-toggle"><button type="button" class="json-toggle-btn" onclick="window._colMapEditor.toggleRaw()">' + (rawMode ? "Show visual editor" : "Show raw JSON") + '</button></div>';
        if (rawMode) {
            editorContainer.innerHTML = html;
            return;
        }
        html += '<div class="mapping-rows">';
        if (mappings.length === 0) html += '<div class="mapping-empty">No column mappings yet. Click "Add Mapping" to start.</div>';
        for (var i = 0; i < mappings.length; i++) html += renderRow(i, mappings[i]);
        html += '</div><button type="button" class="mapping-add-btn" onclick="window._colMapEditor.addRow()">+ Add Mapping</button><p class="mapping-hint">Use Django __ syntax for FK fields (e.g. semester__year). Select "__skip__" to ignore a column.</p><datalist id="model-fields-list"><option value="__skip__">';
        for (var j = 0; j < modelFields.length; j++) html += '<option value="' + utils.escapeAttr(modelFields[j].value) + '" label="' + utils.escapeAttr(modelFields[j].label) + '">';
        html += "</datalist>";
        editorContainer.innerHTML = html;
    }

    function renderRow(index, mapping) {
        return '<div class="mapping-row"><span class="mapping-row-number">' + (index + 1) + '</span>' +
            '<input type="text" class="mapping-input mapping-header-input" placeholder="Sheet Header (e.g. Year)" value="' + utils.escapeAttr(mapping.header) + '" onchange="window._colMapEditor.updateHeader(' + index + ', this.value)" oninput="window._colMapEditor.updateHeader(' + index + ', this.value)">' +
            '<span class="mapping-arrow">\u2192</span>' +
            '<input type="text" class="mapping-input mapping-field-input" list="model-fields-list" placeholder="Model Field (e.g. class_code)" value="' + utils.escapeAttr(mapping.field) + '" onchange="window._colMapEditor.updateField(' + index + ', this.value)" oninput="window._colMapEditor.updateField(' + index + ', this.value)">' +
            '<button type="button" class="mapping-remove-btn" title="Remove" onclick="window._colMapEditor.removeRow(' + index + ')">\u00d7</button></div>';
    }

    function addRow() {
        mappings.push({ header: "", field: "" });
        renderEditor();
        syncToHidden();
        var rows = editorContainer.querySelectorAll(".mapping-row");
        var headerInput = rows.length ? rows[rows.length - 1].querySelector(".mapping-input") : null;
        if (headerInput) headerInput.focus();
    }

    function removeRow(index) { mappings.splice(index, 1); renderEditor(); syncToHidden(); }
    function updateHeader(index, value) { mappings[index].header = value; syncToHidden(); }
    function updateField(index, value) { mappings[index].field = value; syncToHidden(); }

    function toggleRaw() {
        if (rawMode) {
            try {
                mappings = Object.entries(JSON.parse(hiddenTextarea.value || "{}")).map(function (entry) { return { header: entry[0], field: String(entry[1]) }; });
                rawMode = false;
                hiddenTextarea.style.display = "none";
                renderEditor();
            } catch (e) {
                alert("Invalid JSON. Please fix the JSON before switching to visual mode.");
            }
            return;
        }
        syncToHidden();
        rawMode = true;
        utils.showTextarea(hiddenTextarea);
        try { hiddenTextarea.value = JSON.stringify(JSON.parse(hiddenTextarea.value), null, 2); } catch (e) {}
        renderEditor();
    }

    function syncToHidden() {
        var obj = {};
        for (var i = 0; i < mappings.length; i++) {
            var header = mappings[i].header.trim();
            if (header) obj[header] = mappings[i].field.trim() || "";
        }
        hiddenTextarea.value = JSON.stringify(obj);
    }

    function fetchModelFields(contentTypeId) {
        if (!fieldsUrl || !contentTypeId) { modelFields = []; renderEditor(); return; }
        fetch(fieldsUrl.replace("__CT_ID__", contentTypeId), { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (resp) { return resp.json(); })
            .then(function (data) { modelFields = data.fields || []; renderEditor(); })
            .catch(function () { modelFields = []; renderEditor(); });
    }

    window._colMapEditor = { addRow: addRow, removeRow: removeRow, updateHeader: updateHeader, updateField: updateField, toggleRaw: toggleRaw };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
