/**
 * FK Config Visual Editor for SheetLink admin.
 *
 * Replaces the raw JSON textarea (#id_fk_config) with a card-based
 * visual editor.  Each FK field gets a card with a create_if_missing
 * toggle and a key-value sub-editor for default values.
 */
(function () {
    "use strict";

    // State
    var fkEntries = [];     // [{fkField, createIfMissing, defaults: [{key, value}]}]
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    // ---------------------------------------------------------------
    // Init
    // ---------------------------------------------------------------

    function init() {
        hiddenTextarea = document.getElementById("id_fk_config");
        if (!hiddenTextarea) return;

        // Parse existing config
        var initial = window.FK_CONFIG_INITIAL || {};
        fkEntries = parseConfig(initial);

        // Hide the textarea and its label/wrapper robustly
        hideFieldAndLabel(hiddenTextarea);

        // Build editor container and insert right after the hidden textarea
        editorContainer = document.createElement("div");
        editorContainer.className = "fk-config-editor";
        hiddenTextarea.parentElement.insertBefore(editorContainer, hiddenTextarea.nextSibling);

        renderEditor();

        // Safety net: sync before form submission
        var form = hiddenTextarea.closest("form");
        if (form) {
            form.addEventListener("submit", function () {
                syncToHidden();
            });
        }
    }

    function parseConfig(initial) {
        var entries = [];
        var keys = Object.keys(initial);
        for (var i = 0; i < keys.length; i++) {
            var fkField = keys[i];
            var cfg = initial[fkField] || {};
            var defaults = [];
            if (cfg.defaults && typeof cfg.defaults === "object") {
                var dKeys = Object.keys(cfg.defaults);
                for (var d = 0; d < dKeys.length; d++) {
                    defaults.push({ key: dKeys[d], value: String(cfg.defaults[dKeys[d]]) });
                }
            }
            entries.push({
                fkField: fkField,
                createIfMissing: !!cfg.create_if_missing,
                defaults: defaults,
            });
        }
        return entries;
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
    // Get FK prefixes from column_mapping
    // ---------------------------------------------------------------

    function getFkPrefixes() {
        var prefixes = [];
        var cmTextarea = document.getElementById("id_column_mapping");
        if (!cmTextarea) return prefixes;
        try {
            var mapping = JSON.parse(cmTextarea.value || "{}");
            var seen = {};
            var vals = Object.values ? Object.values(mapping) : Object.keys(mapping).map(function (k) { return mapping[k]; });
            for (var i = 0; i < vals.length; i++) {
                var v = vals[i];
                if (typeof v === "string" && v.indexOf("__") !== -1 && v !== "__skip__") {
                    var prefix = v.split("__")[0];
                    if (!seen[prefix]) {
                        seen[prefix] = true;
                        prefixes.push(prefix);
                    }
                }
            }
        } catch (e) {
            // ignore parse errors
        }
        return prefixes;
    }

    // ---------------------------------------------------------------
    // Render
    // ---------------------------------------------------------------

    function renderEditor() {
        var html = '';

        // Toggle button
        html += '<div class="json-editor-toggle">';
        html += '<button type="button" class="json-toggle-btn" onclick="window._fkConfigEditor.toggleRaw()">';
        html += rawMode ? "Show visual editor" : "Show raw JSON";
        html += '</button></div>';

        if (rawMode) {
            editorContainer.innerHTML = html;
            return;
        }

        var fkPrefixes = getFkPrefixes();
        html += '<div class="fk-cards">';

        if (fkEntries.length === 0) {
            html += '<div class="fk-empty">No FK configuration yet. Click "Add FK Config" to start.</div>';
        } else {
            for (var i = 0; i < fkEntries.length; i++) {
                html += renderCard(i, fkEntries[i], fkPrefixes);
            }
        }

        html += "</div>";
        html += '<button type="button" class="fk-add-btn" onclick="window._fkConfigEditor.addEntry()">+ Add FK Config</button>';
        html += '<p class="fk-hint">Configure behavior for FK fields found in the column mapping. ' +
            '"Create if missing" uses get_or_create() instead of get().</p>';

        editorContainer.innerHTML = html;
    }

    function renderCard(index, entry, fkPrefixes) {
        var toggleId = "fk-create-" + index;
        var html = '<div class="fk-card">';

        // Header
        html += '<div class="fk-card-header">';
        html += '<span class="fk-card-header-label">FK Field</span>';
        html += '<input type="text" class="fk-card-field-input" list="fk-prefixes-list" ' +
            'placeholder="e.g. semester" value="' + escapeAttr(entry.fkField) + '" ' +
            'onchange="window._fkConfigEditor.updateField(' + index + ', this.value)" ' +
            'oninput="window._fkConfigEditor.updateField(' + index + ', this.value)">';
        html += '<button type="button" class="fk-card-remove-btn" title="Remove FK config" ' +
            'onclick="window._fkConfigEditor.removeEntry(' + index + ')">\u00d7</button>';
        html += "</div>";

        // Body
        html += '<div class="fk-card-body">';

        // Toggle
        html += '<div class="fk-toggle-row">';
        html += '<input type="checkbox" id="' + toggleId + '" ' +
            (entry.createIfMissing ? "checked " : "") +
            'onchange="window._fkConfigEditor.toggleCreate(' + index + ', this.checked)">';
        html += '<label for="' + toggleId + '">Create if missing</label>';
        html += "</div>";

        // Defaults
        html += '<div class="fk-defaults-section">';
        html += '<div class="fk-defaults-label">Defaults (applied when creating)</div>';
        html += '<div class="fk-defaults-rows">';

        if (entry.defaults.length === 0) {
            html += '<div style="font-size:0.8125rem;color:var(--color-base-400,#9ca3af);padding:4px 0;">No defaults set.</div>';
        } else {
            for (var d = 0; d < entry.defaults.length; d++) {
                html += renderDefaultRow(index, d, entry.defaults[d]);
            }
        }

        html += "</div>"; // .fk-defaults-rows
        html += '<button type="button" class="fk-add-default-btn" ' +
            'onclick="window._fkConfigEditor.addDefault(' + index + ')">+ Add Default</button>';
        html += "</div>"; // .fk-defaults-section
        html += "</div>"; // .fk-card-body
        html += "</div>"; // .fk-card

        // Datalist for FK prefixes (one per editor is enough, rendered once)
        if (index === 0) {
            html += '<datalist id="fk-prefixes-list">';
            for (var p = 0; p < fkPrefixes.length; p++) {
                html += '<option value="' + escapeAttr(fkPrefixes[p]) + '">';
            }
            html += "</datalist>";
        }

        return html;
    }

    function renderDefaultRow(entryIndex, defaultIndex, def) {
        return (
            '<div class="fk-defaults-row">' +
            '<input type="text" class="fk-defaults-input" placeholder="Field name" ' +
            'value="' + escapeAttr(def.key) + '" ' +
            'onchange="window._fkConfigEditor.updateDefaultKey(' + entryIndex + "," + defaultIndex + ', this.value)" ' +
            'oninput="window._fkConfigEditor.updateDefaultKey(' + entryIndex + "," + defaultIndex + ', this.value)">' +
            '<span class="fk-defaults-arrow">\u2192</span>' +
            '<input type="text" class="fk-defaults-input" placeholder="Value" ' +
            'value="' + escapeAttr(def.value) + '" ' +
            'onchange="window._fkConfigEditor.updateDefaultValue(' + entryIndex + "," + defaultIndex + ', this.value)" ' +
            'oninput="window._fkConfigEditor.updateDefaultValue(' + entryIndex + "," + defaultIndex + ', this.value)">' +
            '<button type="button" class="fk-defaults-remove-btn" title="Remove default" ' +
            'onclick="window._fkConfigEditor.removeDefault(' + entryIndex + "," + defaultIndex + ')">\u00d7</button>' +
            "</div>"
        );
    }

    // ---------------------------------------------------------------
    // Actions
    // ---------------------------------------------------------------

    function addEntry() {
        fkEntries.push({ fkField: "", createIfMissing: false, defaults: [] });
        renderEditor();
        syncToHidden();
        var cards = editorContainer.querySelectorAll(".fk-card");
        if (cards.length > 0) {
            var lastCard = cards[cards.length - 1];
            var input = lastCard.querySelector(".fk-card-field-input");
            if (input) input.focus();
        }
    }

    function removeEntry(index) {
        fkEntries.splice(index, 1);
        renderEditor();
        syncToHidden();
    }

    function updateField(index, value) {
        fkEntries[index].fkField = value;
        syncToHidden();
    }

    function toggleCreate(index, checked) {
        fkEntries[index].createIfMissing = checked;
        syncToHidden();
    }

    function addDefault(entryIndex) {
        fkEntries[entryIndex].defaults.push({ key: "", value: "" });
        renderEditor();
        syncToHidden();
        var cards = editorContainer.querySelectorAll(".fk-card");
        if (cards[entryIndex]) {
            var rows = cards[entryIndex].querySelectorAll(".fk-defaults-row");
            if (rows.length > 0) {
                var lastRow = rows[rows.length - 1];
                var input = lastRow.querySelector(".fk-defaults-input");
                if (input) input.focus();
            }
        }
    }

    function removeDefault(entryIndex, defaultIndex) {
        fkEntries[entryIndex].defaults.splice(defaultIndex, 1);
        renderEditor();
        syncToHidden();
    }

    function updateDefaultKey(entryIndex, defaultIndex, value) {
        fkEntries[entryIndex].defaults[defaultIndex].key = value;
        syncToHidden();
    }

    function updateDefaultValue(entryIndex, defaultIndex, value) {
        fkEntries[entryIndex].defaults[defaultIndex].value = value;
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
                var obj = JSON.parse(hiddenTextarea.value);
                hiddenTextarea.value = JSON.stringify(obj, null, 2);
            } catch (e) { /* leave as-is */ }
            renderEditor();
        }
    }

    function reparseFromTextarea() {
        try {
            var obj = JSON.parse(hiddenTextarea.value || "{}");
            fkEntries = parseConfig(obj);
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
        for (var i = 0; i < fkEntries.length; i++) {
            var entry = fkEntries[i];
            var fk = entry.fkField.trim();
            if (!fk) continue;

            var config = {
                create_if_missing: entry.createIfMissing,
            };

            var defaults = {};
            for (var d = 0; d < entry.defaults.length; d++) {
                var k = entry.defaults[d].key.trim();
                var v = entry.defaults[d].value.trim();
                if (k) {
                    // Try to parse boolean/number values
                    if (v === "true") defaults[k] = true;
                    else if (v === "false") defaults[k] = false;
                    else if (v !== "" && !isNaN(Number(v))) defaults[k] = Number(v);
                    else defaults[k] = v;
                }
            }
            config.defaults = defaults;

            obj[fk] = config;
        }
        hiddenTextarea.value = JSON.stringify(obj);
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

    window._fkConfigEditor = {
        addEntry: addEntry,
        removeEntry: removeEntry,
        updateField: updateField,
        toggleCreate: toggleCreate,
        addDefault: addDefault,
        removeDefault: removeDefault,
        updateDefaultKey: updateDefaultKey,
        updateDefaultValue: updateDefaultValue,
        toggleRaw: toggleRaw,
    };

    // Init on DOMContentLoaded
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", init);
    } else {
        init();
    }
})();
