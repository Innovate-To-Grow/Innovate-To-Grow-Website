(function() {
    'use strict';

    var previewWindow = null;
    var isHomePage = false;
    var pageSlug = null;

    // Helper to get value from CodeMirror or Textarea
    function getEditorValue(textarea) {
        if (textarea.nextSibling && textarea.nextSibling.CodeMirror) {
            return textarea.nextSibling.CodeMirror.getValue();
        }
        return textarea.value;
    }

    function gatherFormData() {
        // Find all component inline groups
        // Django admin inlines usually have IDs like "pagecomponent_set-0", "pagecomponent_set-1", etc.
        // The prefix might vary depending on the inline definition.
        
        var components = [];
        
        // Look for component rows
        var rows = document.querySelectorAll('.dynamic-pagecomponent_set, .dynamic-components'); 
        // Fallback: try to find by field name pattern if class names differ
        if (rows.length === 0) {
            // This is a bit heuristic, looking for rows that contain component fields
            var allRows = document.querySelectorAll('.inline-related');
            rows = Array.from(allRows).filter(row => row.querySelector('textarea[name$="-html_content"]'));
        }

        rows.forEach(function(row) {
            // Check if deleted
            var deleteInput = row.querySelector('input[name$="-DELETE"]');
            if (deleteInput && deleteInput.checked) return;

            // Extract index from ID or name
            // id="pagecomponent_set-0"
            var idMatch = row.id.match(/-(\d+)$/);
            var index = idMatch ? parseInt(idMatch[1]) : 0;

            // Get fields
            var nameInput = row.querySelector('input[name$="-name"]');
            var typeSelect = row.querySelector('select[name$="-component_type"]');
            var orderInput = row.querySelector('input[name$="-order"]');
            var enabledInput = row.querySelector('input[name$="-is_enabled"]');
            var htmlInput = row.querySelector('textarea[name$="-html_content"]');
            var cssInput = row.querySelector('textarea[name$="-css_code"]');
            var jsInput = row.querySelector('textarea[name$="-js_code"]');
            var configInput = row.querySelector('textarea[name$="-config"]');

            var component = {
                id: 'preview-' + index,
                name: nameInput ? nameInput.value : '',
                component_type: typeSelect ? typeSelect.value : 'html',
                order: orderInput ? parseInt(orderInput.value) || 0 : 0,
                is_enabled: enabledInput ? enabledInput.checked : true, // Default to true if not found/checked logic
                html_content: htmlInput ? getEditorValue(htmlInput) : '',
                css_code: cssInput ? getEditorValue(cssInput) : '',
                js_code: jsInput ? getEditorValue(jsInput) : '',
                config: configInput ? getEditorValue(configInput) : '{}'
            };

            components.push(component);
        });

        return { components: components };
    }

    function buildPreviewHtml(data) {
        if (!data || !data.components) return '';
        
        var components = data.components;
        // Filter enabled components and sort by order
        var sortedComponents = components.filter(function(c) {
            return c.is_enabled;
        }).sort(function(a, b) {
            return a.order - b.order;
        });

        var htmlParts = [];
        htmlParts.push('<div class="components-container">');

        sortedComponents.forEach(function(component) {
            htmlParts.push('<div class="page-component component-' + component.id + '" data-component-name="' + (component.name || '') + '">');
            
            // Add scoped style if present
            if (component.css_code) {
                htmlParts.push('<style>' + component.css_code + '</style>');
            }

            htmlParts.push('<div class="component-content">');
            
            // Render content based on type
            if (component.component_type === 'html' || component.component_type === 'markdown') {
                htmlParts.push(component.html_content || '');
            } else if (component.component_type === 'form') {
                var formSlug = 'Unknown';
                try {
                    var config = JSON.parse(component.config);
                    if (config.form_slug) formSlug = config.form_slug;
                } catch (e) {}
                htmlParts.push('<div style="padding: 20px; border: 1px dashed #ccc; background: #f9f9f9; text-align: center;">[Form: ' + formSlug + ']</div>');
            } else if (component.component_type === 'table') {
                htmlParts.push('<div style="padding: 20px; border: 1px dashed #ccc; background: #f9f9f9; text-align: center;">[Table Component]</div>');
            } else {
                htmlParts.push(component.html_content || '');
            }

            htmlParts.push('</div>'); // .component-content
            htmlParts.push('</div>'); // .page-component
        });

        htmlParts.push('</div>'); // .components-container
        return htmlParts.join('\n');
    }

    function updatePreviewFromForm() {
        var data = gatherFormData();
        var html = buildPreviewHtml(data);
        updatePreview(html);
    }

    function updatePreview(content) {
        if (!previewWindow || previewWindow.closed) return;
        previewWindow.postMessage({
            type: 'preview-update',
            content: content
        }, '*');
    }

    function openPreviewPopup() {
        var width = 1200, height = 800;
        var left = (screen.width - width) / 2;
        var top = (screen.height - height) / 2;
        
        // Use existing window if open
        if (previewWindow && !previewWindow.closed) {
            previewWindow.focus();
            updatePreviewFromForm(); // Refresh content from form
            return;
        }

        previewWindow = window.open(
            '/admin/preview-popup/',
            'pageLivePreview',
            'width=' + width + ',height=' + height + ',left=' + left + ',top=' + top + ',resizable=yes,scrollbars=yes'
        );
        
        // When popup loads, it will send 'preview-ready'
    }

    function initInlineCodeEditors() {
        var textareas = document.querySelectorAll('textarea[name$="-html_content"], textarea[name$="-config"], textarea[name$="-css_code"], textarea[name$="-js_code"]');
        textareas.forEach(function(ta) {
            if (ta.getAttribute('data-cm-inited')) return;
            var isJson = ta.name.indexOf('-config') !== -1;
            var isCss = ta.name.indexOf('-css_code') !== -1;
            var isJs = ta.name.indexOf('-js_code') !== -1;
            
            var mode = 'htmlmixed';
            if (isJson) mode = 'application/json';
            if (isCss) mode = 'css';
            if (isJs) mode = 'javascript';

            var wrapper = document.createElement('div');
            wrapper.className = 'inline-cm-wrapper';
            ta.parentNode.insertBefore(wrapper, ta);
            wrapper.appendChild(ta);
            
            var editor = CodeMirror.fromTextArea(ta, {
                mode: mode,
                lineNumbers: true,
                lineWrapping: true,
                indentUnit: 2,
                tabSize: 2
            });
            
            // Update underlying textarea on change to support form submission
            editor.on('change', function(cm) {
                ta.value = cm.getValue();
                // Debounce preview update
                if (window.previewUpdateTimer) clearTimeout(window.previewUpdateTimer);
                window.previewUpdateTimer = setTimeout(updatePreviewFromForm, 500);
            });

            ta.setAttribute('data-cm-inited', '1');
        });
    }

    function setup() {
        initInlineCodeEditors();

        // Watch for dynamically added inlines
        var container = document.querySelector('#content') || document.querySelector('form');
        if (container && window.MutationObserver) {
            var obs = new MutationObserver(function(mutations) {
                initInlineCodeEditors();
                updatePreviewFromForm();
            });
            obs.observe(container, { childList: true, subtree: true });
        }

        // Bind preview button
        var btn = document.getElementById('popup-preview-btn');
        if (btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                openPreviewPopup();
            });
        }

        // Listen for changes in standard inputs
        var inputs = document.querySelectorAll('input, select');
        inputs.forEach(function(input) {
            input.addEventListener('change', function() {
                updatePreviewFromForm();
            });
            input.addEventListener('input', function() {
                if (window.previewUpdateTimer) clearTimeout(window.previewUpdateTimer);
                window.previewUpdateTimer = setTimeout(updatePreviewFromForm, 500);
            });
        });
    }

    // Listen for preview-ready from popup
    window.addEventListener('message', function(event) {
        if (event.data && event.data.type === 'preview-ready') {
            updatePreviewFromForm();
        }
    });

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', setup);
    } else {
        setup();
    }
})();
