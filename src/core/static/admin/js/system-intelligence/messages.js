(function() {
  'use strict';

  function renderOneMessage(message) {
    var cls = message.role === 'user' ? 'si-msg-user' : 'si-msg-assistant';
    var avatar = message.role === 'user'
      ? '<span class="material-symbols-outlined !text-[16px]">person</span>'
      : '<span class="material-symbols-outlined !text-[16px]">smart_toy</span>';
    var content = message.role === 'assistant' ? SI.formatMarkdown(message.content) : SI.escapeHtml(message.content);
    return renderToolCalls(message) + '<div class="si-msg ' + cls + '">' +
      '<div class="si-msg-avatar">' + avatar + '</div><div class="si-msg-content">' +
      '<div class="si-msg-bubble">' + content + '</div>' + renderUsage(message) + renderActions(message) +
      '</div></div>';
  }

  function renderToolCalls(message) {
    if (!message.tool_calls || !message.tool_calls.length) return '';
    var html = '<div class="si-tool-calls">';
    for (var i = 0; i < message.tool_calls.length; i++) html += SI.renderToolCallPill(message.tool_calls[i]);
    return html + '</div>';
  }

  function renderUsage(message) {
    if (message.role === 'assistant' && message.token_usage && message.token_usage.totalTokens) {
      return SI.renderTokenBadge(message.token_usage);
    }
    return '';
  }

  function renderActions(message) {
    if (message.role !== 'assistant' || !message.action_requests || !message.action_requests.length) return '';
    var html = '<div class="si-action-requests">';
    for (var i = 0; i < message.action_requests.length; i++) html += SI.renderActionRequestCard(message.action_requests[i]);
    return html + '</div>';
  }

  SI.renderOneMessage = renderOneMessage;
})();
