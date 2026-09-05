(function () {
  const app = window.SystemIntelligenceChat;
  const streamTimeoutMs = Math.max(1_000, Number(app.config.streamTimeoutMs) || 180_000);
  const timeoutMessage = "The assistant took too long to respond. Please try again.";

  app.setAssistantStreaming = function (assistant, streaming) {
    assistant.article.classList.toggle("is-streaming", streaming);
    assistant.article.setAttribute("aria-busy", String(streaming));
  };

  app.renderAssistantError = function (assistant, message) {
    app.setAssistantStreaming(assistant, false);
    app.renderRichText(assistant.body, message);
  };

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
    app.setStreaming(true);
    let assistant = null;
    let timeoutId = null;
    let streamCompleted = false;
    try {
      const conversationId = await app.ensureConversation();
      app.setStreaming(true);
      app.showAlert("");
      app.appendMessage("user", text);
      assistant = app.appendMessage("assistant", "");
      app.setAssistantStreaming(assistant, true);
      app.setStatus("Thinking");
      const controller = new AbortController();
      timeoutId = window.setTimeout(() => controller.abort(), streamTimeoutMs);
      const response = await fetch(app.urlFor("send", conversationId), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": app.csrfToken() },
        body: JSON.stringify({ message: text }),
        signal: controller.signal,
      });
      await app.readStream(response, assistant);
      streamCompleted = true;
      await app.loadConversations(conversationId);
    } catch (error) {
      const message = error.name === "AbortError" ? timeoutMessage : error.message;
      if (assistant && !streamCompleted) app.renderAssistantError(assistant, message);
      app.showAlert(streamCompleted ? `The response completed, but the conversation could not refresh. ${message}` : message);
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      app.setStreaming(false);
      app.setStatus(app.state.mode === "plan" ? "Plan mode" : "Ready");
      app.els.input.focus();
    }
  };

  app.runCommand = async function (command, args) {
    if (app.state.streaming) throw new Error("Wait for the current assistant response to finish.");
    app.setStreaming(true);
    let timeoutId = null;
    let assistant = null;
    let streamCompleted = false;
    try {
      const conversationId = await app.ensureConversation();
      app.setStreaming(true);
      app.showAlert("");
      const controller = new AbortController();
      timeoutId = window.setTimeout(() => controller.abort(), streamTimeoutMs);
      const response = await fetch(app.urlFor("command", conversationId), {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", "X-CSRFToken": app.csrfToken() },
        body: JSON.stringify({ command, args: args || "" }),
        signal: controller.signal,
      });
      if ((response.headers.get("content-type") || "").includes("text/event-stream")) {
        assistant = app.appendMessage("assistant", "");
        app.setAssistantStreaming(assistant, true);
        app.setStreaming(true);
        await app.readStream(response, assistant);
        streamCompleted = true;
        await app.selectConversation(conversationId);
        return;
      }
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Command failed.");
      if (payload.mode) app.setMode(payload.mode);
      if (payload.title) app.els.title.textContent = payload.title;
      app.setStatus(payload.message || "Done");
    } catch (error) {
      const normalized = error.name === "AbortError" ? new Error(timeoutMessage) : error;
      if (assistant && !streamCompleted) app.renderAssistantError(assistant, normalized.message);
      if (streamCompleted) {
        throw new Error(`The response completed, but the conversation could not refresh. ${normalized.message}`);
      }
      throw normalized;
    } finally {
      if (timeoutId !== null) window.clearTimeout(timeoutId);
      app.setStreaming(false);
      if (assistant) {
        app.setStatus(app.state.mode === "plan" ? "Plan mode" : "Ready");
      }
    }
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
    const contentType = response.headers.get("content-type") || "";
    if (!contentType.includes("text/event-stream")) {
      if (response.redirected && response.url.includes("/admin/login")) {
        throw new Error("Your admin session expired. Refresh the page and sign in again.");
      }
      throw new Error("The server did not start an assistant response stream.");
    }
    if (!response.body) throw new Error("The assistant response stream is unavailable.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let streamError = "";
    let completed = false;

    const dispatch = function (eventText) {
      const result = app.handleStreamEvent(eventText, assistant);
      if (!result) return;
      if (result.error) streamError = result.error;
      if (result.done) completed = true;
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split(/\r?\n\r?\n/);
      buffer = events.pop();
      events.forEach(dispatch);
    }
    if (buffer.trim()) dispatch(buffer);
    if (streamError) throw new Error(streamError);
    if (!completed) throw new Error("The assistant response ended before it was complete. Please retry.");
  };

  app.handleStreamEvent = function (eventText, assistant) {
    const lines = eventText.replace(/\r\n?/g, "\n").split("\n");
    const eventLine = lines.find((line) => line.startsWith("event:"));
    const event = eventLine ? eventLine.slice(6).trimStart() : "message";
    const dataLines = lines.filter((line) => line.startsWith("data:"));
    if (!dataLines.length) return null;
    const data = dataLines.map((line) => line.slice(5).replace(/^ /, "")).join("\n");
    const payload = data ? JSON.parse(data) : {};
    if (event === "start") {
      app.setStatus("Thinking");
    } else if (event === "text") {
      assistant.article.classList.remove("is-streaming");
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
      const message = payload.error || "The assistant could not complete this turn.";
      app.renderAssistantError(assistant, message);
      app.showAlert(message);
      app.scrollMessages();
      return { event, error: message, done: false };
    } else if (event === "done") {
      app.setAssistantStreaming(assistant, false);
      if (payload.title) app.els.title.textContent = payload.title;
      (payload.action_requests || []).forEach((action) => {
        if (!document.querySelector(`[data-action-id="${action.id}"]`)) app.els.messages.append(app.renderActionCard(action));
      });
    }
    app.scrollMessages();
    return { event, error: "", done: event === "done" };
  };
})();
