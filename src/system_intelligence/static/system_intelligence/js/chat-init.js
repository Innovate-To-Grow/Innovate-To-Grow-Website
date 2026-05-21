(function () {
  const app = window.SystemIntelligenceChat;

  app.els.form.addEventListener("submit", (event) => {
    event.preventDefault();
    const text = app.els.input.value.trim();
    if (!text) return;
    app.els.input.value = "";
    app.resizeInput();
    app.sendMessage(text);
  });

  app.els.input.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      app.els.form.requestSubmit();
    }
  });

  app.els.input.addEventListener("input", app.resizeInput);
  app.setSidebarCollapsed(app.state.sidebarCollapsed);
  app.els.sidebarToggle.addEventListener("click", app.toggleSidebar);
  document.querySelector("[data-si-new-chat]").addEventListener("click", app.createConversation);
  document.querySelector("[data-si-rename]").addEventListener("click", () => {
    const conversation = app.state.conversations.find((item) => item.id === app.state.currentId);
    if (conversation) app.renameConversation(conversation);
  });
  document.querySelectorAll("[data-si-command]").forEach((node) => {
    node.addEventListener("click", () => app.runCommand(node.dataset.siCommand).catch((error) => app.showAlert(error.message)));
  });
  app.els.plan.addEventListener("change", () => {
    const command = app.els.plan.checked ? "plan" : "exit-plan";
    app.runCommand(command).catch((error) => {
      app.els.plan.checked = !app.els.plan.checked;
      app.showAlert(error.message);
    });
  });

  app.loadConversations().catch((error) => app.showAlert(error.message));
})();
