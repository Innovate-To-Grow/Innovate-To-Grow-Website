(function () {
    if (window.I2GMaterialWebAdminInitialized) return;
    window.I2GMaterialWebAdminInitialized = true;

    var modules = [
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/textfield/outlined-text-field.js/+esm",
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/select/outlined-select.js/+esm",
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/select/select-option.js/+esm",
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/switch/switch.js/+esm",
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/checkbox/checkbox.js/+esm",
        "https://cdn.jsdelivr.net/npm/@material/web@2.4.1/radio/radio.js/+esm",
    ];

    function dispatchNativeEvent(nativeField, type) {
        nativeField.dispatchEvent(new Event(type, { bubbles: true }));
    }

    function shouldSkipField(field) {
        if (!field || field.dataset.i2gMdSkip === "1") return true;
        if (field.closest("[data-i2g-md-skip]")) return true;
        // Never touch the hidden inline-formset template. Unfold clones it and then re-writes the
        // row's innerHTML to substitute the form index, which preserves attributes but drops the
        // md-* elements' non-reflecting Lit properties and every listener — leaving a new row whose
        // native input is hidden (opacity:0; pointer-events:none) and whose Material control is
        // decorative, so anything typed into an added Contact Email/Phone row was silently discarded.
        if (field.closest(".empty-form")) return true;
        // Keyed off the native field, not the wrapper class: a cloned row carries the wrapper's
        // "--enhanced" class as an attribute but has no live wiring, so it must be re-enhanced.
        if (field.dataset.i2gMdWired === "1") return true;
        if (field.classList.contains("select2-hidden-accessible")) return true;
        if (field.classList.contains("admin-autocomplete")) return true;
        if (field.classList.contains("vForeignKeyRawIdAdminField")) return true;
        if (field.classList.contains("code-editor-field")) return true;
        if (field.classList.contains("django_ckeditor_5")) return true;
        if (field.closest(".CodeMirror")) return true;
        if (field.closest(".ck-editor")) return true;
        if (field.name === "manual_emails") return true;
        if (field.id === "id_body" && document.querySelector('input[name="body_format"]')) return true;
        if (field.type === "hidden" || field.type === "submit" || field.type === "button") return true;
        if (field.type === "reset" || field.type === "file" || field.type === "image") return true;
        if (field.type === "color" || field.type === "date" || field.type === "time") return true;
        if (field.tagName === "SELECT" && field.multiple) return true;
        return false;
    }

    function ensureWrapper(field) {
        if (field.parentElement && field.parentElement.matches("[data-i2g-md-field]")) {
            var existing = field.parentElement;
            // "--enhanced" on a field that is not wired means this wrapper arrived via
            // cloneNode/innerHTML (an added inline row): it carries the markup but none of the
            // wiring, so drop the dead md-* elements and let this pass build live ones. A wrapper
            // without the class is pre-rendered markup (admin/material_password_widget.html) and is
            // left intact so its template attributes survive.
            if (existing.classList.contains("i2g-md-field--enhanced")) {
                existing.classList.remove("i2g-md-field--enhanced", "i2g-md-toggle");
                existing
                    .querySelectorAll(".i2g-md-field__component, .i2g-md-toggle__component")
                    .forEach(function (stale) {
                        stale.remove();
                    });
            }
            return existing;
        }

        var wrapper = document.createElement("span");
        wrapper.className = "i2g-md-field";
        wrapper.dataset.i2gMdField = "1";
        field.parentNode.insertBefore(wrapper, field);
        wrapper.appendChild(field);
        return wrapper;
    }

    function hideNativeField(field) {
        field.classList.add("i2g-md-field__native");
        field.dataset.i2gMdWired = "1";
        field.tabIndex = -1;
        if (field.required) {
            field.dataset.i2gMdRequired = "1";
            field.required = false;
        }
    }

    function syncFormSubmit(nativeField, syncToNative) {
        if (!nativeField.form) return;
        nativeField.form.addEventListener("submit", syncToNative);
    }

    function getFieldLabel(nativeField) {
        if (!nativeField.id) return "";

        var label = document.querySelector('label[for="' + CSS.escape(nativeField.id) + '"]');
        if (!label) return "";

        return (label.textContent || "").replace(/\*/g, "").trim();
    }

    function enhanceTextField(nativeField) {
        var wrapper = ensureWrapper(nativeField);
        var materialField = wrapper.querySelector("md-outlined-text-field");

        if (!materialField) {
            materialField = document.createElement("md-outlined-text-field");
            materialField.className = "i2g-md-field__component";
            wrapper.appendChild(materialField);
        }

        materialField.type = nativeField.tagName === "TEXTAREA" ? "textarea" : nativeField.type || "text";
        materialField.value = nativeField.value || "";
        materialField.disabled = nativeField.disabled;
        materialField.required = nativeField.required;
        materialField.label = getFieldLabel(nativeField);
        materialField.placeholder = nativeField.getAttribute("placeholder") || "";

        if (nativeField.maxLength > 0) materialField.maxLength = nativeField.maxLength;
        if (nativeField.min) materialField.min = nativeField.min;
        if (nativeField.max) materialField.max = nativeField.max;
        if (nativeField.step) materialField.step = nativeField.step;
        if (nativeField.rows) materialField.rows = nativeField.rows;

        function syncToNative() {
            nativeField.value = materialField.value || "";
            dispatchNativeEvent(nativeField, "input");
            dispatchNativeEvent(nativeField, "change");
        }

        materialField.addEventListener("input", syncToNative);
        materialField.addEventListener("change", syncToNative);
        nativeField.addEventListener("change", function () {
            materialField.value = nativeField.value || "";
        });
        syncFormSubmit(nativeField, syncToNative);
        hideNativeField(nativeField);
        wrapper.classList.add("i2g-md-field--enhanced");
    }

    function enhanceSelect(nativeField) {
        var wrapper = ensureWrapper(nativeField);
        var materialField = document.createElement("md-outlined-select");
        materialField.className = "i2g-md-field__component";
        materialField.disabled = nativeField.disabled;
        materialField.required = nativeField.required;
        materialField.label = getFieldLabel(nativeField);

        Array.from(nativeField.options).forEach(function (option) {
            var materialOption = document.createElement("md-select-option");
            materialOption.value = option.value;
            materialOption.disabled = option.disabled;
            materialOption.selected = option.selected;

            var headline = document.createElement("div");
            headline.slot = "headline";
            headline.textContent = option.textContent;
            materialOption.appendChild(headline);
            materialField.appendChild(materialOption);
        });

        // Assign .value only once the options exist and the element is connected — md-outlined-select
        // resolves a value against its own options, so setting it on an empty, detached element left
        // the control reporting "" and the submit handler then wrote that back over the native
        // <select>, blanking email_type / region.
        wrapper.appendChild(materialField);
        materialField.value = nativeField.value || "";

        function syncToNative() {
            var next = materialField.value || "";
            // Only copy a value the native <select> actually offers; otherwise a Material control
            // that failed to upgrade would set selectedIndex = -1 and submit an empty value.
            var offered = Array.from(nativeField.options).some(function (option) {
                return option.value === next;
            });
            if (!offered) return;
            nativeField.value = next;
            dispatchNativeEvent(nativeField, "change");
        }

        materialField.addEventListener("change", syncToNative);
        nativeField.addEventListener("change", function () {
            materialField.value = nativeField.value || "";
        });
        syncFormSubmit(nativeField, syncToNative);
        hideNativeField(nativeField);
        wrapper.classList.add("i2g-md-field--enhanced");
    }

    function enhanceToggle(nativeField) {
        var wrapper = ensureWrapper(nativeField);
        var isSwitch = nativeField.classList.contains("appearance-none") && nativeField.classList.contains("w-8");
        var materialField = document.createElement(isSwitch ? "md-switch" : "md-checkbox");
        materialField.className = "i2g-md-toggle__component";
        materialField.selected = nativeField.checked;
        materialField.checked = nativeField.checked;
        materialField.disabled = nativeField.disabled;

        function syncToNative() {
            nativeField.checked = isSwitch ? materialField.selected : materialField.checked;
            dispatchNativeEvent(nativeField, "change");
        }

        materialField.addEventListener("change", syncToNative);
        nativeField.addEventListener("change", function () {
            materialField.selected = nativeField.checked;
            materialField.checked = nativeField.checked;
        });
        wrapper.appendChild(materialField);
        hideNativeField(nativeField);
        wrapper.classList.add("i2g-md-field--enhanced", "i2g-md-toggle");
    }

    function enhanceRadio(nativeField) {
        var wrapper = ensureWrapper(nativeField);
        var materialField = document.createElement("md-radio");
        materialField.className = "i2g-md-toggle__component";
        materialField.checked = nativeField.checked;
        materialField.disabled = nativeField.disabled;
        materialField.name = nativeField.name + "__material";

        function syncToNative() {
            nativeField.checked = materialField.checked;
            if (nativeField.checked) {
                var root = nativeField.form || document;
                root.querySelectorAll('input[type="radio"][name="' + CSS.escape(nativeField.name) + '"]').forEach(function (radio) {
                    if (radio !== nativeField) radio.checked = false;
                    var wrapper = radio.closest("[data-i2g-md-field]");
                    var materialRadio = wrapper && wrapper.querySelector("md-radio");
                    if (materialRadio && radio !== nativeField) materialRadio.checked = false;
                });
            }
            dispatchNativeEvent(nativeField, "change");
        }

        materialField.addEventListener("change", syncToNative);
        nativeField.addEventListener("change", function () {
            materialField.checked = nativeField.checked;
        });
        wrapper.appendChild(materialField);
        hideNativeField(nativeField);
        wrapper.classList.add("i2g-md-field--enhanced", "i2g-md-toggle");
    }

    function enhanceField(field) {
        if (shouldSkipField(field)) return;

        if (field.tagName === "SELECT") {
            enhanceSelect(field);
        } else if (field.type === "checkbox") {
            enhanceToggle(field);
        } else if (field.type === "radio") {
            enhanceRadio(field);
        } else {
            enhanceTextField(field);
        }
    }

    function enhanceFieldSafely(field) {
        // Isolate failures: without this, one throwing field aborted the whole forEach and left the
        // fields already processed hidden behind a Material control while later fields stayed raw.
        try {
            enhanceField(field);
        } catch (error) {
            if (window.console && console.warn) {
                console.warn("i2g admin: could not enhance field", field && field.name, error);
            }
        }
    }

    function enhanceAllFields() {
        document.querySelectorAll("#main input, #main textarea, #main select").forEach(enhanceFieldSafely);
        document.querySelectorAll("[data-i2g-md-field]").forEach(function (wrapper) {
            var field = wrapper.querySelector("input, textarea, select");
            if (field) enhanceFieldSafely(field);
        });
    }

    function watchForNewRows() {
        // Unfold emits formsetGroup:added when "Add another" clones an inline row, and htmx settles
        // paginated inline swaps. Both replace markup without any wiring, so re-run enhancement;
        // shouldSkipField's data-i2g-md-wired check keeps it idempotent for untouched fields.
        document.addEventListener("formsetGroup:added", enhanceAllFields);
        document.addEventListener("formset:added", enhanceAllFields);
        document.body.addEventListener("htmx:afterSettle", enhanceAllFields);
    }

    function loadMaterialWeb() {
        Promise.all(modules.map(function (url) { return import(url); }))
            .then(function () {
                return Promise.all([
                    customElements.whenDefined("md-outlined-text-field"),
                    customElements.whenDefined("md-outlined-select"),
                    customElements.whenDefined("md-select-option"),
                    customElements.whenDefined("md-switch"),
                    customElements.whenDefined("md-checkbox"),
                    customElements.whenDefined("md-radio"),
                ]);
            })
            .then(function () {
                enhanceAllFields();
                watchForNewRows();
            })
            .catch(function (error) {
                // Keep native Django/Unfold controls visible as a safe fallback, but say so — a
                // silent catch made a blocked or slow CDN indistinguishable from a working page.
                if (window.console && console.warn) {
                    console.warn("i2g admin: Material Web components unavailable; using native controls.", error);
                }
            });
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", loadMaterialWeb);
    } else {
        loadMaterialWeb();
    }
})();
