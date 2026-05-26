(function () {
  "use strict";

  // ─── State ─────────────────────────────────────────────────────────────
  var editors = {};
  var activeLanguage = "html";
  var previewVisible = false;

  var fieldMap = {
    html: "id_html_code",
    javascript: "id_js_code",
    css: "id_css_code",
  };

  // ─── Monaco Initialization ─────────────────────────────────────────────
  function initMonaco() {
    require.config({
      paths: { vs: "https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs" },
    });

    require(["vs/editor/editor.main"], function (monaco) {
      Object.keys(fieldMap).forEach(function (lang) {
        var textarea = document.getElementById(fieldMap[lang]);
        var value = textarea ? textarea.value : "";

        editors[lang] = monaco.editor.create(document.createElement("div"), {
          value: value,
          language: lang,
          theme: "vs-dark",
          automaticLayout: true,
          minimap: { enabled: true },
          fontSize: 13,
          lineNumbers: "on",
          wordWrap: "on",
          tabSize: 2,
          scrollBeyondLastLine: false,
        });

        // Sync to textarea on change
        editors[lang].onDidChangeModelContent(function () {
          if (textarea) {
            textarea.value = editors[lang].getValue();
          }
        });
      });

      // Mount the active editor
      mountEditor(activeLanguage);

      // Keyboard shortcut: Ctrl+Shift+P for preview
      editors[activeLanguage].addCommand(
        monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyP,
        function () {
          togglePreview();
        }
      );
    });
  }

  function mountEditor(lang) {
    var container = document.getElementById("miniapp-monaco-editor");
    if (!container) return;
    container.innerHTML = "";
    if (editors[lang]) {
      container.appendChild(editors[lang].getDomNode());
      editors[lang].layout();
      editors[lang].focus();
    }
  }

  // ─── Tab Switching ─────────────────────────────────────────────────────
  function initTabs() {
    var tabs = document.querySelectorAll(".miniapp-tab");
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        var lang = tab.dataset.lang;
        if (!lang) return;
        tabs.forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        activeLanguage = lang;
        mountEditor(lang);
      });
    });
  }

  // ─── Preview ───────────────────────────────────────────────────────────
  function togglePreview() {
    var pane = document.getElementById("miniapp-preview-pane");
    if (!pane) return;
    previewVisible = !previewVisible;
    pane.style.display = previewVisible ? "flex" : "none";
    if (previewVisible) {
      refreshPreview();
    }
    // Re-layout editors
    Object.values(editors).forEach(function (e) { e.layout(); });
  }

  function refreshPreview() {
    var iframe = document.getElementById("miniapp-preview-iframe");
    if (!iframe) return;

    var html = editors.html ? editors.html.getValue() : "";
    var js = editors.javascript ? editors.javascript.getValue() : "";
    var css = editors.css ? editors.css.getValue() : "";

    var doc =
      "<!DOCTYPE html><html><head><meta charset=\"UTF-8\">" +
      "<style>* { margin: 0; padding: 0; box-sizing: border-box; } " +
      "body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.5; }" +
      css +
      "</style></head><body>" +
      html +
      "<script>" + js + "<\/script></body></html>";

    iframe.srcdoc = doc;
  }

  function initPreview() {
    var btn = document.getElementById("miniapp-preview-btn");
    if (btn) btn.addEventListener("click", togglePreview);

    var closeBtn = document.getElementById("miniapp-close-preview");
    if (closeBtn) closeBtn.addEventListener("click", togglePreview);

    // Device width buttons
    document.querySelectorAll(".miniapp-device-btn").forEach(function (btn) {
      btn.addEventListener("click", function () {
        document.querySelectorAll(".miniapp-device-btn").forEach(function (b) {
          b.classList.remove("active");
        });
        btn.classList.add("active");
        var iframe = document.getElementById("miniapp-preview-iframe");
        if (iframe) iframe.style.maxWidth = btn.dataset.width;
      });
    });
  }

  // ─── Fullscreen ────────────────────────────────────────────────────────
  function initFullscreen() {
    var btn = document.getElementById("miniapp-fullscreen-btn");
    var container = document.getElementById("miniapp-editor-container");
    if (!btn || !container) return;

    btn.addEventListener("click", function () {
      container.classList.toggle("fullscreen");
      Object.values(editors).forEach(function (e) { e.layout(); });
    });

    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && container.classList.contains("fullscreen")) {
        container.classList.remove("fullscreen");
        Object.values(editors).forEach(function (e) { e.layout(); });
      }
    });
  }

  // ─── Schema Builder ────────────────────────────────────────────────────
  function initSchemaBuilder() {
    var container = document.getElementById("miniapp-schema-builder");
    if (!container) return;

    // Find the schema inline fields textarea (from Django inline)
    var schemaTextarea = document.querySelector(
      "#id_data_schema-0-fields, [name='data_schema-0-fields']"
    );
    var fields = [];
    if (schemaTextarea && schemaTextarea.value) {
      try {
        fields = JSON.parse(schemaTextarea.value);
      } catch (e) {
        fields = [];
      }
    }

    var fieldTypes = [
      "text", "integer", "float", "boolean", "date", "datetime", "email", "url", "json"
    ];

    function render() {
      var html = "";
      fields.forEach(function (field, index) {
        html +=
          '<div class="miniapp-schema-field">' +
          '<input type="text" value="' + (field.name || "") + '" placeholder="Field name" data-idx="' + index + '" data-prop="name">' +
          '<select data-idx="' + index + '" data-prop="type">' +
          fieldTypes.map(function (t) {
            return '<option value="' + t + '"' + (field.type === t ? " selected" : "") + '>' + t + '</option>';
          }).join("") +
          '</select>' +
          '<label><input type="checkbox"' + (field.required ? " checked" : "") + ' data-idx="' + index + '" data-prop="required"> Required</label>' +
          '<button type="button" class="miniapp-schema-field-remove" data-idx="' + index + '">✕</button>' +
          '</div>';
      });
      html += '<button type="button" class="miniapp-schema-add-btn">+ Add Field</button>';
      container.innerHTML = html;
      syncToTextarea();
    }

    function syncToTextarea() {
      if (schemaTextarea) {
        schemaTextarea.value = JSON.stringify(fields);
      }
    }

    container.addEventListener("input", function (e) {
      var idx = parseInt(e.target.dataset.idx, 10);
      var prop = e.target.dataset.prop;
      if (isNaN(idx) || !prop) return;
      if (prop === "required") {
        fields[idx][prop] = e.target.checked;
      } else {
        fields[idx][prop] = e.target.value;
      }
      syncToTextarea();
    });

    container.addEventListener("change", function (e) {
      var idx = parseInt(e.target.dataset.idx, 10);
      var prop = e.target.dataset.prop;
      if (isNaN(idx) || !prop) return;
      if (prop === "required") {
        fields[idx][prop] = e.target.checked;
      } else {
        fields[idx][prop] = e.target.value;
      }
      syncToTextarea();
    });

    container.addEventListener("click", function (e) {
      if (e.target.classList.contains("miniapp-schema-field-remove")) {
        var idx = parseInt(e.target.dataset.idx, 10);
        fields.splice(idx, 1);
        render();
      }
      if (e.target.classList.contains("miniapp-schema-add-btn")) {
        fields.push({ name: "", type: "text", required: false });
        render();
      }
    });

    render();
  }

  // ─── Form Submit Sync ──────────────────────────────────────────────────
  function initFormSync() {
    var form = document.querySelector("#miniapp-changelist-form, #content form, form");
    if (!form) return;

    form.addEventListener("submit", function () {
      Object.keys(fieldMap).forEach(function (lang) {
        var textarea = document.getElementById(fieldMap[lang]);
        if (textarea && editors[lang]) {
          textarea.value = editors[lang].getValue();
        }
      });
    });
  }

  // ─── Boot ──────────────────────────────────────────────────────────────
  document.addEventListener("DOMContentLoaded", function () {
    // Only init on the change form (not the list view)
    if (!document.getElementById("miniapp-editor-container")) return;

    initTabs();
    initPreview();
    initFullscreen();
    initSchemaBuilder();
    initFormSync();
    initMonaco();
  });
})();
