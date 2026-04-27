(function() {
  'use strict';

  function renderOneMessage(message) {
    var cls = message.role === 'user' ? 'si-msg-user' : 'si-msg-assistant';
    var avatar = message.role === 'user'
      ? '<span class="material-symbols-outlined !text-[16px]">person</span>'
      : '<span class="material-symbols-outlined !text-[16px]">smart_toy</span>';
    var body = message.role === 'assistant' ? renderAssistantBody(message.content) : renderUserBody(message.content);
    return renderToolCalls(message) + '<div class="si-msg ' + cls + '">' +
      '<div class="si-msg-avatar">' + avatar + '</div><div class="si-msg-content">' +
      body + renderUsage(message) + renderActions(message) +
      '</div></div>';
  }

  function renderUserBody(content) {
    return '<div class="si-msg-bubble">' + SI.escapeHtml(userDisplayContent(content)) + '</div>';
  }

  function renderAssistantBody(content) {
    return isConfirmationInfoMessage(content)
      ? renderConfirmationInfoCard(content)
      : '<div class="si-msg-bubble">' + SI.formatMarkdown(content) + '</div>';
  }

  function isConfirmationInfoMessage(content) {
    var text = (content || '').trim().toLowerCase();
    if (!text) return false;
    var signals = [
      'before i propose this change',
      'before i create this proposal',
      'before i prepare this proposal',
      'before i proceed',
      'i need to clarify',
      'i need to confirm',
      'please confirm the intended action',
      'questions before i proceed',
      'current state:',
      'question before i proceed:',
      'questions before i proceed:',
    ];
    var matches = 0;
    for (var i = 0; i < signals.length; i++) {
      if (text.indexOf(signals[i]) !== -1) matches++;
    }
    return matches >= 2 || (
      (text.indexOf('before i propose') !== -1 || text.indexOf('before i proceed') !== -1) &&
      (text.indexOf('current state') !== -1 || text.indexOf('question') !== -1 || text.indexOf('confirm') !== -1)
    );
  }

  function renderConfirmationInfoCard(content) {
    var currentState = extractSection(content, /^current state:?$/i, [/^questions? before i proceed:?$/i]);
    var options = parseConfirmationOptions(content);
    return '<div class="si-action-card si-confirmation-card">' +
      '<div class="si-action-card-header"><div class="si-action-title-wrap">' +
        '<span class="si-action-kicker">Confirmation required</span>' +
        '<strong class="si-action-title">Choose the database change to prepare</strong>' +
      '</div>' +
      '<span class="si-action-status si-confirmation-status">Waiting</span></div>' +
      '<div class="si-action-meta">AI will generate the pending database proposal. The database changes only after you approve it.</div>' +
      '<div class="si-confirmation-direct">Pick one option below. No data is changed by this click.</div>' +
      (currentState ? '<div class="si-confirmation-section"><span>Current issue</span><div>' + SI.formatMarkdown(currentState) + '</div></div>' : '') +
      (options.length ? renderConfirmationOptions(options) : '<div class="si-confirmation-body">' + SI.formatMarkdown(content) + '</div>') +
    '</div>';
  }

  function renderConfirmationOptions(options) {
    var html = '<div class="si-confirmation-options"><span>Choose one action</span>';
    for (var i = 0; i < options.length; i++) {
      var option = options[i];
      var prompt = optionPrompt(option);
      var displayText = optionDisplayText(option);
      var needsInput = optionNeedsInput(option);
      var attr = needsInput ? 'data-si-confirmation-fill' : 'data-si-confirmation-send';
      var buttonText = needsInput ? 'Add value' : 'Create approval card';
      html += '<div class="si-confirmation-option">' +
        '<div class="si-confirmation-option-copy">' +
          '<span class="si-confirmation-option-kicker">Option ' + SI.escapeHtml(option.number) + '</span>' +
          '<strong>' + SI.escapeHtml(option.title) + '</strong>' +
          (option.description ? '<p>' + SI.formatMarkdownInline(option.description) + '</p>' : '') +
        '</div>' +
        '<button type="button" class="si-confirmation-option-btn" ' + attr + '="' + encodeURIComponent(prompt) + '" data-si-confirmation-display="' + encodeURIComponent(displayText) + '">' +
          '<span>' + buttonText + '</span>' +
        '</button>' +
      '</div>';
    }
    return html + '</div>';
  }

  function parseConfirmationOptions(content) {
    var lines = (content || '').split(/\r?\n/);
    var options = [];
    var current = null;
    for (var i = 0; i < lines.length; i++) {
      var line = lines[i];
      var trimmed = line.trim();
      var match = trimmed.match(/^(\d+)[\.\)]\s+(.+)$/);
      if (match) {
        current = {number: match[1], raw: match[2]};
        options.push(current);
        continue;
      }
      if (!current || !trimmed) continue;
      if (/^(please reply|questions? before i proceed|current state):?/i.test(trimmed)) {
        current = null;
        continue;
      }
      current.raw += ' ' + trimmed;
    }
    return options.map(normalizeConfirmationOption);
  }

  function normalizeConfirmationOption(option) {
    var raw = option.raw || '';
    var titleMatch = raw.match(/\*\*([^*]+)\*\*/);
    var title = titleMatch ? titleMatch[1] : raw.split('.')[0];
    var description = titleMatch ? raw.replace(titleMatch[0], '').trim() : raw.slice(title.length).trim();
    title = stripMarkdown(title).replace(/[.。]\s*$/, '');
    description = description.replace(/^[:.\-\s]+/, '');
    return {number: option.number, title: title || ('Option ' + option.number), description: description, raw: raw};
  }

  function optionPrompt(option) {
    return 'I choose option ' + option.number + ': ' + option.title + '. ' +
      (option.description ? 'Details: ' + stripMarkdown(option.description) + ' ' : '') +
      'Please create the pending approval proposal(s) for this exact option. Do not apply the database change directly; create the approval card so I can review and approve it.';
  }

  function optionDisplayText(option) {
    return 'Create approval card for option ' + option.number + ': ' + option.title;
  }

  function userDisplayContent(content) {
    var text = String(content || '').trim();
    var match = text.match(/^I choose option\s+(\d+):\s+(.+?)(?:\.\s+Details:|\.\s+Please create|$)/i);
    if (!match) return content;
    return 'Create approval card for option ' + match[1] + ': ' + stripMarkdown(match[2]).replace(/[.。]\s*$/, '');
  }

  function optionNeedsInput(option) {
    var text = (option.title + ' ' + option.description).toLowerCase();
    return /different|provide|new value|new email|unused email|enter|specify/.test(text);
  }

  function extractSection(content, headingRe, stopRes) {
    var lines = (content || '').split(/\r?\n/);
    var collecting = false;
    var out = [];
    for (var i = 0; i < lines.length; i++) {
      var trimmed = lines[i].trim();
      if (!collecting && headingRe.test(trimmed)) {
        collecting = true;
        continue;
      }
      if (!collecting) continue;
      var shouldStop = false;
      for (var j = 0; j < stopRes.length; j++) {
        if (stopRes[j].test(trimmed)) shouldStop = true;
      }
      if (shouldStop) break;
      if (/^\d+[\.\)]\s+/.test(trimmed)) break;
      out.push(lines[i]);
    }
    return out.join('\n').trim();
  }

  function stripMarkdown(text) {
    return String(text || '')
      .replace(/\*\*/g, '')
      .replace(/`/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .trim();
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
  SI.renderAssistantBody = renderAssistantBody;
  SI.renderConfirmationInfoCard = renderConfirmationInfoCard;
  SI.isConfirmationInfoMessage = isConfirmationInfoMessage;
})();
