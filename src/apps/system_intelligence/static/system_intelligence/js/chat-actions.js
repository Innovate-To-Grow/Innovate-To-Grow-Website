(function () {
  const app = window.SystemIntelligenceChat;

  app.loadConversations = async function (selectId) {
    const payload = await app.fetchJson(app.urls.conversations);
    app.state.conversations = payload.conversations || [];
    app.renderConversations();
    if (selectId) return app.selectConversation(selectId);
    if (!app.state.currentId && app.state.conversations.length) {
      return app.selectConversation(app.state.conversations[0].id);
    }
    if (!app.state.conversations.length) app.renderEmpty();
  };

  app.selectConversation = async function (id) {
    app.state.currentId = id;
    app.renderConversations();
    const payload = await app.fetchJson(app.urlFor("detail", id));
    app.els.title.textContent = payload.title || "New Chat";
    app.setMode(payload.mode);
    app.renderMessages(payload.messages || []);
    app.setStatus(app.state.mode === "plan" ? "Plan mode" : "Ready");
  };

  app.createConversation = async function () {
    const payload = await app.fetchJson(app.urls.newConversation, { method: "POST", body: "{}" });
    await app.loadConversations(payload.id);
    return payload.id;
  };

  app.ensureConversation = function () {
    return app.state.currentId || app.createConversation();
  };

  app.renameConversation = async function (conversation) {
    const title = window.prompt("Rename conversation", conversation.title);
    if (!title || !title.trim()) return;
    const payload = await app.fetchJson(app.urlFor("rename", conversation.id), {
      method: "POST",
      body: JSON.stringify({ title: title.trim() }),
    });
    if (conversation.id === app.state.currentId) app.els.title.textContent = payload.title;
    await app.loadConversations(conversation.id);
  };

  app.deleteConversation = async function (id) {
    if (!window.confirm("Delete this conversation?")) return;
    await app.fetchJson(app.urlFor("delete", id), { method: "POST", body: "{}" });
    if (id === app.state.currentId) app.state.currentId = null;
    await app.loadConversations();
  };

  app.updateAction = async function (action, operation) {
    let payload;
    try {
      payload = await app.fetchJson(app.urlFor(operation, action.id), { method: "POST", body: "{}" });
      app.showAlert("");
    } catch (error) {
      // A refused or failed approval answers with the reason and the request's new state (failed): show both.
      app.showAlert(error.message);
      payload = error.payload;
    }
    if (!payload || !payload.action_request) return;
    document.querySelector(`[data-action-id="${action.id}"]`)?.replaceWith(app.renderActionCard(payload.action_request));
  };
})();
