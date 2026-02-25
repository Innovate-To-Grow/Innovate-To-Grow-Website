/**
 * GrapesJS Component Library - Save & reuse components across pages.
 * Phase 7: Save selected components to library, drag to reuse.
 */
var gjsComponentLibrary = (function() {
    'use strict';

    var savedComponents = [];
    var csrfToken = '';

    function apply(editor, csrf) {
        csrfToken = csrf;

        // Load saved components from API
        loadComponents(editor);

        // Add "Save to Library" in the toolbar
        editor.Panels.addButton('options', {
            id: 'save-component',
            className: 'fa fa-bookmark',
            command: function() { saveSelectedComponent(editor); },
            attributes: { title: 'Save Component to Library' },
        });

        // Add "My Components" button to open library
        editor.Panels.addButton('options', {
            id: 'component-library',
            className: 'fa fa-th-large',
            command: function() { showLibraryModal(editor); },
            attributes: { title: 'Component Library' },
        });
    }

    function loadComponents(editor) {
        fetch('/pages/components/', { credentials: 'same-origin' })
            .then(function(res) { return res.ok ? res.json() : []; })
            .then(function(data) {
                savedComponents = data || [];
                // Register as blocks
                savedComponents.forEach(function(comp) {
                    editor.BlockManager.add('saved-' + comp.id, {
                        label: comp.name,
                        category: 'My Components',
                        content: comp.html + (comp.css ? '<style>' + comp.css + '</style>' : ''),
                        attributes: { class: 'fa fa-bookmark' },
                    });
                });
            })
            .catch(function() {
                // Component library API may not exist yet
            });
    }

    function saveSelectedComponent(editor) {
        var selected = editor.getSelected();
        if (!selected) {
            if (window.adminToast) {
                window.adminToast('Select a component first.', 'warning');
            }
            return;
        }

        var name = prompt('Component name:');
        if (!name) return;

        var category = prompt('Category (e.g., Headers, Banners, Footers):', 'Custom');
        if (!category) category = 'Custom';

        var html = selected.toHTML();
        var css = editor.CodeManager.getCode(selected, 'css', { cssc: editor.CssComposer });

        fetch('/pages/components/', {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken,
            },
            body: JSON.stringify({
                name: name,
                category: category,
                html: html,
                css: css || '',
                grapesjs_data: JSON.stringify(selected.toJSON()),
            }),
        })
        .then(function(res) { return res.json(); })
        .then(function(data) {
            savedComponents.push(data);
            editor.BlockManager.add('saved-' + data.id, {
                label: data.name,
                category: 'My Components',
                content: data.html + (data.css ? '<style>' + data.css + '</style>' : ''),
                attributes: { class: 'fa fa-bookmark' },
            });
            if (window.adminToast) {
                window.adminToast('Component "' + name + '" saved to library.', 'success');
            }
        })
        .catch(function() {
            if (window.adminToast) {
                window.adminToast('Failed to save component.', 'error');
            }
        });
    }

    function showLibraryModal(editor) {
        var modal = editor.Modal;
        var html = '<div class="gjs-tpl-gallery">';

        if (savedComponents.length === 0) {
            html += '<p style="text-align:center;color:#888;padding:20px;">No saved components yet. Select a component and click the bookmark icon to save it.</p>';
        }

        savedComponents.forEach(function(comp) {
            html += '<div class="gjs-tpl-item" data-comp-id="' + comp.id + '">' +
                '<div class="gjs-tpl-icon"><i class="fa fa-bookmark"></i></div>' +
                '<div class="gjs-tpl-name">' + comp.name + '</div>' +
                '<div class="gjs-tpl-cat">' + (comp.category || 'Custom') + '</div>' +
            '</div>';
        });

        html += '</div>';

        modal.open({
            title: 'Component Library',
            content: html,
        });

        setTimeout(function() {
            document.querySelectorAll('.gjs-tpl-item[data-comp-id]').forEach(function(item) {
                item.addEventListener('click', function() {
                    var id = item.getAttribute('data-comp-id');
                    var comp = savedComponents.find(function(c) { return String(c.id) === id; });
                    if (comp) {
                        editor.addComponents(comp.html + (comp.css ? '<style>' + comp.css + '</style>' : ''));
                        modal.close();
                        if (window.adminToast) {
                            window.adminToast('Component "' + comp.name + '" inserted.', 'success');
                        }
                    }
                });
            });
        }, 100);
    }

    return { apply: apply };
})();
