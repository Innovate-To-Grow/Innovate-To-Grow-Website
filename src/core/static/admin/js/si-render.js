/**
 * System Intelligence — rendering helpers.
 *
 * Message bubbles, tool-call pills, and token-usage badges.
 */
(function() {
  'use strict';

  var escapeHtml = SI.escapeHtml;
  var formatMarkdown = SI.formatMarkdown;

  function renderOneMessage(m) {
    var cls = m.role === 'user' ? 'si-msg-user' : 'si-msg-assistant';
    var avatar = m.role === 'user'
      ? '<span class="material-symbols-outlined !text-[16px]">person</span>'
      : '<span class="material-symbols-outlined !text-[16px]">smart_toy</span>';
    var content = m.role === 'assistant' ? formatMarkdown(m.content) : escapeHtml(m.content);

    var toolCallsHtml = '';
    if (m.tool_calls && m.tool_calls.length) {
      toolCallsHtml = '<div class="si-tool-calls">';
      for (var t = 0; t < m.tool_calls.length; t++) {
        toolCallsHtml += renderToolCallPill(m.tool_calls[t]);
      }
      toolCallsHtml += '</div>';
    }

    var usageHtml = '';
    if (m.role === 'assistant' && m.token_usage && m.token_usage.totalTokens) {
      usageHtml = renderTokenBadge(m.token_usage);
    }

    return toolCallsHtml +
      '<div class="si-msg ' + cls + '">' +
        '<div class="si-msg-avatar">' + avatar + '</div>' +
        '<div class="si-msg-content">' +
          '<div class="si-msg-bubble">' + content + '</div>' +
          usageHtml +
        '</div>' +
      '</div>';
  }

  function renderTokenBadge(u) {
    return '<div class="si-token-usage">' +
      '<span>' + (u.inputTokens || 0).toLocaleString() + ' in</span>' +
      '<span class="si-token-sep">/</span>' +
      '<span>' + (u.outputTokens || 0).toLocaleString() + ' out</span>' +
      '<span class="si-token-sep">/</span>' +
      '<span class="si-token-total">' + (u.totalTokens || 0).toLocaleString() + ' total</span>' +
    '</div>';
  }

  function renderToolCallPill(tc) {
    var paramStr = '';
    if (tc.input) {
      var keys = Object.keys(tc.input);
      var parts = [];
      for (var k = 0; k < keys.length; k++) {
        parts.push(keys[k] + ': ' + JSON.stringify(tc.input[keys[k]]));
      }
      paramStr = parts.join(', ');
    }
    var displayName = tc.name.replace(/_/g, ' ');
    var preview = tc.result_preview || '';
    var countMatch = preview.match(/^(Showing \d+ of \d+ result\(s\)|Count: \d+|Registration count: \d+|Total[^.]*: \d+)/);
    var summaryLine = countMatch ? countMatch[1] : '';
    var detailText = summaryLine ? preview.substring(summaryLine.length).trim() : preview;
    return '<div class="si-tool-call" data-tool-toggle>' +
      '<span class="material-symbols-outlined !text-[15px] si-tool-call-icon">manage_search</span>' +
      '<span class="si-tool-call-name">' + escapeHtml(displayName) + '</span>' +
      (paramStr ? '<span class="si-tool-call-params">' + escapeHtml(paramStr) + '</span>' : '') +
      '<span class="material-symbols-outlined !text-[16px] si-tool-call-arrow">expand_more</span>' +
      '<div class="si-tool-call-detail">' +
        (summaryLine ? '<strong>' + escapeHtml(summaryLine) + '</strong>\n' : '') +
        escapeHtml(detailText) +
      '</div>' +
    '</div>';
  }

  SI.renderOneMessage = renderOneMessage;
  SI.renderTokenBadge = renderTokenBadge;
  SI.renderToolCallPill = renderToolCallPill;
})();
