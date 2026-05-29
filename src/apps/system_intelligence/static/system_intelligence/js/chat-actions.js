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

  app.sendMessage = async function (text) {
    if (!text || app.state.streaming) return;
    const conversationId = await app.ensureConversation();
    app.showAlert("");
    app.appendMessage("user", text);
    const assistant = app.appendMessage("assistant", "");
    app.setStreaming(true);
    app.setStatus("Thinking");
    try {
      const response = await fetch(app.urlFor("send", conversationId), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": app.csrfToken() },
        body: JSON.stringify({ message: text }),
      });
      await app.readStream(response, assistant);
      await app.loadConversations(conversationId);
    } catch (error) {
      app.showAlert(error.message);
    } finally {
      app.setStreaming(false);
      app.setStatus(app.state.mode === "plan" ? "Plan mode" : "Ready");
      app.els.input.focus();
    }
  };

  app.runCommand = async function (command, args) {
    const conversationId = await app.ensureConversation();
    app.showAlert("");
    const response = await fetch(app.urlFor("command", conversationId), {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": app.csrfToken() },
      body: JSON.stringify({ command, args: args || "" }),
    });
    if ((response.headers.get("content-type") || "").includes("text/event-stream")) {
      const assistant = app.appendMessage("assistant", "");
      app.setStreaming(true);
      await app.readStream(response, assistant);
      app.setStreaming(false);
      await app.selectConversation(conversationId);
      return;
    }
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.error || "Command failed.");
    if (payload.mode) app.setMode(payload.mode);
    if (payload.title) app.els.title.textContent = payload.title;
    app.setStatus(payload.message || "Done");
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
    const payload = await app.fetchJson(app.urlFor(operation, action.id), { method: "POST", body: "{}" });
    document.querySelector(`[data-action-id="${action.id}"]`)?.replaceWith(app.renderActionCard(payload.action_request));
  };

  app.readStream = async function (response, assistant) {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}));
      throw new Error(payload.error || "Stream failed.");
    }
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop();
      events.forEach((eventText) => app.handleStreamEvent(eventText, assistant));
    }
    if (buffer.trim()) app.handleStreamEvent(buffer, assistant);
  };

  app.handleStreamEvent = function (eventText, assistant) {
    const lines = eventText.split("\n");
    const event = (lines.find((line) => line.startsWith("event: ")) || "event: message").slice(7);
    const data = lines.filter((line) => line.startsWith("data: ")).map((line) => line.slice(6)).join("\n");
    const payload = data ? JSON.parse(data) : {};
    if (event === "text") {
      assistant.text += payload.chunk || "";
      app.renderRichText(assistant.body, assistant.text);
    } else if (event === "tool_call") {
      app.els.messages.append(app.renderToolCall(payload));
    } else if (event === "action_request") {
      app.els.messages.append(app.renderActionCard(payload));
    } else if (event === "context") {
      app.setStatus(`Context: ${payload.preparedMessageCount || 0} messages`);
    } else if (event === "usage") {
      app.setStatus(`Tokens: ${payload.totalTokens || 0}`);
    } else if (event === "error") {
      app.renderRichText(assistant.body, payload.error || "The assistant could not complete this turn.");
      app.showAlert(payload.error || "The assistant could not complete this turn.");
    } else if (event === "done") {
      if (payload.title) app.els.title.textContent = payload.title;
      (payload.action_requests || []).forEach((action) => {
        if (!document.querySelector(`[data-action-id="${action.id}"]`)) app.els.messages.append(app.renderActionCard(action));
      });
    }
    app.scrollMessages();
  };
})();
