(function() {
  'use strict';

  function renderActionRequestCard(action) {
    action = action || {};
    var status = action.status || 'pending';
    var target = action.target || {};
    var targetText = [target.app_label, target.model].filter(Boolean).join('.') || 'Database';
    if (target.pk) targetText += ' #' + target.pk;
    var previewHtml = action.preview_url ? renderPreview(action.preview_url) : '';
    var buttons = status === 'pending' ? renderButtons(action.id || '') : '';
    return '<div class="si-action-card" data-si-action-id="' + SI.escapeHtml(action.id || '') +
      '" data-si-action-status="' + SI.escapeHtml(status) + '">' +
      '<div class="si-action-card-header"><div class="si-action-title-wrap">' +
      '<span class="si-action-kicker">Approval required</span>' +
      '<strong class="si-action-title">' + SI.escapeHtml(action.title || 'Proposed change') + '</strong></div>' +
      '<span class="si-action-status si-action-status--' + status + '">' + SI.escapeHtml(statusLabel(status)) + '</span></div>' +
      '<div class="si-action-meta">' + SI.escapeHtml(targetText) + '</div>' +
      (action.summary ? '<p class="si-action-summary">' + SI.escapeHtml(action.summary) + '</p>' : '') +
      renderActionComparison(action.comparison) +
      (!(action.comparison && action.comparison.type === 'cms_page') ? renderActionDiff(action.diff || []) : '') +
      '<div class="si-action-footer">' + previewHtml + buttons + '</div>' +
      (action.error_message ? '<div class="si-action-error">' + SI.escapeHtml(action.error_message) + '</div>' : '') +
    '</div>';
  }

  function renderPreview(url) {
    return '<a class="si-action-preview" href="' + SI.escapeHtml(url) + '" target="_blank" rel="noopener noreferrer">' +
      '<span class="material-symbols-outlined !text-[15px]">visibility</span> Preview</a>';
  }

  function renderButtons(id) {
    return '<div class="si-action-buttons">' +
      '<button type="button" class="si-action-btn si-action-btn--approve" data-si-action-approve="' + SI.escapeHtml(id) + '">Approve</button>' +
      '<button type="button" class="si-action-btn si-action-btn--reject" data-si-action-reject="' + SI.escapeHtml(id) + '">Reject</button>' +
    '</div>';
  }

  function renderActionComparison(comparison) {
    if (!comparison || comparison.type !== 'cms_page') return '';
    var html = '<div class="si-action-comparison"><div class="si-action-comparison-head"><span>Before / After</span>' +
      (comparison.page_route ? '<span>' + SI.escapeHtml(comparison.page_route) + '</span>' : '') + '</div>';
    html += renderComparisonFields(comparison.fields || []);
    html += renderComparisonBlocks(comparison.blocks || []);
    if (comparison.truncated) html += '<div class="si-action-diff-more">Large change truncated. Open Preview for the full page.</div>';
    return html + '</div>';
  }

  function renderComparisonFields(fields) {
    if (!fields.length) return '';
    var html = '<div class="si-action-field-comparison">';
    for (var i = 0; i < fields.length; i++) {
      var item = fields[i] || {};
      html += '<div class="si-action-field-row"><span class="si-action-diff-field">' + SI.escapeHtml(item.field || '') + '</span>' +
        '<span class="si-action-diff-value si-action-before">' + SI.escapeHtml(formatDiffValue(item.before)) + '</span>' +
        '<span class="si-action-diff-arrow">&rarr;</span><span class="si-action-diff-value si-action-after">' +
        SI.escapeHtml(formatDiffValue(item.after)) + '</span></div>';
    }
    return html + '</div>';
  }

  function renderComparisonBlocks(blocks) {
    if (!blocks.length) return '';
    var html = '';
    for (var i = 0; i < blocks.length; i++) {
      var block = blocks[i] || {};
      var changedKeys = block.changed_keys && block.changed_keys.length
        ? '<span class="si-action-block-keys">' + SI.escapeHtml(block.changed_keys.join(', ')) + '</span>' : '';
      html += '<div class="si-action-block-comparison"><div class="si-action-block-head"><div>' +
        '<strong>' + SI.escapeHtml(block.label || 'Changed block') + '</strong>' +
        '<span>' + SI.escapeHtml(block.block_type || 'block') + orderLabel(block.sort_order) + '</span></div>' +
        changedKeys + '</div><div class="si-action-before-after">' +
        renderSide('before', block.before_text) + renderSide('after', block.after_text) + '</div></div>';
    }
    return html;
  }

  function renderSide(kind, text) {
    var label = kind === 'before' ? 'Before' : 'After';
    return '<div class="si-action-side si-action-side--' + kind + '">' +
      '<span class="si-action-side-label">' + label + '</span>' +
      '<div class="si-action-side-text">' + SI.escapeHtml(formatDiffValue(text)) + '</div></div>';
  }

  function orderLabel(sortOrder) {
    return sortOrder !== '' && sortOrder !== undefined ? ' · order ' + SI.escapeHtml(String(sortOrder)) : '';
  }

  function renderActionDiff(diff) {
    if (!diff.length) return '';
    var html = '<div class="si-action-diff">';
    var shown = Math.min(diff.length, 6);
    for (var i = 0; i < shown; i++) {
      var item = diff[i] || {};
      html += '<div class="si-action-diff-row"><span class="si-action-diff-field">' + SI.escapeHtml(item.field || '') + '</span>' +
        '<span class="si-action-diff-value">' + SI.escapeHtml(formatDiffValue(item.before)) + '</span>' +
        '<span class="si-action-diff-arrow">&rarr;</span><span class="si-action-diff-value">' +
        SI.escapeHtml(formatDiffValue(item.after)) + '</span></div>';
    }
    if (diff.length > shown) html += '<div class="si-action-diff-more">+' + (diff.length - shown) + ' more change(s)</div>';
    return html + '</div>';
  }

  function formatDiffValue(value) {
    if (value === null || value === undefined || value === '') return 'empty';
    if (typeof value === 'object') return JSON.stringify(value);
    return String(value);
  }

  function statusLabel(status) {
    if (status === 'applied') return 'Applied';
    if (status === 'rejected') return 'Rejected';
    if (status === 'failed') return 'Failed';
    return 'Pending';
  }

  function replaceActionRequestCard(action) {
    if (!action || !action.id) return;
    var existing = document.querySelector('[data-si-action-id="' + CSS.escape(action.id) + '"]');
    if (existing) existing.outerHTML = renderActionRequestCard(action);
  }

  SI.renderActionRequestCard = renderActionRequestCard;
  SI.replaceActionRequestCard = replaceActionRequestCard;
})();
