(function () {
  const config = JSON.parse(document.getElementById("si-chat-config").textContent);
  const sidebarStorageKey = "system_intelligence_sidebar_collapsed";
  const getStoredSidebarState = function () {
    try {
      return window.localStorage.getItem(sidebarStorageKey) === "true";
    } catch {
      return false;
    }
  };
  const app = {
    config,
    urls: config.urls,
    placeholder: config.uuidPlaceholder,
    state: {
      conversations: [],
      currentId: null,
      mode: "normal",
      sidebarCollapsed: getStoredSidebarState(),
      streaming: false,
    },
    els: {
      shell: document.querySelector("[data-si-root]") || document.getElementById("si-root"),
      list: document.querySelector("[data-si-conversations]"),
      messages: document.querySelector("[data-si-messages]"),
      title: document.querySelector("[data-si-title]"),
      status: document.querySelector("[data-si-status]"),
      alert: document.querySelector("[data-si-alert]"),
      form: document.querySelector("[data-si-form]"),
      input: document.querySelector("[data-si-input]"),
      plan: document.querySelector("[data-si-plan-toggle]"),
      send: document.querySelector("[data-si-send]"),
      sidebarToggle: document.querySelector("[data-si-sidebar-toggle]"),
      sidebarToggleIcon: document.querySelector("[data-si-sidebar-toggle-icon]"),
    },
  };

  app.urlFor = function (name, id) {
    return app.urls[name].replace(app.placeholder, id);
  };

  app.csrfToken = function () {
    return document.querySelector("[name=csrfmiddlewaretoken]").value;
  };

  app.fetchJson = async function (url, options) {
    const response = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": app.csrfToken() },
      ...options,
    });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Request failed.");
    return payload;
  };

  app.setStatus = function (text) {
    app.els.status.textContent = text;
  };

  app.showAlert = function (message) {
    app.els.alert.textContent = message;
    app.els.alert.hidden = !message;
  };

  app.setSidebarCollapsed = function (collapsed) {
    const label = collapsed ? "Expand conversations" : "Collapse conversations";
    app.state.sidebarCollapsed = collapsed;
    app.els.shell.classList.toggle("is-sidebar-collapsed", collapsed);
    app.els.sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    app.els.sidebarToggle.setAttribute("aria-label", label);
    app.els.sidebarToggle.title = label;
    app.els.sidebarToggleIcon.textContent = collapsed ? ">" : "<";
    try {
      window.localStorage.setItem(sidebarStorageKey, String(collapsed));
    } catch {
      return;
    }
  };

  app.toggleSidebar = function () {
    app.setSidebarCollapsed(!app.state.sidebarCollapsed);
  };

  app.setMode = function (mode) {
    app.state.mode = mode || "normal";
    app.els.plan.checked = app.state.mode === "plan";
  };

  app.setStreaming = function (streaming) {
    app.state.streaming = streaming;
    app.els.send.disabled = streaming;
    app.els.input.disabled = streaming;
  };

  app.button = function (className, text, handler) {
    const node = document.createElement("button");
    node.type = "button";
    node.className = className;
    node.textContent = text;
    node.addEventListener("click", handler);
    return node;
  };

  app.safeHref = function (href) {
    // Strip ASCII whitespace and C0 control chars (tab/newline/CR included) before
    // testing the scheme: browsers ignore those when parsing href, so "java\tscript:"
    // would otherwise slip past the scheme check and still execute.
    const value = String(href || "").replace(/[\x00-\x20]+/g, "");
    // Allow only relative URLs and explicit http(s) schemes. Any other scheme
    // (javascript:, data:, vbscript:, ...) is rejected to prevent XSS via href.
    const schemeMatch = /^[a-z][a-z0-9+.-]*:/i.exec(value);
    if (schemeMatch && !/^https?:$/i.test(schemeMatch[0])) {
      return "about:blank";
    }
    return value;
  };

  app.link = function (href, text) {
    const node = document.createElement("a");
    node.href = app.safeHref(href);
    node.textContent = text;
    node.target = "_blank";
    node.rel = "noopener";
    return node;
  };

  app.scrollMessages = function () {
    app.els.messages.scrollTop = app.els.messages.scrollHeight;
  };

  app.resizeInput = function () {
    app.els.input.style.height = "auto";
    app.els.input.style.height = `${Math.min(160, app.els.input.scrollHeight)}px`;
  };

  window.SystemIntelligenceChat = app;
})();
