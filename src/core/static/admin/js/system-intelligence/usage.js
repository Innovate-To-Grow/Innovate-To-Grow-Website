(function() {
  'use strict';

  function renderTokenBadge(raw) {
    var usage = normalizeTokenUsage(raw);
    if (usage.totalTokens) {
      window.setTimeout(function() { updateContextUsage(usage, {state: 'ready'}); }, 0);
    }
    return '<div class="si-token-usage">' +
      '<span>' + usage.inputTokens.toLocaleString() + ' in</span>' +
      '<span class="si-token-sep">/</span>' +
      '<span>' + usage.outputTokens.toLocaleString() + ' out</span>' +
      '<span class="si-token-sep">/</span>' +
      '<span class="si-token-total">' + usage.totalTokens.toLocaleString() + ' total</span>' +
    '</div>';
  }

  function normalizeTokenUsage(u) {
    u = u || {};
    var inputTokens = Number(u.inputTokens || u.input_tokens || u.promptTokenCount || 0);
    var outputTokens = Number(u.outputTokens || u.output_tokens || u.candidatesTokenCount || 0);
    var totalTokens = Number(u.totalTokens || u.total_tokens || u.totalTokenCount || 0);
    if (!totalTokens) totalTokens = inputTokens + outputTokens;
    return {inputTokens: inputTokens, outputTokens: outputTokens, totalTokens: totalTokens};
  }

  function latestContextUsage(messages) {
    messages = messages || [];
    for (var i = messages.length - 1; i >= 0; i--) {
      var message = messages[i];
      if (message.role === 'assistant' && message.token_usage) {
        var usage = normalizeTokenUsage(message.token_usage);
        if (usage.totalTokens) return usage;
      }
    }
    return null;
  }

  function updateContextUsage(usage, options) {
    options = options || {};
    var root = document.getElementById('si-context-usage');
    var labelEl = document.getElementById('si-context-usage-label');
    var detailEl = document.getElementById('si-context-usage-detail');
    if (!root || !labelEl || !detailEl) return;

    var normalized = usage ? normalizeTokenUsage(usage) : null;
    var hasUsage = normalized && normalized.totalTokens;
    var contextWindow = getContextWindow();
    root.setAttribute('data-state', options.state || (hasUsage ? 'ready' : 'empty'));
    labelEl.textContent = options.label || 'Context';

    if (!hasUsage) {
      detailEl.textContent = options.state === 'loading' ? (options.detail || 'Loading...') : emptyContextLabel(contextWindow);
      return;
    }
    detailEl.textContent = contextWindow
      ? contextPercentLabel(normalized.totalTokens, contextWindow) + ' · ' + formatCompactNumber(normalized.totalTokens) + ' / ' + formatCompactNumber(contextWindow)
      : normalized.inputTokens.toLocaleString() + ' in · ' + normalized.totalTokens.toLocaleString() + ' total';
  }

  function getContextWindow() {
    var root = document.getElementById('si-root');
    return root ? Number(root.getAttribute('data-context-window') || 0) : 0;
  }

  function contextPercentLabel(usedTokens, contextWindow) {
    var percent = usedTokens / contextWindow * 100;
    if (percent > 0 && percent < 1) return '<1% full';
    return Math.min(100, Math.round(percent)) + '% full';
  }

  function emptyContextLabel(contextWindow) {
    return contextWindow ? '0% full · 0 / ' + formatCompactNumber(contextWindow) : '0% full';
  }

  function formatCompactNumber(value) {
    value = Number(value || 0);
    if (value >= 1000000) return Math.round(value / 100000) / 10 + 'm';
    if (value >= 10000) return Math.round(value / 1000) + 'k';
    if (value >= 1000) return Math.round(value / 100) / 10 + 'k';
    return value.toLocaleString();
  }

  SI.renderTokenBadge = renderTokenBadge;
  SI.normalizeTokenUsage = normalizeTokenUsage;
  SI.latestContextUsage = latestContextUsage;
  SI.updateContextUsage = updateContextUsage;
})();
