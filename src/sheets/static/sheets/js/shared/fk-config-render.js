(function () {
    "use strict";

    var utils = window.SheetsJsonEditorUtils;

    function getFkPrefixes() {
        var prefixes = [];
        var cmTextarea = document.getElementById("id_column_mapping");
        if (!cmTextarea) return prefixes;
        try {
            var mapping = JSON.parse(cmTextarea.value || "{}");
            var seen = {};
            var values = Object.values ? Object.values(mapping) : Object.keys(mapping).map(function (key) { return mapping[key]; });
            for (var i = 0; i < values.length; i++) {
                var value = values[i];
                if (typeof value === "string" && value.indexOf("__") !== -1 && value !== "__skip__") {
                    var prefix = value.split("__")[0];
                    if (!seen[prefix]) {
                        seen[prefix] = true;
                        prefixes.push(prefix);
                    }
                }
            }
        } catch (e) {}
        return prefixes;
    }

    function renderEditor(editorContainer, rawMode, fkEntries) {
        var html = '<div class="json-editor-toggle"><button type="button" class="json-toggle-btn" onclick="window._fkConfigEditor.toggleRaw()">' + (rawMode ? "Show visual editor" : "Show raw JSON") + '</button></div>';
        if (rawMode) {
            editorContainer.innerHTML = html;
            return;
        }
        var fkPrefixes = getFkPrefixes();
        html += '<div class="fk-cards">';
        if (fkEntries.length === 0) {
            html += '<div class="fk-empty">No FK configuration yet. Click "Add FK Config" to start.</div>';
        } else {
            for (var i = 0; i < fkEntries.length; i++) html += renderCard(i, fkEntries[i], fkPrefixes);
        }
        html += '</div><button type="button" class="fk-add-btn" onclick="window._fkConfigEditor.addEntry()">+ Add FK Config</button><p class="fk-hint">Configure behavior for FK fields found in the column mapping. "Create if missing" uses get_or_create() instead of get().</p>';
        editorContainer.innerHTML = html;
    }

    function renderCard(index, entry, fkPrefixes) {
        var toggleId = "fk-create-" + index;
        var html = '<div class="fk-card"><div class="fk-card-header"><span class="fk-card-header-label">FK Field</span>' +
            '<input type="text" class="fk-card-field-input" list="fk-prefixes-list" placeholder="e.g. semester" value="' + utils.escapeAttr(entry.fkField) + '" onchange="window._fkConfigEditor.updateField(' + index + ', this.value)" oninput="window._fkConfigEditor.updateField(' + index + ', this.value)">' +
            '<button type="button" class="fk-card-remove-btn" title="Remove FK config" onclick="window._fkConfigEditor.removeEntry(' + index + ')">\u00d7</button></div>' +
            '<div class="fk-card-body"><div class="fk-toggle-row"><input type="checkbox" id="' + toggleId + '" ' + (entry.createIfMissing ? "checked " : "") + 'onchange="window._fkConfigEditor.toggleCreate(' + index + ', this.checked)"><label for="' + toggleId + '">Create if missing</label></div>' +
            '<div class="fk-defaults-section"><div class="fk-defaults-label">Defaults (applied when creating)</div><div class="fk-defaults-rows">';
        if (entry.defaults.length === 0) {
            html += '<div style="font-size:0.8125rem;color:var(--color-base-400,#9ca3af);padding:4px 0;">No defaults set.</div>';
        } else {
            for (var d = 0; d < entry.defaults.length; d++) html += renderDefaultRow(index, d, entry.defaults[d]);
        }
        html += '</div><button type="button" class="fk-add-default-btn" onclick="window._fkConfigEditor.addDefault(' + index + ')">+ Add Default</button></div></div></div>';
        if (index === 0) {
            html += '<datalist id="fk-prefixes-list">';
            for (var p = 0; p < fkPrefixes.length; p++) html += '<option value="' + utils.escapeAttr(fkPrefixes[p]) + '">';
            html += "</datalist>";
        }
        return html;
    }

    function renderDefaultRow(entryIndex, defaultIndex, def) {
        return '<div class="fk-defaults-row">' +
            '<input type="text" class="fk-defaults-input" placeholder="Field name" value="' + utils.escapeAttr(def.key) + '" onchange="window._fkConfigEditor.updateDefaultKey(' + entryIndex + "," + defaultIndex + ', this.value)" oninput="window._fkConfigEditor.updateDefaultKey(' + entryIndex + "," + defaultIndex + ', this.value)">' +
            '<span class="fk-defaults-arrow">\u2192</span>' +
            '<input type="text" class="fk-defaults-input" placeholder="Value" value="' + utils.escapeAttr(def.value) + '" onchange="window._fkConfigEditor.updateDefaultValue(' + entryIndex + "," + defaultIndex + ', this.value)" oninput="window._fkConfigEditor.updateDefaultValue(' + entryIndex + "," + defaultIndex + ', this.value)">' +
            '<button type="button" class="fk-defaults-remove-btn" title="Remove default" onclick="window._fkConfigEditor.removeDefault(' + entryIndex + "," + defaultIndex + ')">\u00d7</button></div>';
    }

    window.SheetsFkConfigRenderer = {
        renderEditor: renderEditor,
    };
})();
