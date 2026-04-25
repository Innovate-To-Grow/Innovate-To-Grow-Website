(function() {
  'use strict';

  function renderToolCallPill(tc) {
    var paramStr = '';
    if (tc.input) {
      var keys = Object.keys(tc.input);
      var parts = [];
      for (var k = 0; k < keys.length; k++) parts.push(keys[k] + ': ' + JSON.stringify(tc.input[keys[k]]));
      paramStr = parts.join(', ');
    }
    var displayName = tc.name.replace(/_/g, ' ');
    var preview = tc.result_preview || '';
    var countMatch = preview.match(/^(Showing \d+ of \d+ result\(s\)|Count: \d+|Registration count: \d+|Total[^.]*: \d+)/);
    var summaryLine = countMatch ? countMatch[1] : '';
    var detailText = summaryLine ? preview.substring(summaryLine.length).trim() : preview;
    return '<div class="si-tool-call" data-tool-toggle>' +
      '<span class="material-symbols-outlined !text-[15px] si-tool-call-icon">manage_search</span>' +
      '<span class="si-tool-call-name">' + SI.escapeHtml(displayName) + '</span>' +
      (paramStr ? '<span class="si-tool-call-params">' + SI.escapeHtml(paramStr) + '</span>' : '') +
      '<span class="material-symbols-outlined !text-[16px] si-tool-call-arrow">expand_more</span>' +
      '<div class="si-tool-call-detail">' +
        (summaryLine ? '<strong>' + SI.escapeHtml(summaryLine) + '</strong>\n' : '') +
        SI.escapeHtml(detailText) +
      '</div>' +
    '</div>';
  }

  SI.renderToolCallPill = renderToolCallPill;
})();
