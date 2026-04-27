(function() {
  'use strict';

  function createStreamEventHandler(ctx) {
    return function(eventType, data) {
      if (eventType === 'text') return handleText(ctx, data);
      if (eventType === 'tool_call') return handleToolCall(ctx, data);
      if (eventType === 'action_request') return handleAction(ctx, data);
      if (eventType === 'context') return handleContext(ctx, data);
      if (eventType === 'usage') return handleUsage(ctx, data);
      if (eventType === 'done') return handleDone(ctx, data);
      if (eventType === 'error') return handleError(ctx, data);
    };
  }

  function ensureBubble(ctx) {
    if (ctx.bubbleStarted) return;
    ctx.bubbleStarted = true;
    if (ctx.toolsContainer) {
      var actives = ctx.toolsContainer.querySelectorAll('.si-tool-call.is-active');
      for (var i = 0; i < actives.length; i++) actives[i].classList.remove('is-active');
    }
    var streamEl = document.getElementById(ctx.streamId);
    if (!streamEl) return;
    ctx.bubbleEl = streamEl.querySelector('.si-msg-bubble');
    if (ctx.bubbleEl) {
      ctx.bubbleEl.classList.remove('si-typing-dots');
      ctx.bubbleEl.innerHTML = '';
    }
  }

  function handleText(ctx, data) {
    ensureBubble(ctx);
    ctx.rawText += data.chunk;
    if (ctx.bubbleEl) ctx.bubbleEl.innerHTML = SI.formatMarkdown(ctx.rawText);
    scroll(ctx);
  }

  function handleToolCall(ctx, data) {
    if (!ctx.toolsContainer) return;
    ctx.toolsContainer.style.display = 'flex';
    ctx.toolsContainer.insertAdjacentHTML('beforeend', SI.renderToolCallPill(data));
    var lastPill = ctx.toolsContainer.lastElementChild;
    if (lastPill) {
      lastPill.classList.add('is-expanded', 'is-active');
      lastPill.style.animation = 'si-tool-enter 0.35s ease both';
    }
    scroll(ctx);
  }

  function handleAction(ctx, data) {
    if (!ctx.actionsContainer) return;
    ctx.actionsContainer.insertAdjacentHTML('beforeend', SI.renderActionRequestCard(data));
    scroll(ctx);
  }

  function handleContext(ctx, data) {
    ctx.contextUsage = data;
    SI.updateContextUsage(data, {state: 'streaming', kind: 'context'});
  }

  function handleUsage(ctx, data) {
    SI.updateContextUsage(data, {state: 'streaming', kind: 'latest', reset: false});
    var usageEl = document.getElementById(ctx.streamId + '-usage');
    var usageText = document.getElementById(ctx.streamId + '-usage-text');
    if (usageEl) usageEl.style.display = '';
    if (usageText) {
      usageText.textContent = (data.inputTokens || 0).toLocaleString() + ' in / ' +
        (data.outputTokens || 0).toLocaleString() + ' out / ' +
        (data.totalTokens || 0).toLocaleString() + ' total';
    }
  }

  function handleDone(ctx, data) {
    if (!ctx.bubbleStarted) {
      ensureBubble(ctx);
      if (ctx.bubbleEl) ctx.bubbleEl.innerHTML = SI.formatMarkdown(ctx.rawText || '(empty response)');
    }
    finalizeAssistantBody(ctx);
    collapseToolPills(ctx.toolsContainer);
    if (data.title) updateConversationTitle(ctx, data.title);
    finalizeUsage(ctx, data.token_usage);
    SI.updateContextUsage(
      {contextUsage: data.context_usage || ctx.contextUsage, latestUsage: data.token_usage},
      {state: 'ready', reset: false}
    );
  }

  function handleError(ctx, data) {
    var streamEl = document.getElementById(ctx.streamId);
    if (streamEl) streamEl.remove();
    ctx.messagesEl.insertAdjacentHTML('beforeend', '<div class="p-3 text-sm text-red-600 bg-red-50 dark:bg-red-900/20 rounded-lg">' + SI.escapeHtml(data.error) + '</div>');
  }

  function finalizeAssistantBody(ctx) {
    if (!ctx.bubbleEl || !SI.isConfirmationInfoMessage || !SI.isConfirmationInfoMessage(ctx.rawText)) return;
    ctx.bubbleEl.outerHTML = SI.renderConfirmationInfoCard(ctx.rawText || '(empty response)');
    ctx.bubbleEl = null;
  }

  function collapseToolPills(container) {
    if (!container) return;
    var pills = container.querySelectorAll('.si-tool-call');
    for (var i = 0; i < pills.length; i++) pills[i].classList.remove('is-expanded', 'is-active');
  }

  function updateConversationTitle(ctx, title) {
    var item = ctx.convoList.querySelector('[data-convo-id="' + SI.activeConvoId + '"] .si-convo-title');
    if (item) item.textContent = title;
  }

  function finalizeUsage(ctx, tokenUsage) {
    var liveUsage = document.getElementById(ctx.streamId + '-usage');
    if (!liveUsage) return;
    liveUsage.classList.remove('si-token-live');
    if (tokenUsage && tokenUsage.totalTokens) {
      liveUsage.innerHTML = SI.renderTokenBadge(tokenUsage).replace(/^<div[^>]*>/, '').replace(/<\/div>$/, '');
      liveUsage.style.display = '';
    }
  }

  function scroll(ctx) {
    ctx.messagesEl.scrollTop = ctx.messagesEl.scrollHeight;
  }

  SI.createStreamEventHandler = createStreamEventHandler;
})();
