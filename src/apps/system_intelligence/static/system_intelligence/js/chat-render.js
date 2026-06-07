(function () {
  const app = window.SystemIntelligenceChat;

  app.renderConversations = function () {
    app.els.list.replaceChildren();
    app.state.conversations.forEach((conversation) => {
      const row = document.createElement("div");
      row.className = "si-conversation" + (conversation.id === app.state.currentId ? " is-active" : "");
      const actions = document.createElement("div");
      actions.className = "si-conversation-actions";
      const rename = app.button("si-conversation-action", "Edit", () => app.renameConversation(conversation));
      rename.setAttribute("aria-label", `Rename ${conversation.title}`);
      rename.title = "Rename";
      const remove = app.button("si-conversation-action si-conversation-action-danger", "Del", () =>
        app.deleteConversation(conversation.id),
      );
      remove.setAttribute("aria-label", `Delete ${conversation.title}`);
      remove.title = "Delete";
      actions.append(rename, remove);
      row.append(
        app.button("si-conversation-title", conversation.title, () => app.selectConversation(conversation.id)),
        actions,
      );
      app.els.list.append(row);
    });
  };

  app.renderMessages = function (messages) {
    app.els.messages.replaceChildren();
    if (!messages.length) {
      app.renderEmpty();
      return;
    }
    messages.forEach((message) => {
      app.appendMessage(message.role, message.content);
      if (message.role === "assistant") {
        (message.tool_calls || []).forEach((tool) => app.els.messages.append(app.renderToolCall(tool)));
        (message.action_requests || []).forEach((action) => app.els.messages.append(app.renderActionCard(action)));
      }
    });
    app.scrollMessages();
  };

  app.renderEmpty = function () {
    app.els.messages.replaceChildren();
    const empty = document.createElement("div");
    empty.className = "si-chat-empty";
    const title = document.createElement("h3");
    title.textContent = "Ask about members, events, CMS, projects, email, or analytics.";
    const copy = document.createElement("p");
    copy.textContent = "Responses can include tool results, approval requests, previews, and exports.";
    empty.append(title, copy);
    app.els.messages.append(empty);
  };

  app.appendMessage = function (role, content) {
    app.els.messages.querySelector(".si-chat-empty")?.remove();
    const article = document.createElement("article");
    article.className = `si-message si-message-${role}`;
    const body = document.createElement("div");
    body.className = "si-message-body";
    app.renderRichText(body, content || "");
    article.append(body);
    app.els.messages.append(article);
    app.scrollMessages();
    return { article, body, text: content || "" };
  };

  app.renderToolCall = function (tool) {
    const node = document.createElement("div");
    node.className = "si-tool-call";
    const name = tool.name || "tool";
    const preview = tool.result_preview || tool.result || "";
    node.textContent = preview ? `${name}: ${preview}` : name;
    return node;
  };

  app.renderActionCard = function (action) {
    const node = document.createElement("section");
    node.className = "si-action-card";
    node.dataset.actionId = action.id;
    const title = document.createElement("h4");
    title.textContent = `${action.title || "Action request"} (${action.status || "pending"})`;
    const summary = document.createElement("p");
    summary.textContent = action.summary || action.failure_notice || "Review this proposed change.";
    const diff = document.createElement("pre");
    diff.textContent = JSON.stringify(action.comparison || action.diff || [], null, 2);
    node.append(title, summary, diff, app.renderActionButtons(action));
    return node;
  };

  app.renderActionButtons = function (action) {
    const buttons = document.createElement("div");
    buttons.className = "si-action-buttons";
    if (action.preview_url) buttons.append(app.link(action.preview_url, "Preview"));
    buttons.append(app.link(app.urlFor("fullPreview", action.id), "Full Preview"));
    if (action.status === "pending") {
      buttons.append(app.button("", "Approve", () => app.updateAction(action, "approve")));
      buttons.append(app.button("", "Reject", () => app.updateAction(action, "reject")));
    }
    return buttons;
  };

  app.renderRichText = function (container, text) {
    container.replaceChildren();
    const pattern =
      /\[([^\]]+)\]\(\/admin\/system-intelligence\/exports\/([0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12})\/download\/\)/gi;
    let index = 0;
    let match = pattern.exec(text);
    while (match) {
      container.append(document.createTextNode(text.slice(index, match.index)));
      container.append(app.link(app.urlFor("exportDownload", match[2]), match[1]));
      index = pattern.lastIndex;
      match = pattern.exec(text);
    }
    container.append(document.createTextNode(text.slice(index)));
  };
})();
