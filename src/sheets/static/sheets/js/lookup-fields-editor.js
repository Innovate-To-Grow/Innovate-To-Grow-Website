(function () {
    "use strict";

    var utils = window.SheetsJsonEditorUtils;
    var lookupFields = [];
    var modelFields = [];
    var fieldsUrl = "";
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    function init() {
        hiddenTextarea = document.getElementById("id_lookup_fields");
        if (!hiddenTextarea) return;
        fieldsUrl = window.MODEL_FIELDS_URL || "";
        lookupFields = Array.isArray(window.LOOKUP_FIELDS_INITIAL) ? window.LOOKUP_FIELDS_INITIAL.slice() : [];
        utils.hideFieldAndLabel(hiddenTextarea);
        editorContainer = utils.createEditorContainer(hiddenTextarea, "lookup-fields-editor");
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
        var html = '<div class="json-editor-toggle"><button type="button" class="json-toggle-btn" onclick="window._lookupFieldsEditor.toggleRaw()">' + (rawMode ? "Show visual editor" : "Show raw JSON") + '</button></div>';
        if (rawMode) { editorContainer.innerHTML = html; return; }
        html += '<div class="lookup-rows">';
        if (lookupFields.length === 0) html += '<div class="lookup-empty">No lookup fields yet. Click "Add Field" to start.</div>';
        for (var i = 0; i < lookupFields.length; i++) html += renderRow(i, lookupFields[i]);
        html += '</div><button type="button" class="lookup-add-btn" onclick="window._lookupFieldsEditor.addField()">+ Add Field</button><p class="lookup-hint">Fields forming the unique key for upserts (used with update_or_create). Use direct field names or FK field names (e.g. "semester", not "semester__year").</p><datalist id="lookup-fields-list">';
        for (var j = 0; j < modelFields.length; j++) html += '<option value="' + utils.escapeAttr(modelFields[j].value) + '" label="' + utils.escapeAttr(modelFields[j].label) + '">';
        html += "</datalist>";
        editorContainer.innerHTML = html;
    }

    function renderRow(index, fieldName) {
        return '<div class="lookup-row"><span class="lookup-row-number">' + (index + 1) + '</span>' +
            '<input type="text" class="lookup-input" list="lookup-fields-list" placeholder="Field name (e.g. semester)" value="' + utils.escapeAttr(fieldName) + '" onchange="window._lookupFieldsEditor.updateField(' + index + ', this.value)" oninput="window._lookupFieldsEditor.updateField(' + index + ', this.value)">' +
            '<button type="button" class="lookup-remove-btn" title="Remove" onclick="window._lookupFieldsEditor.removeField(' + index + ')">\u00d7</button></div>';
    }

    function addField() {
        lookupFields.push("");
        renderEditor();
        syncToHidden();
        var rows = editorContainer.querySelectorAll(".lookup-row");
        var input = rows.length ? rows[rows.length - 1].querySelector(".lookup-input") : null;
        if (input) input.focus();
    }

    function removeField(index) { lookupFields.splice(index, 1); renderEditor(); syncToHidden(); }
    function updateField(index, value) { lookupFields[index] = value; syncToHidden(); }

    function toggleRaw() {
        if (rawMode) {
            try {
                var arr = JSON.parse(hiddenTextarea.value || "[]");
                if (!Array.isArray(arr)) throw new Error("Expected array");
                lookupFields = arr.map(function (value) { return String(value); });
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
        var arr = [];
        for (var i = 0; i < lookupFields.length; i++) {
            var value = lookupFields[i].trim();
            if (value) arr.push(value);
        }
        hiddenTextarea.value = JSON.stringify(arr);
    }

    function fetchModelFields(contentTypeId) {
        if (!fieldsUrl || !contentTypeId) { modelFields = []; renderEditor(); return; }
        fetch(fieldsUrl.replace("__CT_ID__", contentTypeId), { headers: { "X-Requested-With": "XMLHttpRequest" } })
            .then(function (resp) { return resp.json(); })
            .then(function (data) {
                var seenFk = {};
                modelFields = (data.fields || []).reduce(function (result, field) {
                    if (field.group && field.group.indexOf("FK:") === 0) {
                        var prefix = field.group.replace("FK: ", "").replace("FK:", "").trim();
                        if (!seenFk[prefix]) {
                            seenFk[prefix] = true;
                            result.push({ value: prefix, label: prefix + " (FK field)", group: "FK fields" });
                        }
                    } else result.push(field);
                    return result;
                }, []);
                renderEditor();
            })
            .catch(function () { modelFields = []; renderEditor(); });
    }

    window._lookupFieldsEditor = { addField: addField, removeField: removeField, updateField: updateField, toggleRaw: toggleRaw };
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
