(function() {
  'use strict';

  function renderActionRequestCard(action) {
    action = action || {};
    var status = action.status || 'pending';
    var actionType = action.action_type || '';
    var target = action.target || {};
    var targetText = [target.app_label, target.model].filter(Boolean).join('.') || 'Database';
    if (target.pk) targetText += ' #' + target.pk;
    var previewButtonHtml = action.preview_url ? renderPreviewControls(action) : '';
    var previewFrameHtml = action.preview_url ? renderPreviewFrame(action.preview_url, action.title) : '';
    var buttons = status === 'pending' ? renderButtons(action.id || '') : '';
    var hasStructuredComparison = action.comparison && action.comparison.type;
    return '<div class="si-action-card" data-si-action-id="' + SI.escapeHtml(action.id || '') +
      '" data-si-action-status="' + SI.escapeHtml(status) +
      '" data-si-action-type="' + SI.escapeHtml(actionType) + '">' +
      '<div class="si-action-card-header"><div class="si-action-title-wrap">' +
      '<span class="si-action-kicker">Approval required</span>' +
      '<strong class="si-action-title">' + SI.escapeHtml(action.title || 'Proposed change') + '</strong></div>' +
      '<span class="si-action-status si-action-status--' + status + '">' + SI.escapeHtml(statusLabel(status)) + '</span></div>' +
      '<div class="si-action-meta">' + SI.escapeHtml(targetText) + '</div>' +
      (action.summary ? '<p class="si-action-summary">' + SI.escapeHtml(action.summary) + '</p>' : '') +
      renderActionComparison(action.comparison) +
      (!hasStructuredComparison ? renderActionDiff(action.diff || []) : '') +
      '<div class="si-action-footer">' + previewButtonHtml + buttons + '</div>' +
      previewFrameHtml +
      (action.failure_notice ? '<div class="si-action-error">' + SI.escapeHtml(action.failure_notice) + '</div>' : '') +
    '</div>';
  }

  function renderPreviewControls(action) {
    return '<div class="si-action-preview-controls">' +
      '<button type="button" class="si-action-preview" data-si-action-preview aria-expanded="false">' +
      '<span class="material-symbols-outlined !text-[15px]">visibility</span><span>Preview</span></button>' +
      '<a class="si-action-preview si-action-preview--full-page" href="' + SI.escapeHtml(fullPagePreviewUrl(action.id || '')) +
      '" target="_blank" rel="noopener noreferrer" title="Open full CMS page preview in a new tab">' +
      '<span class="material-symbols-outlined !text-[15px]">open_in_new</span><span>Full page</span></a>' +
      '</div>';
  }

  function fullPagePreviewUrl(id) {
    return '/admin/core/system-intelligence/actions/' + encodeURIComponent(id) + '/preview/full/';
  }

  function renderPreviewFrame(url, title) {
    return '<div class="si-action-preview-panel" data-si-preview-panel hidden>' +
      '<iframe class="si-action-preview-iframe" data-si-preview-frame data-si-preview-external-src="' + SI.escapeHtml(url) +
      '" title="' + SI.escapeHtml((title || 'CMS page') + ' preview') + '" loading="lazy"></iframe></div>';
  }

  function renderButtons(id) {
    return '<div class="si-action-buttons">' +
      '<button type="button" class="si-action-btn si-action-btn--approve" data-si-action-approve="' + SI.escapeHtml(id) + '">Approve</button>' +
      '<button type="button" class="si-action-btn si-action-btn--reject" data-si-action-reject="' + SI.escapeHtml(id) + '">Reject</button>' +
    '</div>';
  }

  function renderActionComparison(comparison) {
    if (!comparison || !comparison.type) return '';
    if (comparison.type === 'cms_page') return renderCmsComparison(comparison);
    if (comparison.type === 'db_record') return renderDbComparison(comparison);
    return '';
  }

  function renderCmsComparison(comparison) {
    var html = '<div class="si-action-comparison"><div class="si-action-comparison-head"><span>Before / After</span>' +
      (comparison.page_route ? '<span>' + SI.escapeHtml(comparison.page_route) + '</span>' : '') + '</div>';
    html += renderComparisonFields(comparison.fields || []);
    html += renderComparisonBlocks(comparison.blocks || []);
    if (comparison.truncated) html += '<div class="si-action-diff-more">Large change truncated. Open Full page for the complete preview.</div>';
    return html + '</div>';
  }

  function renderDbComparison(comparison) {
    var mode = comparison.mode || 'update';
    var headLabel = dbHeadLabel(mode, comparison.model_label || 'Record');
    var recordRepr = comparison.record_repr || '';
    var html = '<div class="si-action-comparison si-action-comparison--db">' +
      '<div class="si-action-comparison-head"><span>' + SI.escapeHtml(headLabel) + '</span>' +
      (recordRepr ? '<span>' + SI.escapeHtml(recordRepr) + '</span>' : '') + '</div>';
    var fields = comparison.fields || [];
    if (!fields.length) {
      html += '<div class="si-action-diff-more">No field changes detected.</div>';
    } else {
      for (var i = 0; i < fields.length; i++) html += renderDbRow(fields[i], mode);
    }
    var contextFields = comparison.context_fields || [];
    if (contextFields.length) {
      html += '<details class="si-action-db-context"><summary>Other fields (' + contextFields.length + ')</summary>';
      for (var j = 0; j < contextFields.length; j++) html += renderDbRow(contextFields[j], mode);
      html += '</details>';
    }
    if (comparison.truncated) html += '<div class="si-action-diff-more">Large change truncated.</div>';
    return html + '</div>';
  }

  function dbHeadLabel(mode, modelLabel) {
    if (mode === 'create') return 'Create new ' + modelLabel;
    if (mode === 'delete') return 'Delete ' + modelLabel;
    return 'Update ' + modelLabel;
  }

  function renderDbRow(row, mode) {
    row = row || {};
    var label = row.label || row.field || '';
    var typeChip = row.type ? '<span class="si-action-field-type">' + SI.escapeHtml(row.type) + '</span>' : '';
    var beforeText = row.before_display !== undefined ? row.before_display : formatDiffValue(row.before);
    var afterText = row.after_display !== undefined ? row.after_display : formatDiffValue(row.after);
    var sides;
    if (mode === 'create') {
      sides = '<div class="si-action-side si-action-side--after si-action-side--full">' +
        '<span class="si-action-side-label">New value</span>' +
        '<div class="si-action-side-text">' + SI.escapeHtml(afterText) + '</div></div>';
    } else if (mode === 'delete') {
      sides = '<div class="si-action-side si-action-side--before si-action-side--full">' +
        '<span class="si-action-side-label">Current value</span>' +
        '<div class="si-action-side-text">' + SI.escapeHtml(beforeText) + '</div></div>';
    } else {
      sides = renderSide('before', beforeText) + renderSide('after', afterText);
    }
    return '<div class="si-action-db-row">' +
      '<div class="si-action-db-label"><span>' + SI.escapeHtml(label) + '</span>' + typeChip + '</div>' +
      '<div class="si-action-before-after">' + sides + '</div></div>';
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
    if (value === null || value === undefined || value === '') return '—';
    if (value === true) return 'Yes';
    if (value === false) return 'No';
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
