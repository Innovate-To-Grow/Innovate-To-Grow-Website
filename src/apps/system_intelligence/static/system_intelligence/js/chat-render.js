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

  // The agent is instructed (APPROVAL_INSTRUCTION) to flag ambiguous edits with
  // these two headings and a numbered list of options. Render that shape as an
  // information card with clickable choices instead of a plain chat bubble.
  const CURRENT_STATE_RE = /^\s*(?:#{1,6}\s*)?\**\s*Current state:\s*\**\s*$/im;
  const QUESTIONS_RE = /^\s*(?:#{1,6}\s*)?\**\s*Questions before I proceed:\s*\**\s*$/im;
  const CHOICE_RE = /^\s*(\d+)[.)]\s+(.*)$/;

  app.parseClarification = function (text) {
    const questionsMatch = QUESTIONS_RE.exec(text);
    if (!questionsMatch) return null;
    const stateMatch = CURRENT_STATE_RE.exec(text);
    const questionsStart = questionsMatch.index;
    const stateStart = stateMatch && stateMatch.index < questionsStart ? stateMatch.index : -1;

    const preamble = text.slice(0, stateStart >= 0 ? stateStart : questionsStart).trim();
    const currentState =
      stateStart >= 0 ? text.slice(stateStart + stateMatch[0].length, questionsStart).trim() : "";
    const questionsBody = text.slice(questionsStart + questionsMatch[0].length);

    const choices = [];
    const intro = [];
    questionsBody.split(/\r?\n/).forEach((line) => {
      const choice = CHOICE_RE.exec(line);
      if (choice) {
        choices.push({ number: choice[1], ...app.splitChoiceLine(choice[2]) });
      } else if (choices.length && line.trim()) {
        const last = choices[choices.length - 1];
        last.description = `${last.description} ${line.trim()}`.trim();
      } else if (line.trim()) {
        intro.push(line.trim());
      }
    });
    return { preamble, currentState, questions: intro.join("\n"), choices };
  };

  app.splitChoiceLine = function (line) {
    const bold = /^\s*\*\*(.+?)\*\*\s*[:\-–—]?\s*(.*)$/.exec(line);
    if (bold) return { title: bold[1].trim(), description: app.stripInlineMarkdown(bold[2]) };
    return { title: app.stripInlineMarkdown(line), description: "" };
  };

  app.stripInlineMarkdown = function (text) {
    return String(text || "")
      .replace(/\*\*(.+?)\*\*/g, "$1")
      .replace(/`([^`]+)`/g, "$1")
      .trim();
  };

  app.renderClarificationCard = function (container, parsed) {
    const card = document.createElement("section");
    card.className = "si-clarification-card";
    const heading = document.createElement("h4");
    heading.textContent = "Clarification needed";
    card.append(heading);
    if (parsed.preamble) card.append(app.clarificationBlock("", parsed.preamble));
    if (parsed.currentState) card.append(app.clarificationBlock("Current state", parsed.currentState));
    card.append(app.clarificationBlock("Questions before I proceed", parsed.questions));
    if (parsed.choices.length) {
      const list = document.createElement("div");
      list.className = "si-clarification-choices";
      parsed.choices.forEach((choice) => list.append(app.renderChoiceButton(choice)));
      card.append(list);
    }
    container.append(card);
  };

  app.clarificationBlock = function (label, text) {
    const block = document.createElement("div");
    block.className = "si-clarification-block";
    if (label) {
      const title = document.createElement("div");
      title.className = "si-clarification-label";
      title.textContent = label;
      block.append(title);
    }
    const body = document.createElement("div");
    body.className = "si-clarification-text";
    app.renderMarkdownLite(body, text);
    block.append(body);
    return block;
  };

  app.renderChoiceButton = function (choice) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "si-clarification-choice";
    button.dataset.siChoice = choice.number;
    button.disabled = Boolean(app.state.streaming);
    const number = document.createElement("span");
    number.className = "si-clarification-choice-number";
    number.textContent = choice.number;
    const label = document.createElement("span");
    label.className = "si-clarification-choice-label";
    const title = document.createElement("strong");
    title.textContent = choice.title;
    label.append(title);
    if (choice.description) {
      const description = document.createElement("span");
      description.className = "si-clarification-choice-description";
      description.textContent = choice.description;
      label.append(description);
    }
    button.append(number, label);
    button.addEventListener("click", () => app.sendMessage(`Option ${choice.number}: ${choice.title}`));
    return button;
  };

  // Text nodes with line breaks preserved and **bold** rendered; nothing else
  // is interpreted so model output can never inject markup.
  app.renderMarkdownLite = function (container, text) {
    String(text || "")
      .split(/\r?\n/)
      .forEach((line, index) => {
        if (index) container.append(document.createElement("br"));
        const parts = line.split(/\*\*(.+?)\*\*/);
        parts.forEach((part, partIndex) => {
          if (!part) return;
          if (partIndex % 2) {
            const strong = document.createElement("strong");
            strong.textContent = part;
            container.append(strong);
          } else {
            container.append(document.createTextNode(part));
          }
        });
      });
  };

  app.renderRichText = function (container, text) {
    container.replaceChildren();
    const clarification = app.parseClarification(text);
    if (clarification) {
      app.renderClarificationCard(container, clarification);
      return;
    }
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
