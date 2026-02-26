(function() {
    'use strict';

    var previewSessionId = null;

    function getEditorValue(textarea) {
        if (textarea.nextSibling && textarea.nextSibling.CodeMirror) {
            return textarea.nextSibling.CodeMirror.getValue();
        }
        return textarea.value;
    }

    function gatherFormData() {
        var components = [];

        var rows = document.querySelectorAll('.dynamic-pagecomponent_set, .dynamic-components');
        if (rows.length === 0) {
            var allRows = document.querySelectorAll('.inline-related');
            rows = Array.from(allRows).filter(function(row) {
                return row.querySelector('textarea[name$="-html_content"], input[name$="-html_content"]');
            });
        }

        rows.forEach(function(row) {
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;

            var idMatch = row.id.match(/-(\d+)$/);
            var index = idMatch ? parseInt(idMatch[1]) : 0;

            var nameInput = row.querySelector('input[name$="-name"]');
            var typeSelect = row.querySelector('select[name$="-component_type"]');
            var orderInput = row.querySelector('input[name$="-order"]');
            var enabledInput = row.querySelector('input[name$="-is_enabled"]');
            var htmlInput = row.querySelector('textarea[name$="-html_content"], input[name$="-html_content"]');
            var cssInput = row.querySelector('textarea[name$="-css_code"], input[name$="-css_code"]');
            var jsInput = row.querySelector('textarea[name$="-js_code"], input[name$="-js_code"]');
            var configInput = row.querySelector('textarea[name$="-config"], input[name$="-config"]');
            var googleSheetInput = row.querySelector('select[name$="-google_sheet"], input[name$="-google_sheet"]');
            var googleSheetStyleInput = row.querySelector(
                'select[name$="-google_sheet_style"], input[name$="-google_sheet_style"]'
            );

            components.push({
                id: 'preview-' + index,
                name: nameInput ? nameInput.value : '',
                component_type: typeSelect ? typeSelect.value : 'html',
                order: orderInput ? parseInt(orderInput.value) || 0 : 0,
                is_enabled: enabledInput ? enabledInput.checked : true,
                html_content: htmlInput ? getEditorValue(htmlInput) : '',
                css_code: cssInput ? getEditorValue(cssInput) : '',
                js_code: jsInput ? getEditorValue(jsInput) : '',
                config: configInput ? getEditorValue(configInput) : '{}',
                google_sheet: googleSheetInput ? (googleSheetInput.value || null) : null,
                google_sheet_style: googleSheetStyleInput ? googleSheetStyleInput.value : 'default'
            });
        });

        return { components: components };
    }

    function pushPreviewData() {
        if (!previewSessionId) return;

        var csrfToken = document.querySelector('input[name="csrfmiddlewaretoken"]');

        // GrapesJS mode: push editor content directly
        if (window.gjsEditor) {
            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/pages/preview/data/', true);
            xhr.setRequestHeader('Content-Type', 'application/json');
            if (csrfToken) {
                xhr.setRequestHeader('X-CSRFToken', csrfToken.value);
            }
            xhr.send(JSON.stringify({
                sessionId: previewSessionId,
                html: window.gjsEditor.getHtml(),
                css: window.gjsEditor.getCss()
            }));
            return;
        }

        // Legacy component form mode
        var data = gatherFormData();

        var xhr2 = new XMLHttpRequest();
        xhr2.open('POST', '/pages/preview/data/', true);
        xhr2.setRequestHeader('Content-Type', 'application/json');
        if (csrfToken) {
            xhr2.setRequestHeader('X-CSRFToken', csrfToken.value);
        }
        xhr2.send(JSON.stringify({
            sessionId: previewSessionId,
            components: data.components
        }));
    }

    function openPreview() {
        var btn = document.getElementById('popup-preview-btn');
        if (!btn) return;

        previewSessionId = btn.dataset.previewSessionId || null;

        var previewUrl = '/preview';

        if (btn.dataset.frontendUrl) {
            previewUrl = btn.dataset.frontendUrl.replace(/\/$/, '') + '/preview';
        } else if (window.location.port === '8000') {
            previewUrl = window.location.protocol + '//' + window.location.hostname + ':5173/preview';
        }

        var queryParams = [];
        if (btn.dataset.previewToken) {
            queryParams.push('token=' + encodeURIComponent(btn.dataset.previewToken));
        }
        if (btn.dataset.objectId) {
            queryParams.push('objectId=' + encodeURIComponent(btn.dataset.objectId));
        }
        if (previewSessionId) {
            queryParams.push('sessionId=' + encodeURIComponent(previewSessionId));
        }
        if (queryParams.length > 0) {
            previewUrl += '?' + queryParams.join('&');
        }

        // Push data to server first so the preview page can fetch it immediately
        pushPreviewData();

        // Open in new tab
        window.open(previewUrl, '_blank');
    }

    function setup() {
        var btn = document.getElementById('popup-preview-btn');
        if (btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                openPreview();
            });
        }

        // Listen for changes in standard inputs and push data
        var form = document.querySelector('#content form') || document.querySelector('form');
        if (form) {
            form.addEventListener('change', function() {
                pushPreviewData();
            });
            form.addEventListener('input', function() {
                if (window._previewDebounce) clearTimeout(window._previewDebounce);
                window._previewDebounce = setTimeout(pushPreviewData, 500);
            });
        }

        // Watch for dynamically added inlines
        var container = document.querySelector('#content') || document.querySelector('form');
        if (container && window.MutationObserver) {
            var obs = new MutationObserver(function() {
                pushPreviewData();
            });
            obs.observe(container, { childList: true, subtree: true });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setup);
    } else {
        setup();
    }
})();
