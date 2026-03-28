(function () {
    "use strict";

    var utils = window.SheetsJsonEditorUtils;
    var renderer = window.SheetsFkConfigRenderer;
    var fkEntries = [];
    var hiddenTextarea = null;
    var editorContainer = null;
    var rawMode = false;

    function init() {
        hiddenTextarea = document.getElementById("id_fk_config");
        if (!hiddenTextarea) return;
        fkEntries = parseConfig(window.FK_CONFIG_INITIAL || {});
        utils.hideFieldAndLabel(hiddenTextarea);
        editorContainer = utils.createEditorContainer(hiddenTextarea, "fk-config-editor");
        renderer.renderEditor(editorContainer, rawMode, fkEntries);
        var form = hiddenTextarea.closest("form");
        if (form) form.addEventListener("submit", syncToHidden);
    }

    function parseConfig(initial) {
        return Object.keys(initial).map(function (fkField) {
            var cfg = initial[fkField] || {};
            var defaults = [];
            if (cfg.defaults && typeof cfg.defaults === "object") {
                Object.keys(cfg.defaults).forEach(function (key) { defaults.push({ key: key, value: String(cfg.defaults[key]) }); });
            }
            return { fkField: fkField, createIfMissing: !!cfg.create_if_missing, defaults: defaults };
        });
    }

    function render() { renderer.renderEditor(editorContainer, rawMode, fkEntries); }
    function addEntry() { fkEntries.push({ fkField: "", createIfMissing: false, defaults: [] }); render(); syncToHidden(); focusLast(".fk-card", ".fk-card-field-input"); }
    function removeEntry(index) { fkEntries.splice(index, 1); render(); syncToHidden(); }
    function updateField(index, value) { fkEntries[index].fkField = value; syncToHidden(); }
    function toggleCreate(index, checked) { fkEntries[index].createIfMissing = checked; syncToHidden(); }
    function addDefault(entryIndex) { fkEntries[entryIndex].defaults.push({ key: "", value: "" }); render(); syncToHidden(); focusDefaultRow(entryIndex); }
    function removeDefault(entryIndex, defaultIndex) { fkEntries[entryIndex].defaults.splice(defaultIndex, 1); render(); syncToHidden(); }
    function updateDefaultKey(entryIndex, defaultIndex, value) { fkEntries[entryIndex].defaults[defaultIndex].key = value; syncToHidden(); }
    function updateDefaultValue(entryIndex, defaultIndex, value) { fkEntries[entryIndex].defaults[defaultIndex].value = value; syncToHidden(); }

    function toggleRaw() {
        if (rawMode) {
            try {
                fkEntries = parseConfig(JSON.parse(hiddenTextarea.value || "{}"));
                rawMode = false;
                hiddenTextarea.style.display = "none";
                render();
            } catch (e) {
                alert("Invalid JSON. Please fix the JSON before switching to visual mode.");
            }
            return;
        }
        syncToHidden();
        rawMode = true;
        utils.showTextarea(hiddenTextarea);
        try { hiddenTextarea.value = JSON.stringify(JSON.parse(hiddenTextarea.value), null, 2); } catch (e) {}
        render();
    }

    function syncToHidden() {
        var obj = {};
        for (var i = 0; i < fkEntries.length; i++) {
            var entry = fkEntries[i];
            var fkField = entry.fkField.trim();
            if (!fkField) continue;
            obj[fkField] = { create_if_missing: entry.createIfMissing, defaults: buildDefaults(entry.defaults) };
        }
        hiddenTextarea.value = JSON.stringify(obj);
    }

    function buildDefaults(defaultsList) {
        var defaults = {};
        for (var i = 0; i < defaultsList.length; i++) {
            var key = defaultsList[i].key.trim();
            var value = defaultsList[i].value.trim();
            if (!key) continue;
            defaults[key] = value === "true" ? true : value === "false" ? false : value !== "" && !isNaN(Number(value)) ? Number(value) : value;
        }
        return defaults;
    }

    function focusLast(cardSelector, inputSelector) {
        var cards = editorContainer.querySelectorAll(cardSelector);
        var input = cards.length ? cards[cards.length - 1].querySelector(inputSelector) : null;
        if (input) input.focus();
    }

    function focusDefaultRow(entryIndex) {
        var cards = editorContainer.querySelectorAll(".fk-card");
        var rows = cards[entryIndex] ? cards[entryIndex].querySelectorAll(".fk-defaults-row") : [];
        var input = rows.length ? rows[rows.length - 1].querySelector(".fk-defaults-input") : null;
        if (input) input.focus();
    }

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
    if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", init);
    else init();
})();
