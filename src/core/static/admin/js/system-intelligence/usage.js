(function() {
  'use strict';

  var currentContextUsage = null;
  var currentLatestUsage = null;

  function renderTokenBadge(raw) {
    var usage = normalizeTokenUsage(raw);
    if (usage.totalTokens) {
      window.setTimeout(function() { updateContextUsage(usage, {state: 'ready', kind: 'latest', reset: false}); }, 0);
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

  function normalizeContextUsage(u) {
    u = u || {};
    var contextWindow = Number(u.contextWindow || u.context_window || getContextWindow() || 0);
    return {
      contextWindow: contextWindow,
      rawTokens: Number(u.rawTokens || u.raw_tokens || 0),
      preparedTokens: Number(u.preparedTokens || u.prepared_tokens || 0),
      compactThreshold: Number(u.compactThreshold || u.compact_threshold || 0),
      hardLimit: Number(u.hardLimit || u.hard_limit || 0),
      compacted: Boolean(u.compacted),
      summaryUsed: Boolean(u.summaryUsed || u.summary_used),
      summaryUpdated: Boolean(u.summaryUpdated || u.summary_updated),
      summaryFailed: Boolean(u.summaryFailed || u.summary_failed),
      retainedMessages: Number(u.retainedMessages || u.retained_messages || 0),
      summarizedMessages: Number(u.summarizedMessages || u.summarized_messages || 0),
      trimmedMessages: Number(u.trimmedMessages || u.trimmed_messages || 0),
    };
  }

  function latestContextUsage(messages) {
    messages = messages || [];
    for (var i = messages.length - 1; i >= 0; i--) {
      var message = messages[i];
      if (message.role !== 'assistant') continue;
      var contextUsage = message.context_usage ? normalizeContextUsage(message.context_usage) : null;
      var tokenUsage = message.token_usage ? normalizeTokenUsage(message.token_usage) : null;
      if ((contextUsage && contextUsage.preparedTokens) || (tokenUsage && tokenUsage.totalTokens)) {
        return {contextUsage: contextUsage, latestUsage: tokenUsage};
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

    if (!usage && options.reset !== false) {
      currentContextUsage = null;
      currentLatestUsage = null;
    }
    applyUsageUpdate(usage, options);

    var hasUsage = (currentContextUsage && currentContextUsage.preparedTokens) ||
      (currentLatestUsage && currentLatestUsage.totalTokens);
    var contextWindow = getContextWindow();
    root.setAttribute('data-state', options.state || (hasUsage ? 'ready' : 'empty'));
    labelEl.textContent = options.label || 'Context';

    if (!hasUsage) {
      detailEl.textContent = options.state === 'loading' ? (options.detail || 'Loading...') : emptyContextLabel(contextWindow);
      return;
    }
    detailEl.textContent = renderContextDetail(contextWindow);
  }

  function applyUsageUpdate(usage, options) {
    if (!usage) return;
    if (usage.contextUsage || usage.latestUsage) {
      if (usage.contextUsage) currentContextUsage = normalizeContextUsage(usage.contextUsage);
      if (usage.latestUsage) currentLatestUsage = normalizeTokenUsage(usage.latestUsage);
      return;
    }
    if (options.kind === 'context' || looksLikeContextUsage(usage)) {
      currentContextUsage = normalizeContextUsage(usage);
      return;
    }
    currentLatestUsage = normalizeTokenUsage(usage);
  }

  function looksLikeContextUsage(usage) {
    return Object.prototype.hasOwnProperty.call(usage, 'preparedTokens') ||
      Object.prototype.hasOwnProperty.call(usage, 'prepared_tokens') ||
      Object.prototype.hasOwnProperty.call(usage, 'rawTokens') ||
      Object.prototype.hasOwnProperty.call(usage, 'raw_tokens') ||
      Object.prototype.hasOwnProperty.call(usage, 'compacted');
  }

  function renderContextDetail(fallbackContextWindow) {
    var pieces = [];
    var contextWindow = fallbackContextWindow;
    if (currentContextUsage && currentContextUsage.preparedTokens) {
      contextWindow = currentContextUsage.contextWindow || contextWindow;
      var prefix = currentContextUsage.compacted ? 'Compacted · Prepared ' : 'Prepared ';
      pieces.push(prefix + contextPercentOnly(currentContextUsage.preparedTokens, contextWindow) + ' · ' +
        formatCompactNumber(currentContextUsage.preparedTokens) + ' / ' + formatCompactNumber(contextWindow));
      if (currentContextUsage.summaryFailed) pieces.push('Summary fallback');
    }
    if (currentLatestUsage && currentLatestUsage.totalTokens) {
      if (!pieces.length && contextWindow) {
        pieces.push('Latest ' + contextPercentOnly(currentLatestUsage.totalTokens, contextWindow) + ' · ' +
          formatCompactNumber(currentLatestUsage.totalTokens) + ' / ' + formatCompactNumber(contextWindow));
      } else {
        pieces.push('Latest ' + formatCompactNumber(currentLatestUsage.totalTokens));
      }
    }
    return pieces.join(' · ');
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

  function contextPercentOnly(usedTokens, contextWindow) {
    if (!contextWindow) return formatCompactNumber(usedTokens);
    var percent = usedTokens / contextWindow * 100;
    if (percent > 0 && percent < 1) return '<1%';
    return Math.min(100, Math.round(percent)) + '%';
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
  SI.normalizeContextUsage = normalizeContextUsage;
  SI.latestContextUsage = latestContextUsage;
  SI.updateContextUsage = updateContextUsage;
})();
